from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from pska_essential.agentic_loop import list_resumable_agentic_questions
from pska_essential.audit import audit_event
from pska_essential.cli_errors import startup_error_payload
from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable
from pska_essential.env_file import preload_env_file
from pska_essential.ingest_loop import resume_ingest_loop, run_ingest_loop
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.workflow import WorkflowService


def run_smoke_eval(service: WorkflowService) -> dict:
    return service.eval_run("smoke")


def run_eval(
    suite: str,
    service: WorkflowService,
    *,
    gateway_factory: Any | None = None,
) -> dict[str, Any]:
    selected = (suite or "smoke").strip().lower()
    if selected == "smoke":
        result = dict(run_smoke_eval(service))
        result.setdefault("kind", "eval")
        add_eval_run_audit(service.store, result)
        return result
    if selected in {"product_acceptance", "file_to_work_product"}:
        if gateway_factory is None:
            raise ValueError("product_acceptance eval requires a KB gateway factory")
        result = run_product_acceptance_eval(service, gateway_factory())
        add_eval_run_audit(service.store, result)
        return result
    raise ValueError(f"unsupported eval suite: {suite}")


def run_product_acceptance_eval(service: WorkflowService, gateway: Any) -> dict[str, Any]:
    """Run a local product-loop acceptance check through PSKA contracts."""

    steps: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    def step(name: str, condition: bool, message: str, **metadata: Any) -> bool:
        steps.append(
            {
                "name": name,
                "status": "ok" if condition else "error",
                "message": message,
                "required": True,
                "metadata": metadata,
            }
        )
        return condition

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ready_file = tmp_dir / "pska-product-acceptance.txt"
            ready_file.write_text(
                "PSKA product acceptance verifies sourced work products, review gates, "
                "and resumable upload loops through PSKA contracts.",
                encoding="utf-8",
            )
            ready = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(ready_file)],
                dataset_name=f"pska-acceptance-ready-{uuid4().hex}",
                question="What does this acceptance source verify?",
                proposal_kind="writing_brief",
                create_review=False,
                wait_ready=True,
                export_format="json",
                limit=3,
                source_inspection_limit=1,
            )
            artifacts["ready_run_id"] = ready.get("run_id") or ""
            step(
                "upload_loop.ready_export",
                ready.get("status") == "ok"
                and bool(ready.get("run_id"))
                and bool(ready.get("context_packets"))
                and bool(ready.get("export")),
                "Upload loop produced a sourced transient work product and explicit export.",
                run_id=ready.get("run_id") or "",
                context_count=len(ready.get("context_packets") or []),
                export_format=ready.get("export_format") or "",
            )

            slow_file = tmp_dir / "pska-product-acceptance-processing.txt"
            slow_file.write_text(
                "PSKA product acceptance keeps long ingestion resumable instead of answering from missing context.",
                encoding="utf-8",
            )
            blocked = run_ingest_loop(
                service,
                gateway,
                file_paths=[str(slow_file)],
                dataset_name=f"pska-acceptance-processing-{uuid4().hex}",
                question="What should happen after ingestion finishes?",
                proposal_kind="writing_brief",
                parse=False,
                wait_ready=False,
                export_format="json",
                limit=3,
                source_inspection_limit=1,
            )
            artifacts["blocked_run_id"] = blocked.get("run_id") or ""
            step(
                "upload_loop.not_ready_contract",
                blocked.get("status") == "not_ready"
                and blocked.get("ask_status") == "not_ready"
                and (blocked.get("resume") or {}).get("tool") == "pska_ingest_loop_resume"
                and blocked.get("export") is None,
                "Processing ingestion stopped before retrieval/export and returned a PSKA resume contract.",
                run_id=blocked.get("run_id") or "",
                resume=blocked.get("resume"),
                next_actions=blocked.get("next_actions") or [],
            )

            resumable = list_resumable_agentic_questions(service, gateway, limit=10)
            matching = next(
                (
                    item
                    for item in resumable
                    if (item.get("run") or {}).get("run_id") == blocked.get("run_id")
                ),
                None,
            )
            step(
                "upload_loop.resumable_index",
                bool(matching)
                and (matching.get("resume") or {}).get("tool") == "pska_ingest_loop_resume"
                and matching.get("can_resume") is False,
                "Blocked upload loop is visible through the resumable Ask index with a PSKA resume tool.",
                run_id=blocked.get("run_id") or "",
                resume=(matching or {}).get("resume"),
            )

            dataset_id = str((blocked.get("dataset") or {}).get("dataset_id") or "")
            document_ids = [
                str(document.get("document_id") or "")
                for document in blocked.get("documents") or []
                if document.get("document_id")
            ]
            gateway.parse_documents(dataset_id=dataset_id, document_ids=document_ids, wait=True)
            resumed = resume_ingest_loop(service, gateway, run_id=str(blocked.get("run_id") or ""))
            artifacts["resumed_run_id"] = resumed.get("run_id") or ""
            step(
                "upload_loop.resume_export",
                resumed.get("status") == "ok"
                and resumed.get("ask_status") == "ready"
                and bool(resumed.get("export")),
                "Resumed upload loop produced the preserved sourced work product/export.",
                run_id=resumed.get("run_id") or "",
                resumed_from_run_id=blocked.get("run_id") or "",
            )

            memory_transition = service.memory_review_from_workflow(
                str(ready.get("run_id") or ""),
                "Preserve the acceptance workflow finding as durable knowledge.",
            )
            review = memory_transition.get("review") or {}
            review_id = str(review.get("review_id") or "")
            governance = memory_transition.get("governance") or {}
            blocked_before_review = False
            applied = memory_transition.get("memory_apply")
            if governance.get("action") == "manual_review":
                try:
                    service.memory_apply(review_id)
                except Exception:  # noqa: BLE001 - acceptance records whether the gate blocks.
                    blocked_before_review = True
                service.review_decide(review_id, "accept", "product acceptance eval")
                applied = to_jsonable(service.memory_apply(review_id))
            step(
                "durable_knowledge.governed_transition",
                bool(review_id)
                and (
                    blocked_before_review
                    if governance.get("action") == "manual_review"
                    else governance.get("action") in {"auto_accept", "auto_apply"}
                )
                and bool(applied),
                "Durable memory transition went through workspace governance before apply.",
                review_id=review_id,
                governance_action=governance.get("action") or "",
                blocked_before_review=blocked_before_review,
            )

            audit_actions = {event.action for event in service.store.list_audit_events(limit=200)}
            required_audit = {"kb.ingest", "agentic_loop.complete", "workflow.export", "review.create", "memory.apply"}
            step(
                "audit.traceability",
                required_audit.issubset(audit_actions),
                "Acceptance path produced traceable KB, workflow, export, review, and memory audit records.",
                required_actions=sorted(required_audit),
                observed_actions=sorted(audit_actions),
            )
    except Exception as exc:  # noqa: BLE001 - eval must report structured failures.
        steps.append(
            {
                "name": "eval.error",
                "status": "error",
                "message": str(exc),
                "required": True,
                "metadata": {"error_type": exc.__class__.__name__},
            }
        )

    status = "ok" if all(item.get("status") == "ok" for item in steps) else "error"
    return {
        "kind": "eval",
        "suite": "product_acceptance",
        "status": status,
        "ok": status == "ok",
        "message": (
            "Product acceptance eval passed."
            if status == "ok"
            else "Product acceptance eval failed; inspect failing steps."
        ),
        "providers": {
            "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", "").strip().lower()
            or str(getattr(service.retrieval, "backend_name", "custom")),
            "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower()
            or str(getattr(gateway, "backend_name", "custom")),
            "memory": os.getenv("PSKA_MEMORY_PROVIDER", "").strip().lower()
            or str(getattr(service.memory, "backend_name", "custom")),
            "dev_fake": os.getenv("PSKA_DEV_FAKE", "").strip().lower() in {"1", "true", "yes", "on"},
        },
        "steps": steps,
        "artifacts": artifacts,
    }


