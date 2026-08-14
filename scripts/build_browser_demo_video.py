#!/usr/bin/env python3
"""Build a browser-operation replay video from real PSKA WebUI screenshots."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "demo" / "browser" / "pska_webui_demo" / "demo_plan.json"
DEFAULT_OUT = ROOT / "demo" / "browser" / "pska_webui_demo" / "dist"
FONT_CANDIDATES = [
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
    Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]


@dataclass
class SceneBuild:
    index: int
    scene: dict[str, Any]
    duration: float
    segment_path: Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--voice", default=None, help="macOS say voice. Use 'none' to disable narration.")
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    width, height = [int(value) for value in plan.get("resolution", [1280, 720])]
    fps = int(plan.get("fps", 24))
    voice = args.voice if args.voice is not None else plan.get("voice", "Tingting")
    if str(voice).lower() in {"", "none", "silent", "false"}:
        voice = ""

    out_dir = args.out
    build_dir = out_dir / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    font_path = first_existing(FONT_CANDIDATES)
    fonts = {
        "title": ImageFont.truetype(str(font_path), 28),
        "caption": ImageFont.truetype(str(font_path), 20),
        "small": ImageFont.truetype(str(font_path), 15),
        "tiny": ImageFont.truetype(str(font_path), 13),
    }

    builds: list[SceneBuild] = []
    for index, scene in enumerate(plan["scenes"], start=1):
        duration = float(scene.get("duration") or 7)
        audio_path = None
        if voice:
            candidate = build_dir / f"{index:02d}_{scene['id']}.aiff"
            if run_say(scene["narration"], voice=voice, output=candidate):
                audio_path = candidate
                measured = ffprobe_duration(candidate)
                if measured:
                    duration = max(duration, measured + 0.5)

        frames_dir = build_dir / f"frames_{index:02d}_{scene['id']}"
        frames_dir.mkdir(parents=True, exist_ok=True)
        render_scene_frames(
            plan=plan,
            scene=scene,
            index=index,
            total=len(plan["scenes"]),
            plan_dir=args.plan.parent,
            frames_dir=frames_dir,
            width=width,
            height=height,
            fps=fps,
            duration=duration,
            fonts=fonts,
        )

        segment_path = build_dir / f"{index:02d}_{scene['id']}.mp4"
        render_segment(frames_dir, fps, audio_path, segment_path, duration)
        builds.append(SceneBuild(index=index, scene=scene, duration=duration, segment_path=segment_path))

    base_name = plan.get("output_basename") or "pska_webui_browser_demo"
    final_mp4 = out_dir / f"{base_name}.mp4"
    concat_video([build.segment_path for build in builds], final_mp4, build_dir / "segments.txt")

    write_srt(builds, out_dir / f"{base_name}.zh.srt")
    write_storyboard(plan, builds, out_dir / "storyboard.zh.md")
    write_voiceover(plan, builds, out_dir / "voiceover.zh.md")

    if not args.keep_build:
        shutil.rmtree(build_dir, ignore_errors=True)

    print(f"video: {final_mp4}")
    print(f"subtitles: {out_dir / f'{base_name}.zh.srt'}")
    print(f"storyboard: {out_dir / 'storyboard.zh.md'}")
    print(f"voiceover: {out_dir / 'voiceover.zh.md'}")
    return 0


def first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise SystemExit("No usable Chinese font found.")


def render_scene_frames(
    *,
    plan: dict[str, Any],
    scene: dict[str, Any],
    index: int,
    total: int,
    plan_dir: Path,
    frames_dir: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    screenshot = Image.open(plan_dir / scene["image"]).convert("RGB")
    base = fit_cover(screenshot, width, height)
    frame_count = max(1, int(math.ceil(duration * fps)))
    cursor = tuple(scene.get("cursor", [width - 96, height - 96]))
    start = (max(265, int(cursor[0] - 210)), max(92, int(cursor[1] - 135)))
    click_at = float(scene.get("click_at") or 0)

    for frame_index in range(frame_count):
        t = frame_index / fps
        progress = min(1.0, t / max(1.1, duration * 0.34))
        eased = ease_out(progress)
        x = int(start[0] + (cursor[0] - start[0]) * eased)
        y = int(start[1] + (cursor[1] - start[1]) * eased)

        frame = base.copy().convert("RGBA")
        draw = ImageDraw.Draw(frame)
        draw_header(draw, plan, scene, index, total, width, fonts)
        draw_caption(draw, scene["caption"], width, height, fonts)
        if click_at and abs(t - click_at) < 0.55:
            draw_click_ripple(draw, cursor, abs(t - click_at))
        draw_cursor(draw, (x, y))

        frame.convert("RGB").save(frames_dir / f"frame_{frame_index:05d}.jpg", quality=91)


def fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    ratio = max(width / image.width, height / image.height)
    resized = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def draw_header(
    draw: ImageDraw.ImageDraw,
    plan: dict[str, Any],
    scene: dict[str, Any],
    index: int,
    total: int,
    width: int,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    draw.rectangle((0, 0, width, 74), fill=(16, 28, 26, 216))
    draw.text((278, 14), f"{index:02d}/{total:02d}  {scene['title']}", font=fonts["title"], fill=(243, 249, 246, 255))
    draw.text((278, 48), plan["subtitle"], font=fonts["tiny"], fill=(197, 219, 211, 255))


def draw_caption(draw: ImageDraw.ImageDraw, text: str, width: int, height: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    lines = wrap_text(draw, text, fonts["caption"], max_width=855)
    box_h = 34 + len(lines) * 27
    x0, y0 = 278, height - box_h - 22
    x1, y1 = width - 28, height - 22
    draw.rounded_rectangle((x0, y0, x1, y1), radius=12, fill=(16, 28, 26, 222), outline=(84, 182, 168, 190), width=1)
    draw.text((x0 + 18, y0 + 12), "浏览器操作演示", font=fonts["small"], fill=(133, 213, 199, 255))
    line_y = y0 + 34
    for line in lines:
        draw.text((x0 + 18, line_y), line, font=fonts["caption"], fill=(246, 250, 248, 255))
        line_y += 27


def draw_cursor(draw: ImageDraw.ImageDraw, point: tuple[int, int]) -> None:
    x, y = point
    shadow = [(x + 2, y + 2), (x + 2, y + 34), (x + 12, y + 26), (x + 19, y + 43), (x + 27, y + 39), (x + 20, y + 22), (x + 32, y + 22)]
    arrow = [(x, y), (x, y + 32), (x + 10, y + 24), (x + 17, y + 41), (x + 25, y + 37), (x + 18, y + 20), (x + 30, y + 20)]
    draw.polygon(shadow, fill=(0, 0, 0, 100))
    draw.polygon(arrow, fill=(255, 255, 255, 255), outline=(16, 28, 26, 255))


def draw_click_ripple(draw: ImageDraw.ImageDraw, point: tuple[int, int], delta: float) -> None:
    x, y = point
    radius = int(16 + delta * 72)
    alpha = max(0, int(210 * (1 - delta / 0.55)))
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(36, 136, 126, alpha), width=5)
    draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=(36, 136, 126, 230))


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, *, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def ease_out(value: float) -> float:
    return 1 - pow(1 - value, 3)


def run_say(text: str, *, voice: str, output: Path) -> bool:
    say = shutil.which("say")
    if not say:
        return False
    result = subprocess.run([say, "-v", voice, "-r", "176", "-o", str(output), text], text=True, capture_output=True)
    if result.returncode == 0:
        return True
    print(f"warning: say failed for voice {voice!r}; generating silent video")
    output.unlink(missing_ok=True)
    return False


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def render_segment(frames_dir: Path, fps: int, audio_path: Path | None, segment_path: Path, duration: float) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.jpg"),
    ]
    if audio_path:
        cmd.extend(["-i", str(audio_path), "-filter_complex", f"[1:a]apad=whole_dur={duration:.3f}[a]", "-map", "0:v", "-map", "[a]"])
    else:
        cmd.extend(["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-map", "0:v", "-map", "1:a"])
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
            "23",
            "-r",
            str(fps),
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
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(final_mp4)],
        check=True,
    )


def write_srt(builds: list[SceneBuild], path: Path) -> None:
    cursor = 0.0
    blocks: list[str] = []
    for build in builds:
        start = cursor
        end = cursor + build.duration
        text = "\n".join(subtitle_lines(build.scene["narration"], max_units=42))
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
                f"Screenshot: `{scene['image']}`",
                f"Cursor: `{scene.get('cursor', [])}`",
                "",
                scene["caption"],
                "",
                f"Narration: {scene['narration']}",
                "",
            ]
        )
        cursor += build.duration
    path.write_text("\n".join(lines), encoding="utf-8")


def write_voiceover(plan: dict[str, Any], builds: list[SceneBuild], path: Path) -> None:
    lines = [f"# {plan['title']} Voiceover", "", "旁白稿可直接用于重新录音或导入剪映。", ""]
    for build in builds:
        lines.extend([f"## {build.index:02d}. {build.scene['title']}", "", build.scene["narration"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
