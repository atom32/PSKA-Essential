from __future__ import annotations

import builtins
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.mcp_server import tool_registry
from pska_essential.source_watch import watch_source_once
from pska_essential.workflow import build_fake_service


class SourceWatchTests(unittest.TestCase):
    def test_watch_source_once_enqueues_jobs_from_authorized_root_event(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            root = service.source_root_register(root_path)
            with _fake_watchdog_modules(root_path / "New.md"):
                result = watch_source_once(
                    service,
                    root_id=root["root_id"],
                    duration_seconds=0,
                    enqueue_extraction=True,
                    enqueue_audit=True,
                    label="Watch smoke",
                    max_files=10,
                    audit_limit=10,
                )

        self.assertEqual(result["schema"], "pska.source_watch_once.v1")
        self.assertEqual(result["status"], "changed")
        self.assertEqual(result["event_count"], 1)
        self.assertEqual(result["events"][0]["relative_path"], "New.md")
        self.assertIn("extraction", result["created_jobs"])
        self.assertIn("audit", result["created_jobs"])
        self.assertEqual(result["next_actions"][0]["tool"], "pska_source_extract_job_run")
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertTrue(result["data_flow"]["queues_jobs_only"])
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("source.watch_once", actions)
        self.assertIn("source.extraction_job.enqueue", actions)
        self.assertIn("source.audit_job.enqueue", actions)

    def test_watch_source_once_reports_missing_optional_dependency(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            root = service.source_root_register(root_path)
            original_import = builtins.__import__

            def _blocked_import(name, *args, **kwargs):
                if name == "watchdog" or name.startswith("watchdog."):
                    raise ImportError("watchdog missing for test")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=_blocked_import):
                result = watch_source_once(service, root_id=root["root_id"], duration_seconds=0)

        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["adapter"]["name"], "watchdog_tick")
        self.assertIn("python -m pip install '.[watch]'", result["next_actions"][0]["command"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])

    def test_mcp_source_watch_once_tool_queues_extraction_job(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            root = tools["pska_source_root_register"](str(root_path))
            with _fake_watchdog_modules(root_path / "Daily.md"):
                result = tools["pska_source_watch_once"](
                    root["root_id"],
                    duration_seconds=0,
                    enqueue_extraction=True,
                    enqueue_audit=False,
                )

        self.assertEqual(result["status"], "changed")
        self.assertIn("extraction", result["created_jobs"])
        self.assertNotIn("audit", result["created_jobs"])


class _FakeWatchdogEvent:
    event_type = "created"
    is_directory = False

    def __init__(self, src_path: Path):
        self.src_path = str(src_path)


class _FakeWatchdogObserver:
    def __init__(self, event_path: Path):
        self.event_path = event_path
        self.handler = None

    def schedule(self, handler, path, recursive=True):
        self.handler = handler

    def start(self):
        if self.handler is not None:
            self.handler.on_any_event(_FakeWatchdogEvent(self.event_path))

    def stop(self):
        return None

    def join(self):
        return None


class _FakeWatchdogModules:
    def __init__(self, event_path: Path):
        self.event_path = event_path
        self.patcher = None

    def __enter__(self):
        watchdog_pkg = types.ModuleType("watchdog")
        watchdog_pkg.__path__ = []
        events_mod = types.ModuleType("watchdog.events")
        observers_mod = types.ModuleType("watchdog.observers")

        class FileSystemEventHandler:
            def on_any_event(self, event):
                return None

        event_path = self.event_path

        class Observer(_FakeWatchdogObserver):
            def __init__(self):
                super().__init__(event_path)

        events_mod.FileSystemEventHandler = FileSystemEventHandler
        observers_mod.Observer = Observer
        self.patcher = patch.dict(
            sys.modules,
            {
                "watchdog": watchdog_pkg,
                "watchdog.events": events_mod,
                "watchdog.observers": observers_mod,
            },
        )
        self.patcher.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.patcher is not None:
            self.patcher.__exit__(exc_type, exc, tb)


def _fake_watchdog_modules(event_path: Path) -> _FakeWatchdogModules:
    return _FakeWatchdogModules(event_path)


if __name__ == "__main__":
    unittest.main()
