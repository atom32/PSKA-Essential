from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.env_file import preload_env_file
from pska_essential.source_audit_jobs import list_source_audit_jobs


WAKEUP_PLAN_SCHEMA = "pska.wakeup_plan.v1"
DEFAULT_LABEL = "com.pska-essential.source-audit-tick"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_INTERVAL_MINUTES = 15
DEFAULT_LIMIT = 20
MIN_INTERVAL_MINUTES = 5
MAX_INTERVAL_MINUTES = 24 * 60


def build_wakeup_plan(
    service: Any,
    *,
    api_base_url: str = "",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    limit: int = DEFAULT_LIMIT,
    label: str = "",
    launch_agents_dir: str = "",
    now: str = "",
    check_loaded: bool = False,
) -> dict[str, Any]:
    """Return a read-only plan for waking due PSKA source audit schedules.

    The plan is deliberately passive: it inspects the local launchd plist path
    and scheduled PSKA jobs, then returns installation material. It does not
    write LaunchAgents, call launchctl, tick jobs, scan sources, or run jobs.
    """

    selected_api_base_url = normalize_api_base_url(api_base_url)
    selected_interval = bounded_interval_minutes(interval_minutes)
    selected_limit = max(1, int(limit))
    selected_label = normalize_label(label)
    plist_path = launchd_plist_path(selected_label, launch_agents_dir=launch_agents_dir)
    expected_plist = launchd_plist(
        api_base_url=selected_api_base_url,
        interval_minutes=selected_interval,
        limit=selected_limit,
        label=selected_label,
    )
    existing_plist = read_launchd_plist(plist_path)
    matches_expected = bool(existing_plist and plist_matches_expected(existing_plist, expected_plist))
    loaded = launchd_loaded(selected_label) if check_loaded else None
    scheduled = scheduled_source_audit_summary(service, now=now)
    supported = is_launchd_supported()
    status = wakeup_status(
        supported=supported,
        scheduled_count=int(scheduled.get("scheduled_count") or 0),
        plist_exists=plist_path.is_file(),
        matches_expected=matches_expected,
        loaded=loaded,
    )
    return {
        "kind": "wakeup_plan",
        "schema": WAKEUP_PLAN_SCHEMA,
        "generated_at": utc_now_iso(),
        "status": status,
        "summary": {
            "scheduler_provider": "launchd" if supported else "cron_or_external",
            "scheduled_source_audit_count": scheduled.get("scheduled_count", 0),
            "due_source_audit_count": scheduled.get("due_count", 0),
            "next_due_at": scheduled.get("next_due_at", ""),
            "launchd_plist_exists": plist_path.is_file(),
            "launchd_plist_matches_expected": matches_expected,
            "launchd_loaded": loaded,
        },
        "source_audit": scheduled,
        "launchd": {
            "supported": supported,
            "label": selected_label,
            "plist_path": str(plist_path),
            "plist_exists": plist_path.is_file(),
            "plist_matches_expected": matches_expected,
            "loaded": loaded,
            "start_interval_seconds": selected_interval * 60,
            "program_arguments": expected_plist["ProgramArguments"],
            "plist_preview": expected_plist,
            "install_command": command_line("install", selected_api_base_url, selected_interval, selected_limit, selected_label),
            "print_plist_command": command_line("print-plist", selected_api_base_url, selected_interval, selected_limit, selected_label),
            "uninstall_command": command_line("uninstall", selected_api_base_url, selected_interval, selected_limit, selected_label),
            "load_command": f"launchctl bootstrap gui/$(id -u) {shlex.quote(str(plist_path))}",
            "unload_command": f"launchctl bootout gui/$(id -u)/{shlex.quote(selected_label)}",
        },
        "cron": {
            "supported": True,
            "line": cron_line(
                api_base_url=selected_api_base_url,
                interval_minutes=selected_interval,
                limit=selected_limit,
            ),
            "note": "Use only if launchd is unavailable; cron line still calls the same explicit PSKA tick endpoint.",
        },
        "target": {
            "api": "POST /api/sources/audit-jobs/tick",
            "url": f"{selected_api_base_url}/api/sources/audit-jobs/tick",
            "payload": {"limit": selected_limit},
            "tool": "pska_source_audit_job_tick",
        },
        "data_flow": {
            "read_only": True,
            "writes_launch_agent": False,
            "installs_scheduler": False,
            "calls_tick_endpoint": False,
            "activates_due_jobs": False,
            "runs_jobs": False,
            "writes_source_files": False,
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "embedding_required": False,
        },
        "scheduled_trigger_data_flow": {
            "read_only": False,
            "calls_tick_endpoint": True,
            "activates_due_jobs": True,
            "runs_jobs": False,
            "writes_source_files": False,
            "writes_source_registry": True,
            "writes_memory_directly": False,
            "embedding_required": False,
            "note": "The scheduled tick only promotes due waiting source audit jobs to queued; explicit job runners perform scans later.",
        },
        "next_actions": wakeup_next_actions(status, scheduled, supported=supported),
    }


