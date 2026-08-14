#!/usr/bin/env python3
"""Create a distributable PSKA WebUI browser demo package."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "pska_webui_demo"
DEFAULT_OUT = DEMO_DIR / "dist" / "pska_webui_demo_package.zip"
DEFAULT_MANIFEST_OUT = DEMO_DIR / "dist" / "pska_webui_demo_package_manifest.json"
ARCHIVE_ROOT = "pska_webui_demo"
FORBIDDEN_PARTS = {
    ".DS_Store",
    "__pycache__",
    "playwright-build",
}
FORBIDDEN_SUFFIXES = {
    "_raw.webm",
}


PACKAGE_FILES = [
    "README.zh.md",
    "DEMO_PACKAGE.zh.md",
    "FEATURE_EVIDENCE_MATRIX.zh.md",
    "JIANYING_IMPORT.zh.md",
    "report.html",
    "demo_plan.json",
    "source/pska-demo-note.md",
    "dist/pska_webui_browser_recording_narrated.mp4",
    "dist/pska_webui_browser_recording_narrated.zh.srt",
    "dist/playwright_narrated_manifest.json",
    "dist/playwright_narrated_storyboard.zh.md",
    "dist/playwright_narrated_voiceover.zh.md",
    "dist/pska_webui_browser_recording.mp4",
    "dist/pska_webui_browser_recording.zh.srt",
    "dist/playwright_recording_manifest.json",
    "dist/playwright_storyboard.zh.md",
    "dist/pska_webui_browser_demo.mp4",
    "dist/pska_webui_browser_demo.zh.srt",
    "dist/storyboard.zh.md",
    "dist/voiceover.zh.md",
    "dist/posters/01_context_brief.png",
    "dist/posters/02_sourced_brief.png",
    "dist/posters/03_source_search.png",
    *[f"capture/{index:02d}_{name}.png" for index, name in enumerate(
        [
            "home",
            "context_brief",
            "ask_prefill",
            "ask_result",
            "ask_result_brief",
            "loop_trace",
            "memory_cards",
            "activity_trace",
            "sources",
            "sources_search",
        ]
    )],
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--manifest-out", type=Path, default=DEFAULT_MANIFEST_OUT)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()

    demo_dir = args.demo_dir.resolve()
    archive_path = args.out.resolve()
    manifest_out = args.manifest_out.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.parent.mkdir(parents=True, exist_ok=True)

    if not args.skip_verify:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "verify_browser_demo_pack.py"),
                "--demo-dir",
                str(demo_dir),
            ],
            cwd=ROOT,
            check=True,
        )

    file_records = build_file_records(demo_dir, PACKAGE_FILES)
    manifest = {
        "schema": "pska.browser_demo_distribution_package.v1",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "archive_root": ARCHIVE_ROOT,
        "archive": str(archive_path.relative_to(ROOT)),
        "entrypoint": f"{ARCHIVE_ROOT}/report.html",
        "source_demo_dir": str(demo_dir.relative_to(ROOT)),
        "git_commit": git_commit(),
        "file_count": len(file_records),
        "files": file_records,
        "excluded": [
            "dist/playwright-build/",
            "dist/pska_webui_browser_recording_raw.webm",
            ".DS_Store",
            "__pycache__/",
        ],
    }

    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr(f"{ARCHIVE_ROOT}/PACKAGE_MANIFEST.json", manifest_text)
        for record in file_records:
            archive.write(demo_dir / record["path"], f"{ARCHIVE_ROOT}/{record['path']}")

    manifest_out.write_text(manifest_text + "\n", encoding="utf-8")
    verify_archive(archive_path, manifest)
    print(f"package: {archive_path}")
    print(f"manifest: {manifest_out}")
    print(f"files: {len(file_records)}")
    print(f"size: {archive_path.stat().st_size} bytes")
    return 0


def build_file_records(demo_dir: Path, relative_paths: list[str]) -> list[dict[str, Any]]:
    records = []
    missing = []
    seen = set()
    for relative in relative_paths:
        if relative in seen:
            continue
        seen.add(relative)
        path = demo_dir / relative
        if not path.exists():
            missing.append(relative)
            continue
        if path.is_dir():
            raise SystemExit(f"package entry must be a file, got directory: {relative}")
        records.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    if missing:
        raise SystemExit("missing package files:\n" + "\n".join(missing))
    return records


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def verify_archive(archive_path: Path, manifest: dict[str, Any]) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        if f"{ARCHIVE_ROOT}/report.html" not in names:
            raise SystemExit("package archive is missing report.html")
        if f"{ARCHIVE_ROOT}/PACKAGE_MANIFEST.json" not in names:
            raise SystemExit("package archive is missing PACKAGE_MANIFEST.json")
        for name in names:
            parts = set(Path(name).parts)
            if parts & FORBIDDEN_PARTS:
                raise SystemExit(f"package archive contains forbidden path: {name}")
            if any(name.endswith(suffix) for suffix in FORBIDDEN_SUFFIXES):
                raise SystemExit(f"package archive contains forbidden artifact: {name}")
        expected = {f"{ARCHIVE_ROOT}/{record['path']}" for record in manifest["files"]}
        missing = sorted(expected - names)
        if missing:
            raise SystemExit("package archive is missing manifest files:\n" + "\n".join(missing))


if __name__ == "__main__":
    raise SystemExit(main())
