from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any

from pska_essential.audit import audit_event
from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.env_file import env_file_arg_parser, load_env_file
from pska_essential.source_audit_jobs import enqueue_source_audit_job
from pska_essential.source_extraction_jobs import enqueue_source_extraction_job
from pska_essential.workflow import WorkflowService


SOURCE_WATCH_ONCE_SCHEMA = "pska.source_watch_once.v1"
_IGNORED_PATH_PARTS = {".pska", ".pska-essential", "__pycache__", ".git"}
_IGNORED_FILENAMES = {".DS_Store"}


def watch_source_once(
    service: WorkflowService,
    *,
    root_id: str,
    duration_seconds: float = 5.0,
    quiet_seconds: float = 0.25,
    max_events: int = 100,
    recursive: bool = True,
    enqueue_extraction: bool = True,
    enqueue_audit: bool = False,
    label: str = "",
    priority: int = 0,
    extractor: str = "auto",
    max_files: int = 1000,
    max_bytes: int = 1_000_000,
    audit_limit: int = 20,
) -> dict[str, Any]:
    """Watch one registered source root for a bounded interval and enqueue PSKA jobs.

    The watcher is intentionally not a daemon. It only listens to an already
    registered source root, records a compact event summary, and creates PSKA
    workflow jobs. It never edits source files or writes durable memory.
    """

    selected_root_id = str(root_id or "").strip()
    if not selected_root_id:
        raise ValueError("root_id is required")
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be greater than or equal to 0")
    if quiet_seconds < 0:
        raise ValueError("quiet_seconds must be greater than or equal to 0")
    if max_events < 1:
        raise ValueError("max_events must be greater than 0")
    if max_files < 1:
        raise ValueError("max_files must be greater than 0")
    if max_bytes < 1:
        raise ValueError("max_bytes must be greater than 0")
    if audit_limit < 1:
        raise ValueError("audit_limit must be greater than 0")

    root = _source_root(service, selected_root_id)
    root_path = Path(str(root.get("absolute_path") or root.get("path") or "")).expanduser()
    if not root_path.is_dir():
        raise ValueError(f"source root is not readable: {root_path}")
    root_path = root_path.resolve(strict=False)
    started_at = utc_now_iso()

    unavailable = _watchdog_unavailable_result(
        root=root,
        root_path=root_path,
        started_at=started_at,
        duration_seconds=duration_seconds,
        quiet_seconds=quiet_seconds,
        max_events=max_events,
    )
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        _add_watch_audit(service, unavailable)
        return unavailable

    event_signal = threading.Event()
    lock = threading.Lock()
    events: list[dict[str, Any]] = []
    event_keys: set[tuple[str, str, str]] = set()
    last_event_at = {"value": 0.0}

    class _Handler(FileSystemEventHandler):
        def on_any_event(self, event: Any) -> None:
            if bool(getattr(event, "is_directory", False)):
                return
            recorded = _normalize_watchdog_event(event, root_path=root_path)
            if not recorded:
                return
            key = (
                recorded["event_type"],
                recorded["relative_path"],
                recorded.get("dest_relative_path", ""),
            )
            with lock:
                if key in event_keys or len(events) >= max_events:
                    return
                event_keys.add(key)
                events.append(recorded)
                last_event_at["value"] = time.monotonic()
            event_signal.set()

    observer = Observer()
    observer.schedule(_Handler(), str(root_path), recursive=bool(recursive))
    observer.start()
    try:
        _wait_for_events(
            event_signal,
            events,
            last_event_at,
            duration_seconds=float(duration_seconds),
            quiet_seconds=float(quiet_seconds),
        )
    finally:
        observer.stop()
        observer.join()

    with lock:
        recorded_events = list(events)

    created_jobs = _created_jobs(
        service,
        root=root,
        root_id=selected_root_id,
        events=recorded_events,
        enqueue_extraction=enqueue_extraction,
        enqueue_audit=enqueue_audit,
        label=label,
        priority=priority,
        extractor=extractor,
        max_files=max_files,
        max_bytes=max_bytes,
        audit_limit=audit_limit,
    )
    result = {
        "schema": SOURCE_WATCH_ONCE_SCHEMA,
        "status": "changed" if recorded_events else "no_changes",
        "root_id": selected_root_id,
        "root": _root_summary(root),
        "root_path": str(root_path),
        "started_at": started_at,
        "duration_seconds": float(duration_seconds),
        "quiet_seconds": float(quiet_seconds),
        "recursive": bool(recursive),
        "event_count": len(recorded_events),
        "events": recorded_events,
        "truncated": len(recorded_events) >= max_events,
        "created_jobs": created_jobs,
        "next_actions": _job_next_actions(created_jobs),
        "data_flow": _watch_data_flow(),
    }
    _add_watch_audit(service, result)
    return result


