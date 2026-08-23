import argparse
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "verify_hermes_extension_demo_pack.py"
HERMES_RECORDER_PATH = ROOT / "scripts" / "record_hermes_pska_extension_demo.cjs"
CUSTOMER_BUILDER_PATH = ROOT / "scripts" / "build_customer_demo_video.py"
CUSTOMER_PACKAGER_PATH = ROOT / "scripts" / "package_customer_demo_assets.py"
CUSTOMER_RECORDER_PATH = ROOT / "scripts" / "record_customer_demo_pack.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_hermes_extension_demo_pack", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_packager():
    spec = importlib.util.spec_from_file_location("package_customer_demo_assets", CUSTOMER_PACKAGER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HermesExtensionDemoPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = load_verifier()
        cls.packager = load_packager()

    def test_core_demo_defaults_to_short_smoke_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_extension_demo",
            case="",
            min_duration=None,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 30.0)

    def test_long_core_demo_defaults_to_long_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_extension_demo_long",
            case="",
            min_duration=None,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 180.0)

    def test_known_business_cases_default_to_two_minute_floor(self):
        for case_id, basename in [
            ("finance_report_research", "hermes_pska_finance_case_demo"),
            ("webnovel_author", "hermes_pska_webnovel_case_demo"),
        ]:
            with self.subTest(case_id=case_id):
                args = argparse.Namespace(
                    basename=basename,
                    case=case_id,
                    min_duration=None,
                )
                self.assertEqual(self.verifier.resolve_min_duration(args), 120.0)

    def test_explicit_min_duration_cannot_lower_builtin_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_webnovel_case_demo",
            case="webnovel_author",
            min_duration=45.0,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 120.0)

    def test_explicit_min_duration_can_raise_builtin_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_webnovel_case_demo",
            case="webnovel_author",
            min_duration=150.0,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 150.0)

    def test_customer_walkthrough_defaults_to_five_minute_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_customer_walkthrough_demo",
            case="",
            min_duration=None,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 300.0)

    def test_all_video_packs_cover_expected_assets(self):
        packs = self.verifier.DEMO_VIDEO_PACKS
        self.assertEqual(
            [(pack["basename"], pack["case"]) for pack in packs],
            [
                ("hermes_pska_extension_demo", ""),
                ("hermes_pska_extension_demo_long", ""),
                ("hermes_pska_finance_case_demo", "finance_report_research"),
                ("hermes_pska_webnovel_case_demo", "webnovel_author"),
                ("hermes_pska_customer_walkthrough_demo", ""),
            ],
        )

    def test_customer_video_builder_masks_browser_history_titles(self):
        script = CUSTOMER_BUILDER_PATH.read_text(encoding="utf-8")

        self.assertIn("SIDEBAR_HISTORY_MASK_FILTER", script)
        self.assertIn("sidebar_history_masked", script)
        self.assertIn("hide_sidebar=True", script)
        self.assertIn("customer_facing_operational_walkthrough", script)

    def test_customer_video_builder_writes_voiceover_script(self):
        script = CUSTOMER_BUILDER_PATH.read_text(encoding="utf-8")

        self.assertIn("write_voiceover", script)
        self.assertIn("write_voiceover_tts", script)
        self.assertIn("_voiceover.zh.md", script)
        self.assertIn("_voiceover_tts.zh.txt", script)
        self.assertIn('"voiceover": str(voiceover.relative_to(ROOT))', script)
        self.assertIn('"voiceover_tts": str(voiceover_tts.relative_to(ROOT))', script)
        self.assertIn("客户版实操演示视频旁白稿", script)

    def test_recorder_supports_tail_padding_for_stable_long_capture(self):
        script = HERMES_RECORDER_PATH.read_text(encoding="utf-8")

        self.assertIn("--tail-pad-ms", script)
        self.assertIn("HERMES_DEMO_TAIL_PAD_MS", script)
        self.assertIn("tail_pad_ms", script)

    def test_customer_demo_packager_collects_delivery_assets(self):
        script = CUSTOMER_PACKAGER_PATH.read_text(encoding="utf-8")

        self.assertIn("pska.customer_demo_delivery_pack.v1", script)
        self.assertIn("hermes_pska_customer_walkthrough_demo", script)
        self.assertIn('"voiceover"', script)
        self.assertIn('"voiceover_tts"', script)
        self.assertIn("客户演示视频交付包", script)
        self.assertIn("硬字幕版视频", script)
        self.assertIn("纯旁白文本", script)
        self.assertIn("write_subtitled_video", script)
        self.assertIn("write_package_index", script)
        self.assertIn("write_delivery_summary", script)
        self.assertIn("入口页面", script)
        self.assertIn("交付摘要", script)
        self.assertIn("先看这个", script)
        self.assertIn("直接播放时，优先使用硬字幕版视频", script)
        self.assertIn("创作画布必须保留", script)
        self.assertIn("不要说这是独立前端", script)
        self.assertIn("sha256_file", script)
        self.assertIn("write_preview_contact_sheet", script)
        self.assertIn("write_zip_checksum", script)
        self.assertIn("write_external_handoff_note", script)
        self.assertIn("关键画面预览", script)
        self.assertIn('".sha256"', script)
        self.assertIn("zip_sha256", script)
        self.assertIn("客户演示视频外部交付说明", script)
        self.assertIn('"bytes": path.stat().st_size', script)
        self.assertIn("zipfile.ZipFile", script)

    def test_hard_subtitle_wrapping_does_not_silently_drop_text(self):
        text = "这是一段稍微长一点的客户演示字幕，用来确认硬字幕生成时不会悄悄丢掉后面的文字。"
        lines = self.packager.split_subtitle_lines(text)

        self.assertGreater(len(lines), 1)
        self.assertEqual("".join(lines), text)

        with self.assertRaises(SystemExit):
            self.packager.split_subtitle_lines("这是一段很长的字幕" * 20)

    def test_makefile_has_customer_delivery_pack_target(self):
        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("demo-browser-customer-record-package", makefile)
        self.assertIn("scripts/record_customer_demo_pack.py", makefile)
        self.assertIn("DEMO_RECORD_ARGS", makefile)
        self.assertIn("demo-browser-customer-package", makefile)
        self.assertIn("scripts/build_customer_demo_video.py", makefile)
        self.assertIn("scripts/package_customer_demo_assets.py", makefile)
        self.assertIn("--all-videos --require-video --require-delivery-pack", makefile)

    def test_customer_demo_recorder_dry_run_covers_full_recording_pipeline(self):
        result = subprocess.run(
            [sys.executable, str(CUSTOMER_RECORDER_PATH), "--dry-run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[dry-run] 核心长版", result.stdout)
        self.assertIn("[dry-run] 财报调研案例", result.stdout)
        self.assertIn("[dry-run] 网文续写和创作画布案例", result.stdout)
        self.assertIn("record_hermes_pska_extension_demo.cjs --case core", result.stdout)
        self.assertIn("--output-basename hermes_pska_extension_demo_long", result.stdout)
        self.assertIn("--tail-pad-ms 15000", result.stdout)
        self.assertIn("--case finance_report_research", result.stdout)
        self.assertIn("--case webnovel_author", result.stdout)
        self.assertIn("build_customer_demo_video.py", result.stdout)
        self.assertIn("package_customer_demo_assets.py", result.stdout)
        self.assertIn("verify_hermes_extension_demo_pack.py --all-videos --require-video --require-delivery-pack", result.stdout)

    def test_customer_demo_recorder_preflight_checks_hard_subtitle_dependencies(self):
        script = CUSTOMER_RECORDER_PATH.read_text(encoding="utf-8")

        self.assertIn("missing Pillow", script)
        self.assertIn("missing ffprobe", script)
        self.assertIn("overlay filter required for hard-subtitled delivery video", script)
        self.assertIn("libx264 encoder required for MP4 delivery videos", script)
        self.assertIn("python_module_available", script)
        self.assertIn("ffmpeg_has_filter", script)
        self.assertIn("ffmpeg_has_encoder", script)

    def test_customer_demo_recorder_preflight_fails_before_recording_when_services_are_missing(self):
        result = subprocess.run(
            [
                sys.executable,
                str(CUSTOMER_RECORDER_PATH),
                "--preflight-only",
                "--base-url",
                "http://127.0.0.1:1",
                "--pska-api-base-url",
                "http://127.0.0.1:1",
                "--no-seed-eidolia-data",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("preflight failed", result.stderr)
        self.assertIn("Hermes WebUI is not reachable", result.stderr)
        self.assertIn("PSKA API is not reachable", result.stderr)
        self.assertNotIn("==> 核心长版", result.stdout)

    def test_verifier_can_require_customer_delivery_pack(self):
        script = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("--require-delivery-pack", script)
        self.assertIn("verify_delivery_pack", script)
        self.assertIn("pska.customer_demo_delivery_pack.v1", script)
        self.assertIn("delivery zip contains index, summary, video, hard-subtitled video, subtitles, voiceover, 纯旁白文本, preview sheet, storyboard, manifests, and README", script)
        self.assertIn("_subtitled.mp4", script)
        self.assertIn("index.html", script)
        self.assertIn("DELIVERY_SUMMARY.zh.md", script)
        self.assertIn("_voiceover_tts.zh.txt", script)
        self.assertIn("客户演示视频交付摘要", script)
        self.assertIn("does not describe the delivery package", script)
        self.assertIn("硬字幕版视频", script)
        self.assertIn("customer delivery preview sheet does not look like a valid JPEG", script)
        self.assertIn("delivery zip integrity verified with sha256", script)
        self.assertIn("delivery zip external checksum verified with sha256", script)
        self.assertIn("external handoff note covers checksum and editing steps", script)
        self.assertIn("片子面向客户，不讲内部接口、数据库或模型术语", script)
        self.assertIn("创作画布里的想法节点、产物节点和续写草稿", script)
        self.assertIn("verify_delivery_integrity", script)
        self.assertIn("verify_hard_subtitled_video", script)
        self.assertIn("video_bottom_band_bytes", script)
        self.assertIn("hard subtitles visible in bottom-band pixel check", script)
        self.assertIn("does not show visible subtitle overlay", script)
        self.assertIn("verify_zip_checksum_file", script)
        self.assertIn("verify_external_handoff_note", script)
        self.assertIn("verify_customer_voiceover_tts_text", script)
        self.assertIn("customer delivery item checksum mismatch", script)

    def test_delivery_integrity_verifies_zip_member_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "pack.zip"
            data = b"customer demo asset"
            readme = "# 客户演示视频交付包\n"
            manifest = {
                "integrity": {
                    "algorithm": "sha256",
                    "readme": {
                        "filename": "README.zh.md",
                        "bytes": len(readme.encode("utf-8")),
                        "sha256": hashlib.sha256(readme.encode("utf-8")).hexdigest(),
                    },
                },
                "items": [
                    {
                        "filename": "demo.mp4",
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                ],
            }
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("pack/README.zh.md", readme)
                archive.writestr("pack/demo.mp4", data)

            with zipfile.ZipFile(zip_path) as archive:
                self.verifier.verify_delivery_integrity(archive, "pack", manifest)

            bad_manifest = json.loads(json.dumps(manifest))
            bad_manifest["items"][0]["sha256"] = "0" * 64
            with zipfile.ZipFile(zip_path) as archive:
                with self.assertRaises(SystemExit):
                    self.verifier.verify_delivery_integrity(archive, "pack", bad_manifest)

    def test_preview_image_bytes_require_jpeg_payload(self):
        self.verifier.verify_preview_image_bytes(b"\xff\xd8" + b"x" * 10_000)

        with self.assertRaises(SystemExit):
            self.verifier.verify_preview_image_bytes(b"not a jpeg")

    def test_zip_checksum_file_verifies_transferred_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = pathlib.Path(tmp) / "pack.zip"
            zip_path.write_bytes(b"zip payload")
            checksum_path = pathlib.Path(tmp) / "pack.zip.sha256"
            checksum_path.write_text(
                f"{hashlib.sha256(zip_path.read_bytes()).hexdigest()}  pack.zip\n",
                encoding="utf-8",
            )

            self.verifier.verify_zip_checksum_file(zip_path, checksum_path)

            checksum_path.write_text(f"{'0' * 64}  pack.zip\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.verifier.verify_zip_checksum_file(zip_path, checksum_path)

    def test_external_handoff_note_names_checksum_and_editing_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            zip_path = root / "pack.zip"
            checksum_path = root / "pack.zip.sha256"
            handoff_path = root / "handoff.zh.md"
            handoff_path.write_text(
                "\n".join(
                    [
                        "# 客户演示视频外部交付说明",
                        "",
                        "`pack.zip`",
                        "`pack.zip.sha256`",
                        "```bash",
                        "shasum -a 256 -c pack.zip.sha256",
                        "```",
                        "## 快速确认",
                        "DELIVERY_SUMMARY.zh.md",
                        "index.html",
                        "## 直接预览",
                        "`pack_subtitled.mp4`",
                        "## 剪辑顺序",
                        "关键画面预览图。",
                        "长期记忆待确认。",
                        "创作画布。",
                        "不要说这是独立前端。",
                        "不要展示底层数据库或资料库管理界面。",
                    ]
                ),
                encoding="utf-8",
            )

            self.verifier.verify_external_handoff_note(handoff_path, zip_path, checksum_path)

            handoff_path.write_text("# 客户演示视频外部交付说明\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.verifier.verify_external_handoff_note(handoff_path, zip_path, checksum_path)

    def test_customer_recording_manual_uses_customer_facing_scope(self):
        manual = (
            ROOT
            / "demo"
            / "browser"
            / "hermes_pska_extension_demo"
            / "CUSTOMER_DEMO_RECORDING.zh.md"
        ).read_text(encoding="utf-8")

        self.assertIn("五个通过检查的视频包，并可生成一个硬字幕版本", manual)
        self.assertIn("hermes_pska_customer_walkthrough_demo_subtitled.mp4", manual)
        self.assertIn("最省事的交付方式", manual)
        self.assertIn("实操讲解顺序", manual)
        self.assertIn("make demo-browser-customer-record-package", manual)
        self.assertIn("DEMO_RECORD_ARGS=\"--dry-run\"", manual)
        self.assertIn("DEMO_RECORD_ARGS=\"--preflight-only\"", manual)
        self.assertIn("Node、ffmpeg、录制依赖", manual)
        self.assertIn("按客户实际使用顺序讲", manual)
        self.assertIn("hermes_pska_customer_walkthrough_demo_delivery_pack.zip.sha256", manual)
        self.assertIn("不要录独立的知识助手页面作为主入口", manual)
        self.assertIn("创作画布里能看到想法节点和产物节点", manual)
        self.assertIn("“想法”节点承接设定、反馈、资料线索和下一步方向", manual)
        self.assertIn("“产物”节点承接报告草稿、续写草稿和后续可交付内容", manual)
        self.assertIn("--require-delivery-pack", manual)

    def test_demo_readme_mentions_hard_subtitled_customer_video(self):
        readme = (
            ROOT
            / "demo"
            / "browser"
            / "hermes_pska_extension_demo"
            / "README.zh.md"
        ).read_text(encoding="utf-8")

        self.assertIn("hermes_pska_customer_walkthrough_demo_subtitled.mp4", readme)
        self.assertIn("硬字幕版主片，适合直接预览或发给客户确认", readme)

    def test_plain_chinese_subtitle_check_rejects_english_terms(self):
        with self.assertRaises(SystemExit):
            self.verifier.verify_plain_chinese_subtitles(
                pathlib.Path("demo.zh.srt"),
                "1\n00:00:00,000 --> 00:00:01,000\nAgentic Brief 会让听众困惑。\n",
            )

    def test_plain_chinese_subtitle_check_accepts_chinese_caption(self):
        self.verifier.verify_plain_chinese_subtitles(
            pathlib.Path("demo.zh.srt"),
            "1\n00:00:00,000 --> 00:00:01,000\n回答前整理会把资料和记忆放在一起。\n",
        )

    def test_customer_voiceover_rejects_missing_required_topic(self):
        text = "\n".join(
            [
                "# 客户版实操演示视频旁白稿",
                "",
                "这份稿子用于人工讲解或导入剪映生成中文配音。",
                "",
                *[f"## 第{index}段：片段\n\n对话工作台。资料范围。开始前。回答前。已有记忆。确认记忆。同步任务。财报。经营报告草稿。创作画布。" for index in range(1, 11)],
                "## 收尾",
                "",
                "这套流程保持在同一个工作流里。",
            ]
        )
        with self.assertRaises(SystemExit):
            self.verifier.verify_customer_voiceover_script(pathlib.Path("voiceover.zh.md"), text)

    def test_customer_voiceover_accepts_required_customer_topics(self):
        text = "\n".join(
            [
                "# 客户版实操演示视频旁白稿",
                "",
                "这份稿子用于人工讲解或导入剪映生成中文配音。",
                "",
                *[f"## 第{index}段：片段\n\n对话工作台。资料范围。开始前。回答前。已有记忆。确认记忆。同步任务。财报。经营报告草稿。创作画布。续写草稿。" for index in range(1, 11)],
                "## 收尾",
                "",
                "这套流程保持在同一个工作流里。",
            ]
        )

        self.verifier.verify_customer_voiceover_script(pathlib.Path("voiceover.zh.md"), text)

    def test_customer_voiceover_tts_text_rejects_headings(self):
        text = "\n\n".join(
            [
                "# 客户版实操演示视频旁白稿",
                "对话工作台。资料范围。回答前。确认记忆。财报。经营报告草稿。创作画布。续写草稿。同一个工作流。",
                *["补充段落。" for _ in range(9)],
            ]
        )

        with self.assertRaises(SystemExit):
            self.verifier.verify_customer_voiceover_tts_text(pathlib.Path("voiceover_tts.zh.txt"), text)

    def test_customer_voiceover_tts_text_accepts_plain_narration(self):
        text = "\n\n".join(
            [
                "我们先从用户每天使用的对话工作台开始。",
                "这个入口会在后台整理资料。",
                "用户可以选择资料范围。",
                "开始前可以看到待确认内容。",
                "回答前会先整理参考材料。",
                "用户可以确认记忆。",
                "财报资料会被找回。",
                "资料可以整理成经营报告草稿。",
                "创作前可以恢复上下文。",
                "创作画布会连接想法和续写草稿。",
                "这套流程保持在同一个工作流里。",
            ]
        )

        self.verifier.verify_customer_voiceover_tts_text(pathlib.Path("voiceover_tts.zh.txt"), text)

    def test_feature_matrix_covers_all_demo_scenes(self):
        checks = []
        self.verifier.verify_feature_matrix(
            ROOT / "demo" / "browser" / "hermes_pska_extension_demo" / "FEATURE_EVIDENCE_MATRIX.zh.md",
            checks,
        )
        self.assertIn("feature matrix: 10 scenes covered in plain Chinese", checks)


if __name__ == "__main__":
    unittest.main()