def add_eval_run_audit(store: Any, result: dict[str, Any]) -> None:
    artifacts = result.get("artifacts") or {}
    steps = result.get("steps") or []
    store.add_audit_event(
        audit_event(
            "eval.run",
            "eval",
            str(result.get("suite") or "eval"),
            suite=str(result.get("suite") or ""),
            status=str(result.get("status") or ("ok" if result.get("ok") else "error")),
            ok=bool(result.get("ok")),
            step_count=len(steps),
            failed_steps=[
                str(step.get("name") or "")
                for step in steps
                if str(step.get("status") or "") not in {"ok", "skipped"}
            ],
            ready_run_id=str(artifacts.get("ready_run_id") or ""),
            blocked_run_id=str(artifacts.get("blocked_run_id") or ""),
            resumed_run_id=str(artifacts.get("resumed_run_id") or ""),
            providers=result.get("providers") or {},
        )
    )


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    env_parser = preload_env_file(argv)
    parser = argparse.ArgumentParser(description="Run PSKA eval suites.", parents=[env_parser])
    parser.add_argument("suite", nargs="?", default=os.getenv("PSKA_EVAL_SUITE", "smoke"))
    args = parser.parse_args(argv)

    try:
        result = run_eval(args.suite, build_service_from_env(), gateway_factory=build_kb_gateway_from_env)
    except Exception as exc:  # noqa: BLE001 - CLI must report startup failures without fallback.
        result = startup_error_payload("eval", exc, operation="Eval")
        result["suite"] = args.suite
    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
