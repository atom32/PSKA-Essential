from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.config import build_service_from_env
from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.kb_gateway import reset_fake_kb_gateway
from pska_essential.mcp_server import tool_registry
from pska_essential.workflow import build_fake_service


EXPECTED_TOOLS = {
    "pska_agentic_question_start",
    "pska_agentic_question_resumable",
    "pska_agentic_question_resume",
    "pska_workflow_start",
    "pska_workflow_list",
    "pska_workflow_state",
    "pska_workflow_artifact",
    "pska_workflow_brief",
    "pska_workspace_status",
    "pska_jarvis_briefing",
    "pska_agentic_context_brief",
    "pska_agentic_context_brief_list",
    "pska_agentic_specialist_profiles",
    "pska_hermes_answer_proofs",
    "pska_alpha_readiness",
    "pska_alpha_trial_guide",
    "pska_alpha_recovery_plan",
    "pska_alpha_first_run_session",
    "pska_alpha_first_run_item_update",
    "pska_context_retrieve",
    "pska_source_read",
    "pska_source_root_list",
    "pska_source_root_register",
    "pska_source_scan",
    "pska_source_search",
    "pska_search_index_evaluation",
    "pska_source_neighbors",
    "pska_duplicate_report",
    "pska_duplicate_review_list",
    "pska_duplicate_group_mark",
    "pska_duplicate_cleanup_propose",
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
    "pska_source_collection_create",
    "pska_source_collection_list",
    "pska_source_collection_resolve",
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
    "pska_policy_get",
    "pska_capabilities_get",
    "pska_migration_manifest",
    "pska_provider_jobs",
    "pska_component_check",
    "pska_digest_scope",
    "pska_digest_job_enqueue",
    "pska_digest_job_list",
    "pska_digest_job_run",
    "pska_ingest_loop",
    "pska_ingest_loop_resume",
    "pska_propose",
    "pska_runtime_diagnostics",
    "pska_review_create",
    "pska_review_list",
    "pska_review_get",
    "pska_review_decide",
    "pska_review_decide_batch",
    "pska_review_merge_candidates",
    "pska_review_revise",
    "pska_memory_search",
    "pska_memory_card_list",
    "pska_memory_card_get",
    "pska_memory_briefing",
    "pska_memory_review_queue",
    "pska_memory_candidate_dedup",
    "pska_memory_health_scan",
    "pska_memory_use_trace",
    "pska_memory_why_used",
    "pska_memory_timeline",
    "pska_workflow_memory_attribution",
    "pska_workflow_memory_suggestions",
    "pska_memory_apply",
    "pska_memory_change_from_conversation",
    "pska_conversation_memory_candidates_create",
    "pska_memory_delete_review",
    "pska_memory_lifecycle",
    "pska_memory_probe",
    "pska_memory_review_from_workflow",
    "pska_memory_refresh_review",
    "pska_memory_update_review",
    "pska_export_brief",
    "pska_audit_list",
    "pska_retrieval_probe",
    "pska_live_closed_loop_probe",
    "pska_eval_run",
    "pska_kb_create",
    "pska_kb_delete",
    "pska_kb_document_status",
    "pska_kb_graph_read",
    "pska_kb_ingest_files",
    "pska_kb_ingestion_status",
    "pska_kb_list",
    "pska_kb_parse_documents",
    "pska_kb_readiness",
}


