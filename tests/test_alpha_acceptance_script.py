from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = ROOT / "scripts" / "run_alpha_acceptance.py"
    spec = importlib.util.spec_from_file_location("run_alpha_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load run_alpha_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlphaAcceptanceScriptTests(unittest.TestCase):
    def test_selects_explicit_dataset_ids_before_workspace_ready_ids(self):
        module = _load_script_module()
        args = argparse.Namespace(dataset_id=["explicit-a"], dataset_ids="explicit-b, explicit-c")
        workspace = {"workspace_status": {"kb": {"ready_dataset_ids": ["ready-a"]}}}

        self.assertEqual(
            module._selected_dataset_ids(args, workspace),
            ["explicit-a", "explicit-b", "explicit-c"],
        )

    def test_selects_first_ready_workspace_dataset_when_no_explicit_scope(self):
        module = _load_script_module()
        args = argparse.Namespace(dataset_id=[], dataset_ids="")
        workspace = {"workspace_status": {"kb": {"ready_dataset_ids": ["ready-a", "ready-b"]}}}

        self.assertEqual(module._selected_dataset_ids(args, workspace), ["ready-a"])

    def test_summary_markdown_includes_check_status_and_artifacts(self):
        module = _load_script_module()
        markdown = module._summary_markdown(
            {
                "status": "ok",
                "out_dir": "/tmp/pska-alpha-acceptance-test",
                "checks": [
                    {
                        "name": "full_component_proof",
                        "ok": True,
                        "message": "status=ok",
                        "metadata": {"run_id": "run-demo", "dataset_ids": ["ready-a"]},
                    }
                ],
                "artifacts": {"summary": "/tmp/pska-alpha-acceptance-test/summary.json"},
            }
        )

        self.assertIn("Status: `ok`", markdown)
        self.assertIn("`PASS` full_component_proof", markdown)
        self.assertIn("run_id: `run-demo`", markdown)
        self.assertIn("dataset_ids: `ready-a`", markdown)
        self.assertIn("summary.json", markdown)

    def test_run_json_preserves_structured_payload_from_nonzero_command(self):
        module = _load_script_module()

        payload = module._run_json(
            [
                sys.executable,
                "-c",
                "import json, sys; print(json.dumps({'status':'incomplete','detail':'scope missing'})); sys.exit(2)",
            ],
            env=os.environ.copy(),
            timeout=10,
        )

        self.assertEqual(payload["status"], "incomplete")
        self.assertEqual(payload["detail"], "scope missing")
        self.assertEqual(payload["command_returncode"], 2)

    def test_product_boundary_contract_helper_runs_static_gate(self):
        module = _load_script_module()

        payload = module._run_product_boundary_contract(env=os.environ.copy(), timeout=30)

        self.assertTrue(payload["ok"], payload.get("stderr"))
        self.assertEqual(payload["status"], "ok")
        self.assertIn("Hermes config example uses PSKA HTTP MCP only", payload["checks"])
        self.assertIn("pska-mini stays a thin WebUI sidecar extension", payload["checks"])

    def test_live_product_boundary_args_include_config_manifest_and_consent(self):
        module = _load_script_module()

        args = module._live_product_boundary_args(
            live_hermes_config=Path("/tmp/hermes/config.yaml"),
            live_webui_extension_manifest=Path("/tmp/extensions/extensions.json"),
            live_webui_extension_overrides=Path("/tmp/webui/extension-overrides.json"),
        )

        self.assertEqual(
            args,
            [
                "--live-hermes-config",
                "/tmp/hermes/config.yaml",
                "--live-webui-extension-manifest",
                "/tmp/extensions/extensions.json",
                "--live-webui-extension-overrides",
                "/tmp/webui/extension-overrides.json",
            ],
        )

    def test_default_live_webui_extension_paths_follow_env(self):
        module = _load_script_module()
        old_manifest_path = os.environ.get("HERMES_WEBUI_EXTENSION_MANIFEST_PATH")
        old_extension_dir = os.environ.get("HERMES_WEBUI_EXTENSION_DIR")
        old_manifest = os.environ.get("HERMES_WEBUI_EXTENSION_MANIFEST")
        old_overrides_path = os.environ.get("HERMES_WEBUI_EXTENSION_OVERRIDES_PATH")
        old_state_dir = os.environ.get("HERMES_WEBUI_STATE_DIR")
        try:
            os.environ.pop("HERMES_WEBUI_EXTENSION_MANIFEST_PATH", None)
            os.environ["HERMES_WEBUI_EXTENSION_DIR"] = "/tmp/extensions-root"
            os.environ["HERMES_WEBUI_EXTENSION_MANIFEST"] = "manifest.json"
            os.environ.pop("HERMES_WEBUI_EXTENSION_OVERRIDES_PATH", None)
            os.environ["HERMES_WEBUI_STATE_DIR"] = "/tmp/webui-state"

            self.assertEqual(
                module._default_live_webui_extension_manifest(),
                Path("/tmp/extensions-root/manifest.json"),
            )
            self.assertEqual(
                module._default_live_webui_extension_overrides(),
                Path("/tmp/webui-state/extension-overrides.json"),
            )
        finally:
            _restore_env("HERMES_WEBUI_EXTENSION_MANIFEST_PATH", old_manifest_path)
            _restore_env("HERMES_WEBUI_EXTENSION_DIR", old_extension_dir)
            _restore_env("HERMES_WEBUI_EXTENSION_MANIFEST", old_manifest)
            _restore_env("HERMES_WEBUI_EXTENSION_OVERRIDES_PATH", old_overrides_path)
            _restore_env("HERMES_WEBUI_STATE_DIR", old_state_dir)

    def test_boundary_check_lines_extracts_reported_checks(self):
        module = _load_script_module()

        self.assertEqual(
            module._boundary_check_lines("header\n- one\n- two\n"),
            ["one", "two"],
        )

    def test_demo_video_count_counts_known_video_lines_once(self):
        module = _load_script_module()

        self.assertEqual(
            module._demo_video_count(
                [
                    "hermes_pska_extension_demo.mp4: 88.9s, 1280x720, no audio",
                    "hermes_pska_extension_demo.zh.srt: 10 ordered subtitle blocks",
                    "hermes_pska_extension_demo_long.mp4: 200.8s, 1280x720, no audio",
                    "hermes_pska_extension_demo_long.mp4: duplicate line",
                    "hermes_pska_finance_case_demo.mp4: 123.4s, 1280x720, no audio",
                    "hermes_pska_webnovel_case_demo.mp4: 133.5s, 1280x720, no audio",
                ]
            ),
            4,
        )

    def test_demo_video_count_ignores_unknown_media(self):
        module = _load_script_module()

        self.assertEqual(module._demo_video_count(["unknown.mp4: 1.0s"]), 0)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
