from __future__ import annotations

import unittest
from pathlib import Path


class SkillDocsTests(unittest.TestCase):
    def test_hermes_skill_uses_workspace_status_as_navigation_entrypoint(self):
        text = Path("skills/hermes/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("pska_workspace_status", text)
        self.assertIn("next_actions", text)
        self.assertIn("Refresh `pska_workspace_status` after KB, Ask, review, or memory actions", text)
        self.assertIn("pska_agentic_question_resume", text)
        self.assertIn("pska_runtime_diagnostics", text)
        self.assertIn("pska_component_check", text)
        self.assertIn("pska_capabilities_get", text)
        self.assertIn("workspace.memory_namespace", text)
        self.assertIn("provider-native", text)
        self.assertIn("memory group IDs", text)
        self.assertIn("Do not call RAGFlow or Graphiti MCP servers directly.", text)

    def test_hermes_config_exposes_operational_loop_tools(self):
        text = Path("skills/hermes/config.example.yaml").read_text(encoding="utf-8")

        for tool_name in [
            "pska_workspace_status",
            "pska_runtime_diagnostics",
            "pska_capabilities_get",
            "pska_workflow_list",
            "pska_agentic_question_resumable",
            "pska_agentic_question_resume",
            "pska_audit_list",
            "pska_component_check",
            "pska_memory_probe",
            "pska_live_closed_loop_probe",
        ]:
            self.assertIn(f"- {tool_name}", text)


if __name__ == "__main__":
    unittest.main()
