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
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_QUESTION = "Summarize the selected PSKA alpha demo scope with cited evidence and next actions."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PSKA alpha acceptance checks.")
    parser.add_argument("--env-file", default=os.getenv("ENV_FILE", ".env.pska"))
    parser.add_argument("--api-base-url", default=os.getenv("PSKA_API_BASE_URL", DEFAULT_API_BASE_URL))
    parser.add_argument("--dataset-id", action="append", default=[])
    parser.add_argument("--dataset-ids", default=os.getenv("PSKA_ALPHA_ACCEPTANCE_DATASET_IDS", ""))
    parser.add_argument("--question", default=os.getenv("PSKA_ALPHA_ACCEPTANCE_QUESTION", DEFAULT_QUESTION))
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--skip-product-boundary-contract", action="store_true")
    parser.add_argument("--skip-full-proof", action="store_true")
    parser.add_argument("--include-webui-contract", action="store_true")
    parser.add_argument("--include-webui-visual", action="store_true")
    parser.add_argument("--include-webui-turn-bridge", action="store_true")
    parser.add_argument("--include-webui-llm-proof", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    out_dir = (args.out_dir or _default_out_dir()).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    checks: list[dict[str, Any]] = []
    artifacts: dict[str, str] = {}

    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath(env)

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
        boundary = _run_product_boundary_contract(env=env, timeout=args.timeout)
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


def _run_product_boundary_contract(*, env: dict[str, str], timeout: int) -> dict[str, Any]:
    command = [sys.executable, "scripts/verify_product_boundaries.py"]
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
        "command": command,
        "returncode": result.returncode,
        "checks": _boundary_check_lines(result.stdout),
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


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


def _pythonpath(env: dict[str, str]) -> str:
    current = env.get("PYTHONPATH", "")
    src = str(ROOT / "src")
    return src if not current else f"{src}{os.pathsep}{current}"


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
