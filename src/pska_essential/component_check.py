from __future__ import annotations

import argparse
import json
import os
from typing import Any

from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable
from pska_essential.diagnostics import (
    add_live_closed_loop_probe_audit,
    add_memory_probe_audit,
    add_retrieval_probe_audit,
    build_runtime_diagnostics,
    run_live_closed_loop_probe,
    run_memory_probe,
    run_retrieval_probe,
)
from pska_essential.env_file import preload_env_file
from pska_essential.kb_gateway import build_kb_gateway_from_env


_INCOMPLETE_STEP_STATUSES = {
    "incomplete",
    "skipped",
    "not_ready",
    "processing",
    "retrieval_not_ready",
    "agentic_not_ready",
}


def run_component_check(
    service: Any,
    gateway: Any,
    *,
    dataset_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    question: str = "PSKA component check",
    memory_query: str = "PSKA component memory probe",
    limit: int = 3,
    retrieval_limit: int = 1,
    proposal_kind: str = "writing_brief",
    use_kg: bool = False,
    export_format: str = "json",
    source_inspection_limit: int = 1,
    require_memory: bool = True,
    run_closed_loop: bool = True,
) -> dict[str, Any]:
    selected_dataset_ids = _normalized_ids(dataset_ids or [])
    selected_document_ids = _normalized_ids(document_ids or [])
    steps: list[dict[str, Any]] = []

    def add_step(name: str, status: str, message: str, *, required: bool = True, **metadata: Any) -> None:
        steps.append(
            {
                "name": name,
                "status": status,
                "message": message,
                "required": required,
                "metadata": metadata,
            }
        )

    diagnostics = build_runtime_diagnostics(service=service, kb_gateway_factory=lambda: gateway)
    add_step(
        "runtime.diagnostics",
        str(diagnostics.get("status") or "unknown"),
        "Runtime diagnostics completed.",
        required=False,
        providers=diagnostics.get("providers") or {},
    )

    memory_probe = None
    if require_memory:
        memory_probe = run_memory_probe(
            service,
            query=memory_query,
            scope={},
            limit=1,
            require_live=True,
        )
        add_memory_probe_audit(service.store, memory_probe)
        add_step(
            "memory.probe",
            str(memory_probe.get("status") or "unknown"),
            str(memory_probe.get("message") or "Memory probe completed."),
            provider=memory_probe.get("provider") or "",
            memory_count=int(memory_probe.get("memory_count") or 0),
        )
    else:
        add_step("memory.probe", "skipped", "Memory probe skipped by configuration.")

    retrieval_probe = None
    closed_loop_probe = None
    if not selected_dataset_ids:
        add_step(
            "scope.check",
            "incomplete",
            "dataset_ids are required for retrieval and closed-loop component checks.",
            dataset_ids=[],
        )
    else:
        retrieval_probe = run_retrieval_probe(
            service,
            gateway,
            question=question,
            dataset_ids=selected_dataset_ids,
            document_ids=selected_document_ids,
            limit=retrieval_limit,
            use_kg=use_kg,
        )
        add_retrieval_probe_audit(service.store, retrieval_probe)
        add_step(
            "retrieval.probe",
            str(retrieval_probe.get("status") or "unknown"),
            str(retrieval_probe.get("message") or "Retrieval probe completed."),
            provider=retrieval_probe.get("provider") or "",
            context_count=int(retrieval_probe.get("context_count") or 0),
        )

        if run_closed_loop:
            closed_loop_probe = run_live_closed_loop_probe(
                service,
                gateway,
                question=question,
                dataset_ids=selected_dataset_ids,
                document_ids=selected_document_ids,
                limit=limit,
                proposal_kind=proposal_kind,
                use_kg=use_kg,
                export_format=export_format,
                source_inspection_limit=source_inspection_limit,
            )
            add_live_closed_loop_probe_audit(service.store, closed_loop_probe)
            add_step(
                "closed_loop.probe",
                str(closed_loop_probe.get("status") or "unknown"),
                str(closed_loop_probe.get("message") or "Closed-loop probe completed."),
                context_count=int(closed_loop_probe.get("context_count") or 0),
                source_count=int(closed_loop_probe.get("source_count") or 0),
                source_inspection_count=int(closed_loop_probe.get("source_inspection_count") or 0),
                run_id=str(closed_loop_probe.get("run_id") or ""),
            )
        else:
            add_step("closed_loop.probe", "skipped", "Closed-loop probe skipped by configuration.")

    status = _component_status(steps)
    return {
        "kind": "component_check",
        "status": status,
        "message": _component_message(status),
        "providers": {
            **(diagnostics.get("providers") or {}),
            "kb": str(getattr(gateway, "backend_name", None) or (diagnostics.get("providers") or {}).get("kb") or ""),
        },
        "scope": {"dataset_ids": selected_dataset_ids, "document_ids": selected_document_ids, "use_kg": bool(use_kg)},
        "steps": steps,
        "diagnostics": diagnostics,
        "memory_probe": memory_probe,
        "retrieval_probe": retrieval_probe,
        "closed_loop_probe": closed_loop_probe,
    }


