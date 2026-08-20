from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pska_essential.gbrain_component import build_gbrain_component_status


class GBrainComponentStatusTests(unittest.TestCase):
    def test_source_checkout_without_runtime_is_visible_but_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gbrain = root / "gbrain"
            gbrain.mkdir()
            (root / "components.yaml").write_text("schema: pska.components.registry.v1\n", encoding="utf-8")
            (gbrain / "package.json").write_text(
                json.dumps(
                    {
                        "name": "gbrain",
                        "version": "0.46.12.3",
                        "description": "Postgres-native personal knowledge brain with hybrid RAG search",
                    }
                ),
                encoding="utf-8",
            )

            status = build_gbrain_component_status(
                environ={"PSKA_COMPONENTS_ROOT": str(root)},
                command_resolver=lambda _command: None,
            )

        self.assertEqual(status["schema"], "pska.gbrain_component_status.v1")
        self.assertEqual(status["mode"], "source_only")
        self.assertEqual(status["package"]["version"], "0.46.12.3")
        self.assertFalse(status["runtime"]["participates_in_memory_search"])
        self.assertFalse(status["runtime"]["participates_in_agentic_context_brief"])
        self.assertFalse(status["governance"]["direct_hermes_mcp_allowed"])
        self.assertFalse(status["transport"]["stdio_product_flow_allowed"])
        self.assertEqual(status["runtime"]["pska_adapter"], "available_not_selected")
        self.assertIn("configure_gbrain_http_mcp", {item["action"] for item in status["next_actions"]})
        checks = {item["name"]: item for item in status["checks"]}
        self.assertEqual(checks["pska_brain_adapter"]["status"], "ok")

    def test_http_mcp_settings_are_detected_without_claiming_provider_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gbrain = root / "gbrain"
            gbrain.mkdir()
            (gbrain / "package.json").write_text(json.dumps({"name": "gbrain"}), encoding="utf-8")
            environ = {
                "PSKA_COMPONENTS_ROOT": str(root),
                "GBRAIN_MCP_URL": "http://127.0.0.1:33333/mcp",
                "GBRAIN_REMOTE_TOKEN": "redacted-test-token",
            }

            status = build_gbrain_component_status(
                environ=environ,
                command_resolver=lambda command: f"/fake/bin/{command}",
            )

        self.assertEqual(status["mode"], "http_mcp_configured_adapter_available")
        self.assertTrue(status["transport"]["mcp_url_configured"])
        self.assertTrue(status["transport"]["auth_configured"])
        self.assertEqual(status["transport"]["mcp_url"], "http://127.0.0.1:33333/mcp")
        self.assertEqual(status["runtime"]["product_flow_status"], "candidate_visible_not_in_recall_path")
        self.assertFalse(status["runtime"]["participates_in_memory_search"])

    def test_selected_gbrain_memory_provider_reports_participation_when_http_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gbrain = root / "gbrain"
            gbrain.mkdir()
            (gbrain / "package.json").write_text(json.dumps({"name": "gbrain"}), encoding="utf-8")
            environ = {
                "PSKA_COMPONENTS_ROOT": str(root),
                "PSKA_MEMORY_PROVIDER": "gbrain",
                "GBRAIN_MCP_URL": "http://127.0.0.1:33333/mcp",
                "GBRAIN_MCP_TOKEN": "redacted-test-token",
            }

            status = build_gbrain_component_status(
                environ=environ,
                command_resolver=lambda command: f"/fake/bin/{command}",
            )

        self.assertEqual(status["mode"], "pska_memory_provider_configured")
        self.assertEqual(status["runtime"]["pska_adapter"], "configured")
        self.assertTrue(status["runtime"]["participates_in_memory_search"])
        self.assertTrue(status["pska"]["selected_as_memory_provider"])
        self.assertFalse(status["governance"]["direct_hermes_mcp_allowed"])

    def test_selected_gbrain_memory_provider_reports_incomplete_http_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gbrain = root / "gbrain"
            gbrain.mkdir()
            (gbrain / "package.json").write_text(json.dumps({"name": "gbrain"}), encoding="utf-8")

            status = build_gbrain_component_status(
                environ={"PSKA_COMPONENTS_ROOT": str(root), "PSKA_MEMORY_PROVIDER": "gbrain"},
                command_resolver=lambda _command: None,
            )

        self.assertEqual(status["mode"], "pska_memory_provider_incomplete")
        self.assertEqual(status["runtime"]["pska_adapter"], "configured_but_incomplete")
        self.assertFalse(status["runtime"]["participates_in_memory_search"])
        checks = {item["name"]: item for item in status["checks"]}
        self.assertEqual(checks["pska_brain_adapter"]["status"], "warning")


if __name__ == "__main__":
    unittest.main()
