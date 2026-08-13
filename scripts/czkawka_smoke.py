from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pska_essential.contracts import to_jsonable
from pska_essential.dedup import czkawka_command_path
from pska_essential.workflow import build_fake_service


def main() -> int:
    service = build_fake_service()
    with TemporaryDirectory(prefix="pska-czkawka-smoke-") as temp_dir:
        root_path = Path(temp_dir) / "DuplicateRoot"
        root_path.mkdir()
        text = "# Same\n\nCzkawka should report this duplicate content.\n"
        (root_path / "a.md").write_text(text, encoding="utf-8")
        (root_path / "b.md").write_text(text, encoding="utf-8")
        (root_path / "unique.md").write_text("# Unique\n\nNo duplicate here.\n", encoding="utf-8")

        root = service.source_root_register(root_path, label="czkawka smoke root")
        scan = service.source_scan(root["root_id"], max_files=10, extractor="auto")
        report = service.duplicate_report({"root_ids": [root["root_id"]]}, mode="czkawka_hash", limit=10)

    payload = {
        "status": report["status"],
        "provider": report["provider"],
        "czkawka_path": czkawka_command_path() or "",
        "scan_counts": scan["counts"],
        "group_count": report["group_count"],
        "duplicate_file_count": report["duplicate_file_count"],
        "data_flow": report["data_flow"],
        "message": report.get("message") or "",
    }
    print(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, sort_keys=True))

    if report["status"] == "unavailable":
        return 77
    if report["status"] != "ok":
        raise SystemExit(f"expected ok Czkawka report, got {report['status']}: {report.get('message') or ''}")
    if report["group_count"] < 1:
        raise SystemExit("expected at least one duplicate group")
    if report["duplicate_file_count"] < 1:
        raise SystemExit("expected at least one duplicate file")
    if report["data_flow"]["writes_source_files"]:
        raise SystemExit("Czkawka smoke must not write source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
