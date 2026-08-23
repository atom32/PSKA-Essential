#!/usr/bin/env python3
"""Verify the Hermes WebUI PSKA extension demo assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "demo" / "browser" / "hermes_pska_extension_demo"
DIST_DIR = DEMO_DIR / "dist"
BASE_NAME = "hermes_pska_extension_demo"
DEFAULT_MIN_DURATION_SECONDS = 30.0
MIN_DURATION_BY_BASENAME = {
    "hermes_pska_extension_demo_long": 180.0,
    "hermes_pska_finance_case_demo": 120.0,
    "hermes_pska_webnovel_case_demo": 120.0,
    "hermes_pska_customer_walkthrough_demo": 300.0,
}
MIN_DURATION_BY_CASE = {
    "finance_report_research": 120.0,
    "webnovel_author": 120.0,
}
DEMO_VIDEO_PACKS = [
    {"basename": BASE_NAME, "case": ""},
    {"basename": "hermes_pska_extension_demo_long", "case": ""},
    {"basename": "hermes_pska_finance_case_demo", "case": "finance_report_research"},
    {"basename": "hermes_pska_webnovel_case_demo", "case": "webnovel_author"},
    {"basename": "hermes_pska_customer_walkthrough_demo", "case": ""},
]
FEATURE_MATRIX_TERMS = [
    "对话工作台入口",
    "连接状态",
    "资料范围",
    "开始前总览",
    "回答前整理",
    "按文件信息找资料",
    "对话回答",
    "待确认记忆",
    "同步任务",
    "创作画布",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-dir", type=Path, default=DEMO_DIR)
    parser.add_argument("--require-video", action="store_true")
    parser.add_argument("--require-delivery-pack", action="store_true")
    parser.add_argument("--all-videos", action="store_true", help="Verify every known generated demo video pack.")
    parser.add_argument("--basename", default=BASE_NAME)
    parser.add_argument("--case", default="")
    parser.add_argument(
        "--min-duration",
        type=float,
        default=None,
        help="Add a duration floor. Known demo floors still apply: 30s core, 180s long core, 120s business cases.",
    )
    args = parser.parse_args()

    demo_dir = args.demo_dir.resolve()
    dist_dir = demo_dir / "dist"
    checks: list[str] = []

    required = [
        demo_dir / "README.zh.md",
        demo_dir / "FEATURE_EVIDENCE_MATRIX.zh.md",
        demo_dir / "demo_plan.json",
        demo_dir / "source_root" / "Architecture.md",
        demo_dir / "source_root" / "Memory-Trace.md",
        demo_dir / "source_root" / "Eidolia-Bridge.md",
        ROOT / "scripts" / "record_hermes_pska_extension_demo.cjs",
        ROOT / "scripts" / "package_customer_demo_assets.py",
    ]
    require_files(required, checks)
    verify_plan(demo_dir / "demo_plan.json", checks)
    verify_feature_matrix(demo_dir / "FEATURE_EVIDENCE_MATRIX.zh.md", checks)
    verify_recorder(ROOT / "scripts" / "record_hermes_pska_extension_demo.cjs", checks)
    verify_customer_packager(ROOT / "scripts" / "package_customer_demo_assets.py", checks)
    if args.case and not (args.require_video or args.all_videos):
        verify_case_fixture(demo_dir, args.case, checks)
    verify_legacy_demo_disabled(checks)

    if args.all_videos:
        for pack in DEMO_VIDEO_PACKS:
            verify_media_pack(
                demo_dir,
                dist_dir,
                basename=pack["basename"],
                case_id=pack["case"],
                min_duration_arg=args.min_duration,
                checks=checks,
            )
        if args.require_delivery_pack:
            verify_delivery_pack(dist_dir, "hermes_pska_customer_walkthrough_demo", checks)
    elif args.require_video:
        verify_media_pack(
            demo_dir,
            dist_dir,
            basename=args.basename,
            case_id=args.case,
            min_duration_arg=args.min_duration,
            checks=checks,
        )
        if args.require_delivery_pack:
            verify_delivery_pack(dist_dir, args.basename, checks)
    else:
        media_files = media_files_for(dist_dir, args.basename)
        existing = [path for path in media_files if path.exists()]
        checks.append(f"media optional in this mode: {len(existing)}/{len(media_files)} present")
        if args.require_delivery_pack:
            verify_delivery_pack(dist_dir, args.basename, checks)

    print("Hermes extension demo verification passed:")
    for check in checks:
        print(f"- {check}")
    return 0


def resolve_min_duration(args: argparse.Namespace) -> float:
    candidates = [DEFAULT_MIN_DURATION_SECONDS]
    basename = str(args.basename or "")
    if basename in MIN_DURATION_BY_BASENAME:
        candidates.append(MIN_DURATION_BY_BASENAME[basename])
    case_id = str(args.case or "")
    if case_id in MIN_DURATION_BY_CASE:
        candidates.append(MIN_DURATION_BY_CASE[case_id])
    if args.min_duration is not None:
        candidates.append(float(args.min_duration))
    return max(candidates)


def media_files_for(dist_dir: Path, basename: str) -> list[Path]:
    return [
        dist_dir / f"{basename}.mp4",
        dist_dir / f"{basename}.zh.srt",
        dist_dir / f"{basename}_storyboard.zh.md",
        dist_dir / f"{basename}_manifest.json",
    ]


def verify_media_pack(
    demo_dir: Path,
    dist_dir: Path,
    *,
    basename: str,
    case_id: str,
    min_duration_arg: float | None,
    checks: list[str],
) -> None:
    if case_id:
        verify_case_fixture(demo_dir, case_id, checks)
    media_files = media_files_for(dist_dir, basename)
    min_duration = resolve_min_duration(
        argparse.Namespace(basename=basename, case=case_id, min_duration=min_duration_arg)
    )
    require_files(media_files, checks)
    checks.append(f"{basename}: duration threshold: {min_duration:.1f}s")
    duration = verify_video(media_files[0], min_duration, checks)
    verify_srt(media_files[1], duration, checks)
    verify_manifest(media_files[3], checks, expected_case=case_id or None)


def require_files(paths: list[Path], checks: list[str]) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise SystemExit("missing required files:\n" + "\n".join(str(path) for path in missing))
    checks.append(f"{len(paths)} required files exist")


def verify_plan(path: Path, checks: list[str]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "pska.hermes_extension_demo_plan.v1":
        raise SystemExit(f"{path} has wrong schema")
    scenes = payload.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 10:
        raise SystemExit(f"{path} expected 10 scenes")
    if payload.get("entrypoint") != "Hermes WebUI":
        raise SystemExit(f"{path} must use Hermes WebUI entrypoint")
    if str(payload.get("tts") or "").lower() != "none":
        raise SystemExit(f"{path} must disable TTS")
    checks.append("demo_plan.json: Hermes entrypoint, 10 scenes, no TTS")


def verify_feature_matrix(path: Path, checks: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    missing = [term for term in FEATURE_MATRIX_TERMS if term not in text]
    if missing:
        raise SystemExit(f"{path} missing feature matrix scene terms: {', '.join(missing)}")
    verify_no_english_terms(path, text, "feature evidence matrix")
    checks.append("feature matrix: 10 scenes covered in plain Chinese")


def verify_recorder(path: Path, checks: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    required = [
        "record_hermes_pska_extension_demo",
        "#pskaMiniChip",
        "pskaMiniJarvisBrief",
        "pskaMiniAgenticBrief",
        "pskaMiniSourceRecall",
        "pskaMiniOpenMemoryPage",
        "pskaMiniSyncReviews",
        "pskaMiniCreateDigestTask",
        "#eidoliaRailButton",
        "seedHermesDemoData",
        "SOURCE_RECALL_QUERY",
        "/api/sources/roots",
        "no_tts",
        "writeSrt",
    ]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"{path} missing recorder markers: {', '.join(missing)}")
    forbidden = [
        "record_browser_demo_video.cjs",
        "src/pska_essential/web",
        "pska_webui_demo",
        "say ",
        "edge TTS",
    ]
    offenders = [needle for needle in forbidden if needle in text]
    if offenders:
        raise SystemExit(f"{path} contains forbidden diagnostic/TTS markers: {', '.join(offenders)}")
    checks.append("recorder: extension selectors present and no diagnostic/TTS path")


def verify_customer_packager(path: Path, checks: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    required = [
        "pska.customer_demo_delivery_pack.v1",
        "hermes_pska_customer_walkthrough_demo",
        '"voiceover"',
        "客户演示视频交付包",
        "创作画布必须保留",
        "不要说这是独立前端",
        "sha256_file",
        "zipfile.ZipFile",
    ]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"{path} missing customer packager markers: {', '.join(missing)}")
    checks.append("customer packager: delivery assets and zip output covered")


def verify_delivery_pack(dist_dir: Path, basename: str, checks: list[str]) -> None:
    if basename != "hermes_pska_customer_walkthrough_demo":
        raise SystemExit("--require-delivery-pack is only supported for hermes_pska_customer_walkthrough_demo")
    package_dir_name = f"{basename}_delivery_pack"
    zip_path = dist_dir / f"{package_dir_name}.zip"
    checksum_path = zip_path.with_suffix(zip_path.suffix + ".sha256")
    package_dir = dist_dir / package_dir_name
    required_names = [
        f"{package_dir_name}/README.zh.md",
        f"{package_dir_name}/delivery_manifest.json",
        f"{package_dir_name}/{basename}.mp4",
        f"{package_dir_name}/{basename}.zh.srt",
        f"{package_dir_name}/{basename}_voiceover.zh.md",
        f"{package_dir_name}/{basename}_storyboard.zh.md",
        f"{package_dir_name}/{basename}_manifest.json",
    ]
    if not zip_path.exists():
        raise SystemExit(f"missing customer delivery zip: {zip_path}")
    verify_zip_checksum_file(zip_path, checksum_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        missing = [name for name in required_names if name not in names]
        if missing:
            raise SystemExit(f"{zip_path} missing delivery files: {', '.join(missing)}")
        readme = archive.read(f"{package_dir_name}/README.zh.md").decode("utf-8")
        delivery_manifest = json.loads(archive.read(f"{package_dir_name}/delivery_manifest.json").decode("utf-8"))
        integrity_count = verify_delivery_integrity(archive, package_dir_name, delivery_manifest)
    required_readme_terms = [
        "客户演示视频交付包",
        "旁白稿",
        "片子面向客户，不讲内部接口、数据库或模型术语",
        "回答前会先整理资料、已有记忆、操作记录和下一步建议",
        "长期记忆需要用户确认",
        "创作画布里的想法节点、产物节点和续写草稿",
        "不要说这是独立前端",
        "不要展示底层数据库或资料库管理界面",
    ]
    missing_readme_terms = [term for term in required_readme_terms if term not in readme]
    if missing_readme_terms:
        raise SystemExit(f"{zip_path} README does not describe the delivery package")
    if delivery_manifest.get("schema") != "pska.customer_demo_delivery_pack.v1":
        raise SystemExit(f"{zip_path} has wrong delivery manifest schema")
    item_filenames = {str(item.get("filename") or "") for item in delivery_manifest.get("items") or []}
    expected_filenames = {Path(name).name for name in required_names if Path(name).name not in {"README.zh.md", "delivery_manifest.json"}}
    if not expected_filenames.issubset(item_filenames):
        raise SystemExit(f"{zip_path} delivery manifest missing expected items")
    if package_dir.exists():
        require_files([package_dir / Path(name).name for name in required_names], checks)
    checks.append(f"{zip_path.name}: delivery zip contains video, subtitles, voiceover, storyboard, manifests, and README")
    checks.append(f"{zip_path.name}: delivery zip integrity verified with sha256 for {integrity_count} files")
    checks.append(f"{checksum_path.name}: delivery zip external checksum verified with sha256")


def verify_delivery_integrity(
    archive: zipfile.ZipFile,
    package_dir_name: str,
    delivery_manifest: dict[str, Any],
) -> int:
    if (delivery_manifest.get("integrity") or {}).get("algorithm") != "sha256":
        raise SystemExit("customer delivery manifest must declare sha256 integrity")
    items = list(delivery_manifest.get("items") or [])
    readme_item = (delivery_manifest.get("integrity") or {}).get("readme") or {}
    if readme_item:
        items.append(readme_item)
    for item in items:
        filename = str(item.get("filename") or "")
        expected_size = item.get("bytes")
        expected_sha = str(item.get("sha256") or "")
        if not filename or not isinstance(expected_size, int) or expected_size <= 0:
            raise SystemExit(f"customer delivery manifest has invalid integrity metadata for {filename or '<missing>'}")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise SystemExit(f"customer delivery manifest has invalid sha256 for {filename}")
        member_name = f"{package_dir_name}/{filename}"
        try:
            data = archive.read(member_name)
        except KeyError as exc:
            raise SystemExit(f"customer delivery zip missing manifest item: {member_name}") from exc
        if len(data) != expected_size:
            raise SystemExit(f"customer delivery item size mismatch: {filename}")
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != expected_sha:
            raise SystemExit(f"customer delivery item checksum mismatch: {filename}")
    return len(items)


def verify_zip_checksum_file(zip_path: Path, checksum_path: Path) -> None:
    if not checksum_path.exists():
        raise SystemExit(f"missing customer delivery zip checksum: {checksum_path}")
    raw = checksum_path.read_text(encoding="utf-8").strip()
    parts = raw.split()
    if len(parts) != 2:
        raise SystemExit(f"{checksum_path} must contain '<sha256>  <filename>'")
    expected_sha, filename = parts
    if filename != zip_path.name:
        raise SystemExit(f"{checksum_path} references wrong file: {filename}")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise SystemExit(f"{checksum_path} contains invalid sha256")
    actual_sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if actual_sha != expected_sha:
        raise SystemExit(f"{checksum_path} checksum mismatch for {zip_path.name}")


def verify_case_fixture(demo_dir: Path, case_id: str, checks: list[str]) -> None:
    case_root = demo_dir / "cases" / case_id / "source_root"
    if not case_root.exists():
        raise SystemExit(f"unknown or missing demo case source root: {case_root}")
    files = sorted(case_root.glob("*.md"))
    if len(files) < 3:
        raise SystemExit(f"{case_root} expected at least 3 Markdown source files")
    total_chars = sum(len(path.read_text(encoding="utf-8")) for path in files)
    if total_chars < 2_000:
        raise SystemExit(f"{case_root} is too small to support a meaningful demo case")
    checks.append(f"case fixture {case_id}: {len(files)} Markdown files, {total_chars} chars")


def verify_legacy_demo_disabled(checks: list[str]) -> None:
    legacy_paths = [
        ROOT / "scripts" / "record_browser_demo_video.cjs",
        ROOT / "scripts" / "build_browser_demo_video.py",
        ROOT / "scripts" / "build_recording_narrated_cut.py",
        ROOT / "scripts" / "package_browser_demo_pack.py",
        ROOT / "scripts" / "verify_browser_demo_pack.py",
        ROOT / "demo" / "browser" / "pska_webui_demo" / "README.zh.md",
        ROOT / "demo" / "browser" / "pska_webui_demo" / "DEMO_PACKAGE.zh.md",
        ROOT / "demo" / "browser" / "pska_webui_demo" / "JIANYING_IMPORT.zh.md",
        ROOT / "demo" / "browser" / "pska_webui_demo" / "FEATURE_EVIDENCE_MATRIX.zh.md",
        ROOT / "demo" / "browser" / "pska_webui_demo" / "report.html",
    ]
    require_files(legacy_paths, checks)
    offenders: list[Path] = []
    for path in legacy_paths:
        text = path.read_text(encoding="utf-8")
        if "disabled" not in text.lower() and "已禁用" not in text:
            offenders.append(path)
    if offenders:
        raise SystemExit("legacy diagnostic demo is not hard-disabled:\n" + "\n".join(str(path) for path in offenders))
    checks.append("legacy diagnostic demo scripts/docs are hard-disabled")


def verify_video(path: Path, min_duration: float, checks: list[str]) -> float:
    payload = ffprobe(path)
    streams = payload.get("streams") or []
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video:
        raise SystemExit(f"{path} has no video stream")
    first = video[0]
    width = int(first.get("width") or 0)
    height = int(first.get("height") or 0)
    if (width, height) != (1280, 720):
        raise SystemExit(f"{path} expected 1280x720, got {width}x{height}")
    if audio:
        raise SystemExit(f"{path} must not contain TTS/audio stream")
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if duration < min_duration:
        raise SystemExit(f"{path} duration too short: {duration:.1f}s < {min_duration:.1f}s")
    checks.append(f"{path.name}: {duration:.1f}s, 1280x720, no audio")
    return duration


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
    text = path.read_text(encoding="utf-8")
    verify_plain_chinese_subtitles(path, text)
    blocks = parse_srt(text)
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
    checks.append(f"{path.name}: plain Chinese subtitles")


def verify_plain_chinese_subtitles(path: Path, text: str) -> None:
    verify_no_english_terms(path, text, "subtitles")


def verify_no_english_terms(path: Path, text: str, label: str) -> None:
    offenders = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*", text)))
    if offenders:
        raise SystemExit(
            f"{path} {label} must avoid English/technical terms for TTS/user clarity: "
            + ", ".join(offenders[:20])
        )


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


def verify_manifest(path: Path, checks: list[str], expected_case: str | None = None) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ["schema", "base_url", "mp4", "subtitles", "storyboard", "timeline", "no_tts", "entrypoint"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise SystemExit(f"{path} missing keys: {', '.join(missing)}")
    if payload["schema"] != "pska.hermes_extension_playwright_recording.v1":
        raise SystemExit(f"{path} has wrong schema")
    if len(payload.get("timeline") or []) != 10:
        raise SystemExit(f"{path} expected 10 timeline scenes")
    if payload.get("no_tts") is not True:
        raise SystemExit(f"{path} must set no_tts=true")
    if payload.get("entrypoint") != "Hermes WebUI extension":
        raise SystemExit(f"{path} has wrong entrypoint")
    if expected_case:
        demo_case = payload.get("demo_case") or {}
        if demo_case.get("id") != expected_case:
            raise SystemExit(f"{path} expected demo_case.id={expected_case!r}, got {demo_case.get('id')!r}")
        verify_business_case_manifest(path, payload, expected_case)
    if (payload.get("demo_case") or {}).get("id") == "customer_walkthrough":
        verify_customer_walkthrough_manifest(path, payload)
    checks.append(f"{path.name}: manifest schema, entrypoint, 10 scenes, no TTS")


def verify_customer_walkthrough_manifest(path: Path, payload: dict[str, Any]) -> None:
    expected_scene_ids = [
        "entry",
        "connection",
        "scope",
        "overview",
        "pre_answer_context",
        "chat_memory_tasks",
        "finance_evidence",
        "finance_report",
        "webnovel_answer",
        "eidolia_canvas",
    ]
    scene_ids = [str(scene.get("id") or "") for scene in payload.get("timeline") or []]
    if scene_ids != expected_scene_ids:
        raise SystemExit(f"{path} customer walkthrough scenes do not match expected flow: {scene_ids}")
    composition = payload.get("composition") or {}
    sources = set(composition.get("source_recordings") or [])
    expected_sources = {
        "hermes_pska_extension_demo_long.mp4",
        "hermes_pska_finance_case_demo.mp4",
        "hermes_pska_webnovel_case_demo.mp4",
    }
    if sources != expected_sources:
        raise SystemExit(f"{path} expected source recordings {sorted(expected_sources)}, got {sorted(sources)}")
    cleanup = composition.get("visual_cleanup") or {}
    if cleanup.get("sidebar_history_masked") is not True:
        raise SystemExit(f"{path} expected customer walkthrough to mask browser history/sidebar titles")
    mask_filters = cleanup.get("mask_filters") or []
    if not isinstance(mask_filters, list) or len(mask_filters) < 2:
        raise SystemExit(f"{path} expected visual cleanup mask_filters")
    if any("drawbox=" not in str(mask_filter or "") for mask_filter in mask_filters):
        raise SystemExit(f"{path} expected visual cleanup drawbox filters")
    voiceover = str(payload.get("voiceover") or "")
    if not voiceover:
        raise SystemExit(f"{path} expected customer walkthrough voiceover script")
    voiceover_path = ROOT / voiceover
    if not voiceover_path.exists():
        raise SystemExit(f"{path} voiceover script does not exist: {voiceover_path}")
    voiceover_text = voiceover_path.read_text(encoding="utf-8")
    verify_customer_voiceover_script(voiceover_path, voiceover_text)
    durations = {
        str(scene.get("id") or ""): float(scene.get("endsAt") or 0) - float(scene.get("startsAt") or 0)
        for scene in payload.get("timeline") or []
    }
    if durations.get("eidolia_canvas", 0.0) < 20.0:
        raise SystemExit(f"{path} customer walkthrough Eidolia scene is too short")
    if durations.get("finance_report", 0.0) < 45.0:
        raise SystemExit(f"{path} customer walkthrough finance report scene is too short")


def verify_customer_voiceover_script(path: Path, text: str) -> None:
    if "旁白稿" not in text or "剪映" not in text:
        raise SystemExit(f"{path} does not look like a customer voiceover script")
    verify_no_english_terms(path, text, "voiceover script")
    segments = re.findall(r"^## 第\d+段：", text, flags=re.MULTILINE)
    if len(segments) != 10:
        raise SystemExit(f"{path} expected 10 customer voiceover segments, got {len(segments)}")
    required_terms = [
        "对话工作台",
        "资料范围",
        "开始前",
        "回答前",
        "已有记忆",
        "确认记忆",
        "同步任务",
        "财报",
        "经营报告草稿",
        "创作画布",
        "续写草稿",
        "同一个工作流",
    ]
    missing = [term for term in required_terms if term not in text]
    if missing:
        raise SystemExit(f"{path} customer voiceover missing required topics: {', '.join(missing)}")


def verify_business_case_manifest(path: Path, payload: dict[str, Any], expected_case: str) -> None:
    eidolia = payload.get("seeded_eidolia_project") or {}
    if not eidolia.get("project_id") or not eidolia.get("draft_node_id"):
        raise SystemExit(f"{path} expected seeded Eidolia project for business case {expected_case!r}")
    if not isinstance(eidolia.get("focus_node_ids"), list) or len(eidolia.get("focus_node_ids") or []) < 3:
        raise SystemExit(f"{path} expected at least 3 Eidolia focus nodes")
    if int(eidolia.get("source_packets") or 0) < 1:
        raise SystemExit(f"{path} expected Eidolia source packets from PSKA source recall")
    scene_minimums = {
        "finance_report_research": {"eidolia_bridge": 10.0, "chat_injection": 30.0},
        "webnovel_author": {"eidolia_bridge": 20.0, "chat_injection": 25.0},
    }
    durations = {
        str(scene.get("id") or ""): float(scene.get("endsAt") or 0) - float(scene.get("startsAt") or 0)
        for scene in payload.get("timeline") or []
    }
    for scene_id, minimum in scene_minimums.get(expected_case, {}).items():
        duration = durations.get(scene_id, 0.0)
        if duration < minimum:
            raise SystemExit(
                f"{path} scene {scene_id!r} too short for business case {expected_case!r}: "
                f"{duration:.1f}s < {minimum:.1f}s"
            )


if __name__ == "__main__":
    raise SystemExit(main())
