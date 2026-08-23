#!/usr/bin/env python3
"""Package the customer-facing PSKA demo assets for handoff.

The generated package lives under the ignored demo dist directory. It contains
the real browser recording, subtitles, voiceover script, storyboard, manifest,
and a short Chinese handoff README.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "hermes_pska_extension_demo"
DIST_DIR = DEMO_DIR / "dist"
DEFAULT_BASENAME = "hermes_pska_customer_walkthrough_demo"
PACKAGE_SCHEMA = "pska.customer_demo_delivery_pack.v1"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    demo_dir = args.demo_dir.resolve()
    dist_dir = demo_dir / "dist"
    basename = str(args.basename)
    manifest_path = dist_dir / f"{basename}_manifest.json"
    manifest = read_manifest(manifest_path)

    package_dir = (args.output_dir or dist_dir / f"{basename}_delivery_pack").resolve()
    package_dir.mkdir(parents=True, exist_ok=True)

    copied = copy_assets(manifest, package_dir)
    preview_path = write_preview_contact_sheet(manifest, dist_dir, basename)
    copied.append(copy_asset("关键画面预览", preview_path, package_dir))
    readme_path = package_dir / "README.zh.md"
    write_package_readme(readme_path, basename, copied)
    pack_manifest_path = package_dir / "delivery_manifest.json"
    write_package_manifest(pack_manifest_path, basename, manifest_path, copied, readme_path)

    zip_path = dist_dir / f"{basename}_delivery_pack.zip"
    write_zip(package_dir, zip_path)
    checksum_path = write_zip_checksum(zip_path)
    handoff_path = write_external_handoff_note(dist_dir, basename, zip_path, checksum_path)

    print(f"package_dir: {package_dir}")
    print(f"zip: {zip_path}")
    print(f"zip_sha256: {checksum_path}")
    print(f"handoff: {handoff_path}")
    print(f"readme: {readme_path}")
    print(f"manifest: {pack_manifest_path}")
    return 0


def read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing customer demo manifest: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("demo_case", {}).get("id") != "customer_walkthrough":
        raise SystemExit(f"{path} is not a customer walkthrough manifest")
    required = ["mp4", "subtitles", "storyboard", "voiceover"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise SystemExit(f"{path} missing keys: {', '.join(missing)}")
    return payload


def copy_assets(manifest: dict[str, Any], package_dir: Path) -> list[dict[str, Any]]:
    copied: list[dict[str, Any]] = []
    subtitled_video = write_subtitled_video(manifest)
    for key, label in [
        ("mp4", "视频主片"),
        ("subtitled_mp4", "硬字幕版视频"),
        ("subtitles", "字幕文件"),
        ("voiceover", "旁白稿"),
        ("storyboard", "分镜说明"),
    ]:
        source = subtitled_video if key == "subtitled_mp4" else ROOT / str(manifest[key])
        if not source.exists():
            raise SystemExit(f"missing {label}: {source}")
        copied.append(copy_asset(label, source, package_dir))

    source_manifest = ROOT / str(manifest.get("mp4", "")).replace(".mp4", "_manifest.json")
    if source_manifest.exists():
        copied.append(copy_asset("生成记录", source_manifest, package_dir))
    return copied


def write_subtitled_video(manifest: dict[str, Any]) -> Path:
    video_path = ROOT / str(manifest["mp4"])
    subtitle_path = ROOT / str(manifest["subtitles"])
    output_path = video_path.with_name(video_path.stem + "_subtitled.mp4")
    duration = ffprobe_duration(video_path)
    subtitles = parse_srt(subtitle_path.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        images = write_subtitle_images(subtitles, tmp_dir)
        command = [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
        ]
        for image in images:
            command.extend(["-loop", "1", "-framerate", "25", "-i", str(image)])
        command.extend(
            [
                "-filter_complex",
                subtitle_overlay_filter(subtitles),
                "-map",
                f"[v{len(subtitles)}]",
                "-t",
                f"{duration:.3f}",
                "-c:v",
                "libx264",
                "-crf",
                "20",
                "-preset",
                "veryfast",
                "-an",
                str(output_path),
            ]
        )
        subprocess.run(command, check=True)
    if not output_path.exists() or output_path.stat().st_size < video_path.stat().st_size * 0.5:
        raise SystemExit(f"failed to build hard-subtitled customer video: {output_path}")
    return output_path


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


def parse_srt(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw_block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.rstrip() for line in raw_block.splitlines() if line.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start_raw, end_raw = [item.strip() for item in lines[1].split("-->", 1)]
        blocks.append(
            {
                "start": srt_time_seconds(start_raw),
                "end": srt_time_seconds(end_raw),
                "text": "\n".join(lines[2:]),
            }
        )
    if not blocks:
        raise SystemExit("customer subtitles are empty; cannot build hard-subtitled video")
    return blocks


def srt_time_seconds(value: str) -> float:
    match = re.fullmatch(r"(\d\d):(\d\d):(\d\d),(\d\d\d)", value)
    if not match:
        raise SystemExit(f"invalid SRT timestamp: {value}")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def write_subtitle_images(subtitles: list[dict[str, Any]], tmp_dir: Path) -> list[Path]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise SystemExit("Pillow is required to build the hard-subtitled customer video") from exc

    font = load_subtitle_font(ImageFont)
    images: list[Path] = []
    for index, block in enumerate(subtitles, start=1):
        image = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        lines = split_subtitle_lines(str(block["text"]))
        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_heights = [box[3] - box[1] for box in line_boxes]
        text_width = max((box[2] - box[0] for box in line_boxes), default=0)
        text_height = sum(line_heights) + max(0, len(lines) - 1) * 8
        box_width = min(1120, text_width + 72)
        box_height = text_height + 34
        box_x = (1280 - box_width) // 2
        box_y = 720 - box_height - 38
        draw.rounded_rectangle(
            (box_x, box_y, box_x + box_width, box_y + box_height),
            radius=12,
            fill=(0, 0, 0, 172),
        )
        y = box_y + 16
        for line, line_box, line_height in zip(lines, line_boxes, line_heights):
            width = line_box[2] - line_box[0]
            draw.text(((1280 - width) // 2, y), line, font=font, fill=(255, 255, 255, 255))
            y += line_height + 8
        path = tmp_dir / f"subtitle_{index:02d}.png"
        image.save(path)
        images.append(path)
    return images


def load_subtitle_font(ImageFont: Any) -> Any:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), 27)
    return ImageFont.load_default()


def split_subtitle_lines(text: str) -> list[str]:
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines: list[str] = []
    for line in raw_lines:
        if len(line) <= 30:
            lines.append(line)
            continue
        cursor = 0
        while cursor < len(line):
            lines.append(line[cursor:cursor + 30])
            cursor += 30
    return lines[:3]


def subtitle_overlay_filter(subtitles: list[dict[str, Any]]) -> str:
    chains = ["[0:v]format=rgba[v0]"]
    for index, block in enumerate(subtitles, start=1):
        chains.append(
            f"[v{index - 1}][{index}:v]overlay=0:0:"
            f"enable='between(t,{block['start']:.3f},{block['end']:.3f})'[v{index}]"
        )
    return ";".join(chains)


def copy_asset(label: str, source: Path, package_dir: Path) -> dict[str, Any]:
    target = package_dir / source.name
    shutil.copy2(source, target)
    return file_item(label, target)


def file_item(label: str, path: Path) -> dict[str, Any]:
    return {
        "label": label,
        "filename": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_preview_contact_sheet(manifest: dict[str, Any], dist_dir: Path, basename: str) -> Path:
    video_path = ROOT / str(manifest["mp4"])
    timeline = manifest.get("timeline") or []
    if len(timeline) != 10:
        raise SystemExit("customer preview sheet expects 10 timeline scenes")
    preview_path = dist_dir / f"{basename}_preview_sheet.jpg"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for index, scene in enumerate(timeline, start=1):
            start = float(scene.get("startsAt") or 0)
            end = float(scene.get("endsAt") or start)
            timestamp = max(0.0, start + max(end - start, 1.0) / 2.0)
            frame_path = tmp_dir / f"frame_{index:02d}.jpg"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=320:-1",
                    str(frame_path),
                ],
                check=True,
            )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                "1",
                "-i",
                str(tmp_dir / "frame_%02d.jpg"),
                "-vf",
                "tile=5x2:padding=8:margin=8",
                "-frames:v",
                "1",
                str(preview_path),
            ],
            check=True,
        )
    if not preview_path.exists() or preview_path.stat().st_size < 10_000:
        raise SystemExit(f"failed to build customer preview sheet: {preview_path}")
    return preview_path


def write_package_readme(path: Path, basename: str, copied: list[dict[str, Any]]) -> None:
    lines = [
        "# 客户演示视频交付包",
        "",
        "这个目录可以直接交给剪辑或讲解同事使用。片子面向客户，不讲内部接口、数据库或模型术语。",
        "",
        "## 文件",
        "",
    ]
    for item in copied:
        lines.append(f"- {item['label']}：`{item['filename']}`")
    lines.extend(
        [
            "",
            "## 使用建议",
            "",
            "1. 直接播放时，优先使用硬字幕版视频。",
            "2. 需要二次剪辑时，导入视频主片和字幕文件。",
            "3. 使用旁白稿生成中文配音，语速建议偏慢。",
            "4. 可先打开关键画面预览图，快速确认画面顺序。",
            "5. 如需调整节奏，只裁短等待画面，不删掉提问到回答的过程。",
            "6. 最后一段创作画布必须保留，它展示想法节点、产物节点和续写草稿。",
            "",
            "## 讲解重点",
            "",
            "- 用户仍然在原来的对话工作台里操作。",
            "- 每轮提问都可以选择资料范围。",
            "- 回答前会先整理资料、已有记忆、操作记录和下一步建议。",
            "- 长期记忆需要用户确认。",
            "- 财报分析展示资料如何变成经营报告草稿。",
            "- 创作画布展示资料如何变成可审阅的小说续写草稿。",
            "",
            "## 剪辑不要删",
            "",
            "- 资料范围选择画面。",
            "- 用户提问到助手回答的等待过程。",
            "- 长期记忆待确认画面。",
            "- 创作画布里的想法节点、产物节点和续写草稿。",
            "",
            "## 不要这样讲",
            "",
            "- 不要说这是独立前端。",
            "- 不要展示底层数据库或资料库管理界面。",
            "- 不要在旁白里说向量、嵌入、接口、网关、模型上下文、智能体编排。",
            "",
            f"包名：`{basename}`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_package_manifest(
    path: Path,
    basename: str,
    source_manifest: Path,
    copied: list[dict[str, Any]],
    readme_path: Path,
) -> None:
    payload = {
        "schema": PACKAGE_SCHEMA,
        "basename": basename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(source_manifest.relative_to(ROOT)),
        "readme": readme_path.name,
        "integrity": {
            "algorithm": "sha256",
            "readme": file_item("交付说明", readme_path),
        },
        "items": copied,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_zip(package_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=f"{package_dir.name}/{path.name}")


def write_zip_checksum(zip_path: Path) -> Path:
    checksum_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    checksum_path.write_text(f"{sha256_file(zip_path)}  {zip_path.name}\n", encoding="utf-8")
    return checksum_path


def write_external_handoff_note(dist_dir: Path, basename: str, zip_path: Path, checksum_path: Path) -> Path:
    handoff_path = dist_dir / f"{basename}_delivery_handoff.zh.md"
    lines = [
        "# 客户演示视频外部交付说明",
        "",
        "这份说明放在压缩包外面，交给剪辑或讲解同事时请和压缩包一起发送。",
        "",
        "## 一起发送",
        "",
        f"- `{zip_path.name}`",
        f"- `{checksum_path.name}`",
        "",
        "## 收到后先校验",
        "",
        "```bash",
        f"shasum -a 256 -c {checksum_path.name}",
        "```",
        "",
        "看到校验通过后，再解压压缩包。",
        "",
        "## 直接预览",
        "",
        f"- 直接播放 `{basename}_subtitled.mp4`，不用另外加载字幕。",
        "- 需要二次剪辑时，再使用无字幕主视频和同名字幕文件。",
        "",
        "## 剪辑顺序",
        "",
        "1. 导入主视频。",
        "2. 导入同名字幕。",
        "3. 用旁白稿生成中文配音。",
        "4. 先看关键画面预览图，确认画面顺序。",
        "5. 保留资料范围、提问到回答、长期记忆待确认和创作画布画面。",
        "",
        "## 讲解边界",
        "",
        "- 不要说这是独立前端。",
        "- 不要展示底层数据库或资料库管理界面。",
        "- 不要删掉创作画布里的想法节点、产物节点和续写草稿。",
        "",
        f"包名：`{basename}`",
        "",
    ]
    handoff_path.write_text("\n".join(lines), encoding="utf-8")
    return handoff_path


if __name__ == "__main__":
    raise SystemExit(main())
