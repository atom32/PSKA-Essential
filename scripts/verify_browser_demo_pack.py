#!/usr/bin/env python3
"""Verify the PSKA WebUI browser demo package."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "pska_webui_demo"
DIST_DIR = DEMO_DIR / "dist"


@dataclass(frozen=True)
class VideoExpectation:
    path: Path
    min_duration: float
    max_duration: float
    require_audio: bool
    label: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    args = parser.parse_args()

    demo_dir = args.demo_dir.resolve()
    dist_dir = demo_dir / "dist"
    checks: list[str] = []

    require_files(
        [
            demo_dir / "README.zh.md",
            demo_dir / "JIANYING_IMPORT.zh.md",
            demo_dir / "DEMO_PACKAGE.zh.md",
            demo_dir / "FEATURE_EVIDENCE_MATRIX.zh.md",
            demo_dir / "report.html",
            demo_dir / "demo_plan.json",
            demo_dir / "source" / "pska-demo-note.md",
            *[demo_dir / "capture" / f"{index:02d}_{name}.png" for index, name in enumerate(CAPTURE_NAMES)],
            *[dist_dir / "posters" / name for name in POSTER_NAMES],
            dist_dir / "pska_webui_browser_demo.mp4",
            dist_dir / "pska_webui_browser_demo.zh.srt",
            dist_dir / "storyboard.zh.md",
            dist_dir / "voiceover.zh.md",
            dist_dir / "pska_webui_browser_recording.mp4",
            dist_dir / "pska_webui_browser_recording.zh.srt",
            dist_dir / "playwright_recording_manifest.json",
            dist_dir / "playwright_storyboard.zh.md",
            dist_dir / "pska_webui_browser_recording_narrated.mp4",
            dist_dir / "pska_webui_browser_recording_narrated.zh.srt",
            dist_dir / "playwright_narrated_manifest.json",
            dist_dir / "playwright_narrated_storyboard.zh.md",
            dist_dir / "playwright_narrated_voiceover.zh.md",
        ],
        checks,
    )

    videos = [
        VideoExpectation(dist_dir / "pska_webui_browser_demo.mp4", 100.0, 180.0, True, "screenshot replay"),
        VideoExpectation(dist_dir / "pska_webui_browser_recording.mp4", 30.0, 60.0, False, "real browser recording"),
        VideoExpectation(dist_dir / "pska_webui_browser_recording_narrated.mp4", 120.0, 180.0, True, "narrated real browser cut"),
    ]
    durations: dict[Path, float] = {}
    for expectation in videos:
        media = verify_video(expectation, checks)
        durations[expectation.path] = media["duration"]

    for poster_name in POSTER_NAMES:
        verify_image(dist_dir / "posters" / poster_name, checks)

    verify_srt(dist_dir / "pska_webui_browser_demo.zh.srt", durations[dist_dir / "pska_webui_browser_demo.mp4"], checks)
    verify_srt(
        dist_dir / "pska_webui_browser_recording.zh.srt",
        durations[dist_dir / "pska_webui_browser_recording.mp4"],
        checks,
    )
    verify_srt(
        dist_dir / "pska_webui_browser_recording_narrated.zh.srt",
        durations[dist_dir / "pska_webui_browser_recording_narrated.mp4"],
        checks,
    )
    verify_playwright_manifest(dist_dir / "playwright_recording_manifest.json", checks, narrated=False)
    verify_playwright_manifest(dist_dir / "playwright_narrated_manifest.json", checks, narrated=True)
    verify_markdown_references(demo_dir / "README.zh.md", demo_dir, checks)
    verify_markdown_references(demo_dir / "JIANYING_IMPORT.zh.md", demo_dir, checks)
    verify_markdown_references(demo_dir / "DEMO_PACKAGE.zh.md", demo_dir, checks)
    verify_markdown_references(demo_dir / "FEATURE_EVIDENCE_MATRIX.zh.md", demo_dir, checks)
    verify_html_references(demo_dir / "report.html", demo_dir, checks)

    print("PSKA browser demo package verification passed:")
    for check in checks:
        print(f"- {check}")
    return 0


CAPTURE_NAMES = [
    ("home"),
    ("context_brief"),
    ("ask_prefill"),
    ("ask_result"),
    ("ask_result_brief"),
    ("loop_trace"),
    ("memory_cards"),
    ("activity_trace"),
    ("sources"),
    ("sources_search"),
]

POSTER_NAMES = [
    "01_context_brief.png",
    "02_sourced_brief.png",
    "03_source_search.png",
]

OPTIONAL_GENERATED_REFERENCES = {
    "dist/pska_webui_demo_package.zip",
    "dist/pska_webui_demo_package_manifest.json",
}


def require_files(paths: list[Path], checks: list[str]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        formatted = "\n".join(str(path) for path in missing)
        raise SystemExit(f"missing required demo package files:\n{formatted}")
    checks.append(f"{len(paths)} required files exist")


def verify_video(expectation: VideoExpectation, checks: list[str]) -> dict[str, Any]:
    payload = ffprobe(expectation.path)
    streams = payload.get("streams") or []
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        raise SystemExit(f"{expectation.path} has no video stream")
    first_video = video_streams[0]
    width = int(first_video.get("width") or 0)
    height = int(first_video.get("height") or 0)
    if (width, height) != (1280, 720):
        raise SystemExit(f"{expectation.path} expected 1280x720, got {width}x{height}")
    if expectation.require_audio and not audio_streams:
        raise SystemExit(f"{expectation.path} expected an audio stream")
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if not expectation.min_duration <= duration <= expectation.max_duration:
        raise SystemExit(
            f"{expectation.path} duration {duration:.3f}s outside "
            f"{expectation.min_duration:.1f}-{expectation.max_duration:.1f}s"
        )
    checks.append(
        f"{expectation.label}: {duration:.1f}s, {width}x{height}, "
        f"audio={'yes' if audio_streams else 'no'}"
    )
    return {"duration": duration, "audio_streams": len(audio_streams), "video_streams": len(video_streams)}


def verify_image(path: Path, checks: list[str]) -> None:
    payload = ffprobe(path)
    streams = payload.get("streams") or []
    if not streams:
        raise SystemExit(f"{path} has no image stream")
    stream = streams[0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if (width, height) != (1280, 720):
        raise SystemExit(f"{path} expected 1280x720, got {width}x{height}")
    checks.append(f"{path.name}: poster is {width}x{height}")


def ffprobe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_type,codec_name,width,height",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def verify_srt(path: Path, video_duration: float, checks: list[str]) -> None:
    blocks = parse_srt(path.read_text(encoding="utf-8"))
    if len(blocks) != 10:
        raise SystemExit(f"{path} expected 10 subtitle blocks, got {len(blocks)}")
    previous_end = -1.0
    for index, (start, end, text) in enumerate(blocks, start=1):
        if start < previous_end - 0.05:
            raise SystemExit(f"{path} subtitle {index} starts before previous block ends")
        if end <= start:
            raise SystemExit(f"{path} subtitle {index} has invalid time range")
        if not text.strip():
            raise SystemExit(f"{path} subtitle {index} is empty")
        previous_end = end
    if blocks[-1][1] > video_duration + 5.0:
        raise SystemExit(f"{path} subtitle end exceeds video duration by more than 5s")
    checks.append(f"{path.name}: 10 ordered subtitle blocks")


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    blocks = []
    for raw in re.split(r"\n\s*\n", text.strip()):
        lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        match = re.match(r"(.+?)\s+-->\s+(.+)", lines[1])
        if not match:
            raise SystemExit(f"invalid SRT timing line: {lines[1]}")
        blocks.append((srt_seconds(match.group(1)), srt_seconds(match.group(2)), "\n".join(lines[2:])))
    return blocks


def srt_seconds(value: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+),(\d+)", value.strip())
    if not match:
        raise SystemExit(f"invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = [int(item) for item in match.groups()]
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def verify_playwright_manifest(path: Path, checks: list[str], *, narrated: bool) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if narrated:
        required = ["schema", "source_recording", "mp4", "subtitles", "storyboard", "voiceover", "scale", "seed"]
    else:
        required = ["schema", "base_url", "seed", "mp4", "subtitles", "storyboard", "timeline"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise SystemExit(f"{path} missing keys: {', '.join(missing)}")
    seed = payload.get("seed") or {}
    for key in ["dataset_id", "document_id", "root_id", "memory_id"]:
        if not str(seed.get(key) or "").strip():
            raise SystemExit(f"{path} seed missing {key}")
    timeline = payload.get("timeline")
    if timeline is not None and len(timeline) != 10:
        raise SystemExit(f"{path} expected 10 timeline scenes, got {len(timeline)}")
    checks.append(f"{path.name}: manifest schema and seed complete")


def verify_markdown_references(path: Path, demo_dir: Path, checks: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    references = sorted(
        set(
            re.findall(
                r"`(dist/[^`]+|capture/[^`]+|source/[^`]+|[A-Za-z0-9_.-]+\.md|report\.html)`",
                text,
            )
        )
    )
    missing = [
        reference
        for reference in references
        if reference not in OPTIONAL_GENERATED_REFERENCES and not resolve_reference(reference, demo_dir).exists()
    ]
    if missing:
        raise SystemExit(f"{path} has missing referenced files: {', '.join(missing)}")
    checks.append(f"{path.name}: {len(references)} local references resolve")


def resolve_reference(reference: str, demo_dir: Path) -> Path:
    if reference.startswith("scripts/"):
        return ROOT / reference
    return demo_dir / reference


def verify_html_references(path: Path, demo_dir: Path, checks: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    references = sorted(
        set(
            match
            for match in re.findall(r"""(?:src|href)=["']([^"']+)["']""", text)
            if not re.match(r"^[a-z]+:", match) and not match.startswith("#")
        )
    )
    missing = [reference for reference in references if not (demo_dir / reference).exists()]
    if missing:
        raise SystemExit(f"{path} has missing referenced files: {', '.join(missing)}")
    checks.append(f"{path.name}: {len(references)} local references resolve")


if __name__ == "__main__":
    raise SystemExit(main())