def _source_root(service: WorkflowService, root_id: str) -> dict[str, Any]:
    for root in service.source_root_list():
        if str(root.get("root_id") or "") == root_id:
            return dict(root)
    raise ValueError(f"source root not found: {root_id}")


def _normalize_watchdog_event(event: Any, *, root_path: Path) -> dict[str, Any] | None:
    source_path = _relative_event_path(str(getattr(event, "src_path", "") or ""), root_path=root_path)
    if not source_path:
        return None
    dest_path = _relative_event_path(str(getattr(event, "dest_path", "") or ""), root_path=root_path)
    payload = {
        "event_type": str(getattr(event, "event_type", "") or "modified"),
        "relative_path": source_path,
        "observed_at": utc_now_iso(),
    }
    if dest_path and dest_path != source_path:
        payload["dest_relative_path"] = dest_path
    return payload


def _relative_event_path(raw_path: str, *, root_path: Path) -> str:
    if not raw_path:
        return ""
    path = Path(raw_path).expanduser().resolve(strict=False)
    try:
        relative = path.relative_to(root_path).as_posix()
    except ValueError:
        return ""
    parts = [part for part in relative.split("/") if part]
    if not parts:
        return ""
    if parts[-1] in _IGNORED_FILENAMES:
        return ""
    if any(part in _IGNORED_PATH_PARTS for part in parts):
        return ""
    return "/".join(parts)


def _wait_for_events(
    event_signal: threading.Event,
    events: list[dict[str, Any]],
    last_event_at: dict[str, float],
    *,
    duration_seconds: float,
    quiet_seconds: float,
) -> None:
    deadline = time.monotonic() + max(0.0, duration_seconds)
    if duration_seconds == 0:
        return
    while True:
        now = time.monotonic()
        remaining = deadline - now
        if remaining <= 0:
            return
        wait_for = min(remaining, max(quiet_seconds, 0.05) if quiet_seconds else remaining)
        event_signal.wait(wait_for)
        event_signal.clear()
        if not events or quiet_seconds <= 0:
            continue
        if time.monotonic() - last_event_at.get("value", 0.0) >= quiet_seconds:
            return


def _created_jobs(
    service: WorkflowService,
    *,
    root: dict[str, Any],
    root_id: str,
    events: list[dict[str, Any]],
    enqueue_extraction: bool,
    enqueue_audit: bool,
    label: str,
    priority: int,
    extractor: str,
    max_files: int,
    max_bytes: int,
    audit_limit: int,
) -> dict[str, Any]:
    if not events:
        return {}
    root_label = str(root.get("label") or root_id)
    selected_label = label.strip() if label else f"Watch update: {root_label}"
    jobs: dict[str, Any] = {}
    if enqueue_extraction:
        jobs["extraction"] = enqueue_source_extraction_job(
            service,
            root_id=root_id,
            label=f"{selected_label} extraction",
            priority=priority,
            max_files=max_files,
            max_bytes=max_bytes,
            extractor=extractor,
        )
    if enqueue_audit:
        jobs["audit"] = enqueue_source_audit_job(
            service,
            scope={"root_ids": [root_id]},
            label=f"{selected_label} audit",
            priority=priority,
            limit=audit_limit,
        )
    return to_jsonable(jobs)