class McpContractTests(unittest.TestCase):
    def test_tool_registry_contains_public_contract(self):
        tools = tool_registry(build_fake_service())
        self.assertEqual(set(tools), EXPECTED_TOOLS)
        capabilities = tools["pska_capabilities_get"]()
        self.assertEqual(set(capabilities["tool_policy"]["tools"]), EXPECTED_TOOLS)
        self.assertEqual(capabilities["assistant_layer"]["status"], "m33_specialist_tool_profiles")
        self.assertIn("pska_alpha_readiness", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_alpha_trial_guide", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_alpha_recovery_plan", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_alpha_first_run_session", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_alpha_first_run_item_update", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_agentic_context_brief", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_agentic_context_brief_list", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_agentic_specialist_profiles", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertIn("pska_search_index_evaluation", capabilities["source_layer"]["mcp_tools"]["implemented"])
        evaluation = tools["pska_search_index_evaluation"]()
        self.assertEqual(evaluation["schema"], "pska.search_index_evaluation.v1")
        self.assertEqual(evaluation["current_default"], "sqlite_fts5")
        self.assertEqual(evaluation["recommendation"]["recommended_action"], "keep_sqlite_fts5_default")
        self.assertFalse(evaluation["data_flow"]["writes_source_files"])
        self.assertFalse(evaluation["data_flow"]["writes_source_registry"])
        self.assertFalse(evaluation["data_flow"]["writes_memory_directly"])
        self.assertFalse(evaluation["data_flow"]["creates_index"])

    def test_runtime_diagnostics_tool_reports_checks_without_memory_search_audit(self):
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            reset_fake_kb_gateway()
            diagnostics = tools["pska_runtime_diagnostics"]()

        checks = {item["name"]: item for item in diagnostics["checks"]}
        self.assertEqual(checks["memory_search_contract"]["metadata"]["provider"], "fake")
        self.assertFalse(checks["memory_search_contract"]["metadata"]["semantic_checked"])
        self.assertEqual(service.store.list_audit_events(action="memory.search"), [])

    def test_migration_manifest_tool_reports_provider_owned_boundaries(self):
        service = build_fake_service()
        tools = tool_registry(service)
        run = tools["pska_workflow_start"]("mcp migration manifest", {"dataset_ids": ["demo"]})
        tools["pska_context_retrieve"]("workflow gate", run_id=run["run_id"], limit=1)
        proposal = tools["pska_propose"](run["run_id"], "memory_patch", "manifest memory")
        review = tools["pska_review_create"](proposal["proposal_id"])
        tools["pska_review_decide"](review["review_id"], "accept", "manifest accepted")
        applied = tools["pska_memory_apply"](review["review_id"])

        manifest = tools["pska_migration_manifest"]()

        self.assertEqual(manifest["kind"], "migration_manifest")
        self.assertIn("fake", manifest["components"]["retrieval_providers"])
        self.assertIn("fake", manifest["components"]["memory_providers"])
        self.assertIn(applied["target_id"], manifest["components"]["memory_providers"]["fake"]["target_ids"])
        self.assertFalse(any("content_excerpt" in ref.get("metadata", {}) for ref in manifest["provider_source_refs"]))

    def test_component_check_tool_returns_structured_acceptance_result(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(temp_dir) / "component-check.txt"
            path.write_text("Configured PSKA components can retrieve uploaded source material.", encoding="utf-8")
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = tools["pska_kb_ingest_files"]([str(path)], dataset_name="MCP Component Check", parse=True)
            result = tools["pska_component_check"](
                question="Can the configured components answer?",
                dataset_names=["MCP Component Check"],
                require_memory=False,
                run_closed_loop=False,
            )

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["scope"]["dataset_ids"], [ingested["dataset"]["dataset_id"]])
        self.assertEqual(result["retrieval_probe"]["status"], "ok")
        self.assertIsNone(result["closed_loop_probe"])
        self.assertIn("retrieval.probe", [event.action for event in service.store.list_audit_events()])

    def test_ingest_loop_tool_uploads_asks_exports_and_audits(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(temp_dir) / "loop.txt"
            path.write_text("PSKA produces sourced work products from uploaded materials.", encoding="utf-8")
            service = build_service_from_env()
            tools = tool_registry(service)

            result = tools["pska_ingest_loop"](
                [str(path)],
                dataset_name="MCP Loop",
                question="What does PSKA produce?",
                export_format="json",
                poll_interval_seconds=0.05,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ask_status"], "ready")
        self.assertTrue(result["readiness"]["ready"])
        self.assertTrue(result["run_id"].startswith("run_"))
        self.assertEqual(result["export"]["traceability"]["source_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertIn("agentic_loop.complete", actions)
        self.assertIn("workflow.export", actions)

    def test_ingest_loop_tool_stops_before_ask_when_scope_is_not_ready(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(temp_dir) / "bad.pdf"
            path.write_bytes(b"%PDF-1.5\nbinary")
            service = build_service_from_env()
            tools = tool_registry(service)

            result = tools["pska_ingest_loop"](
                [str(path)],
                dataset_name="MCP Bad Loop",
                question="Should not run",
                poll_interval_seconds=0.05,
            )

        self.assertEqual(result["status"], "not_ready")
        self.assertIsNone(result["export"])
        self.assertIsNone(result["ask_status"])
        self.assertEqual(result["readiness"]["status"], "failed")
        actions = {event.action for event in service.store.list_audit_events(limit=50)}
        self.assertIn("kb.ingest", actions)
        self.assertNotIn("agentic_loop.complete", actions)
        self.assertNotIn("workflow.export", actions)

    def test_ingest_loop_resume_tool_exports_after_processing_completes(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(temp_dir) / "slow-loop.txt"
            path.write_text("Resumable MCP ingest loops should export after parsing completes.", encoding="utf-8")
            service = build_service_from_env()
            tools = tool_registry(service)

            blocked = tools["pska_ingest_loop"](
                [str(path)],
                dataset_name="MCP Slow Loop",
                question="What should the resumable MCP loop do?",
                parse=False,
                wait_ready=False,
                export_format="json",
                poll_interval_seconds=0.05,
            )
            document_ids = [document["document_id"] for document in blocked["documents"]]
            tools["pska_kb_parse_documents"](blocked["dataset"]["dataset_id"], document_ids, wait=True)
            resumed = tools["pska_ingest_loop_resume"](blocked["run_id"])

        self.assertEqual(blocked["status"], "not_ready")
        self.assertEqual(blocked["run"]["metadata"]["ingest_loop"]["export_format"], "json")
        self.assertEqual(blocked["resume"]["tool"], "pska_ingest_loop_resume")
        self.assertEqual(blocked["resume"]["params"]["run_id"], blocked["run_id"])
        self.assertFalse(blocked["resume"]["can_resume"])
        self.assertEqual(blocked["next_actions"][0]["action"], "track_ingestion_status")
        self.assertEqual(blocked["next_actions"][1]["action"], "resume_ingest_loop")
        self.assertEqual(resumed["kind"], "ingest_loop_resume")
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["ask_status"], "ready")
        self.assertEqual(resumed["export_format"], "json")
        self.assertIsNone(resumed["resume"])
        self.assertEqual(resumed["export"]["traceability"]["source_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=80)}
        self.assertIn("agentic_loop.resume", actions)
        self.assertIn("workflow.export", actions)

    def test_mcp_tools_reject_blank_required_scope_lists_before_backend_calls(self):
        tools = tool_registry(build_fake_service())

        for tool_name, args, message in [
            ("pska_agentic_question_start", ("No real scope", ["  "]), "dataset_ids is required"),
            ("pska_kb_readiness", (["  "],), "dataset_ids is required"),
            ("pska_kb_ingest_files", (["  "],), "file_paths is required"),
            ("pska_ingest_loop", (["  "],), "file_paths is required"),
            ("pska_ingest_loop_resume", ("  ",), "run_id is required"),
            ("pska_agentic_question_resume", ("  ",), "run_id is required"),
            ("pska_kb_parse_documents", ("demo", ["  "]), "document_ids is required"),
        ]:
            with self.subTest(tool_name=tool_name):
                with self.assertRaisesRegex(ValueError, message):
                    tools[tool_name](*args)

    def test_mcp_export_requires_sourced_work_product(self):
        tools = tool_registry(build_fake_service())
        run = tools["pska_workflow_start"]("empty mcp export", {"dataset_ids": ["demo"]})

        with self.assertRaisesRegex(Exception, "sourced work product"):
            tools["pska_export_brief"](run["run_id"], "markdown")

    def test_tools_run_full_loop(self):
        service = build_fake_service()
        tools = tool_registry(service)
        run = tools["pska_workflow_start"]("mcp loop", {"dataset_ids": ["demo"]})
        listed = tools["pska_workflow_list"](limit=5)
        self.assertEqual(listed[0]["run_id"], run["run_id"])
        packets = tools["pska_context_retrieve"]("adapter review", run_id=run["run_id"], limit=1)
        self.assertEqual(len(packets), 1)
        source = tools["pska_source_read"](packets[0]["source_ref"])
        self.assertIn("PSKA-Essential", source["text"])
        policy = tools["pska_policy_get"]()
        self.assertEqual(policy["actions"]["memory_patch"], "manual_review")
        self.assertEqual(policy["transient_results"], "skip")
        capabilities = tools["pska_capabilities_get"]()
        self.assertEqual(capabilities["memory"]["backend"], "fake")
        self.assertTrue(capabilities["memory"]["operations"]["apply"]["supported"])
        self.assertTrue(capabilities["memory"]["operations"]["list"]["supported"])
        self.assertTrue(capabilities["memory"]["operations"]["get"]["supported"])
        self.assertTrue(capabilities["memory"]["operations"]["update"]["supported"])
        self.assertTrue(capabilities["memory"]["operations"]["delete"]["supported"])
        self.assertEqual(capabilities["memory"]["card_view"]["schema"], "pska.memory_card_view.v1")
        self.assertEqual(capabilities["memory"]["card_view"]["mcp_tools"]["list"], "pska_memory_card_list")
        self.assertEqual(capabilities["memory"]["briefing_view"]["schema"], "pska.memory_briefing_view.v1")
        self.assertEqual(capabilities["memory"]["briefing_view"]["mcp_tool"], "pska_memory_briefing")
        self.assertIn("pska_review_merge_candidates", capabilities["assistant_layer"]["mcp_tools"]["implemented"])
        self.assertEqual(capabilities["memory"]["review_queue_view"]["schema"], "pska.memory_review_queue_view.v1")
        self.assertEqual(capabilities["memory"]["review_queue_view"]["mcp_tool"], "pska_memory_review_queue")
        self.assertIn("refresh_reviews", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("conversation_candidates", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("candidate_quality", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("related_candidates", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("merged_replacements", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("revised_replacements", capabilities["memory"]["review_queue_view"]["groups"])
        self.assertIn("review_memory_refresh", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("review_conversation_memory_candidate", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("review_memory_candidate_quality", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("mark_memory_candidate_needs_edit", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("mark_quality_group_needs_edit", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("accept_review_group", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("reject_review_group", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("inspect_related_memory_candidates", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("open_revised_review", capabilities["memory"]["review_queue_view"]["next_actions"])
        self.assertIn("source_memory_id", capabilities["memory"]["review_queue_view"]["refresh_review_item_fields"])
        self.assertIn("no_text_change", capabilities["memory"]["review_queue_view"]["refresh_review_item_fields"])
        self.assertIn("top_issue_type", capabilities["memory"]["review_queue_view"]["candidate_quality_summary_fields"])
        self.assertIn("missing_fields", capabilities["memory"]["review_queue_view"]["candidate_quality_summary_fields"])
        self.assertIn("behavior_delta", capabilities["memory"]["review_queue_view"]["needs_edit_memory_candidate_fields"])
        self.assertIn("source_refs", capabilities["memory"]["review_queue_view"]["needs_edit_memory_candidate_fields"])
        self.assertEqual(capabilities["memory"]["health_view"]["schema"], "pska.memory_health_view.v1")
        self.assertEqual(capabilities["memory"]["health_view"]["mcp_tool"], "pska_memory_health_scan")
        self.assertEqual(capabilities["memory"]["use_trace_view"]["schema"], "pska.memory_use_trace_view.v1")
        self.assertEqual(capabilities["memory"]["use_trace_view"]["mcp_tools"]["why_used"], "pska_memory_why_used")
        self.assertEqual(capabilities["memory"]["timeline_view"]["schema"], "pska.memory_timeline_view.v1")
        self.assertEqual(capabilities["memory"]["timeline_view"]["mcp_tool"], "pska_memory_timeline")
        self.assertEqual(capabilities["memory"]["search_view"]["schema"], "pska.memory_search_view.v1")
        self.assertTrue(capabilities["memory"]["search_view"]["default_filters_superseded"])
        self.assertIn(
            "include_superseded_memory",
            capabilities["memory"]["search_view"]["include_superseded_scope_keys"],
        )
        self.assertIn("display_text", capabilities["memory"]["search_view"]["agent_facing_text"]["metadata_keys"])
        self.assertEqual(capabilities["memory"]["lineage"]["schema"], "pska.memory_lineage.v1")
        self.assertFalse(capabilities["memory"]["lineage"]["pska_authoritative_mapping_table"])
        self.assertEqual(capabilities["adapter_slots"]["schema"], "pska.adapter_slots.v1")
        self.assertIn("builtin_text", capabilities["adapter_slots"]["summary"]["extraction"]["available"])
        self.assertIn("sqlite_fts5", capabilities["adapter_slots"]["summary"]["search_index"]["available"])
        self.assertIn("exact_hash", capabilities["adapter_slots"]["summary"]["dedup"]["available"])
        self.assertIn("media_metadata", capabilities["adapter_slots"]["summary"]["dedup"]["available"])
        self.assertEqual(capabilities["adapter_slots"]["slots"]["extraction"]["contract"], "ExtractionPort")
        self.assertEqual(capabilities["adapter_slots"]["slots"]["dedup"]["contract"], "DedupPort")
        self.assertEqual(capabilities["adapter_slots"]["slots"]["thought_artifact"]["contract"], "ThoughtArtifactPort")
        self.assertIn("fclones", capabilities["adapter_slots"]["summary"]["dedup"]["planned"])
        czkawka = next(
            provider
            for provider in capabilities["adapter_slots"]["slots"]["dedup"]["providers"]
            if provider["name"] == "czkawka"
        )
        self.assertIn(czkawka["status"], {"available", "unavailable"})
        self.assertEqual(czkawka["integration"], "external_cli")
        self.assertEqual(czkawka["env_key"], "PSKA_CZKAWKA_BIN")
        self.assertEqual(capabilities["tool_policy"]["mode"], "soft_constraints")
        policy = capabilities["tool_policy"]["tools"]
        self.assertTrue(policy["pska_memory_apply"]["requires_accepted_review"])
        self.assertTrue(policy["pska_digest_job_run"]["requires_ready_scope"])
        self.assertFalse(policy["pska_source_audit_job_run"]["writes_source_files"])
        self.assertFalse(policy["pska_source_audit_job_run"]["writes_memory_directly"])
        self.assertFalse(policy["pska_source_audit_job_run"]["embedding_required"])
        self.assertFalse(policy["pska_source_extract_job_run"]["writes_source_files"])
        self.assertFalse(policy["pska_source_extract_job_run"]["writes_memory_directly"])
        self.assertFalse(policy["pska_source_extract_job_run"]["embedding_required"])
        self.assertTrue(policy["pska_source_extract_job_run"]["writes_source_registry"])
        self.assertTrue(policy["pska_source_watch_once"]["watches_authorized_root_only"])
        self.assertTrue(policy["pska_source_watch_once"]["queues_jobs_only"])
        self.assertFalse(policy["pska_source_watch_once"]["writes_source_files"])
        self.assertFalse(policy["pska_source_watch_once"]["writes_memory_directly"])
        self.assertTrue(policy["pska_source_audit_schedule_create"]["wall_clock_schedule"])
        self.assertTrue(policy["pska_source_audit_job_tick"]["wall_clock_tick"])
        self.assertEqual(
            policy["pska_duplicate_report"]["supports_modes"],
            [
                "exact_hash",
                "size_name_version",
                "text_similarity",
                "media_metadata",
                "image_phash",
                "fclones_hash",
                "czkawka_hash",
            ],
        )
        self.assertFalse(policy["pska_duplicate_review_list"]["writes_source_files"])
        self.assertFalse(policy["pska_duplicate_review_list"]["writes_source_registry"])
        self.assertFalse(policy["pska_duplicate_group_mark"]["writes_source_files"])
        self.assertTrue(policy["pska_duplicate_group_mark"]["writes_source_registry"])
        self.assertFalse(policy["pska_duplicate_group_mark"]["delete_move_merge_supported"])
        self.assertFalse(policy["pska_duplicate_cleanup_propose"]["writes_source_files"])
        self.assertTrue(policy["pska_duplicate_cleanup_propose"]["writes_source_registry"])
        self.assertFalse(policy["pska_duplicate_cleanup_propose"]["delete_move_merge_supported"])
        self.assertFalse(policy["pska_duplicate_cleanup_propose"]["apply_supported"])
        self.assertEqual(policy["pska_source_search"]["ranking"], "sqlite_fts5_bm25_title_path_boost")
        self.assertTrue(policy["pska_source_search"]["snippet_metadata"])
        self.assertEqual(policy["pska_search_index_evaluation"]["access"], "read")
        self.assertEqual(policy["pska_search_index_evaluation"]["default_provider"], "sqlite_fts5")
        self.assertFalse(policy["pska_search_index_evaluation"]["writes_source_files"])
        self.assertFalse(policy["pska_search_index_evaluation"]["writes_source_registry"])
        self.assertFalse(policy["pska_search_index_evaluation"]["writes_memory_directly"])
        self.assertFalse(policy["pska_search_index_evaluation"]["creates_index"])
        self.assertFalse(policy["pska_source_collection_create"]["writes_source_files"])
        self.assertTrue(policy["pska_source_collection_create"]["writes_source_registry"])
        self.assertFalse(policy["pska_source_collection_resolve"]["embedding_required"])
        self.assertTrue(policy["pska_source_collection_resolve"]["returns_context_packets"])
        self.assertEqual(policy["pska_source_tag_apply"]["writes_source_files"], "write_target_dependent")
        self.assertEqual(policy["pska_source_tag_apply"]["writes_sidecar"], "write_target_dependent")
        self.assertEqual(
            policy["pska_source_tag_apply"]["supports_write_targets"],
            ["sidecar", "obsidian_frontmatter"],
        )
        self.assertEqual(
            policy["pska_source_tag_apply"]["requires_native_permission_for"],
            ["obsidian_frontmatter"],
        )
        self.assertEqual(policy["pska_source_comment_apply"]["writes_source_files"], "write_target_dependent")
        self.assertEqual(policy["pska_source_comment_apply"]["writes_sidecar"], "write_target_dependent")
        self.assertEqual(
            policy["pska_source_comment_apply"]["supports_write_targets"],
            ["sidecar", "obsidian_markdown_comment"],
        )
        self.assertEqual(
            policy["pska_source_comment_apply"]["requires_native_permission_for"],
            ["obsidian_markdown_comment"],
        )
        self.assertTrue(policy["pska_obsidian_moc_apply"]["writes_source_files"])
        self.assertTrue(policy["pska_obsidian_moc_apply"]["requires_native_permission"])
        self.assertEqual(
            policy["pska_obsidian_moc_propose"]["supports_group_by"],
            ["none", "folder", "tag", "topic", "project"],
        )
        self.assertEqual(policy["pska_kb_ingest_files"]["access"], "write")
        proposal = tools["pska_propose"](run["run_id"], "memory_patch", "mcp memory")
        artifact = tools["pska_workflow_artifact"](run["run_id"])
        brief = tools["pska_workflow_brief"](run["run_id"], "markdown")
        self.assertEqual(artifact["latest_proposal"]["proposal_id"], proposal["proposal_id"])
        self.assertIn("PSKA-Essential Brief", brief)
        self.assertNotIn("workflow.export", [event.action for event in service.store.list_audit_events()])
        review = tools["pska_review_create"](proposal["proposal_id"])
        pending_reviews = tools["pska_review_list"]("pending")
        review_record = tools["pska_review_get"](review["review_id"])
        self.assertEqual(pending_reviews[0]["review_id"], review["review_id"])
        self.assertEqual(pending_reviews[0]["source_count"], 1)
        self.assertEqual(review_record["proposal"]["proposal_id"], proposal["proposal_id"])
        self.assertEqual(review_record["source_count"], 1)
        self.assertEqual(review_record["source_refs"][0]["adapter"], "fake")
        tools["pska_review_decide"](review["review_id"], "accept", "test")
        applied = tools["pska_memory_apply"](review["review_id"])
        self.assertTrue(applied["applied"])
        memory_cards = tools["pska_memory_card_list"]({}, 10)
        self.assertEqual(memory_cards["cards"][0]["memory_id"], applied["target_id"])
        memory_card = tools["pska_memory_card_get"](applied["target_id"])
        self.assertEqual(memory_card["card"]["memory_id"], applied["target_id"])
        memory_briefing = tools["pska_memory_briefing"]({}, card_limit=10, health_limit=10, trace_limit=10)
        self.assertEqual(memory_briefing["schema"], "pska.memory_briefing.v1")
        self.assertIn(applied["target_id"], memory_briefing["summary"]["top_focus_memory_ids"])
        memory_review_queue = tools["pska_memory_review_queue"]({}, review_limit=10, health_limit=10, focus_limit=10)
        self.assertEqual(memory_review_queue["schema"], "pska.memory_review_queue.v1")
        self.assertGreaterEqual(memory_review_queue["summary"]["memory_focus_count"], 1)
        memory_candidate_dedup = tools["pska_memory_candidate_dedup"]({}, review_limit=10, similarity_threshold=0.82)
        self.assertEqual(memory_candidate_dedup["schema"], "pska.memory_candidate_dedup.v1")
        self.assertIn("related_groups", memory_candidate_dedup)
        self.assertFalse(memory_candidate_dedup["data_flow"]["embedding_required"])
        memory_health = tools["pska_memory_health_scan"]({}, limit=10)
        self.assertEqual(memory_health["schema"], "pska.memory_health.v1")
        memory_attribution = tools["pska_workflow_memory_attribution"](run["run_id"])
        memory_suggestions = tools["pska_workflow_memory_suggestions"](run["run_id"])
        self.assertEqual(memory_attribution["schema"], "pska.memory_attribution.v1")
        self.assertEqual(memory_suggestions["schema"], "pska.memory_suggestions.v1")
        facts = tools["pska_memory_search"]("mcp memory", {}, 10)
        use_trace = tools["pska_memory_use_trace"](applied["target_id"], limit=10)
        why_used = tools["pska_memory_why_used"](applied["target_id"])
        timeline = tools["pska_memory_timeline"](applied["target_id"], limit=10)
        self.assertEqual(use_trace["traces"][0]["memory_ids"], [applied["target_id"]])
        self.assertEqual(why_used["memory_id"], applied["target_id"])
        self.assertEqual(why_used["confidence"], "candidate_retrieval")
        self.assertEqual(timeline["schema"], "pska.memory_timeline.v1")
        self.assertEqual(timeline["memory_id"], applied["target_id"])
        trace = tools["pska_trace_query"](memory_id=applied["target_id"], limit=10)
        self.assertEqual(trace["schema"], "pska.trace_query.v1")
        self.assertEqual(trace["status"], "found")
        self.assertFalse(trace["data_flow"]["embedding_required"])
        probe = tools["pska_memory_probe"]("mcp memory", {}, 1, require_live=False)
        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["memory_count"], 1)
        update_review = tools["pska_memory_update_review"](facts[0], "updated mcp memory", "revise mcp memory")
        self.assertEqual(update_review["proposal"]["kind"], "memory_update")
        tools["pska_review_decide"](update_review["review"]["review_id"], "accept", "update")
        updated = tools["pska_memory_apply"](update_review["review"]["review_id"])
        self.assertTrue(updated["applied"])
        self.assertEqual(updated["metadata"]["operation"], "update")
        updated_facts = tools["pska_memory_search"]("updated mcp", {}, 10)
        self.assertEqual(updated_facts[0]["text"], "updated mcp memory")
        refresh_review = tools["pska_memory_refresh_review"](
            applied["target_id"],
            "updated mcp memory with refresh review",
            "refresh through memory card",
        )
        self.assertEqual(refresh_review["proposal"]["kind"], "memory_update")
        self.assertEqual(refresh_review["review"]["status"], "pending")
        self.assertEqual(refresh_review["proposal"]["memory_update"]["metadata"]["origin"], "memory_card_refresh")
        self.assertFalse(refresh_review["data_flow"]["writes_memory_directly"])
        delete_review = tools["pska_memory_delete_review"](updated_facts[0], "remove mcp memory")
        self.assertEqual(delete_review["proposal"]["kind"], "memory_delete")
        tools["pska_review_decide"](delete_review["review"]["review_id"], "accept", "delete")
        deleted = tools["pska_memory_apply"](delete_review["review"]["review_id"])
        self.assertTrue(deleted["applied"])
        self.assertEqual(deleted["metadata"]["operation"], "delete")
        self.assertEqual(tools["pska_memory_search"]("mcp memory", {}, 10), [])
        lifecycle = tools["pska_memory_lifecycle"](applied["target_id"])
        self.assertEqual(lifecycle["change_count"], 3)
        self.assertEqual(
            [event["action"] for event in lifecycle["events"]],
            ["memory.apply", "memory.update", "memory.delete"],
        )
        self.assertEqual(lifecycle["latest_event"]["action"], "memory.delete")
        exported = tools["pska_export_brief"](run["run_id"], "markdown")
        self.assertIn("PSKA-Essential Brief", exported)
        self.assertIn("workflow.export", [event.action for event in service.store.list_audit_events()])
        audit = tools["pska_audit_list"](limit=10)
        filtered = tools["pska_audit_list"](action="source.read", limit=10)
        self.assertEqual(audit[0]["action"], "workflow.export")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["action"], "source.read")
        source_read = next(event for event in service.store.list_audit_events() if event.action == "source.read")
        self.assertEqual(source_read.metadata["adapter"], "fake")
        self.assertEqual(source_read.metadata["document_id"], packets[0]["source_ref"]["document_id"])

    def test_workflow_list_limits_recent_runs(self):
        tools = tool_registry(build_fake_service())
        older = tools["pska_workflow_start"]("older run", {"dataset_ids": ["demo"]})
        newer = tools["pska_workflow_start"]("newer run", {"dataset_ids": ["demo"]})

        listed = tools["pska_workflow_list"](limit=1)

        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["run_id"], newer["run_id"])
        self.assertNotEqual(listed[0]["run_id"], older["run_id"])

    def test_audit_list_supports_ascending_order(self):
        tools = tool_registry(build_fake_service())
        run = tools["pska_workflow_start"]("audit order", {"dataset_ids": ["demo"]})
        packets = tools["pska_context_retrieve"]("adapter review", run_id=run["run_id"], limit=1)
        tools["pska_source_read"](packets[0]["source_ref"])
        tools["pska_propose"](run["run_id"], "writing_brief", "audit order")
        tools["pska_export_brief"](run["run_id"], "markdown")

        audit = tools["pska_audit_list"](descending=False)

        self.assertEqual(audit[0]["action"], "workflow.start")
        self.assertEqual(audit[-1]["action"], "workflow.export")

    def test_retrieval_probe_reports_scope_and_writes_audit(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="retrieval-probe.txt",
                text="Retrieval probes should answer from explicitly uploaded source material.",
            )
            dataset_id = ingested["dataset"]["dataset_id"]

            probe = tools["pska_retrieval_probe"](
                question="Can retrieval answer?",
                dataset_ids=[dataset_id],
                limit=1,
            )

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["provider"], "fake")
        self.assertEqual(probe["scope"]["dataset_ids"], [dataset_id])
        self.assertEqual(probe["context_count"], 1)
        event = service.store.list_audit_events(action="retrieval.probe", limit=1)[0]
        self.assertEqual(event.metadata["status"], "ok")
        self.assertEqual(event.metadata["context_count"], 1)

    def test_live_closed_loop_probe_rejects_fake_as_product_proof(self):
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            probe = tools["pska_live_closed_loop_probe"](
                question="Can fake prove the product loop?",
                dataset_ids=["demo"],
            )

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertEqual(probe["providers"]["kb"], "fake")
        self.assertEqual(probe["providers"]["retrieval"], "fake")
        event = service.store.list_audit_events(action="closed_loop.probe", limit=1)[0]
        self.assertEqual(event.metadata["status"], "invalid_configuration")

    def test_workspace_status_reports_operational_next_actions(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="workspace-status.txt",
                text="Workspace status should surface uploaded ready knowledge as the Ask scope.",
            )
            dataset_id = ingested["dataset"]["dataset_id"]

            status = tools["pska_workspace_status"]()
            compact = tools["pska_workspace_status"](compact=True, next_action_limit=1)

        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertIn(dataset_id, status["next_actions"][0]["params"]["dataset_ids"])
        self.assertEqual(compact["kind"], "workspace_status_compact")
        self.assertEqual(compact["status"], "ready")
        self.assertEqual(compact["kb"]["dataset_count"], 1)
        self.assertNotIn("datasets", compact["kb"])
        self.assertEqual(compact["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertIn(dataset_id, compact["next_actions"][0]["params"]["dataset_ids"])

    def test_agentic_context_brief_composes_recall_memory_trace_without_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="agentic-context.txt",
                text="Agentic context brief connects source recall, durable memory, and trace before Hermes answers.",
            )
            dataset_id = ingested["dataset"]["dataset_id"]
            service.memory.facts.append(
                MemoryFact(
                    fact_id="mem-agentic-context",
                    text="PSKA should use Agentic Context Brief before broad answers about source recall, memory, and trace.",
                    source_refs=[SourceRef(adapter="conversation", source_id="msg-agentic", title="Conversation")],
                    metadata={"confidence": 0.93},
                )
            )

            brief = tools["pska_agentic_context_brief"](
                objective="Prepare Hermes to answer about source recall, memory, and trace.",
                question="How should PSKA use source recall before answering?",
                scope={"dataset_ids": [dataset_id]},
                evidence_limit=1,
                source_limit=1,
                memory_limit=2,
                trace_limit=6,
            )
            recent = tools["pska_agentic_context_brief_list"](limit=3)
            specialists = tools["pska_agentic_specialist_profiles"](
                question="How should PSKA use source recall, memory, trace, and verification?",
                limit=4,
            )
            answer_proofs = tools["pska_hermes_answer_proofs"](limit=3)

        self.assertEqual(brief["schema"], "pska.agentic_context_brief.v1")
        self.assertIn(brief["status"], {"ready", "degraded"})
        self.assertEqual(brief["scope"]["dataset_ids"], [dataset_id])
        self.assertEqual(len(brief["recall"]["evidence_blocks"]), 1)
        self.assertEqual(brief["memory"]["relevant_memories"][0]["fact_id"], "mem-agentic-context")
        self.assertIn("recall_agent", {role["role_id"] for role in brief["agentic_roles"]})
        self.assertIn("specialists", brief)
        self.assertIn("verifier_specialist", set(brief["specialists"]["selected_profile_ids"]))
        self.assertFalse(brief["specialists"]["data_flow"]["starts_agents"])
        self.assertGreaterEqual(brief["trace"]["signal_count"], 1)
        self.assertIn("run_agentic_question", {action["action"] for action in brief["next_actions"]})
        self.assertFalse(brief["data_flow"]["writes_source_files"])
        self.assertFalse(brief["data_flow"]["writes_memory_directly"])
        self.assertFalse(brief["data_flow"]["generates_answer_text"])
        self.assertEqual(recent["schema"], "pska.agentic_context_brief_list.v1")
        self.assertEqual(recent["count"], 1)
        self.assertEqual(recent["briefs"][0]["brief_id"], brief["brief_id"])
        self.assertEqual(recent["briefs"][0]["run_id"], brief["run_id"])
        self.assertEqual(recent["briefs"][0]["memory"]["relevant_memories"][0]["fact_id"], "mem-agentic-context")
        self.assertFalse(recent["data_flow"]["writes_memory_directly"])
        workflow = service.store.get_workflow(brief["run_id"])
        self.assertEqual(workflow.status, "completed")
        self.assertEqual(len(workflow.context_packets), 1)
        self.assertEqual(workflow.metadata["agentic_context_brief"]["brief_id"], brief["brief_id"])
        self.assertEqual(service.store.list_reviews(status="pending"), [])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("agentic_context.brief.build", actions)
        self.assertIn("memory.search", actions)
        self.assertEqual(specialists["schema"], "pska.agentic_specialist_profile_list.v1")
        self.assertFalse(specialists["data_flow"]["runs_tools"])
        self.assertIn("memory_curator", set(specialists["selected_profile_ids"]))
        self.assertEqual(answer_proofs["schema"], "pska.hermes_answer_proof_list.v1")
        self.assertFalse(answer_proofs["data_flow"]["writes_memory_directly"])

    def test_alpha_readiness_tool_reports_product_trial_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            _ingest_text(
                tools,
                temp_dir,
                name="alpha-readiness.txt",
                text="Alpha readiness should report whether PSKA is safe for technical trial.",
            )
            result = tools["pska_alpha_readiness"]()

        checks = {check["code"]: check for check in result["checks"]}
        self.assertEqual(result["schema"], "pska.alpha_readiness.v1")
        self.assertEqual(result["status"], "technical_alpha")
        self.assertEqual(result["summary"]["required_failure_count"], 0)
        self.assertEqual(checks["provider_configuration"]["status"], "warn")
        self.assertEqual(checks["source_safety"]["status"], "pass")
        self.assertEqual(checks["memory_governance"]["status"], "pass")
        self.assertEqual(checks["user_trial_ux"]["status"], "pass")
        self.assertIn("guided_trial_plan", checks["user_trial_ux"]["evidence"]["implemented"])
        self.assertTrue(checks["user_trial_ux"]["evidence"]["does_not_execute_trial_steps"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertIn("configure_live_providers", [action["action"] for action in result["next_actions"]])

    def test_alpha_trial_guide_tool_turns_readiness_into_guided_first_run(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            _ingest_text(
                tools,
                temp_dir,
                name="alpha-guide.txt",
                text="Alpha trial guide should turn readiness into guarded user trial steps.",
            )
            result = tools["pska_alpha_trial_guide"]()

        phases = {phase["phase_id"]: phase for phase in result["phases"]}
        actions = {action["action"]: action for action in result["next_actions"]}
        self.assertEqual(result["schema"], "pska.alpha_trial_guide.v1")
        self.assertEqual(result["readiness_status"], "technical_alpha")
        self.assertEqual(result["trial_mode"], "guided_technical_alpha")
        self.assertTrue(result["can_start_owner_dogfooding"])
        self.assertTrue(result["can_start_guided_trial"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["executes_trial_steps"])
        self.assertEqual(result["first_run_scope"]["permission_mode"], "read_only")
        self.assertIn("full_disk_scan", result["first_run_scope"]["avoid_on_first_run"])
        self.assertEqual(phases["knowledge_scope"]["status"], "ready")
        self.assertEqual(phases["first_read_only_run"]["status"], "ready")
        self.assertEqual(phases["memory_review"]["status"], "ready")
        self.assertEqual(phases["writeback_pilot"]["status"], "needs_attention")
        self.assertIn("configure_live_providers", actions)
        self.assertIn("keep_writeback_locked", actions)
        self.assertEqual(actions["keep_writeback_locked"]["tool"], "pska_alpha_recovery_plan")

    def test_alpha_recovery_plan_tool_reports_backup_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            _ingest_text(
                tools,
                temp_dir,
                name="alpha-recovery.txt",
                text="Alpha recovery plan should describe backups without executing them.",
            )
            result = tools["pska_alpha_recovery_plan"]()

        items = {item["item_id"]: item for item in result["backup_items"]}
        actions = {action["action"]: action for action in result["next_actions"]}
        self.assertEqual(result["schema"], "pska.alpha_recovery_plan.v1")
        self.assertEqual(result["providers"]["kb"], "fake")
        self.assertIn("review_store", items)
        self.assertIn("source_registry", items)
        self.assertIn("user_source_roots", items)
        self.assertEqual(items["review_store"]["kind"], "sqlite")
        self.assertEqual(items["user_source_roots"]["owner"], "user")
        self.assertFalse(result["data_flow"]["creates_backup"])
        self.assertFalse(result["data_flow"]["restores_data"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertIn("backup_pska_local_state", actions)
        self.assertTrue(any(item["operation"] == "obsidian_moc" for item in result["writeback_preflight"]))

    def test_alpha_first_run_session_tool_persists_checklist_progress_only(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            _ingest_text(
                tools,
                temp_dir,
                name="alpha-first-run.txt",
                text="Alpha first-run session should persist checklist decisions.",
            )
            session = tools["pska_alpha_first_run_session"]()
            updated = tools["pska_alpha_first_run_item_update"](
                "confirm_runtime",
                "done",
                note="diagnostics checked",
            )
            reloaded = tools["pska_alpha_first_run_session"]()

        item = {row["item_id"]: row for row in updated["checklist"]}["confirm_runtime"]
        self.assertEqual(session["schema"], "pska.alpha_first_run_session.v1")
        self.assertEqual(updated["status"], "in_progress")
        self.assertEqual(item["status"], "done")
        self.assertEqual(item["note"], "diagnostics checked")
        self.assertTrue(updated["data_flow"]["writes_checklist_state"])
        self.assertFalse(updated["data_flow"]["writes_source_files"])
        self.assertFalse(updated["data_flow"]["writes_memory_directly"])
        self.assertFalse(updated["data_flow"]["executes_trial_step"])
        self.assertEqual({row["item_id"]: row for row in reloaded["checklist"]}["confirm_runtime"]["status"], "done")
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("alpha.first_run_session.create", actions)
        self.assertIn("alpha.first_run_session.update", actions)

    def test_memory_review_from_workflow_turns_transient_run_into_review(self):
        service = build_fake_service()
        tools = tool_registry(service)
        run = tools["pska_workflow_start"]("transient first", {"dataset_ids": ["demo"]})
        tools["pska_context_retrieve"]("adapter review", run_id=run["run_id"], limit=1)
        tools["pska_propose"](run["run_id"], "writing_brief", "transient first")

        created = tools["pska_memory_review_from_workflow"](run["run_id"], "remember reviewed source")

        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["governance"]["action"], "manual_review")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertEqual(created["review"]["source_count"], 1)
        self.assertEqual(created["artifact"]["latest_proposal"]["kind"], "memory_patch")
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("proposal.create", actions)
        self.assertIn("review.create", actions)

    def test_eidolia_thought_can_be_promoted_to_memory_review(self):
        service = build_fake_service()
        tools = tool_registry(service)

        context = tools["pska_eidolia_context_read"](
            project_id="novel-x",
            node_id="thought-1",
            node_type="thought",
            text="PSKA should keep Eidolia thought and artifact nodes as the canvas primitives.",
            title="Canvas primitives",
            canvas_path="boards/novel-x.canvas",
            role="decision",
        )
        created = tools["pska_eidolia_memory_review_create"](
            project_id="novel-x",
            node_id="thought-1",
            node_type="thought",
            text="Eidolia keeps thought and artifact as its only user-visible node types.",
            behavior_delta="When discussing Eidolia architecture, keep thought/artifact as the canvas primitives.",
            title="Canvas primitives",
            canvas_path="boards/novel-x.canvas",
            role="decision",
            memory_type="project_state",
            memory_scope="project",
            reason="stable Eidolia ontology decision",
        )

        self.assertEqual(context["schema"], "pska.eidolia_context.v1")
        self.assertEqual(context["source_ref"]["adapter"], "eidolia")
        self.assertEqual(context["source_ref"]["metadata"]["node_type"], "thought")
        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertIsNone(created["memory_apply"])
        self.assertEqual(created["memory_card"]["source_origin"], "eidolia")
        self.assertEqual(created["memory_card"]["source_refs"][0]["adapter"], "eidolia")
        self.assertEqual(created["eidolia"]["project_id"], "novel-x")
        self.assertEqual(created["eidolia"]["node_id"], "thought-1")
        self.assertEqual(created["artifact"]["traceability"]["source_count"], 1)
        trace = tools["pska_trace_query"](source_ref=context["source_ref"], limit=20)
        self.assertEqual(trace["schema"], "pska.trace_query.v1")
        self.assertEqual(trace["status"], "found")
        self.assertGreaterEqual(trace["summary"]["review_count"], 1)
        self.assertFalse(trace["data_flow"]["writes_source_files"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("eidolia.context.read", actions)
        self.assertIn("eidolia.memory_review.create", actions)

    def test_eidolia_project_trace_import_tool_reads_project_files_without_memory_writes(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "novel-x"
            trace_dir = project_dir / "agentic-traces"
            trace_dir.mkdir(parents=True)
            (project_dir / "canvas-workspace.json").write_text(
                json.dumps(
                    {
                        "projectId": "novel-x",
                        "nodes": [
                            {
                                "id": "thought-1",
                                "type": "thought",
                                "data": {"kind": "thought", "title": "Decision", "content": "Keep thought/artifact small."},
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (trace_dir / "trace-1.json").write_text(
                json.dumps(
                    {
                        "kind": "thought_candidate",
                        "run_id": "trace-1",
                        "project_id": "novel-x",
                        "start_node_id": "thought-1",
                        "content": "Small ontology.",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = tools["pska_eidolia_project_trace_import"](project_path=str(project_dir))

        self.assertEqual(result["schema"], "pska.eidolia_project_trace_import.v1")
        self.assertEqual(result["summary"]["imported_node_count"], 1)
        self.assertEqual(result["summary"]["imported_trace_count"], 1)
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        trace = tools["pska_trace_query"](source_ref=result["nodes"][0]["source_ref"], limit=10)
        self.assertEqual(trace["status"], "found")
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("eidolia.project_trace.import", actions)

    def test_memory_change_from_conversation_tool_auto_applies(self):
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {}, clear=True):
            result = tools["pska_memory_change_from_conversation"](
                user_message="Remember that my editor is Vim.",
                text="The user's editor is Vim.",
                session_id="sess-tool",
                message_id="msg-tool",
            )

        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["operation"], "memory_patch")
        self.assertEqual(result["governance"]["origin"], "conversation")
        self.assertEqual(result["conversation"]["source_refs"][0]["adapter"], "hermes")
        self.assertEqual(len(service.memory_search("Vim", {}, 10)), 1)

    def test_conversation_memory_candidates_tool_creates_pending_reviews(self):
        service = build_fake_service()
        tools = tool_registry(service)

        result = tools["pska_conversation_memory_candidates_create"](
            messages=[
                {
                    "message_id": "msg-tool-candidate",
                    "role": "user",
                    "text": "When designing PSKA, prefer small object models and explicit trace.",
                }
            ],
            candidates=[
                {
                    "text": "The user prefers small object models and explicit trace when designing PSKA.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When discussing PSKA design, prefer small object models and explicit trace.",
                    "message_ids": ["msg-tool-candidate"],
                }
            ],
            session_id="sess-tool-candidates",
        )

        self.assertEqual(result["schema"], "pska.conversation_memory_candidates.v1")
        self.assertEqual(result["created_count"], 1)
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertEqual(service.store.list_reviews(status="pending")[0]["review_id"], result["created"][0]["review_id"])
        self.assertEqual(len(service.memory_search("small object models", {}, 10)), 0)

    def test_memory_change_from_conversation_tool_returns_needs_target(self):
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {}, clear=True):
            result = tools["pska_memory_change_from_conversation"](
                user_message="Forget that my favorite tea is oolong.",
                operation="forget",
                session_id="sess-tool",
                message_id="msg-tool-missing-target",
            )

        self.assertEqual(result["status"], "needs_target")
        self.assertEqual(result["operation"], "memory_delete")
        self.assertEqual(result["target_resolution"]["status"], "not_found")
        self.assertEqual(result["next_actions"][0]["tool"], "pska_memory_search")
        self.assertIsNone(result["proposal"])
        self.assertEqual(service.store.list_reviews(status="pending"), [])

    def test_review_revise_creates_new_pending_review_from_needs_edit(self):
        service = build_fake_service()
        tools = tool_registry(service)
        run = tools["pska_workflow_start"]("needs revision", {"dataset_ids": ["demo"]})
        tools["pska_context_retrieve"]("adapter review", run_id=run["run_id"], limit=1)
        proposal = tools["pska_propose"](run["run_id"], "memory_patch", "needs revision")
        review = tools["pska_review_create"](proposal["proposal_id"])
        tools["pska_review_decide"](review["review_id"], "edit", "revise it")

        revised = tools["pska_review_revise"](review["review_id"], "revised memory")

        self.assertEqual(revised["previous_review"]["status"], "needs_edit")
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertNotEqual(revised["review"]["review_id"], review["review_id"])
        self.assertEqual(revised["proposal"]["kind"], "memory_patch")
        self.assertEqual(revised["previous_review"]["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(revised["review"]["revision"]["previous_review_id"], review["review_id"])
        old_record = tools["pska_review_get"](review["review_id"])
        new_record = tools["pska_review_get"](revised["review"]["review_id"])
        self.assertEqual(old_record["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(new_record["revision"]["previous_review_id"], review["review_id"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("review.revise", actions)

    def test_review_revise_accepts_memory_candidate_edits(self):
        service = build_fake_service()
        tools = tool_registry(service)
        result = tools["pska_conversation_memory_candidates_create"](
            messages=[
                {
                    "message_id": "msg-tool-candidate-revise",
                    "role": "user",
                    "text": "When PSKA reviews memory, prefer crisp behavior deltas.",
                }
            ],
            candidates=[
                {
                    "text": "The user prefers crisp behavior deltas for PSKA memory.",
                    "memory_type": "working_habit",
                    "memory_scope": "project",
                    "behavior_delta": "When reviewing PSKA memory, keep behavior deltas crisp.",
                    "message_ids": ["msg-tool-candidate-revise"],
                }
            ],
            session_id="sess-tool-candidate-revise",
        )
        review_id = result["created"][0]["review_id"]
        tools["pska_review_decide"](review_id, "edit", "revise candidate fields")

        revised = tools["pska_review_revise"](
            review_id,
            "manual candidate edit",
            memory_candidate={
                "text": "For PSKA memory, prefer crisp behavior-changing candidate text.",
                "memory_type": "preference",
                "memory_scope": "workspace",
                "behavior_delta": "When revising PSKA memory candidates, keep the future behavior change explicit.",
            },
        )

        patch = revised["proposal"]["memory_patch"]
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertEqual(patch["text"], "For PSKA memory, prefer crisp behavior-changing candidate text.")
        self.assertEqual(patch["metadata"]["memory_type"], "preference")
        self.assertEqual(patch["metadata"]["memory_scope"], "workspace")
        self.assertEqual(patch["metadata"]["revision_mode"], "memory_candidate")
        self.assertEqual(patch["source_refs"][0]["adapter"], "hermes")

    def test_review_decide_batch_tool_accepts_candidates(self):
        service = build_fake_service()
        tools = tool_registry(service)
        result = tools["pska_conversation_memory_candidates_create"](
            messages=[
                {"message_id": "msg-tool-batch-1", "role": "user", "text": "Remember tool batch candidate one."},
                {"message_id": "msg-tool-batch-2", "role": "user", "text": "Remember tool batch candidate two."},
            ],
            candidates=[
                {
                    "text": "Tool batch candidate one should be reviewed.",
                    "memory_type": "project_state",
                    "memory_scope": "project",
                    "behavior_delta": "When reviewing tool batch candidates, inspect candidate one.",
                    "message_ids": ["msg-tool-batch-1"],
                },
                {
                    "text": "Tool batch candidate two should be reviewed.",
                    "memory_type": "project_state",
                    "memory_scope": "project",
                    "behavior_delta": "When reviewing tool batch candidates, inspect candidate two.",
                    "message_ids": ["msg-tool-batch-2"],
                },
            ],
            session_id="sess-tool-batch",
        )
        review_ids = [item["review_id"] for item in result["created"]]

        batch = tools["pska_review_decide_batch"](review_ids, "accept", "batch accept")

        self.assertEqual(batch["schema"], "pska.review_decide_batch.v1")
        self.assertEqual(batch["decided_count"], 2)
        self.assertEqual(tools["pska_review_get"](review_ids[0])["status"], "accepted")
        self.assertEqual(tools["pska_review_get"](review_ids[1])["status"], "accepted")
        self.assertFalse(batch["data_flow"]["writes_memory_directly"])

    def test_review_merge_candidates_tool_creates_merged_review(self):
        service = build_fake_service()
        tools = tool_registry(service)
        first = service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route one",
        )
        second = service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture-v2", path="Architecture.md")],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route two",
        )
        review_ids = [first["review"]["review_id"], second["review"]["review_id"]]

        merged = tools["pska_review_merge_candidates"](
            review_ids,
            memory_candidate={
                "text": "When this workspace asks about PSKA architecture, inspect Architecture.md first.",
                "memory_type": "source_route",
                "memory_scope": "project",
                "behavior_delta": "Route future PSKA architecture questions to Architecture.md before broad search.",
            },
            reason="merge duplicate route candidates",
        )

        self.assertEqual(merged["schema"], "pska.review_merge_candidates.v1")
        self.assertEqual(merged["review"]["status"], "pending")
        self.assertEqual(merged["review"]["revision"]["merged_from_review_ids"], review_ids)
        self.assertEqual(merged["proposal"]["memory_patch"]["metadata"]["merged_review_ids"], review_ids)
        self.assertEqual(tools["pska_review_get"](review_ids[0])["status"], "needs_edit")
        self.assertEqual(
            tools["pska_review_get"](review_ids[0])["revision"]["merged_into_review_id"],
            merged["review"]["review_id"],
        )
        self.assertFalse(merged["data_flow"]["writes_memory_directly"])

    def test_agentic_question_start_prepares_reviewed_workflow(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            ingested = _ingest_texts(
                tools,
                temp_dir,
                files={
                    "workflow-gate.txt": "The workflow gate retrieves context and prepares reviewed memory candidates.",
                    "adapter-boundary.txt": "Adapter Boundary keeps provider payloads behind PSKA contracts.",
                },
                dataset_name="MCP Agentic Question",
            )
            dataset_id = ingested["dataset"]["dataset_id"]

            result = tools["pska_agentic_question_start"](
                question="How does the workflow gate work?",
                dataset_ids=[dataset_id],
                limit=1,
                max_iterations=2,
                min_context_packets=2,
                retrieval_queries=["Adapter Boundary"],
                source_inspection_limit=1,
                proposal_kind="memory_patch",
            )
        self.assertEqual(len(result["context_packets"]), 2)
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertEqual(result["loop"]["retrieval_query_plan"][1], "Adapter Boundary")
        self.assertEqual(result["run"]["metadata"]["ask_request"]["retrieval_queries"], ["Adapter Boundary"])
        self.assertEqual(result["run"]["metadata"]["ask_request"]["source_inspection_limit"], 1)
        source_step = next(step for step in result["loop"]["steps"] if step["name"] == "source.inspect")
        self.assertEqual(source_step["metadata"]["inspected_count"], 1)
        self.assertIn("kb.readiness", [step["name"] for step in result["loop"]["steps"]])
        self.assertIn("pska_memory_change_from_conversation", result["note"])

    def test_agentic_question_start_accepts_model_context_budget(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            tools = tool_registry(build_service_from_env())
            ingested = _ingest_texts(
                tools,
                temp_dir,
                files={
                    "budget-a.txt": "Budget tool context A.",
                    "budget-b.txt": "Budget tool context B.",
                    "budget-c.txt": "Budget tool context C.",
                },
                dataset_name="MCP Budget Question",
            )
            dataset_id = ingested["dataset"]["dataset_id"]

            result = tools["pska_agentic_question_start"](
                question="Budget tool context",
                dataset_ids=[dataset_id],
                limit=5,
                max_iterations=1,
                min_context_packets=1,
                source_inspection_limit=2,
                model_context_tokens=2048,
                model_profile="mcp-small",
            )

        budget = result["loop"]["context_budget"]
        self.assertEqual(budget["mode"], "model_context")
        self.assertEqual(budget["model_profile"], "mcp-small")
        self.assertEqual(budget["effective_retrieval_limit"], 1)
        self.assertEqual(result["run"]["metadata"]["ask_request"]["model_context_tokens"], 2048)

    def test_digest_scope_tool_creates_digest_and_optional_memory_review(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="digest-note.txt",
                text="Digestable source says durable summaries should remain governed.",
                dataset_name="MCP Digest Scope",
            )

            result = tools["pska_digest_scope"](
                dataset_ids=[ingested["dataset"]["dataset_id"]],
                question="Digest the uploaded source",
                limit=1,
                source_inspection_limit=0,
                create_memory_review=True,
            )

        self.assertEqual(result["kind"], "digest_scope")
        self.assertEqual(result["digest"]["kind"], "digest")
        self.assertEqual(result["memory_review"]["review"]["status"], "pending")
        self.assertEqual(result["memory_review"]["governance"]["origin"], "digest")
        self.assertIn("does not write Graphiti memory directly", result["note"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("digest.scope", actions)

    def test_digest_job_tools_queue_and_run_ready_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="digest-job-note.txt",
                text="Queued digest source says background digest must remain governed.",
                dataset_name="MCP Digest Job",
            )
            dataset_id = ingested["dataset"]["dataset_id"]

            queued = tools["pska_digest_job_enqueue"](
                dataset_ids=[dataset_id],
                question="Digest queued source",
                priority=5,
                limit=1,
                source_inspection_limit=0,
                create_memory_review=True,
            )
            jobs = tools["pska_digest_job_list"](status="queued", limit=5)
            result = tools["pska_digest_job_run"]()

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(jobs[0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["digest_result"]["memory_review"]["governance"]["origin"], "digest")
        self.assertIn("respects KB readiness", result["note"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("digest.job.enqueue", actions)
        self.assertIn("digest.job.run", actions)

    def test_agentic_question_start_blocks_unready_scope(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            result = tools["pska_agentic_question_start"](
                question="Can I ask this missing dataset?",
                dataset_ids=["missing-dataset"],
                limit=1,
            )
        self.assertEqual(result["status"], "not_ready")
        self.assertIsNotNone(result["run"])
        self.assertEqual(result["run"]["status"], "blocked")
        self.assertEqual(result["context_packets"], [])
        self.assertEqual(result["artifact"]["traceability"]["context_count"], 0)
        self.assertEqual(result["artifact"]["traceability"]["proposal_count"], 0)
        self.assertIn("not ready", result["note"])
        listed = tools["pska_workflow_list"](limit=1)
        self.assertEqual(listed[0]["run_id"], result["run"]["run_id"])
        recovered = tools["pska_workflow_artifact"](result["run"]["run_id"])
        self.assertEqual(recovered["run"]["metadata"]["agentic_loop"]["status"], "not_ready")
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("agentic_loop.not_ready", audit_actions)
        self.assertIn("kb.readiness.blocked", audit_actions)

    def test_agentic_question_resume_uses_persisted_ask_request(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", _fake_env(), clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()
            tools = tool_registry(service)
            ingested = _ingest_text(
                tools,
                temp_dir,
                name="resume-ask.txt",
                text="Resumed Ask should use the persisted request once uploaded context is ready.",
                parse=False,
            )
            dataset_id = ingested["dataset"]["dataset_id"]
            document_id = ingested["documents"][0]["document_id"]
            run = service.start("Resume this Ask", {"dataset_ids": [dataset_id], "document_ids": [], "use_kg": False})
            run.status = "blocked"
            run.metadata["blocked_reason"] = "kb_not_ready"
            run.metadata["ask_request"] = {
                "question": "Resume this Ask",
                "dataset_ids": [dataset_id],
                "document_ids": [],
                "use_kg": False,
                "limit": 1,
                "proposal_kind": "writing_brief",
                "create_review": None,
                "max_iterations": 1,
                "min_context_packets": 1,
                "retrieval_queries": ["resume query"],
                "source_inspection_limit": 0,
            }
            service.store.save_workflow(run)
            tools["pska_kb_parse_documents"](dataset_id, [document_id], wait=True)
            resumable = tools["pska_agentic_question_resumable"](limit=5)
            resumed = tools["pska_agentic_question_resume"](run.run_id)

        self.assertEqual(resumable[0]["run"]["run_id"], run.run_id)
        self.assertTrue(resumable[0]["can_resume"])
        self.assertEqual(resumable[0]["resume"]["tool"], "pska_agentic_question_resume")
        self.assertEqual(resumable[0]["resume"]["api"], f"POST /api/workflows/{run.run_id}/resume-ask")
        self.assertTrue(resumable[0]["resume"]["can_resume"])
        self.assertEqual(resumable[0]["next_actions"][-1]["action"], "resume_blocked_ask")
        self.assertEqual(resumable[0]["ask_request"]["question"], "Resume this Ask")
        self.assertEqual(resumed["status"], "ready")
        self.assertNotEqual(resumed["run"]["run_id"], run.run_id)
        self.assertEqual(resumed["resumed_from_run_id"], run.run_id)
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["question"], "Resume this Ask")
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["retrieval_queries"], ["resume query"])
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["source_inspection_limit"], 0)
        self.assertEqual(resumed["run"]["metadata"]["resumed_from_run_id"], run.run_id)
        self.assertIn("Resumed Ask created", resumed["note"])
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("agentic_loop.resume", audit_actions)

    def test_kb_tools_write_source_operation_audit_records(self):
        service = build_fake_service()
        tools = tool_registry(service)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "note.txt"
            path.write_text("PSKA source material", encoding="utf-8")
            with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
                created = tools["pska_kb_create"](
                    "MCP Dataset",
                    embedding_model="text-embedding-3-small@OpenAI",
                )
                ingested = tools["pska_kb_ingest_files"]([str(path)], dataset_name="MCP Dataset", parse=True)
                dataset_id = ingested["dataset"]["dataset_id"]
                document_id = ingested["documents"][0]["document_id"]
                ingestion_status = tools["pska_kb_ingestion_status"](
                    [dataset_id],
                    [document_id],
                )
                parsed = tools["pska_kb_parse_documents"](dataset_id, [document_id])
                graph = tools["pska_kb_graph_read"](dataset_id, document_id)
                deleted = tools["pska_kb_delete"](dataset_names=["MCP Dataset"])

        self.assertTrue(created["dataset_id"].startswith("fake_ds_"))
        self.assertEqual(created["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(ingested["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(ingested["documents"][0]["name"], "note.txt")
        self.assertEqual(ingested["ingestion_status"]["status"], "ready")
        self.assertTrue(ingested["readiness"]["ready"])
        self.assertIn("Upload accepted", ingested["note"])
        self.assertEqual(ingestion_status["ingestion_status"]["status"], "ready")
        self.assertIn("readiness.ready", ingestion_status["note"])
        self.assertTrue(parsed["parse_started"])
        self.assertEqual(parsed["ingestion_status"]["status"], "ready")
        self.assertIn("Parse started", parsed["note"])
        self.assertEqual(graph["document_id"], document_id)
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["dataset_names"], ["MCP Dataset"])
        self.assertEqual(deleted["dataset_ids"], [created["dataset_id"]])
        events = service.store.list_audit_events()
        actions = [event.action for event in events]
        self.assertIn("kb.dataset.create", actions)
        self.assertIn("kb.dataset.delete", actions)
        self.assertIn("kb.ingest", actions)
        self.assertIn("kb.parse", actions)
        self.assertIn("kb.graph.read", actions)
        create_event = next(event for event in events if event.action == "kb.dataset.create")
        self.assertEqual(create_event.target_id, created["dataset_id"])
        ingest_event = next(event for event in events if event.action == "kb.ingest")
        self.assertEqual(ingest_event.metadata["document_names"], ["note.txt"])
        graph_event = next(event for event in events if event.action == "kb.graph.read")
        self.assertEqual(graph_event.metadata["dataset_id"], dataset_id)
        self.assertEqual(graph_event.metadata["document_id"], document_id)
        delete_event = next(event for event in events if event.action == "kb.dataset.delete")
        self.assertEqual(delete_event.target_id, created["dataset_id"])


def _fake_env() -> dict[str, str]:
    return {
        "PSKA_DEV_FAKE": "1",
        "PSKA_RETRIEVAL_PROVIDER": "fake",
        "PSKA_KB_PROVIDER": "fake",
        "PSKA_MEMORY_PROVIDER": "fake",
        "PSKA_REVIEW_DB": ":memory:",
    }


def _ingest_text(
    tools,
    temp_dir: str,
    *,
    name: str,
    text: str,
    dataset_name: str = "MCP Uploaded Source",
    parse: bool = True,
):
    return _ingest_texts(tools, temp_dir, files={name: text}, dataset_name=dataset_name, parse=parse)


def _ingest_texts(tools, temp_dir: str, *, files: dict[str, str], dataset_name: str, parse: bool = True):
    paths = []
    for name, text in files.items():
        path = Path(temp_dir) / name
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    return tools["pska_kb_ingest_files"](paths, dataset_name=dataset_name, parse=parse)


if __name__ == "__main__":
    unittest.main()
