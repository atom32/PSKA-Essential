from __future__ import annotations

import unittest
from unittest.mock import patch

from pska_essential.mcp_server import tool_registry
from pska_essential.workflow import build_fake_service


EXPECTED_TOOLS = {
    "pska_agentic_question_start",
    "pska_workflow_start",
    "pska_workflow_state",
    "pska_workflow_artifact",
    "pska_workflow_brief",
    "pska_context_retrieve",
    "pska_source_read",
    "pska_propose",
    "pska_review_create",
    "pska_review_decide",
    "pska_memory_search",
    "pska_memory_apply",
    "pska_export_brief",
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
        packets = tools["pska_context_retrieve"]("adapter review", run_id=run["run_id"], limit=1)
        self.assertEqual(len(packets), 1)
        proposal = tools["pska_propose"](run["run_id"], "memory_patch", "mcp memory")
        artifact = tools["pska_workflow_artifact"](run["run_id"])
        brief = tools["pska_workflow_brief"](run["run_id"], "markdown")
        self.assertEqual(artifact["latest_proposal"]["proposal_id"], proposal["proposal_id"])
        self.assertIn("PSKA-Essential Brief", brief)
        self.assertNotIn("workflow.export", [event.action for event in service.store.list_audit_events()])
        review = tools["pska_review_create"](proposal["proposal_id"])
        tools["pska_review_decide"](review["review_id"], "accept", "test")
        applied = tools["pska_memory_apply"](review["review_id"])
        self.assertTrue(applied["applied"])
        exported = tools["pska_export_brief"](run["run_id"], "markdown")
        self.assertIn("PSKA-Essential Brief", exported)
        self.assertIn("workflow.export", [event.action for event in service.store.list_audit_events()])

    def test_agentic_question_start_prepares_reviewed_workflow(self):
        tools = tool_registry(build_fake_service())
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            result = tools["pska_agentic_question_start"](
                question="How does the workflow gate work?",
                dataset_ids=["demo"],
                limit=1,
                proposal_kind="memory_patch",
            )
        self.assertEqual(len(result["context_packets"]), 1)
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertIn("kb.readiness", [step["name"] for step in result["loop"]["steps"]])
        self.assertIn("Memory writes still require", result["note"])

    def test_agentic_question_start_blocks_unready_scope(self):
        tools = tool_registry(build_fake_service())
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=False):
            result = tools["pska_agentic_question_start"](
                question="Can I ask this missing dataset?",
                dataset_ids=["missing-dataset"],
                limit=1,
            )
        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["context_packets"], [])
        self.assertIn("not ready", result["note"])


if __name__ == "__main__":
    unittest.main()