def _job_next_actions(created_jobs: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for job in created_jobs.values():
        for action in list(job.get("next_actions") or []):
            actions.append(dict(action))
    return actions


def _watchdog_unavailable_result(
    *,
    root: dict[str, Any],
    root_path: Path,
    started_at: str,
    duration_seconds: float,
    quiet_seconds: float,
    max_events: int,
) -> dict[str, Any]:
    return {
        "schema": SOURCE_WATCH_ONCE_SCHEMA,
        "status": "unavailable",
        "root_id": str(root.get("root_id") or ""),
        "root": _root_summary(root),
        "root_path": str(root_path),
        "started_at": started_at,
        "duration_seconds": float(duration_seconds),
        "quiet_seconds": float(quiet_seconds),
        "event_count": 0,
        "events": [],
        "truncated": False,
        "created_jobs": {},
        "next_actions": [
            {
                "action": "install_watchdog_extra",
                "label": "Install watchdog extra",
                "command": "python -m pip install '.[watch]'",
                "view": "operator",
            }
        ],
        "adapter": {
            "name": "watchdog_tick",
            "provider": "watchdog",
            "status": "missing",
            "extra": "watch",
            "max_events": int(max_events),
        },
        "data_flow": _watch_data_flow(),
    }


def _root_summary(root: dict[str, Any]) -> dict[str, Any]:
    return {
        "root_id": str(root.get("root_id") or ""),
        "label": str(root.get("label") or ""),
        "kind": str(root.get("kind") or ""),
        "permission_mode": str(root.get("permission_mode") or ""),
        "active_object_count": int(root.get("active_object_count") or 0),
    }


def _watch_data_flow() -> dict[str, Any]:
    return {
        "watches_authorized_root_only": True,
        "writes_source_files": False,
        "writes_memory_directly": False,
        "writes_job_metadata": True,
        "queues_jobs_only": True,
        "embedding_required": False,
    }


def _add_watch_audit(service: WorkflowService, result: dict[str, Any]) -> None:
    service.store.add_audit_event(
        audit_event(
            "source.watch_once",
            "source_root",
            str(result.get("root_id") or ""),
            status=str(result.get("status") or ""),
            event_count=int(result.get("event_count") or 0),
            created_job_ids=_created_job_ids(result.get("created_jobs") or {}),
            data_flow=result.get("data_flow") or {},
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )


def _created_job_ids(created_jobs: dict[str, Any]) -> dict[str, str]:
    ids: dict[str, str] = {}
    for key, job in created_jobs.items():
        run_id = str((job.get("job") or {}).get("run_id") or "")
        if run_id:
            ids[str(key)] = run_id
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Watch one registered PSKA source root for a bounded interval and enqueue source jobs.",
        parents=[env_file_arg_parser()],
    )
    parser.add_argument("root_id")
    parser.add_argument("--duration-seconds", type=float, default=5.0)
    parser.add_argument("--quiet-seconds", type=float, default=0.25)
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--recursive", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enqueue-extraction", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--enqueue-audit", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--label", default="")
    parser.add_argument("--priority", type=int, default=0)
    parser.add_argument("--extractor", default="auto")
    parser.add_argument("--max-files", type=int, default=1000)
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    parser.add_argument("--audit-limit", type=int, default=20)
    args = parser.parse_args(argv)
    if args.env_file:
        load_env_file(args.env_file)
    result = watch_source_once(
        build_service_from_env(),
        root_id=args.root_id,
        duration_seconds=args.duration_seconds,
        quiet_seconds=args.quiet_seconds,
        max_events=args.max_events,
        recursive=args.recursive,
        enqueue_extraction=args.enqueue_extraction,
        enqueue_audit=args.enqueue_audit,
        label=args.label,
        priority=args.priority,
        extractor=args.extractor,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        audit_limit=args.audit_limit,
    )
    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    return 2 if result.get("status") == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
