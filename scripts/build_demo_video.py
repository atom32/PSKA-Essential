#!/usr/bin/env python3
"""Build the PSKA demo video pack from a JSON storyboard.

The generated MP4 is intentionally simple and reproducible: slide cards,
optional macOS narration through `say`, and an external SRT subtitle file.
It is meant as a first-pass demo asset that can later be replaced with real UI
screen recordings while keeping the same timing and narration contract.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "demo" / "video" / "pska_m30_demo" / "demo_plan.json"
DEFAULT_OUT = ROOT / "demo" / "video" / "pska_m30_demo" / "dist"
FONT_CANDIDATES = [
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
]
ACCENTS = [
    ("#0f2d2d", "#d9f2ee", "#54b6a8"),
    ("#172033", "#e8eef9", "#89a7ff"),
    ("#2a2636", "#f0eaf8", "#b99be9"),
    ("#33281e", "#f6eee5", "#d79b5f"),
    ("#263223", "#edf5e9", "#8fbe7e"),
    ("#1e2d35", "#e9f3f7", "#73b5d1"),
]


@dataclass
class SceneBuild:
    index: int
    scene: dict[str, Any]
    duration: float
    image_path: Path
    audio_path: Path | None
    segment_path: Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--voice", default=None, help="macOS say voice. Use 'none' to disable narration.")
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    width, height = plan.get("resolution") or [1280, 720]
    width = args.width or int(width)
    height = args.height or int(height)
    voice = args.voice if args.voice is not None else plan.get("voice", "Tingting")
    if str(voice).lower() in {"", "none", "silent", "false"}:
        voice = ""

    out_dir = args.out
    build_dir = out_dir / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    font_path = first_existing(FONT_CANDIDATES)
    title_font = ImageFont.truetype(str(font_path), 50)
    kicker_font = ImageFont.truetype(str(font_path), 24)
    body_font = ImageFont.truetype(str(font_path), 30)
    small_font = ImageFont.truetype(str(font_path), 20)
    mono_font = ImageFont.truetype(str(font_path), 22)

    builds: list[SceneBuild] = []
    for index, scene in enumerate(plan["scenes"], start=1):
        image_path = build_dir / f"{index:02d}_{scene['id']}.png"
        render_scene_card(
            image_path,
            plan=plan,
            scene=scene,
            index=index,
            total=len(plan["scenes"]),
            width=width,
            height=height,
            fonts=(title_font, kicker_font, body_font, small_font, mono_font),
        )
        audio_path = None
        duration = float(scene.get("duration") or 20)
        if voice:
            audio_path = build_dir / f"{index:02d}_{scene['id']}.aiff"
            run_say(scene["narration"], voice=voice, output=audio_path)
            measured = ffprobe_duration(audio_path)
            if measured:
                duration = max(duration, measured + 0.65)
        segment_path = build_dir / f"{index:02d}_{scene['id']}.mp4"
        render_segment(image_path, audio_path, segment_path, duration)
        builds.append(SceneBuild(index, scene, duration, image_path, audio_path, segment_path))

    final_mp4 = out_dir / "pska_m30_demo.mp4"
    concat_video([build.segment_path for build in builds], final_mp4, build_dir / "segments.txt")

    srt_path = out_dir / "pska_m30_demo.zh.srt"
    write_srt(builds, srt_path)
    write_storyboard(plan, builds, out_dir / "storyboard.zh.md")
    write_voiceover(plan, builds, out_dir / "voiceover.zh.md")

    if not args.keep_build:
        shutil.rmtree(build_dir, ignore_errors=True)

    print(f"video: {final_mp4}")
    print(f"subtitles: {srt_path}")
    print(f"storyboard: {out_dir / 'storyboard.zh.md'}")
    print(f"voiceover: {out_dir / 'voiceover.zh.md'}")
    return 0


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise SystemExit("No usable Chinese font found.")


def render_scene_card(
    path: Path,
    *,
    plan: dict[str, Any],
    scene: dict[str, Any],
    index: int,
    total: int,
    width: int,
    height: int,
    fonts: tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont, ImageFont.FreeTypeFont],
) -> None:
    title_font, kicker_font, body_font, small_font, mono_font = fonts
    bg, fg, accent = ACCENTS[(index - 1) % len(ACCENTS)]
    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((42, 38, width - 42, height - 38), radius=22, outline=accent, width=3)
    draw.rectangle((42, 38, 58, height - 38), fill=accent)
    draw.text((82, 66), f"{index:02d}/{total:02d}", font=small_font, fill=accent)
    draw.text((82, 96), scene["title"], font=title_font, fill=fg)
    draw.text((84, 160), scene.get("kicker", ""), font=kicker_font, fill=accent)

    bullet_y = 238
    for bullet in scene.get("bullets", []):
        lines = wrap_to_width(draw, bullet, body_font, width=680)
        draw.text((92, bullet_y + 5), "-", font=body_font, fill=accent)
        for line in lines:
            draw.text((130, bullet_y), line, font=body_font, fill=fg)
            bullet_y += 42
        bullet_y += 18

    panel_x = width - 390
    draw.rounded_rectangle((panel_x, 225, width - 82, height - 130), radius=18, fill=shade(bg, 1.18), outline=accent, width=2)
    draw.text((panel_x + 28, 250), "Demo Signal", font=kicker_font, fill=accent)
    chips = scene.get("chips", [])
    chip_y = 305
    for chip in chips:
        draw.rounded_rectangle((panel_x + 28, chip_y, width - 118, chip_y + 42), radius=20, fill=shade(bg, 1.35), outline=accent, width=1)
        draw.text((panel_x + 50, chip_y + 8), chip, font=small_font, fill=fg)
        chip_y += 58

    route = "User -> Hermes -> PSKA -> Source / Memory / Trace -> Review"
    draw.text((82, height - 104), route, font=mono_font, fill=accent)
    draw.text((82, height - 72), f"{plan['title']} | {plan.get('version', '')}", font=small_font, fill=fg)
    image.save(path)


def wrap_to_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= width or not current:
            current = candidate
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def shade(hex_color: str, factor: float) -> str:
    value = hex_color.lstrip("#")
    rgb = [int(value[i : i + 2], 16) for i in (0, 2, 4)]
    adjusted = [max(0, min(255, int(channel * factor))) for channel in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in adjusted)


def run_say(text: str, *, voice: str, output: Path) -> None:
    subprocess.run(["say", "-v", voice, "-r", "168", "-o", str(output), text], check=True)


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def render_segment(image_path: Path, audio_path: Path | None, segment_path: Path, duration: float) -> None:
    common = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(image_path),
    ]
    if audio_path:
        cmd = [
            *common,
            "-i",
            str(audio_path),
            "-filter_complex",
            f"[1:a]apad=whole_dur={duration:.3f}[a]",
            "-map",
            "0:v",
            "-map",
            "[a]",
        ]
    else:
        cmd = [
            *common,
            "-f",
            "lavfi",
            "-t",
            f"{duration:.3f}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map",
            "0:v",
            "-map",
            "1:a",
        ]
    cmd.extend(
        [
            "-t",
            f"{duration:.3f}",
            "-vf",
            "format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(segment_path),
        ]
    )
    subprocess.run(cmd, check=True)


def concat_video(segments: list[Path], final_mp4: Path, list_path: Path) -> None:
    list_path.write_text("".join(f"file '{segment}'\n" for segment in segments), encoding="utf-8")
    subprocess.run(
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
            str(final_mp4),
        ],
        check=True,
    )


def write_srt(builds: list[SceneBuild], path: Path) -> None:
    cursor = 0.0
    blocks: list[str] = []
    for build in builds:
        start = cursor
        end = cursor + build.duration
        text = "\n".join(subtitle_lines(build.scene["narration"], max_units=44))
        blocks.append(f"{build.index}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n")
        cursor = end
    path.write_text("\n".join(blocks), encoding="utf-8")


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
        elif ord(char) < 128 and char.isalnum():
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


def write_storyboard(plan: dict[str, Any], builds: list[SceneBuild], path: Path) -> None:
    lines = [f"# {plan['title']} Storyboard", "", f"Version: {plan.get('version', '')}", ""]
    cursor = 0.0
    for build in builds:
        start = srt_time(cursor).replace(",", ".")
        end = srt_time(cursor + build.duration).replace(",", ".")
        scene = build.scene
        lines.extend(
            [
                f"## {build.index:02d}. {scene['title']}",
                "",
                f"Time: `{start}` - `{end}`",
                f"Kicker: {scene.get('kicker', '')}",
                "",
                "Bullets:",
            ]
        )
        lines.extend([f"- {bullet}" for bullet in scene.get("bullets", [])])
        lines.extend(["", f"Narration: {scene['narration']}", ""])
        cursor += build.duration
    path.write_text("\n".join(lines), encoding="utf-8")


def write_voiceover(plan: dict[str, Any], builds: list[SceneBuild], path: Path) -> None:
    lines = [f"# {plan['title']} Voiceover", "", "旁白稿可直接用于重新录音或导入剪映。", ""]
    for build in builds:
        lines.extend([f"## {build.index:02d}. {build.scene['title']}", "", build.scene["narration"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
