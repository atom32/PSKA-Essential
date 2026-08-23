#!/usr/bin/env python3
"""Run a repeatable PSKA alpha acceptance gate.

The script writes raw evidence and a concise report to a temporary output
directory by default. It does not read or persist secrets beyond the current
process environment.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_QUESTION = "Summarize the selected PSKA alpha demo scope with cited evidence and next actions."
DEMO_VIDEO_BASENAMES = [
    "hermes_pska_extension_demo",
    "hermes_pska_extension_demo_long",
    "hermes_pska_finance_case_demo",
    "hermes_pska_webnovel_case_demo",
    "hermes_pska_customer_walkthrough_demo",
]
DEFAULT_PLAYWRIGHT_NODE_PATHS = [
    Path("/tmp/pska-playwright-recorder/node_modules"),
    Path("/tmp/pska-playwright/node_modules"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PSKA alpha acceptance checks.")
    parser.add_argument("--env-file", default=os.getenv("ENV_FILE", ".env.pska"))
    parser.add_argument("--api-base-url", default=os.getenv("PSKA_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--dataset-id", action="append", default=[])
    parser.add_argument("--dataset-ids", default=os.getenv("PSKA_ALPHA_ACCEPTANCE_DATASET_IDS", ""))
    parser.add_argument("--question", default=os.getenv("PSKA_ALPHA_ACCEPTANCE_QUESTION", DEFAULT_QUESTION))
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--skip-product-boundary-contract", action="store_true")
    parser.add_argument("--include-live-product-boundary-contract", action="store_true")
    parser.add_argument("--live-hermes-config", type=Path, default=_default_live_hermes_config())
    parser.add_argument("--live-webui-extension-manifest", type=Path, default=_default_live_webui_extension_manifest())
    parser.add_argument("--live-webui-extension-overrides", type=Path, default=_default_live_webui_extension_overrides())
    parser.add_argument("--skip-full-proof", action="store_true")
    parser.add_argument("--include-webui-contract", action="store_true")
    parser.add_argument("--include-webui-visual", action="store_true")
    parser.add_argument("--include-webui-turn-bridge", action="store_true")
    parser.add_argument("--include-webui-llm-proof", action="store_true")
    parser.add_argument("--include-demo-videos", action="store_true")
    parser.add_argument("--include-eidolia-bridge", action="store_true")
    parser.add_argument("--include-recovery-boundary", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    out_dir = (args.out_dir or _default_out_dir()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}

    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath(env)
    _configure_default_playwright_env(env)

    if args.skip_product_boundary_contract:
        checks.append(
            _check(
                "product_boundary_contract",
                True,
                "skipped by --skip-product-boundary-contract",
                skipped=True,
            )
        )
    else:
        boundary = _run_product_boundary_contract(
            env=env,
            timeout=args.timeout,
            live=args.include_live_product_boundary_contract,
            live_hermes_config=args.live_hermes_config,
            live_webui_extension_manifest=args.live_webui_extension_manifest,
            live_webui_extension_overrides=args.live_webui_extension_overrides,
        )
        _write_json(out_dir / "product_boundary_contract.json", boundary)
        artifacts["product_boundary_contract"] = str(out_dir / "product_boundary_contract.json")
        checks.append(
            _check(
                "product_boundary_contract",
                bool(boundary.get("ok")),
                f"status={boundary.get('status')}",
                checks=boundary.get("checks") or [],
            )
        )

    api_base = args.api_base_url.rstrip("/")
    alpha = _api_get_json(f"{api_base}/api/alpha/readiness")
    workspace = _api_get_json(f"{api_base}/api/workspace/status?compact=1&view=channel&next_action_limit=8")
    _write_json(out_dir / "alpha_readiness.json", alpha)
    _write_json(out_dir / "workspace_status_compact.json", workspace)
    artifacts["alpha_readiness"] = str(out_dir / "alpha_readiness.json")
    artifacts["workspace_status"] = str(out_dir / "workspace_status_compact.json")

    alpha_status = str((alpha.get("alpha_readiness") or {}).get("status") or "")
    alpha_summary = (alpha.get("alpha_readiness") or {}).get("summary") or {}
    checks.append(
        _check(
            "alpha_readiness",
            alpha_status == "alpha_ready",
            f"status={alpha_status}",
            summary=alpha_summary,
        )
    )

    connectivity = _run_component_check(
        env=env,
        env_file=args.env_file,
        extra_env={"PSKA_COMPONENT_CONNECTIVITY_ONLY": "1"},
        timeout=args.timeout,
    )
    _write_json(out_dir / "live_connectivity_check.json", connectivity)
    artifacts["live_connectivity_check"] = str(out_dir / "live_connectivity_check.json")
    checks.append(
        _check(
            "live_connectivity_check",
            connectivity.get("status") == "ok" and connectivity.get("mode") == "connectivity_only",
            f"status={connectivity.get('status')} mode={connectivity.get('mode')}",
            steps=_step_summary(connectivity),
        )
    )

    selected_dataset_ids = _selected_dataset_ids(args, workspace)
    full_proof: dict[str, Any] | None = None
    if args.skip_full_proof:
        checks.append(_check("full_component_proof", True, "skipped by --skip-full-proof", skipped=True))
    elif not selected_dataset_ids:
        checks.append(
            _check(
                "full_component_proof",
                False,
                "no ready dataset id available; pass --dataset-id or set PSKA_ALPHA_ACCEPTANCE_DATASET_IDS",
            )
        )
    else:
        full_proof = _run_component_check(
            env=env,
            env_file=args.env_file,
            extra_env={
                "PSKA_COMPONENT_DATASET_IDS": ",".join(selected_dataset_ids),
                "PSKA_COMPONENT_QUESTION": args.question,
                "PSKA_COMPONENT_LIMIT": "4",
                "PSKA_COMPONENT_RETRIEVAL_LIMIT": "2",
                "PSKA_COMPONENT_SOURCE_INSPECTION_LIMIT": "2",
            },
            timeout=args.timeout,
        )
        _write_json(out_dir / "full_component_proof.json", full_proof)
        artifacts["full_component_proof"] = str(out_dir / "full_component_proof.json")
        closed_loop = full_proof.get("closed_loop_probe") or {}
        checks.append(
            _check(
                "full_component_proof",
                full_proof.get("status") == "ok" and full_proof.get("mode") == "full_component_proof",
                f"status={full_proof.get('status')} mode={full_proof.get('mode')}",
                dataset_ids=selected_dataset_ids,
                steps=_step_summary(full_proof),
                run_id=closed_loop.get("run_id") or "",
                context_count=closed_loop.get("context_count") or 0,
                source_count=closed_loop.get("source_count") or 0,
                source_inspection_count=closed_loop.get("source_inspection_count") or 0,
                exported=bool(closed_loop.get("export")),
            )
        )

    if args.include_webui_contract:
        contract = _run_node_json(["node", "scripts/test_pska_webui_extension.mjs"], env=env, timeout=args.timeout)
        _write_json(out_dir / "webui_extension_contract.json", contract)
        artifacts["webui_extension_contract"] = str(out_dir / "webui_extension_contract.json")
        checks.append(
            _check(
                "webui_extension_contract",
                bool(contract.get("ok")),
                f"passed={contract.get('passed')}/{contract.get('total')}",
                failed_names=contract.get("failed_names") or [],
            )
        )

    if args.include_webui_visual:
        visual = _run_node_json(["node", "scripts/test_pska_webui_visual.cjs"], env=env, timeout=args.timeout)
        _write_json(out_dir / "webui_extension_visual.json", visual)
        artifacts["webui_extension_visual"] = str(out_dir / "webui_extension_visual.json")
        checks.append(
            _check(
                "webui_extension_visual",
                bool(visual.get("ok")),
                f"ok={visual.get('ok')}",
                output_dir=visual.get("output_dir") or "",
            )
        )

    if args.include_webui_turn_bridge:
        turn_bridge = _run_node_json(["node", "scripts/test_pska_webui_turn_bridge.cjs"], env=env, timeout=args.timeout)
        _write_json(out_dir / "webui_extension_turn_bridge.json", turn_bridge)
        artifacts["webui_extension_turn_bridge"] = str(out_dir / "webui_extension_turn_bridge.json")
        captured = turn_bridge.get("captured_chat_start") or {}
        checks.append(
            _check(
                "webui_extension_turn_bridge",
                bool(turn_bridge.get("ok")),
                f"ok={turn_bridge.get('ok')} forced_context_count={captured.get('forced_context_count')}",
                output_dir=turn_bridge.get("output_dir") or "",
                message_length=captured.get("message_length") or 0,
            )
        )

    if args.include_webui_llm_proof:
        llm_timeout = max(args.timeout, int(os.getenv("PSKA_LLM_PROOF_ACCEPTANCE_TIMEOUT", "300")))
        llm_proof = _run_node_json(["node", "scripts/test_pska_webui_llm_proof.cjs"], env=env, timeout=llm_timeout)
        _write_json(out_dir / "webui_extension_llm_proof.json", llm_proof)
        artifacts["webui_extension_llm_proof"] = str(out_dir / "webui_extension_llm_proof.json")
        checks.append(
            _check(
                "webui_extension_llm_proof",
                bool(llm_proof.get("ok")),
                f"ok={llm_proof.get('ok')}",
                output_dir=llm_proof.get("output_dir") or "",
                session_id=llm_proof.get("session_id") or "",
                kept_session=bool(llm_proof.get("kept_session")),
            )
        )

    if args.include_demo_videos:
        demo_timeout = max(args.timeout, int(os.getenv("PSKA_DEMO_VIDEO_ACCEPTANCE_TIMEOUT", "240")))
        demo_videos = _run_demo_video_pack(env=env, timeout=demo_timeout)
        _write_json(out_dir / "demo_video_pack.json", demo_videos)
        artifacts["demo_video_pack"] = str(out_dir / "demo_video_pack.json")
        checks.append(
            _check(
                "demo_video_pack",
                bool(demo_videos.get("ok")),
                (
                    f"status={demo_videos.get('status')} "
                    f"videos={demo_videos.get('video_count')}/{demo_videos.get('expected_video_count')} "
                    f"delivery={'yes' if demo_videos.get('delivery_pack') else 'no'} "
                    f"preview={'yes' if demo_videos.get('delivery_preview') else 'no'} "
                    f"integrity={'yes' if demo_videos.get('delivery_integrity') else 'no'} "
                    f"handoff={'yes' if demo_videos.get('delivery_handoff') else 'no'}"
                ),
                checks=demo_videos.get("checks") or [],
            )
        )

    if args.include_eidolia_bridge:
        eidolia_bridge = _run_eidolia_bridge(api_base)
        _write_json(out_dir / "eidolia_bridge.json", eidolia_bridge)
        artifacts["eidolia_bridge"] = str(out_dir / "eidolia_bridge.json")
        checks.append(
            _check(
                "eidolia_bridge",
                bool(eidolia_bridge.get("ok")),
                f"status={eidolia_bridge.get('status')} review={eidolia_bridge.get('review_status')}",
                steps=eidolia_bridge.get("steps") or [],
                review_id=eidolia_bridge.get("review_id") or "",
            )
        )

    if args.include_recovery_boundary:
        recovery_boundary = _run_recovery_boundary(api_base)
        _write_json(out_dir / "recovery_boundary.json", recovery_boundary)
        artifacts["recovery_boundary"] = str(out_dir / "recovery_boundary.json")
        checks.append(
            _check(
                "recovery_boundary",
                bool(recovery_boundary.get("ok")),
                (
                    f"status={recovery_boundary.get('status')} "
                    f"recovery={recovery_boundary.get('recovery_status')}"
                ),
                steps=recovery_boundary.get("steps") or [],
                backup_item_count=recovery_boundary.get("backup_item_count") or 0,
                restore_drill_count=recovery_boundary.get("restore_drill_count") or 0,
                blocked_native_writeback_operations=(
                    recovery_boundary.get("blocked_native_writeback_operations") or []
                ),
            )
        )

    summary = {
        "schema": "pska.alpha_acceptance_run.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if all(check["ok"] for check in checks) else "failed",
        "api_base_url": api_base,
        "env_file": args.env_file,
        "out_dir": str(out_dir),
        "dataset_ids": selected_dataset_ids,
        "checks": checks,
        "artifacts": artifacts,
    }
    _write_json(out_dir / "summary.json", summary)
    (out_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    print(_summary_markdown(summary), end="")
    return 0 if summary["status"] == "ok" else 2


def _api_get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _api_post_json(api_base_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{api_base_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _run_component_check(*, env: dict[str, str], env_file: str, extra_env: dict[str, str], timeout: int) -> dict[str, Any]:
    selected_env = env.copy()
    selected_env.update(extra_env)
    command = [
        sys.executable,
        "-m",
        "pska_essential.component_check",
        "--env-file",
        env_file,
    ]
    return _run_json(command, env=selected_env, timeout=timeout)


def _run_node_json(command: list[str], *, env: dict[str, str], timeout: int) -> dict[str, Any]:
    return _run_json(command, env=env, timeout=timeout)


def _run_eidolia_bridge(api_base_url: str) -> dict[str, Any]:
    marker = f"pska-alpha-eidolia-{uuid4().hex[:10]}"
    project_id = f"pska-alpha-acceptance-{marker}"
    node_id = "thought-eidolia-bridge-proof"
    context_payload = {
        "project_id": project_id,
        "node_id": node_id,
        "node_type": "thought",
        "title": "Eidolia bridge alpha proof",
        "text": (
            "Eidolia thought and artifact nodes should enter PSKA as sourced context, "
            "and durable memory must stay governed by Review."
        ),
        "canvas_path": f"eidolia://{project_id}/canvas-workspace.json#{node_id}",
        "role": "decision",
        "metadata": {
            "origin": "alpha_acceptance_eidolia_bridge",
            "temporary": True,
            "marker": marker,
        },
    }
    review_payload = {
        **context_payload,
        "text": "Eidolia keeps thought and artifact as the user-visible canvas primitives.",
        "behavior_delta": "When discussing Eidolia architecture, keep thought/artifact as canvas primitives.",
        "memory_type": "project_state",
        "memory_scope": "project",
        "reason": "Temporary alpha acceptance proof for Eidolia governed memory bridge.",
        "scope": {"origin": "alpha_acceptance_eidolia_bridge", "marker": marker},
    }
    steps: list[dict[str, Any]] = []
    context: dict[str, Any] = {}
    created: dict[str, Any] = {}
    trace: dict[str, Any] = {}
    cleanup: dict[str, Any] = {}
    review_id = ""
    error = ""
    try:
        context = _api_post_json(api_base_url, "/api/eidolia/context/read", context_payload)
        context_body = context.get("context") or {}
        steps.append(_eidolia_step(
            "context_read",
            context.get("ok") is True
            and context_body.get("schema") == "pska.eidolia_context.v1"
            and ((context_body.get("source_ref") or {}).get("adapter") == "eidolia")
            and (context_body.get("data_flow") or {}).get("writes_memory_directly") is False
            and (context_body.get("data_flow") or {}).get("writes_source_files") is False,
            "Eidolia node normalized to a source-safe SourceRef.",
        ))

        created = _api_post_json(api_base_url, "/api/eidolia/memory-reviews", review_payload)
        review_id = str(((created.get("review") or {}).get("review_id")) or "")
        steps.append(_eidolia_step(
            "memory_review_create",
            created.get("ok") is True
            and bool(review_id)
            and ((created.get("review") or {}).get("status") == "pending")
            and created.get("memory_apply") is None
            and ((created.get("memory_card") or {}).get("source_origin") == "eidolia")
            and (created.get("governance") or {}).get("writes_memory_directly") is False,
            "Eidolia memory candidate created as pending Review without durable write.",
        ))

        if review_id:
            trace = _api_get_json(f"{api_base_url.rstrip('/')}/api/trace/query?review_id={review_id}&limit=20")
            steps.append(_eidolia_step(
                "trace_query",
                trace.get("ok") is True
                and trace.get("schema") == "pska.trace_query.v1"
                and trace.get("status") == "found"
                and (trace.get("data_flow") or {}).get("writes_memory_directly") is False,
                "Trace query found Eidolia Review lineage without writes.",
            ))
    except Exception as exc:  # pragma: no cover - exercised by live acceptance.
        error = str(exc)
        steps.append(_eidolia_step("exception", False, error))
    finally:
        if review_id:
            try:
                cleanup = _api_post_json(
                    api_base_url,
                    f"/api/reviews/{review_id}/decision",
                    {
                        "decision": "reject",
                        "reason": "Reject temporary alpha acceptance Eidolia bridge proof.",
                    },
                )
                steps.append(_eidolia_step(
                    "cleanup_reject_review",
                    cleanup.get("ok") is True
                    and ((cleanup.get("decision") or {}).get("decision") == "reject"),
                    "Temporary Eidolia Review rejected after proof.",
                ))
            except Exception as exc:  # pragma: no cover - exercised by live acceptance.
                steps.append(_eidolia_step("cleanup_reject_review", False, str(exc)))

    ok = bool(steps) and all(bool(step.get("ok")) for step in steps) and not error
    return {
        "schema": "pska.alpha_eidolia_bridge_acceptance.v1",
        "ok": ok,
        "status": "ok" if ok else "failed",
        "project_id": project_id,
        "node_id": node_id,
        "review_id": review_id,
        "review_status": ((cleanup.get("decision") or {}).get("decision")) or ((created.get("review") or {}).get("status")) or "",
        "steps": steps,
        "context": context,
        "created": created,
        "trace": trace,
        "cleanup": cleanup,
        "error": error,
        "data_flow": {
            "writes_memory_directly": False,
            "writes_source_files": False,
            "creates_review": True,
            "rejects_temporary_review": bool(review_id),
            "embedding_required": False,
        },
    }


def _run_recovery_boundary(api_base_url: str) -> dict[str, Any]:
    payload = _api_get_json(f"{api_base_url.rstrip('/')}/api/alpha/recovery-plan")
    plan = payload.get("alpha_recovery_plan") or {}
    backup_items = plan.get("backup_items") or []
    restore_drills = plan.get("restore_drills") or []
    writeback_preflight = plan.get("writeback_preflight") or []
    data_flow = plan.get("data_flow") or {}
    item_ids = {str(item.get("item_id") or "") for item in backup_items}
    drill_ids = {str(drill.get("drill_id") or "") for drill in restore_drills}
    blocked_native_ops = [
        str(item.get("operation") or "")
        for item in writeback_preflight
        if str(item.get("operation") or "") != "sidecar_annotation"
        and item.get("allowed_first_trial") is False
    ]
    next_actions = {
        str(action.get("action") or "")
        for action in plan.get("next_actions") or []
    }
    required_flow = {
        "read_only": True,
        "creates_backup": False,
        "restores_data": False,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "executes_provider_export": False,
    }
    flow_ok = all(data_flow.get(name) is expected for name, expected in required_flow.items())
    required_items = {"review_store", "source_registry", "user_source_roots", "kb_provider"}
    required_drills = {
        "copy_pska_local_state",
        "restore_pska_local_state",
        "provider_restore_boundary",
        "native_writeback_rollback",
    }
    steps = [
        _recovery_step(
            "schema",
            payload.get("ok") is True and plan.get("schema") == "pska.alpha_recovery_plan.v1",
            "Recovery plan route returns the alpha recovery schema.",
        ),
        _recovery_step(
            "read_only_data_flow",
            flow_ok,
            "Recovery plan is read-only and does not create backups, restore data, export providers, write sources, or write memory.",
        ),
        _recovery_step(
            "backup_items",
            required_items.issubset(item_ids),
            "PSKA ledgers, source roots, and provider-owned KB state are named as backup boundaries.",
        ),
        _recovery_step(
            "restore_drills",
            required_drills.issubset(drill_ids),
            "Local restore, provider restore, and native writeback rollback drills are listed.",
        ),
        _recovery_step(
            "native_writeback_locked",
            len(blocked_native_ops) >= 3
            and "verify_source_writeback_backup" in next_actions,
            "Native tag/comment/MOC writeback remains locked until backup is verified.",
        ),
        _recovery_step(
            "status_is_operator_gate",
            str(plan.get("status") or "") in {"ready", "needs_rehearsal"},
            "Recovery status is an operator gate, not an automatic writeback unlock.",
        ),
    ]
    ok = bool(steps) and all(bool(step.get("ok")) for step in steps)
    return {
        "schema": "pska.alpha_recovery_boundary_acceptance.v1",
        "ok": ok,
        "status": "ok" if ok else "failed",
        "recovery_status": str(plan.get("status") or ""),
        "backup_item_count": len(backup_items),
        "restore_drill_count": len(restore_drills),
        "blocked_native_writeback_operations": blocked_native_ops,
        "steps": steps,
        "plan": plan,
        "data_flow": data_flow,
    }


def _run_demo_video_pack(*, env: dict[str, str], timeout: int) -> dict[str, Any]:
    command = [
        sys.executable,
        "scripts/verify_hermes_extension_demo_pack.py",
        "--all-videos",
        "--require-video",
        "--require-delivery-pack",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    checks = _boundary_check_lines(result.stdout)
    video_count = _demo_video_count(checks)
    expected_video_count = len(DEMO_VIDEO_BASENAMES)
    delivery_pack = _demo_delivery_pack_present(checks)
    delivery_preview = _demo_delivery_preview_present(checks)
    delivery_integrity = _demo_delivery_integrity_present(checks)
    delivery_handoff = _demo_delivery_handoff_present(checks)
    ok = (
        result.returncode == 0
        and video_count == expected_video_count
        and delivery_pack
        and delivery_preview
        and delivery_integrity
        and delivery_handoff
    )
    return {
        "ok": ok,
        "status": "ok" if ok else "failed",
        "command": command,
        "returncode": result.returncode,
        "video_count": video_count,
        "expected_video_count": expected_video_count,
        "delivery_pack": delivery_pack,
        "delivery_preview": delivery_preview,
        "delivery_integrity": delivery_integrity,
        "delivery_handoff": delivery_handoff,
        "checks": checks,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _run_product_boundary_contract(
    *,
    env: dict[str, str],
    timeout: int,
    live: bool = False,
    live_hermes_config: Path | None = None,
    live_webui_extension_manifest: Path | None = None,
    live_webui_extension_overrides: Path | None = None,
) -> dict[str, Any]:
    command = [sys.executable, "scripts/verify_product_boundaries.py"]
    if live:
        command.extend(_live_product_boundary_args(
            live_hermes_config=live_hermes_config,
            live_webui_extension_manifest=live_webui_extension_manifest,
            live_webui_extension_overrides=live_webui_extension_overrides,
        ))
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "ok": result.returncode == 0,
        "status": "ok" if result.returncode == 0 else "failed",
        "mode": "repository_and_live" if live else "repository",
        "command": command,
        "returncode": result.returncode,
        "checks": _boundary_check_lines(result.stdout),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _live_product_boundary_args(
    *,
    live_hermes_config: Path | None,
    live_webui_extension_manifest: Path | None,
    live_webui_extension_overrides: Path | None,
) -> list[str]:
    args: list[str] = []
    if live_hermes_config is not None:
        args.extend(["--live-hermes-config", str(live_hermes_config.expanduser())])
    if live_webui_extension_manifest is not None:
        args.extend(["--live-webui-extension-manifest", str(live_webui_extension_manifest.expanduser())])
    if live_webui_extension_overrides is not None:
        args.extend(["--live-webui-extension-overrides", str(live_webui_extension_overrides.expanduser())])
    return args


def _run_json(command: list[str], *, env: dict[str, str], timeout: int) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": "command_failed" if result.returncode else "invalid_json",
            "command": command,
            "error": str(exc),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    if result.returncode != 0:
        payload["command_returncode"] = result.returncode
        if result.stderr:
            payload["command_stderr"] = result.stderr
    return payload


def _selected_dataset_ids(args: argparse.Namespace, workspace: dict[str, Any]) -> list[str]:
    explicit = list(args.dataset_id or [])
    explicit.extend(_split_csv(args.dataset_ids))
    if explicit:
        return _normalized(explicit)
    for env_name in ("PSKA_COMPONENT_DATASET_IDS", "PSKA_LIVE_DATASET_IDS"):
        from_env = _split_csv(os.getenv(env_name, ""))
        if from_env:
            return _normalized(from_env)
    ready = (((workspace.get("workspace_status") or {}).get("kb") or {}).get("ready_dataset_ids")) or []
    return _normalized(ready[:1])


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _normalized(values: list[Any]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _default_out_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path(tempfile.gettempdir()) / f"pska-alpha-acceptance-{stamp}"


def _default_live_hermes_config() -> Path:
    return Path(os.getenv("HERMES_CONFIG_PATH", str(Path.home() / ".hermes" / "config.yaml")))


def _default_live_webui_extension_manifest() -> Path:
    explicit = os.getenv("HERMES_WEBUI_EXTENSION_MANIFEST_PATH", "")
    if explicit:
        return Path(explicit)
    root = Path(os.getenv("HERMES_WEBUI_EXTENSION_DIR", str(Path.home() / ".hermes" / "webui-local-extensions")))
    name = os.getenv("HERMES_WEBUI_EXTENSION_MANIFEST", "extensions.json")
    return root / name


def _default_live_webui_extension_overrides() -> Path:
    explicit = os.getenv("HERMES_WEBUI_EXTENSION_OVERRIDES_PATH", "")
    if explicit:
        return Path(explicit)
    state_dir = Path(os.getenv("HERMES_WEBUI_STATE_DIR", str(Path.home() / ".hermes" / "webui")))
    return state_dir / "extension-overrides.json"


def _pythonpath(env: dict[str, str]) -> str:
    current = env.get("PYTHONPATH", "")
    src = str(ROOT / "src")
    return src if not current else f"{src}{os.pathsep}{current}"


def _configure_default_playwright_env(
    env: dict[str, str],
    *,
    candidates: list[Path] | None = None,
) -> None:
    node_path = str(env.get("NODE_PATH") or "").strip()
    module = str(env.get("PSKA_PLAYWRIGHT_MODULE") or env.get("PLAYWRIGHT_MODULE") or "").strip()
    candidates = candidates or DEFAULT_PLAYWRIGHT_NODE_PATHS

    if not node_path:
        for candidate in candidates:
            if candidate.exists():
                node_path = str(candidate)
                env["NODE_PATH"] = node_path
                break

    if module or not node_path:
        return

    root = Path(node_path)
    if (root / "playwright").exists():
        env["PSKA_PLAYWRIGHT_MODULE"] = "playwright"
    elif (root / "playwright-core").exists():
        env["PSKA_PLAYWRIGHT_MODULE"] = "playwright-core"
        env.setdefault("PSKA_PLAYWRIGHT_CHANNEL", "chrome")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _step_summary(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "name": str(step.get("name") or ""),
            "status": str(step.get("status") or ""),
            "message": str(step.get("message") or ""),
        }
        for step in payload.get("steps") or []
    ]


def _boundary_check_lines(stdout: str) -> list[str]:
    return [
        line[2:].strip()
        for line in str(stdout or "").splitlines()
        if line.startswith("- ")
    ]


def _demo_video_count(checks: list[str]) -> int:
    seen = set()
    for line in checks:
        for basename in DEMO_VIDEO_BASENAMES:
            if line.startswith(f"{basename}.mp4:"):
                seen.add(basename)
    return len(seen)


def _demo_delivery_pack_present(checks: list[str]) -> bool:
    return any(
        line.startswith("hermes_pska_customer_walkthrough_demo_delivery_pack.zip:")
        and "delivery zip contains index, summary, video, hard-subtitled video, subtitles, voiceover, preview sheet, storyboard, manifests, and README" in line
        for line in checks
    )


def _demo_delivery_preview_present(checks: list[str]) -> bool:
    return any(
        line.startswith("hermes_pska_customer_walkthrough_demo_delivery_pack.zip:")
        and "preview sheet" in line
        for line in checks
    )


def _demo_delivery_integrity_present(checks: list[str]) -> bool:
    internal = any(
        line.startswith("hermes_pska_customer_walkthrough_demo_delivery_pack.zip:")
        and "delivery zip integrity verified with sha256 for " in line
        for line in checks
    )
    external = any(
        line.startswith("hermes_pska_customer_walkthrough_demo_delivery_pack.zip.sha256:")
        and "delivery zip external checksum verified with sha256" in line
        for line in checks
    )
    return internal and external


def _demo_delivery_handoff_present(checks: list[str]) -> bool:
    return any(
        line.startswith("hermes_pska_customer_walkthrough_demo_delivery_handoff.zh.md:")
        and "external handoff note covers checksum and editing steps" in line
        for line in checks
    )


def _eidolia_step(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message}


def _recovery_step(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message}


def _check(name: str, ok: bool, message: str, **metadata: Any) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "message": message, "metadata": metadata}


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# PSKA Alpha Acceptance Run",
        "",
        f"Status: `{summary['status']}`",
        f"Output: `{summary['out_dir']}`",
        "",
        "## Checks",
        "",
    ]
    for check in summary["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        lines.append(f"- `{mark}` {check['name']}: {check['message']}")
        metadata = check.get("metadata") or {}
        if metadata.get("run_id"):
            lines.append(f"  run_id: `{metadata['run_id']}`")
        if metadata.get("dataset_ids"):
            lines.append(f"  dataset_ids: `{', '.join(metadata['dataset_ids'])}`")
    lines.extend(["", "## Artifacts", ""])
    for name, path in sorted((summary.get("artifacts") or {}).items()):
        lines.append(f"- `{name}`: `{path}`")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
