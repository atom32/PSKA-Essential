#!/usr/bin/env python3
"""Build a narrated cut from the PSKA diagnostic page Playwright recording."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "pska_webui_demo"
DIST_DIR = DEMO_DIR / "dist"
DEFAULT_MANIFEST = DIST_DIR / "playwright_recording_manifest.json"
DEFAULT_INPUT = DIST_DIR / "pska_webui_browser_recording.mp4"
DEFAULT_OUT = DIST_DIR / "pska_webui_browser_recording_narrated.mp4"


@dataclass
class AudioItem:
    kind: str
    duration: float
    path: Path
    scene: dict[str, Any] | None = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--voice", default="Tingting")
    parser.add_argument("--rate", default="176")
    parser.add_argument("--min-scale", type=float, default=1.85)
    parser.add_argument("--margin", type=float, default=0.65)
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    timeline = manifest.get("timeline") or []
    if not timeline:
        raise SystemExit("manifest has no timeline")

    output = args.output
    out_dir = output.parent
    build_dir = out_dir / "narrated-build"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    source_duration = ffprobe_duration(args.input)
    voice_segments = render_voice_segments(timeline, build_dir, voice=args.voice, rate=args.rate)
    scale = required_scale(timeline, voice_segments, args.min_scale, args.margin)
    scaled_duration = source_duration * scale

    audio_path = build_dir / "narration.wav"
    build_audio_track(
        timeline=timeline,
        voice_segments=voice_segments,
        build_dir=build_dir,
        output=audio_path,
        scale=scale,
        source_duration=source_duration,
        margin=args.margin,
    )
    mux_video_audio(args.input, audio_path, output, scale=scale)

    srt_path = output.with_suffix(".zh.srt")
    write_srt(timeline, srt_path, scale=scale)
    storyboard_path = out_dir / "playwright_narrated_storyboard.zh.md"
    write_storyboard(timeline, storyboard_path, scale=scale)
    voiceover_path = out_dir / "playwright_narrated_voiceover.zh.md"
    write_voiceover(timeline, voiceover_path)
    manifest_path = out_dir / "playwright_narrated_manifest.json"
    write_manifest(
        source_manifest=manifest,
        path=manifest_path,
        output=output,
        srt_path=srt_path,
        storyboard_path=storyboard_path,
        voiceover_path=voiceover_path,
        scale=scale,
        source_duration=source_duration,
        scaled_duration=scaled_duration,
        voice=args.voice,
        rate=args.rate,
    )

    if not args.keep_build:
        shutil.rmtree(build_dir, ignore_errors=True)

    print(f"video: {output}")
    print(f"subtitles: {srt_path}")
    print(f"storyboard: {storyboard_path}")
    print(f"voiceover: {voiceover_path}")
    print(f"manifest: {manifest_path}")
    print(f"scale: {scale:.3f}")
    return 0


def render_voice_segments(timeline: list[dict[str, Any]], build_dir: Path, *, voice: str, rate: str) -> list[AudioItem]:
    say = shutil.which("say")
    if not say:
        raise SystemExit("macOS say is required to build the narrated cut")
    items: list[AudioItem] = []
    for index, scene in enumerate(timeline, start=1):
        path = build_dir / f"{index:02d}_{scene['id']}.aiff"
        text = str(scene.get("narration") or scene.get("caption") or scene.get("title") or "").strip()
        subprocess.run([say, "-v", voice, "-r", str(rate), "-o", str(path), text], check=True)
        items.append(AudioItem(kind="voice", duration=ffprobe_duration(path), path=path, scene=scene))
    return items


def required_scale(
    timeline: list[dict[str, Any]],
    voice_segments: list[AudioItem],
    min_scale: float,
    margin: float,
) -> float:
    scale = max(1.0, float(min_scale))
    for scene, voice in zip(timeline, voice_segments, strict=True):
        span = float(scene["endsAt"]) - float(scene["startsAt"])
        if span <= 0:
            continue
        scale = max(scale, (voice.duration + margin) / span)
    return round(scale, 3)


def build_audio_track(
    *,
    timeline: list[dict[str, Any]],
    voice_segments: list[AudioItem],
    build_dir: Path,
    output: Path,
    scale: float,
    source_duration: float,
    margin: float,
) -> None:
    parts: list[AudioItem] = []
    cursor = 0.0
    part_index = 1
    for scene, voice in zip(timeline, voice_segments, strict=True):
        start = float(scene["startsAt"])
        end = float(scene["endsAt"])
        if start > cursor:
            silence = build_dir / f"{part_index:02d}_gap.wav"
            render_silence(silence, (start - cursor) * scale)
            parts.append(AudioItem(kind="silence", duration=(start - cursor) * scale, path=silence))
            part_index += 1
        span = max(voice.duration + margin, (end - start) * scale)
        padded = build_dir / f"{part_index:02d}_{scene['id']}.wav"
        pad_audio(voice.path, padded, span)
        parts.append(AudioItem(kind="voice", duration=span, path=padded, scene=scene))
        part_index += 1
        cursor = end
    if source_duration > cursor:
        silence = build_dir / f"{part_index:02d}_tail.wav"
        render_silence(silence, (source_duration - cursor) * scale)
        parts.append(AudioItem(kind="silence", duration=(source_duration - cursor) * scale, path=silence))

    input_args: list[str] = []
    filter_inputs = []
    for index, item in enumerate(parts):
        input_args.extend(["-i", str(item.path)])
        filter_inputs.append(f"[{index}:a]")
    filter_complex = "".join(filter_inputs) + f"concat=n={len(parts)}:v=0:a=1[a]"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *input_args,
            "-filter_complex",
            filter_complex,
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


def render_silence(output: Path, duration: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-t",
            f"{max(0.05, duration):.3f}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


def pad_audio(input_path: Path, output: Path, duration: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-filter_complex",
            f"[0:a]apad=whole_dur={duration:.3f}[a]",
            "-map",
            "[a]",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(output),
        ],
        check=True,
    )


def mux_video_audio(input_video: Path, audio_path: Path, output: Path, *, scale: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_video),
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[0:v]setpts={scale:.3f}*PTS,format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )


def write_srt(timeline: list[dict[str, Any]], path: Path, *, scale: float) -> None:
    blocks = []
    for index, scene in enumerate(timeline, start=1):
        text = "\n".join(subtitle_lines(str(scene.get("caption") or ""), max_units=42))
        blocks.append(
            f"{index}\n{srt_time(float(scene['startsAt']) * scale)} --> {srt_time(float(scene['endsAt']) * scale)}\n{text}\n"
        )
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_storyboard(timeline: list[dict[str, Any]], path: Path, *, scale: float) -> None:
    lines = ["# PSKA Diagnostic Page Playwright Narrated Cut Storyboard", ""]
    for index, scene in enumerate(timeline, start=1):
        lines.extend(
            [
                f"## {index:02d}. {scene['title']}",
                "",
                f"Time: `{srt_time(float(scene['startsAt']) * scale).replace(',', '.')}` - `{srt_time(float(scene['endsAt']) * scale).replace(',', '.')}`",
                "",
                str(scene.get("caption") or ""),
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_voiceover(timeline: list[dict[str, Any]], path: Path) -> None:
    lines = ["# PSKA Diagnostic Page Playwright Narrated Cut Voiceover", "", "旁白来自真实浏览器录屏 timeline。", ""]
    for index, scene in enumerate(timeline, start=1):
        lines.extend([f"## {index:02d}. {scene['title']}", "", str(scene.get("narration") or scene.get("caption") or ""), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(
    *,
    source_manifest: dict[str, Any],
    path: Path,
    output: Path,
    srt_path: Path,
    storyboard_path: Path,
    voiceover_path: Path,
    scale: float,
    source_duration: float,
    scaled_duration: float,
    voice: str,
    rate: str,
) -> None:
    payload = {
        "schema": "pska.browser_playwright_narrated_cut.v1",
        "source_recording_manifest": "demo/browser/pska_webui_demo/dist/playwright_recording_manifest.json",
        "source_recording": source_manifest.get("mp4"),
        "mp4": str(output.relative_to(ROOT)),
        "subtitles": str(srt_path.relative_to(ROOT)),
        "storyboard": str(storyboard_path.relative_to(ROOT)),
        "voiceover": str(voiceover_path.relative_to(ROOT)),
        "scale": scale,
        "source_duration_seconds": round(source_duration, 3),
        "duration_seconds": round(scaled_duration, 3),
        "voice": voice,
        "rate": str(rate),
        "seed": source_manifest.get("seed") or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def subtitle_lines(text: str, *, max_units: int) -> list[str]:
    tokens = subtitle_tokens(text)
    lines: list[str] = []
    current = ""
    current_width = 0
    for token in tokens:
        token_width = display_width(token)
        if token.isspace():
            if current and not current.endswith(" "):
                current += " "
                current_width += 1
            continue
        if current and current_width + token_width > max_units:
            lines.append(current.rstrip())
            current = ""
            current_width = 0
        current += token
        current_width += token_width
    if current:
        lines.append(current.rstrip())
    return lines


def subtitle_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    ascii_token = ""
    for char in text:
        if char.isspace():
            if ascii_token:
                tokens.append(ascii_token)
                ascii_token = ""
            tokens.append(" ")
        elif ord(char) < 128 and (char.isalnum() or char in "_.-"):
            ascii_token += char
        else:
            if ascii_token:
                tokens.append(ascii_token)
                ascii_token = ""
            tokens.append(char)
    if ascii_token:
        tokens.append(ascii_token)
    return tokens


def display_width(text: str) -> int:
    return sum(1 if ord(char) < 128 else 2 for char in text)


def srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


if __name__ == "__main__":
    raise SystemExit(main())
