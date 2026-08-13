from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pska_essential.contracts import to_jsonable
from pska_essential.source_watch import watch_source_once
from pska_essential.workflow import build_fake_service


def main() -> int:
    service = build_fake_service()
    with TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir) / "WatchRoot"
        root_path.mkdir()
        root = service.source_root_register(root_path, label="watchdog smoke root")

        def writer() -> None:
            time.sleep(1.0)
            (root_path / "Inbox.md").write_text(
                "# Inbox\n\nwatchdog smoke should queue PSKA source jobs.\n",
                encoding="utf-8",
            )

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        result = watch_source_once(
            service,
            root_id=root["root_id"],
            duration_seconds=4.0,
            quiet_seconds=0.5,
            enqueue_extraction=True,
            enqueue_audit=True,
            label="watchdog smoke",
            max_files=10,
            audit_limit=10,
        )
        thread.join(timeout=2.0)

    print(json.dumps(to_jsonable(result), ensure_ascii=False, indent=2))
    if result["status"] != "changed":
        raise SystemExit(f"expected changed status, got {result['status']}")
    if result["event_count"] < 1:
        raise SystemExit("expected at least one watchdog event")
    if "extraction" not in result["created_jobs"] or "audit" not in result["created_jobs"]:
        raise SystemExit("expected both extraction and audit jobs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
