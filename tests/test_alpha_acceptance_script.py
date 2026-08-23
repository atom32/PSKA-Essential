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
                    "hermes_pska_customer_walkthrough_demo.mp4: 325.4s, 1280x720, no audio",
                ]
            ),
            5,
        )

    def test_demo_video_count_ignores_unknown_media(self):
        module = _load_script_module()

        self.assertEqual(module._demo_video_count(["unknown.mp4: 1.0s"]), 0)

    def test_eidolia_bridge_rejects_temporary_review_after_trace(self):
        module = _load_script_module()
        calls = []
        old_post = module._api_post_json
        old_get = module._api_get_json

        def fake_post(api_base_url, path, payload):
            calls.append(("POST", path, payload))
            if path == "/api/eidolia/context/read":
                return {
                    "ok": True,
                    "context": {
                        "schema": "pska.eidolia_context.v1",
                        "source_ref": {"adapter": "eidolia", "metadata": {"node_type": "thought"}},
                        "data_flow": {
                            "writes_memory_directly": False,
                            "writes_source_files": False,
                        },
                    },
                }
            if path == "/api/eidolia/memory-reviews":
                return {
                    "ok": True,
                    "review": {"review_id": "rev-eidolia-alpha", "status": "pending"},
                    "memory_apply": None,
                    "memory_card": {"source_origin": "eidolia"},
                    "governance": {"writes_memory_directly": False},
                }
            if path == "/api/reviews/rev-eidolia-alpha/decision":
                return {"ok": True, "decision": {"decision": "reject"}}
            raise AssertionError(path)

        def fake_get(url):
            calls.append(("GET", url, {}))
            self.assertIn("review_id=rev-eidolia-alpha", url)
            return {
                "ok": True,
                "schema": "pska.trace_query.v1",
                "status": "found",
                "data_flow": {"writes_memory_directly": False},
            }

        try:
            module._api_post_json = fake_post
            module._api_get_json = fake_get

            result = module._run_eidolia_bridge("http://127.0.0.1:8765")
        finally:
            module._api_post_json = old_post
            module._api_get_json = old_get

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["review_id"], "rev-eidolia-alpha")
        self.assertEqual(result["review_status"], "reject")
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertTrue(result["data_flow"]["creates_review"])
        self.assertTrue(result["data_flow"]["rejects_temporary_review"])
        self.assertEqual(
            [call[1] for call in calls],
            [
                "/api/eidolia/context/read",
                "/api/eidolia/memory-reviews",
                "http://127.0.0.1:8765/api/trace/query?review_id=rev-eidolia-alpha&limit=20",
                "/api/reviews/rev-eidolia-alpha/decision",
            ],
        )

    def test_recovery_boundary_proves_read_only_backup_and_writeback_lock(self):
        module = _load_script_module()
        old_get = module._api_get_json

        def fake_get(url):
            self.assertEqual(url, "http://127.0.0.1:8765/api/alpha/recovery-plan")
            return {
                "ok": True,
                "alpha_recovery_plan": {
                    "schema": "pska.alpha_recovery_plan.v1",
                    "status": "needs_rehearsal",
                    "backup_items": [
                        {"item_id": "review_store"},
                        {"item_id": "source_registry"},
                        {"item_id": "user_source_roots"},
                        {"item_id": "kb_provider"},
                    ],
                    "restore_drills": [
                        {"drill_id": "copy_pska_local_state"},
                        {"drill_id": "restore_pska_local_state"},
                        {"drill_id": "provider_restore_boundary"},
                        {"drill_id": "native_writeback_rollback"},
                    ],
                    "writeback_preflight": [
                        {"operation": "sidecar_annotation", "allowed_first_trial": True},
                        {"operation": "obsidian_frontmatter_tags", "allowed_first_trial": False},
                        {"operation": "obsidian_markdown_comment", "allowed_first_trial": False},
                        {"operation": "obsidian_moc", "allowed_first_trial": False},
                    ],
                    "next_actions": [
                        {"action": "verify_source_writeback_backup"},
                    ],
                    "data_flow": {
                        "read_only": True,
                        "creates_backup": False,
                        "restores_data": False,
                        "writes_source_files": False,
                        "writes_memory_directly": False,
                        "executes_provider_export": False,
                    },
                },
            }

        try:
            module._api_get_json = fake_get
            result = module._run_recovery_boundary("http://127.0.0.1:8765")
        finally:
            module._api_get_json = old_get

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["recovery_status"], "needs_rehearsal")
        self.assertEqual(result["backup_item_count"], 4)
        self.assertEqual(result["restore_drill_count"], 4)
        self.assertIn("obsidian_moc", result["blocked_native_writeback_operations"])
        self.assertFalse(result["data_flow"]["creates_backup"])
        self.assertFalse(result["data_flow"]["restores_data"])


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