def main(argv: list[str] | None = None) -> int:
    env_parser = preload_env_file(argv)
    parser = argparse.ArgumentParser(description="Run PSKA configured component checks.", parents=[env_parser])
    parser.parse_args(argv)

    try:
        service = build_service_from_env()
        gateway = build_kb_gateway_from_env()
    except Exception as exc:  # noqa: BLE001 - CLI must report startup failures without fallback.
        print(json.dumps(to_jsonable(_startup_error(exc)), ensure_ascii=False, indent=2))
        return 2

    result = run_component_check(
        service,
        gateway,
        dataset_ids=_csv_env("PSKA_COMPONENT_DATASET_IDS") or _csv_env("PSKA_LIVE_DATASET_IDS"),
        document_ids=_csv_env("PSKA_COMPONENT_DOCUMENT_IDS") or _csv_env("PSKA_LIVE_DOCUMENT_IDS"),
        question=_env("PSKA_COMPONENT_QUESTION", _env("PSKA_LIVE_QUESTION", "PSKA component check")),
        memory_query=_env("PSKA_COMPONENT_MEMORY_QUERY", "PSKA component memory probe"),
        limit=_int_env("PSKA_COMPONENT_LIMIT", _int_env("PSKA_LIVE_LIMIT", 3)),
        retrieval_limit=_int_env("PSKA_COMPONENT_RETRIEVAL_LIMIT", 1),
        proposal_kind=_env("PSKA_COMPONENT_PROPOSAL_KIND", _env("PSKA_LIVE_PROPOSAL_KIND", "writing_brief")),
        use_kg=_env_enabled("PSKA_COMPONENT_USE_KG") or _env_enabled("PSKA_LIVE_USE_KG"),
        export_format=_env("PSKA_COMPONENT_EXPORT_FORMAT", _env("PSKA_LIVE_EXPORT_FORMAT", "json")),
        source_inspection_limit=_int_env(
            "PSKA_COMPONENT_SOURCE_INSPECTION_LIMIT",
            _int_env("PSKA_LIVE_SOURCE_INSPECTION_LIMIT", 1),
        ),
        require_memory=not _env_enabled("PSKA_COMPONENT_SKIP_MEMORY"),
        run_closed_loop=not _env_enabled("PSKA_COMPONENT_SKIP_CLOSED_LOOP"),
    )
    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 2


def _component_status(steps: list[dict[str, Any]]) -> str:
    required = [step for step in steps if step.get("required")]
    if any(step.get("status") in _INCOMPLETE_STEP_STATUSES for step in required):
        return "incomplete"
    if any(step.get("status") == "error" for step in steps):
        return "error"
    if any(step.get("status") not in {"ok"} for step in required):
        return "error"
    if any(step.get("status") == "warning" for step in steps):
        return "warning"
    return "ok"


def _component_message(status: str) -> str:
    if status == "ok":
        return "All requested component checks passed."
    if status == "incomplete":
        return (
            "Component check is incomplete; provide the required scope/configuration, "
            "wait for readiness, or run all required checks."
        )
    if status == "warning":
        return "Component checks passed with warnings."
    return "One or more component checks failed."


def _startup_error(exc: Exception) -> dict[str, Any]:
    return {
        "kind": "component_check",
        "status": "error",
        "message": f"Component check startup failed: {exc}",
        "providers": {
            "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", "").strip().lower(),
            "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower(),
            "memory": os.getenv("PSKA_MEMORY_PROVIDER", "").strip().lower(),
            "dev_fake": _env_enabled("PSKA_DEV_FAKE"),
        },
        "scope": {"dataset_ids": _csv_env("PSKA_COMPONENT_DATASET_IDS") or _csv_env("PSKA_LIVE_DATASET_IDS")},
        "steps": [
            {
                "name": "runtime.startup",
                "status": "error",
                "message": str(exc),
                "required": True,
                "metadata": {"error_type": exc.__class__.__name__},
            }
        ],
        "diagnostics": None,
        "memory_probe": None,
        "retrieval_probe": None,
        "closed_loop_probe": None,
    }


def _csv_env(name: str) -> list[str]:
    return _normalized_ids(os.getenv(name, "").split(","))


def _normalized_ids(values: list[str] | list[Any]) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _env(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else int(default)


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
