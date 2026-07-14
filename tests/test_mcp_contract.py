from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    "pska_context_retrieve",
    "pska_source_read",
    "pska_policy_get",
    "pska_propose",
    "pska_review_create",
    "pska_review_list",
    "pska_review_get",
    "pska_review_decide",
    "pska_review_revise",
    "pska_memory_search",
    "pska_memory_apply",
    "pska_memory_delete_review",
    "pska_memory_lifecycle",
    "pska_memory_review_from_workflow",
    "pska_memory_update_review",
    "pska_export_brief",
    "pska_audit_list",
    "pska_retrieval_probe",
    "pska_eval_run",
    "pska_kb_create",
    "pska_kb_document_status",
    "pska_kb_graph_read",
    "pska_kb_ingest_files",
    "pska_kb_list",
    "pska_kb_parse_documents",
    "pska_kb_readiness",
}


class McpContractTests(unittest.TestCase):
    def test_tool_registry_contains_public_contract(self):
        tools = tool_registry(build_fake_service())
        self.assertEqual(set(tools), EXPECTED_TOOLS)

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
                proposal_kind="memory_patch",
            )
        self.assertEqual(len(result["context_packets"]), 2)
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertEqual(result["loop"]["retrieval_query_plan"][1], "Adapter Boundary")
        self.assertEqual(result["run"]["metadata"]["ask_request"]["retrieval_queries"], ["Adapter Boundary"])
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
                created = tools["pska_kb_create"]("MCP Dataset")
                ingested = tools["pska_kb_ingest_files"]([str(path)], dataset_name="MCP Dataset", parse=True)
                parsed = tools["pska_kb_parse_documents"]("demo", ["doc-1"])
                graph = tools["pska_kb_graph_read"]("demo", "doc-1")

        self.assertTrue(created["dataset_id"].startswith("fake_ds_"))
        self.assertEqual(ingested["documents"][0]["name"], "note.txt")
        self.assertTrue(parsed["parse_started"])
        self.assertEqual(graph["document_id"], "doc-1")
        events = service.store.list_audit_events()
        actions = [event.action for event in events]
        self.assertIn("kb.dataset.create", actions)
        self.assertIn("kb.ingest", actions)
        self.assertIn("kb.parse", actions)
        self.assertIn("kb.graph.read", actions)
        create_event = next(event for event in events if event.action == "kb.dataset.create")
        self.assertEqual(create_event.target_id, created["dataset_id"])
        ingest_event = next(event for event in events if event.action == "kb.ingest")
        self.assertEqual(ingest_event.metadata["document_names"], ["note.txt"])
        graph_event = next(event for event in events if event.action == "kb.graph.read")
        self.assertEqual(graph_event.metadata["dataset_id"], "demo")
        self.assertEqual(graph_event.metadata["document_id"], "doc-1")


if __name__ == "__main__":
    unittest.main()