def install_launchd_agent(
    *,
    api_base_url: str = "",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    limit: int = DEFAULT_LIMIT,
    label: str = "",
    launch_agents_dir: str = "",
    load: bool = False,
) -> dict[str, Any]:
    selected_api_base_url = normalize_api_base_url(api_base_url)
    selected_interval = bounded_interval_minutes(interval_minutes)
    selected_limit = max(1, int(limit))
    selected_label = normalize_label(label)
    plist_path = launchd_plist_path(selected_label, launch_agents_dir=launch_agents_dir)
    plist = launchd_plist(
        api_base_url=selected_api_base_url,
        interval_minutes=selected_interval,
        limit=selected_limit,
        label=selected_label,
    )
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)
    loaded = None
    launchctl_result: dict[str, Any] | None = None
    if load:
        launchctl_result = run_launchctl(["bootstrap", f"gui/{os.getuid()}", str(plist_path)])
        loaded = launchd_loaded(selected_label)
    return {
        "schema": WAKEUP_PLAN_SCHEMA,
        "status": "installed",
        "launchd": {
            "label": selected_label,
            "plist_path": str(plist_path),
            "plist_exists": plist_path.is_file(),
            "loaded": loaded,
            "launchctl": launchctl_result,
        },
        "data_flow": {
            "read_only": False,
            "writes_launch_agent": True,
            "loads_scheduler": bool(load),
            "calls_tick_endpoint": False,
            "activates_due_jobs": False,
            "runs_jobs": False,
            "writes_source_files": False,
            "writes_memory_directly": False,
        },
    }


def uninstall_launchd_agent(
    *,
    label: str = "",
    launch_agents_dir: str = "",
    unload: bool = False,
) -> dict[str, Any]:
    selected_label = normalize_label(label)
    plist_path = launchd_plist_path(selected_label, launch_agents_dir=launch_agents_dir)
    launchctl_result: dict[str, Any] | None = None
    if unload:
        launchctl_result = run_launchctl(["bootout", f"gui/{os.getuid()}/{selected_label}"])
    existed = plist_path.exists()
    if existed:
        plist_path.unlink()
    return {
        "schema": WAKEUP_PLAN_SCHEMA,
        "status": "uninstalled" if existed else "not_installed",
        "launchd": {
            "label": selected_label,
            "plist_path": str(plist_path),
            "removed": existed,
            "launchctl": launchctl_result,
        },
        "data_flow": {
            "read_only": False,
            "removes_launch_agent": existed,
            "unloads_scheduler": bool(unload),
            "calls_tick_endpoint": False,
            "activates_due_jobs": False,
            "runs_jobs": False,
            "writes_source_files": False,
            "writes_memory_directly": False,
        },
    }


def launchd_plist(
    *,
    api_base_url: str = "",
    interval_minutes: int = DEFAULT_INTERVAL_MINUTES,
    limit: int = DEFAULT_LIMIT,
    label: str = "",
) -> dict[str, Any]:
    selected_api_base_url = normalize_api_base_url(api_base_url)
    selected_interval = bounded_interval_minutes(interval_minutes)
    selected_limit = max(1, int(limit))
    selected_label = normalize_label(label)
    log_dir = Path.home() / ".pska-essential" / "logs"
    return {
        "Label": selected_label,
        "ProgramArguments": [
            "/usr/bin/curl",
            "-fsS",
            "--max-time",
            "15",
            "-X",
            "POST",
            f"{selected_api_base_url}/api/sources/audit-jobs/tick",
            "-H",
            "content-type: application/json",
            "-d",
            json.dumps({"limit": selected_limit}, separators=(",", ":")),
        ],
        "StartInterval": selected_interval * 60,
        "RunAtLoad": False,
        "StandardOutPath": str(log_dir / "source-audit-tick.out.log"),
        "StandardErrorPath": str(log_dir / "source-audit-tick.err.log"),
        "ProcessType": "Background",
    }


def launchd_plist_path(label: str = "", *, launch_agents_dir: str = "") -> Path:
    selected_label = normalize_label(label)
    base = Path(launch_agents_dir).expanduser() if launch_agents_dir else Path.home() / "Library" / "LaunchAgents"
    return base / f"{selected_label}.plist"


