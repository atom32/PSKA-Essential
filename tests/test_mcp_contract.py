from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.config import build_service_from_env
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
    "pska_context_retrieve",
    "pska_source_read",
    "pska_policy_get",
    "pska_capabilities_get",
    "pska_component_check",
    "pska_ingest_loop",
    "pska_ingest_loop_resume",
    "pska_propose",
    "pska_runtime_diagnostics",
    "pska_review_create",
    "pska_review_list",
    "pska_review_get",
    "pska_review_decide",
    "pska_review_revise",
    "pska_memory_search",
    "pska_memory_apply",
    "pska_memory_delete_review",
    "pska_memory_lifecycle",
    "pska_memory_probe",
    "pska_memory_review_from_workflow",
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

    def test_component_check_tool_returns_structured_acceptance_result(self):
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            reset_fake_kb_gateway()
            result = tools["pska_component_check"](
                question="Can the configured components answer?",
                dataset_ids=["demo"],
                require_memory=False,
                run_closed_loop=False,
            )

        self.assertEqual(result["status"], "incomplete")
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
        self.assertTrue(capabilities["memory"]["operations"]["update"]["supported"])
        self.assertTrue(capabilities["memory"]["operations"]["delete"]["supported"])
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
        facts = tools["pska_memory_search"]("mcp memory", {}, 10)
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
        service = build_fake_service()
        tools = tool_registry(service)

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            probe = tools["pska_retrieval_probe"](
                question="Can retrieval answer?",
                dataset_ids=["demo"],
                limit=1,
            )

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["provider"], "fake")
        self.assertEqual(probe["scope"]["dataset_ids"], ["demo"])
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
        tools = tool_registry(build_fake_service())

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            reset_fake_kb_gateway()
            status = tools["pska_workspace_status"]()

        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertIn("demo", status["next_actions"][0]["params"]["dataset_ids"])

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

    def test_agentic_question_start_prepares_reviewed_workflow(self):
        tools = tool_registry(build_fake_service())
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            result = tools["pska_agentic_question_start"](
                question="How does the workflow gate work?",
                dataset_ids=["demo"],
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
        self.assertIn("Memory changes still require", result["note"])

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
        service = build_fake_service()
        run = service.start("Resume this Ask", {"dataset_ids": ["demo"], "document_ids": [], "use_kg": False})
        run.status = "blocked"
        run.metadata["blocked_reason"] = "kb_not_ready"
        run.metadata["ask_request"] = {
            "question": "Resume this Ask",
            "dataset_ids": ["demo"],
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
        tools = tool_registry(service)

        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            resumable = tools["pska_agentic_question_resumable"](limit=5)
            resumed = tools["pska_agentic_question_resume"](run.run_id)

        self.assertEqual(resumable[0]["run"]["run_id"], run.run_id)
        self.assertTrue(resumable[0]["can_resume"])
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
                ingestion_status = tools["pska_kb_ingestion_status"](
                    [ingested["dataset"]["dataset_id"]],
                    [ingested["documents"][0]["document_id"]],
                )
                parsed = tools["pska_kb_parse_documents"]("demo", ["demo-1"])
                graph = tools["pska_kb_graph_read"]("demo", "demo-1")
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
        self.assertEqual(graph["document_id"], "demo-1")
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
        self.assertEqual(graph_event.metadata["dataset_id"], "demo")
        self.assertEqual(graph_event.metadata["document_id"], "demo-1")
        delete_event = next(event for event in events if event.action == "kb.dataset.delete")
        self.assertEqual(delete_event.target_id, created["dataset_id"])


if __name__ == "__main__":
    unittest.main()
