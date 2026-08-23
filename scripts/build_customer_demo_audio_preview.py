#!/usr/bin/env python3
"""Build an optional spoken preview for the customer demo video.

This uses macOS `say` to read the plain Chinese subtitle text. The resulting
video is for quick customer preview only; the no-audio master remains the
editing source of record.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "hermes_pska_extension_demo"
DEFAULT_BASENAME = "hermes_pska_customer_walkthrough_demo"


class CaptionBlock(NamedTuple):
    start: float
    end: float
    text: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--voice", default="Tingting")
    parser.add_argument("--rate", type=int, default=130)
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()

    ensure_say_available()
    demo_dir = args.demo_dir.resolve()
    dist_dir = demo_dir / "dist"
    basename = str(args.basename)
    video_path = dist_dir / f"{basename}_subtitled.mp4"
    subtitle_path = dist_dir / f"{basename}.zh.srt"
    output_audio = dist_dir / f"{basename}_voiceover_preview.m4a"
    output_video = dist_dir / f"{basename}_subtitled_voiceover.mp4"
    build_dir = dist_dir / f"{basename}_audio_preview_build"
    build_dir.mkdir(parents=True, exist_ok=True)

    if not video_path.exists():
        raise SystemExit(f"missing hard-subtitled video: {video_path}")
    if not subtitle_path.exists():
        raise SystemExit(f"missing subtitle file: {subtitle_path}")

    blocks = parse_srt(subtitle_path.read_text(encoding="utf-8"))
    if not blocks:
        raise SystemExit(f"no subtitle blocks found: {subtitle_path}")

    video_duration = ffprobe_duration(video_path)
    audio_segments = build_audio_segments(blocks, video_duration, build_dir, args.voice, args.rate)
    concat_audio(audio_segments, build_dir / "audio_concat.txt", output_audio)
    mux_audio(video_path, output_audio, output_video)
    write_audio_manifest(output_audio, output_video, subtitle_path, video_duration, blocks, args.voice, args.rate)

    if not args.keep_build:
        shutil.rmtree(build_dir, ignore_errors=True)

    print(f"audio: {output_audio}")
    print(f"video: {output_video}")
    return 0


def ensure_say_available() -> None:
    if not shutil.which("say"):
        raise SystemExit("macOS say command is required for the optional customer audio preview")


def parse_srt(text: str) -> list[CaptionBlock]:
    blocks: list[CaptionBlock] = []
    for raw_block in text.strip().split("\n\n"):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [part.strip() for part in lines[1].split("-->", 1)]
        blocks.append(CaptionBlock(start=srt_seconds(start_raw), end=srt_seconds(end_raw), text=" ".join(lines[2:])))
    return blocks


def srt_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":", 2)
    seconds, millis = rest.split(",", 1)
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def build_audio_segments(
    blocks: list[CaptionBlock],
    video_duration: float,
    build_dir: Path,
    voice: str,
    rate: int,
) -> list[Path]:
    segments: list[Path] = []
    cursor = 0.0
    for index, block in enumerate(blocks, start=1):
        if block.start > cursor + 0.05:
            gap_path = build_dir / f"segment_{index:02d}_gap.wav"
            write_silence(block.start - cursor, gap_path)
            segments.append(gap_path)

        raw_path = build_dir / f"segment_{index:02d}_raw.aiff"
        segment_path = build_dir / f"segment_{index:02d}_speech.wav"
        run(["say", "-v", voice, "-r", str(rate), "-o", str(raw_path), block.text])
        normalize_speech_segment(raw_path, max(0.1, block.end - block.start), segment_path)
        segments.append(segment_path)
        cursor = block.end

    if video_duration > cursor + 0.05:
        tail_path = build_dir / "segment_tail.wav"
        write_silence(video_duration - cursor, tail_path)
        segments.append(tail_path)
    return segments


def normalize_speech_segment(raw_path: Path, target_duration: float, output_path: Path) -> None:
    raw_duration = ffprobe_duration(raw_path)
    filters: list[str] = []
    if raw_duration > target_duration:
        filters.extend(atempo_filters(raw_duration / target_duration))
    elif raw_duration > target_duration * 0.75:
        filters.extend(atempo_filters(raw_duration / target_duration))
    filters.extend(["apad", f"atrim=0:{target_duration:.3f}", "asetpts=N/SR/TB"])
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(raw_path),
            "-af",
            ",".join(filters),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def write_silence(duration: float, output_path: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def concat_audio(segments: list[Path], list_path: Path, output_audio: Path) -> None:
    list_path.write_text("".join(f"file '{escape_concat_path(path)}'\n" for path in segments), encoding="utf-8")
    intermediate = output_audio.with_suffix(".wav")
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(intermediate),
        ]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(intermediate),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(output_audio),
        ]
    )


def mux_audio(video_path: Path, audio_path: Path, output_video: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-shortest",
            str(output_video),
        ]
    )


def atempo_filters(factor: float) -> list[str]:
    if factor <= 0:
        raise ValueError("tempo factor must be positive")
    filters: list[str] = []
    while factor > 2.0:
        filters.append("atempo=2.000000")
        factor /= 2.0
    while factor < 0.5:
        filters.append("atempo=0.500000")
        factor /= 0.5
    filters.append(f"atempo={factor:.6f}")
    return filters


def write_audio_manifest(
    output_audio: Path,
    output_video: Path,
    subtitle_path: Path,
    video_duration: float,
    blocks: list[CaptionBlock],
    voice: str,
    rate: int,
) -> None:
    payload = {
        "schema": "pska.customer_demo_audio_preview.v1",
        "audio": str(output_audio.relative_to(ROOT)),
        "video": str(output_video.relative_to(ROOT)),
        "subtitles": str(subtitle_path.relative_to(ROOT)),
        "source": "subtitle_text",
        "voice": voice,
        "rate": rate,
        "video_duration": video_duration,
        "caption_blocks": len(blocks),
        "purpose": "customer_quick_preview_with_machine_voice",
    }
    manifest_path = output_video.with_name(output_video.stem + "_manifest.json")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def escape_concat_path(path: Path) -> str:
    return str(path).replace("'", "'\\''")


def ffprobe_duration(path: Path) -> float:
    raw = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(raw)


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
