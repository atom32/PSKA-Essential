#!/usr/bin/env python3
"""Package the customer-facing PSKA demo assets for handoff.

The generated package lives under the ignored demo dist directory. It contains
the real browser recording, subtitles, voiceover script, storyboard, manifest,
and a short Chinese handoff README.
"""

from __future__ import annotations

import argparse
import json
import shutil
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
    readme_path = package_dir / "README.zh.md"
    write_package_readme(readme_path, basename, copied)
    pack_manifest_path = package_dir / "delivery_manifest.json"
    write_package_manifest(pack_manifest_path, basename, manifest_path, copied, readme_path)

    zip_path = dist_dir / f"{basename}_delivery_pack.zip"
    write_zip(package_dir, zip_path)

    print(f"package_dir: {package_dir}")
    print(f"zip: {zip_path}")
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


def copy_assets(manifest: dict[str, Any], package_dir: Path) -> list[dict[str, str]]:
    copied: list[dict[str, str]] = []
    for key, label in [
        ("mp4", "视频主片"),
        ("subtitles", "字幕文件"),
        ("voiceover", "旁白稿"),
        ("storyboard", "分镜说明"),
    ]:
        source = ROOT / str(manifest[key])
        if not source.exists():
            raise SystemExit(f"missing {label}: {source}")
        target = package_dir / source.name
        shutil.copy2(source, target)
        copied.append({"label": label, "filename": target.name})

    source_manifest = ROOT / str(manifest.get("mp4", "")).replace(".mp4", "_manifest.json")
    if source_manifest.exists():
        target = package_dir / source_manifest.name
        shutil.copy2(source_manifest, target)
        copied.append({"label": "生成记录", "filename": target.name})
    return copied


def write_package_readme(path: Path, basename: str, copied: list[dict[str, str]]) -> None:
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
            "1. 先导入视频主片。",
            "2. 再导入字幕文件。",
            "3. 使用旁白稿生成中文配音，语速建议偏慢。",
            "4. 如需调整节奏，只裁短等待画面，不删掉提问到回答的过程。",
            "5. 最后一段创作画布必须保留，它展示想法节点、产物节点和续写草稿。",
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
    copied: list[dict[str, str]],
    readme_path: Path,
) -> None:
    payload = {
        "schema": PACKAGE_SCHEMA,
        "basename": basename,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(source_manifest.relative_to(ROOT)),
        "readme": readme_path.name,
        "items": copied,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_zip(package_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=f"{package_dir.name}/{path.name}")


if __name__ == "__main__":
    raise SystemExit(main())
