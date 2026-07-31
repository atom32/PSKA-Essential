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
        self.assertIn("dataset_names", text)
        self.assertIn("run_file_to_work_product_loop", text)
        self.assertIn("wait_for_resumable_ask", text)
        self.assertIn("wait_ready=false", text)
        self.assertIn("pska_capabilities_get", text)
        self.assertIn("workspace.memory_namespace", text)
        self.assertIn("provider-native", text)
        self.assertIn("memory group IDs", text)
        self.assertIn("Do not call RAGFlow or Graphiti MCP servers directly.", text)

    def test_knowledge_retrieval_skill_is_retrieval_first(self):
        text = Path("skills/hermes/knowledge-retrieval/SKILL.md").read_text(encoding="utf-8")
        recovery = Path(
            "skills/hermes/knowledge-retrieval/references/pska-graphiti-failure.md"
        ).read_text(encoding="utf-8")

        self.assertIn("name: knowledge-retrieval", text)
        normalized = re.sub(r"\s+", " ", text)
        self.assertIn("PSKA-Mini Runtime Scope", text)
        self.assertIn("pska_retrieval_probe", text)
        self.assertIn("pska_context_retrieve", text)
        self.assertIn("Memory Candidate Pass", text)
        self.assertIn("force_review=True", text)
        self.assertIn("local SQLite review store", text)
        self.assertIn("Treat Graphiti as an optional memory backend", text)
        self.assertIn("Do not let a failed memory service block", text)
        self.assertIn("Do not invent IDs", text)
        self.assertIn("Graphiti down means memory is down", normalized)
        self.assertIn("/api/runtime/retrieval-probe", recovery)
        self.assertIn("Graphiti is NOT bundled with PSKA-Essential", recovery)

    def test_hermes_config_exposes_daily_pska_surface(self):
        text = Path("skills/hermes/config.example.yaml").read_text(encoding="utf-8")

        self.assertIn("--env-file", text)
        self.assertIn("/Users/xudawei/PSKA-Essential/.env.pska", text)
        self.assertNotIn("PSKA_DEV_FAKE", text)
        self.assertNotIn("PSKA_RETRIEVAL_PROVIDER: \"fake\"", text)
        self.assertNotIn("PSKA_MEMORY_PROVIDER: \"fake\"", text)

        for tool_name in [
            "pska_workspace_status",
            "pska_policy_get",
            "pska_capabilities_get",
            "pska_kb_list",
            "pska_kb_readiness",
            "pska_kb_ingestion_status",
            "pska_kb_document_status",
            "pska_retrieval_probe",
            "pska_context_retrieve",
            "pska_source_read",
            "pska_agentic_question_start",
            "pska_agentic_question_resumable",
            "pska_agentic_question_resume",
            "pska_memory_search",
            "pska_memory_change_from_conversation",
            "pska_memory_lifecycle",
            "pska_review_list",
            "pska_review_get",
            "pska_provider_jobs",
            "pska_runtime_diagnostics",
            "pska_component_check",
        ]:
            self.assertIn(f"- {tool_name}", text)

        for tool_name in [
            "pska_workflow_start",
            "pska_workflow_list",
            "pska_audit_list",
            "pska_eval_run",
            "pska_kb_ingest_files",
            "pska_kb_delete",
            "pska_memory_apply",
            "pska_digest_job_run",
        ]:
            self.assertNotIn(f"- {tool_name}", text)

    def test_hermes_config_tool_list_is_mcp_registry_subset(self):
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

        self.assertTrue(configured_tools)
        self.assertLess(configured_tools, actual_tools)
        self.assertTrue(configured_tools.issubset(actual_tools))
        self.assertIn("pska_workflow_start", actual_tools - configured_tools)

    def test_openclaw_skill_prefers_pska_ingest_loop_boundary(self):
        text = Path("skills/openclaw/SKILL.md").read_text(encoding="utf-8")

        self.assertIn("pska_ingest_loop", text)
        self.assertIn("pska_ingest_loop_resume", text)
        self.assertIn("wait_ready=false", text)
        self.assertIn("do not answer from missing context", text)

    def test_frontend_redesign_is_hermes_webui_first(self):
        text = Path("docs/FRONTEND_REDESIGN.md").read_text(encoding="utf-8")

        self.assertIn("Hermes WebUI is the user workspace", text)
        self.assertIn("PSKA should not maintain a second full conversation frontend", text)
        self.assertIn("upload once through PSKA Product API", text)
        self.assertIn("Configure Hermes MCP to expose PSKA tools only", text)
        self.assertIn("Use `memory.search_view`", text)
        self.assertNotIn("### Conversation\n\nNative page.", text)
        self.assertNotIn("Make conversation the default landing page.", text)

    def test_product_design_keeps_review_as_exception_inbox(self):
        text = Path("docs/PRODUCT_DESIGN.md").read_text(encoding="utf-8")

        self.assertIn("Hermes-based frontend", text)
        self.assertIn("conversation-native memory is the primary user path", text.lower())
        self.assertIn("Review is an exception inbox", text)
        self.assertIn("auto-apply clear user-driven remember/correct/forget", text)
        self.assertIn("PSKA may auto-accept and auto-apply", text)
        self.assertNotIn("Review is the primary user-facing action", text)


if __name__ == "__main__":
    unittest.main()
