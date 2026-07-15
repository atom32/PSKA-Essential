from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.mcp_server import tool_registry


class SkillDocsTests(unittest.TestCase):
    def test_hermes_skill_uses_workspace_status_as_navigation_entrypoint(self):
        text = Path("skills/hermes/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("pska_workspace_status", text)
        self.assertIn("next_actions", text)
        self.assertIn("Refresh `pska_workspace_status` after KB, Ask, review, or memory actions", text)
        self.assertIn("pska_agentic_question_resume", text)
        self.assertIn("pska_runtime_diagnostics", text)
        self.assertIn("pska_component_check", text)
        self.assertIn("pska_ingest_loop", text)
        self.assertIn("pska_ingest_loop_resume", text)
        self.assertIn("run_file_to_work_product_loop", text)
        self.assertIn("wait_for_resumable_ask", text)
        self.assertIn("wait_ready=false", text)
        self.assertIn("pska_capabilities_get", text)
        self.assertIn("workspace.memory_namespace", text)
        self.assertIn("provider-native", text)
        self.assertIn("memory group IDs", text)
        self.assertIn("Do not call RAGFlow or Graphiti MCP servers directly.", text)

    def test_hermes_config_exposes_operational_loop_tools(self):
        text = Path("skills/hermes/config.example.yaml").read_text(encoding="utf-8")

        self.assertIn("--env-file", text)
        self.assertIn("/Users/xudawei/PSKA-Essential/.env.pska", text)
        self.assertNotIn("PSKA_DEV_FAKE", text)
        self.assertNotIn("PSKA_RETRIEVAL_PROVIDER: \"fake\"", text)
        self.assertNotIn("PSKA_MEMORY_PROVIDER: \"fake\"", text)

        for tool_name in [
            "pska_workspace_status",
            "pska_runtime_diagnostics",
            "pska_capabilities_get",
            "pska_workflow_list",
            "pska_agentic_question_resumable",
            "pska_agentic_question_resume",
            "pska_audit_list",
            "pska_component_check",
            "pska_ingest_loop",
            "pska_ingest_loop_resume",
            "pska_memory_probe",
            "pska_live_closed_loop_probe",
        ]:
            self.assertIn(f"- {tool_name}", text)

    def test_hermes_config_tool_list_matches_mcp_registry(self):
        text = Path("skills/hermes/config.example.yaml").read_text(encoding="utf-8")
        configured_tools = set(re.findall(r"^\s*- (pska_[A-Za-z0-9_]+)\s*$", text, flags=re.MULTILINE))
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }

        with patch.dict("os.environ", env, clear=True):
            actual_tools = set(tool_registry())

        self.assertEqual(configured_tools, actual_tools)

    def test_openclaw_skill_prefers_pska_ingest_loop_boundary(self):
        text = Path("skills/openclaw/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("pska_ingest_loop", text)
        self.assertIn("pska_ingest_loop_resume", text)
        self.assertIn("wait_ready=false", text)
        self.assertIn("do not answer from missing context", text)


if __name__ == "__main__":
    unittest.main()