def normalize_api_base_url(value: str = "") -> str:
    raw = str(value or os.getenv("PSKA_API_BASE_URL") or DEFAULT_API_BASE_URL).strip()
    parsed = urlsplit(raw)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc
    path = parsed.path.rstrip("/")
    if not netloc and path:
        pieces = path.split("/", 1)
        netloc = pieces[0]
        path = f"/{pieces[1]}" if len(pieces) > 1 else ""
    if not netloc:
        netloc = "127.0.0.1:8765"
    return urlunsplit((scheme, netloc, path, "", "")).rstrip("/")


def normalize_label(value: str = "") -> str:
    selected = str(value or os.getenv("PSKA_WAKEUP_LAUNCHD_LABEL") or DEFAULT_LABEL).strip()
    if not selected:
        return DEFAULT_LABEL
    return "".join(ch for ch in selected if ch.isalnum() or ch in "._-") or DEFAULT_LABEL


def bounded_interval_minutes(value: int) -> int:
    selected = int(value or DEFAULT_INTERVAL_MINUTES)
    return min(MAX_INTERVAL_MINUTES, max(MIN_INTERVAL_MINUTES, selected))


def cron_line(*, api_base_url: str, interval_minutes: int, limit: int) -> str:
    selected_interval = bounded_interval_minutes(interval_minutes)
    minute_expr = f"*/{selected_interval}" if selected_interval < 60 else "0"
    if selected_interval > 59:
        hours = max(1, selected_interval // 60)
        hour_expr = f"*/{hours}"
    else:
        hour_expr = "*"
    command = " ".join(
        [
            "/usr/bin/curl",
            "-fsS",
            "--max-time",
            "15",
            "-X",
            "POST",
            shlex.quote(f"{normalize_api_base_url(api_base_url)}/api/sources/audit-jobs/tick"),
            "-H",
            shlex.quote("content-type: application/json"),
            "-d",
            shlex.quote(json.dumps({"limit": max(1, int(limit))}, separators=(",", ":"))),
            ">/dev/null",
            "2>>$HOME/.pska-essential/logs/source-audit-tick.err.log",
        ]
    )
    return f"{minute_expr} {hour_expr} * * * {command}"


def read_launchd_plist(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as handle:
            loaded = plistlib.load(handle)
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return None
    return loaded if isinstance(loaded, dict) else None


def plist_matches_expected(existing: dict[str, Any], expected: dict[str, Any]) -> bool:
    keys = {"Label", "ProgramArguments", "StartInterval", "RunAtLoad"}
    return all(existing.get(key) == expected.get(key) for key in keys)


def is_launchd_supported() -> bool:
    return platform.system().lower() == "darwin"


def launchd_loaded(label: str) -> bool | None:
    if not is_launchd_supported():
        return None
    result = run_launchctl(["print", f"gui/{os.getuid()}/{normalize_label(label)}"])
    return result["returncode"] == 0


def run_launchctl(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["launchctl", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-1000:],
        "stderr": completed.stderr[-1000:],
    }


def scheduled_source_audit_summary(service: Any, *, now: str = "") -> dict[str, Any]:
    now_dt = parse_datetime(now) or datetime.now(timezone.utc)
    try:
        waiting = list_source_audit_jobs(service, status="waiting", limit=500)
    except Exception as exc:  # noqa: BLE001 - status endpoint should explain degraded ledgers.
        return {
            "status": "unavailable",
            "error": str(exc),
            "scheduled_count": 0,
            "due_count": 0,
            "next_due_at": "",
            "jobs": [],
        }
    jobs = [item.get("source_audit_job") or {} for item in waiting]
    scheduled = [job for job in jobs if str(job.get("schedule_mode") or "") == "scheduled"]
    due = [job for job in scheduled if is_due(str(job.get("due_at") or ""), now_dt)]
    next_due_at = next_due(scheduled, now_dt=now_dt)
    return {
        "status": "ok",
        "now": now_dt.isoformat(),
        "waiting_count": len(jobs),
        "scheduled_count": len(scheduled),
        "due_count": len(due),
        "next_due_at": next_due_at,
        "jobs": [
            {
                "status": str(job.get("status") or ""),
                "label": str((job.get("request") or {}).get("label") or ""),
                "cadence": str(job.get("cadence") or (job.get("request") or {}).get("cadence") or ""),
                "due_at": str(job.get("due_at") or ""),
                "series_id": str(job.get("series_id") or ""),
            }
            for job in scheduled[:20]
        ],
    }


def wakeup_status(
    *,
    supported: bool,
    scheduled_count: int,
    plist_exists: bool,
    matches_expected: bool,
    loaded: bool | None,
) -> str:
    if not supported:
        return "cron_or_external_required"
    if plist_exists and not matches_expected:
        return "drift"
    if plist_exists and loaded is True:
        return "active"
    if plist_exists and loaded is False:
        return "configured_not_loaded"
    if plist_exists:
        return "configured"
    if scheduled_count <= 0:
        return "idle"
    return "install_required"


def wakeup_next_actions(status: str, scheduled: dict[str, Any], *, supported: bool) -> list[dict[str, Any]]:
    if status == "idle":
        return [
            {
                "action": "create_source_audit_schedule",
                "label": "Create Recurring Source Audit",
                "api": "POST /api/sources/audit-schedules",
                "tool": "pska_source_audit_schedule_create",
            }
        ]
    if status == "install_required":
        return [
            {
                "action": "install_launchd_tick",
                "label": "Install Local Wakeup",
                "cli": "pska-essential-wakeup install",
                "manual_approval_required": True,
            }
        ]
    if status == "configured_not_loaded":
        return [
            {
                "action": "load_launchd_tick",
                "label": "Load Local Wakeup",
                "cli": "pska-essential-wakeup install --load",
                "manual_approval_required": True,
            }
        ]
    if status == "drift":
        return [
            {
                "action": "review_launchd_drift",
                "label": "Review Wakeup Plist Drift",
                "cli": "pska-essential-wakeup print-plist",
                "manual_approval_required": True,
            }
        ]
    if status == "cron_or_external_required":
        return [
            {
                "action": "install_external_cron_tick",
                "label": "Install Cron Or External Scheduler",
                "manual_approval_required": True,
                "reason": "launchd is only available on macOS.",
            }
        ]
    if int(scheduled.get("due_count") or 0):
        return [
            {
                "action": "wait_for_wakeup_or_tick_now",
                "label": "Wait For Wakeup Or Tick Now",
                "api": "POST /api/sources/audit-jobs/tick",
                "tool": "pska_source_audit_job_tick",
            }
        ]
    if supported:
        return []
    return []


def command_line(action: str, api_base_url: str, interval_minutes: int, limit: int, label: str) -> str:
    parts = [
        "pska-essential-wakeup",
        action,
        "--api-base-url",
        normalize_api_base_url(api_base_url),
        "--interval-minutes",
        str(bounded_interval_minutes(interval_minutes)),
        "--limit",
        str(max(1, int(limit))),
        "--label",
        normalize_label(label),
    ]
    return " ".join(shlex.quote(part) for part in parts)


def is_due(value: str, now_dt: datetime) -> bool:
    due_at = parse_datetime(value)
    return bool(due_at and due_at <= now_dt)


def next_due(jobs: list[dict[str, Any]], *, now_dt: datetime) -> str:
    future: list[datetime] = []
    for job in jobs:
        due_at = parse_datetime(str(job.get("due_at") or ""))
        if due_at and due_at > now_dt:
            future.append(due_at)
    if not future:
        return ""
    return min(future).isoformat()


def parse_datetime(value: str) -> datetime | None:
    selected = str(value or "").strip()
    if not selected:
        return None
    try:
        if selected.endswith("Z"):
            selected = f"{selected[:-1]}+00:00"
        parsed = datetime.fromisoformat(selected)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    env_parser = preload_env_file(argv)
    parser = argparse.ArgumentParser(
        description="Inspect or install the PSKA local wakeup bridge for due source audit ticks.",
        parents=[env_parser],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "print-plist", "install", "uninstall"):
        sub = subparsers.add_parser(name)
        sub.add_argument("--api-base-url", default="")
        sub.add_argument("--interval-minutes", type=int, default=DEFAULT_INTERVAL_MINUTES)
        sub.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
        sub.add_argument("--label", default="")
        sub.add_argument("--launch-agents-dir", default="")
        if name == "status":
            sub.add_argument("--check-loaded", action="store_true")
        if name == "install":
            sub.add_argument("--load", action="store_true")
        if name == "uninstall":
            sub.add_argument("--unload", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "print-plist":
        result = launchd_plist(
            api_base_url=args.api_base_url,
            interval_minutes=args.interval_minutes,
            limit=args.limit,
            label=args.label,
        )
    elif args.command == "install":
        result = install_launchd_agent(
            api_base_url=args.api_base_url,
            interval_minutes=args.interval_minutes,
            limit=args.limit,
            label=args.label,
            launch_agents_dir=args.launch_agents_dir,
            load=args.load,
        )
    elif args.command == "uninstall":
        result = uninstall_launchd_agent(
            label=args.label,
            launch_agents_dir=args.launch_agents_dir,
            unload=args.unload,
        )
    else:
        result = build_wakeup_plan(
            build_service_from_env(),
            api_base_url=args.api_base_url,
            interval_minutes=args.interval_minutes,
            limit=args.limit,
            label=args.label,
            launch_agents_dir=args.launch_agents_dir,
            check_loaded=args.check_loaded,
        )
    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
