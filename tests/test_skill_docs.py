from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.mcp_server import tool_registry


class SkillDocsTests(unittest.TestCase):
    def test_hermes_skill_uses_workspace_status_as_navigation_entrypoint(self):
        text = Path("skills/hermes/SKILL.md").read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", text)

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
        self.assertIn("Obsidian vaults and local folders as PSKA source scopes", normalized)
        self.assertIn("do not use direct filesystem, Obsidian, or shell file operations", normalized)
        self.assertIn("pska_source_audit_job_enqueue", text)
        self.assertIn("pska_source_audit_schedule_create", text)
        self.assertIn("pska_source_audit_job_tick", text)
        self.assertIn("pska_source_audit_job_run", text)
        self.assertIn("pska_source_extract_job_enqueue", text)
        self.assertIn("pska_source_extract_job_list", text)
        self.assertIn("pska_source_extract_job_run", text)
        self.assertIn("pska_source_watch_once", text)
        self.assertIn("pska_memory_card_list", text)
        self.assertIn("pska_memory_card_get", text)
        self.assertIn("pska_memory_health_scan", text)
        self.assertIn("pska_memory_use_trace", text)
        self.assertIn("pska_memory_why_used", text)
        self.assertIn("pska_workflow_memory_attribution", text)
        self.assertIn("pska_workflow_memory_suggestions", text)
        self.assertIn("pska_obsidian_moc_propose", text)
        self.assertIn("pska_obsidian_moc_apply", text)

    def test_personal_knowledge_architecture_declares_concrete_source_layer(self):
        text = Path("docs/PERSONAL_KNOWLEDGE_ARCHITECTURE.zh.md").read_text(encoding="utf-8")
        contracts = Path("docs/ADAPTER_CONTRACTS.md").read_text(encoding="utf-8")

        for phrase in [
            "Source Root",
            "File Card",
            "Duplicate Group",
            "Memory Card",
            "Memory Quality Gate",
            "Memory As Cognitive Continuity",
            "Four Memory Layers",
            "Memory Card Anatomy",
            "Memory Formation Routes",
            "Belief And Decision As Projections",
            "Automatic Update Without Silent Identity Rewrite",
            "Source Registry",
            "Obsidian 应作为一等 personal knowledge source",
            "SQLite FTS5",
            "pska_source_search",
            "pska_duplicate_report",
            "pska_obsidian_moc_propose",
            "Obsidian MOC Writeback",
            "Behavior delta",
            "pska_source_audit_job_enqueue",
            "pska_source_audit_schedule_create",
            "Wall-Clock Source Audit Scheduler",
            "Jarvis Bar",
            "Proactive Source Audit Jobs",
        ]:
            self.assertIn(phrase, text)

        for phrase in [
            "PersonalSourcePort",
            "Upgrade Adapter Slots",
            "ExtractionPort",
            "SearchIndexPort",
            "DedupPort",
            "ThoughtArtifactPort",
            "ObservabilityPort",
            "WorkflowPort",
            "CloudSourcePort",
            "register_root",
            "duplicate_report",
            "duplicate_review_list",
            "duplicate_group_mark",
            "duplicate_cleanup_propose",
            "read_only",
            "sidecar_write",
            "native_write",
            "M1-M21",
            "match_reason",
            "size_name_version",
            "text_similarity",
            "media_metadata",
            "image_phash",
            "source_collection_create",
            "group_by",
            "obsidian_frontmatter",
            "obsidian_markdown_comment",
            "frontmatter `tags`",
            "PSKA Comment marker block",
            "pska_obsidian_moc_apply",
            "PSKA-managed MOC block",
            "planned vNext surface",
        ]:
            self.assertIn(phrase, contracts)

    def test_system_architecture_vision_covers_ecosystem_not_only_pska(self):
        text = Path("docs/SYSTEM_ARCHITECTURE_VISION.zh.md").read_text(encoding="utf-8")

        for phrase in [
            "Hermes-WebUI",
            "Hermes Agent",
            "Eidolia",
            "PSKA-Essential",
            "RAGFlow",
            "Obsidian",
            "Local Folders",
            "SQLite Memory",
            "Graphiti",
            "Future Cloud Connectors",
            "Minimal Cognitive Object Model",
            "Source",
            "Thought",
            "Artifact",
            "Trace",
            "Memory Plane In Detail",
            "Memory Lifecycle",
            "High-Cognition Mode First",
            "Reference Architectures We Borrow From",
            "OpenAI Agents SDK",
            "Anthropic Effective Agents",
            "LangGraph",
            "MCP Host/Client/Server",
            "Agentic Document Workflows",
            "Canonical Agentic Loop",
            "Jarvis Briefing",
            "The Jarvis Standard",
            "Desired End State",
        ]:
            self.assertIn(phrase, text)

    def test_agentic_system_technical_proposal_covers_users_scenarios_and_strategy(self):
        text = Path("docs/PSKA_AGENTIC_SYSTEM_TECHNICAL_PROPOSAL.zh.md").read_text(
            encoding="utf-8"
        )
        readme = Path("README.md").read_text(encoding="utf-8")

        for phrase in [
            "Core Characteristics",
            "Target Users",
            "Applicable Scenarios",
            "System Architecture",
            "Core Object Model",
            "Memory Architecture",
            "RAG And Retrieval Strategy",
            "Agent Design",
            "Governance And Security",
            "Open-Source And Existing Component Strategy",
            "Roadmap",
            "Success Metrics",
            "Key Risks And Mitigations",
            "Source-first",
            "Memory-governed",
            "Hermes-first",
            "Canvas-native",
            "No-embedding-first",
            "High-Cognition-first",
            "研究者、博士生、独立学者",
            "工程师、独立开发者",
            "作家、创作者",
            "Personal Knowledge Workspace",
            "Eidolia Infinite Canvas Creation",
            "Decision And Belief Reconstruction",
            "Jarvis-Style Daily Briefing",
            "Source / Thought / Artifact / Memory / Trace",
            "SQLite、Graphiti、Zep、Mem0",
        ]:
            self.assertIn(phrase, text)

        self.assertIn("PSKA_AGENTIC_SYSTEM_TECHNICAL_PROPOSAL.zh.md", readme)

    def test_markitdown_smoke_target_is_documented(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")
        script = Path("scripts/markitdown_smoke.py").read_text(encoding="utf-8")
        docling_script = Path("scripts/docling_smoke.py").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")
        upgrade_plan = Path("docs/PSKA_AGENTIC_SYSTEM_UPGRADE_PLAN.zh.md").read_text(encoding="utf-8")

        self.assertIn("live-markitdown-smoke", makefile)
        self.assertIn("live-docling-smoke", makefile)
        self.assertIn("adapter_slots_contract", script)
        self.assertIn("extract_source_file", script)
        self.assertIn("docling", docling_script)
        self.assertIn("extract_source_file", docling_script)
        self.assertIn("note.pdf", docling_script)
        self.assertIn("pdf_section_count", docling_script)
        self.assertIn("live-markitdown-smoke", readme)
        self.assertIn("live-docling-smoke", readme)
        self.assertIn("P3-1", upgrade_plan)
        self.assertIn("P3-4", upgrade_plan)

    def test_agentic_system_upgrade_plan_maps_current_project_to_component_reuse(self):
        text = Path("docs/PSKA_AGENTIC_SYSTEM_UPGRADE_PLAN.zh.md").read_text(encoding="utf-8")
        readme = Path("README.md").read_text(encoding="utf-8")

        for phrase in [
            "Current-State Evidence",
            "Target Requirements",
            "Upgrade Principle",
            "Target Architecture Delta",
            "Build Vs Buy Matrix",
            "Required Project Changes",
            "Adapter Contracts",
            "Optional Extras",
            "Source Registry Schema",
            "Memory Schema And APIs",
            "Thought/Artifact Bridge",
            "Source Extraction Jobs",
            "Dedup Adapter",
            "Search Strategy",
            "Jobs And Wakeup",
            "Observability And Eval",
            "Upgrade Phases",
            "Concrete Backlog",
            "What Not To Do Yet",
            "MarkItDown",
            "Docling",
            "Apache Tika",
            "fclones",
            "Czkawka",
            "Graphiti",
            "Zep",
            "Mem0",
            "Temporal",
            "OpenTelemetry",
            "Tantivy",
            "SourceRef",
            "Memory Card envelope",
            "Phase 1: Extraction And Dedup Quick Wins",
            "Phase 2: Memory Productization",
        ]:
            self.assertIn(phrase, text)

        self.assertIn("PSKA_AGENTIC_SYSTEM_UPGRADE_PLAN.zh.md", readme)

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
            "pska_jarvis_briefing",
            "pska_agentic_context_brief",
            "pska_policy_get",
            "pska_capabilities_get",
            "pska_kb_list",
            "pska_kb_readiness",
            "pska_kb_ingestion_status",
            "pska_kb_document_status",
            "pska_retrieval_probe",
            "pska_context_retrieve",
            "pska_source_read",
            "pska_source_root_list",
            "pska_source_root_register",
            "pska_source_scan",
            "pska_source_search",
            "pska_source_neighbors",
            "pska_duplicate_report",
            "pska_source_audit_run",
            "pska_source_audit_job_enqueue",
            "pska_source_audit_schedule_create",
            "pska_source_audit_job_list",
            "pska_source_audit_job_tick",
            "pska_source_audit_job_run",
            "pska_source_extract_job_enqueue",
            "pska_source_extract_job_list",
            "pska_source_extract_job_run",
            "pska_source_watch_once",
            "pska_saved_search_create",
            "pska_source_tag_propose",
            "pska_source_tag_apply",
            "pska_source_comment_propose",
            "pska_source_comment_apply",
            "pska_obsidian_moc_propose",
            "pska_obsidian_moc_apply",
            "pska_source_memory_review_create",
            "pska_source_memory_candidates_from_audit",
            "pska_eidolia_context_read",
            "pska_eidolia_memory_review_create",
            "pska_trace_query",
            "pska_eidolia_project_trace_import",
            "pska_memory_card_list",
            "pska_memory_card_get",
            "pska_agentic_question_start",
            "pska_agentic_question_resumable",
            "pska_agentic_question_resume",
            "pska_memory_search",
            "pska_memory_card_list",
            "pska_memory_card_get",
            "pska_memory_candidate_dedup",
            "pska_review_merge_candidates",
            "pska_memory_health_scan",
            "pska_memory_use_trace",
            "pska_memory_why_used",
            "pska_workflow_memory_attribution",
            "pska_workflow_memory_suggestions",
            "pska_memory_change_from_conversation",
            "pska_conversation_memory_candidates_create",
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
        self.assertIn("governed Obsidian MOC proposal/apply", text)
        self.assertIn("PSKA may auto-accept and auto-apply", text)
        self.assertNotIn("Review is the primary user-facing action", text)


if __name__ == "__main__":
    unittest.main()
