from __future__ import annotations

import unittest

from pska_essential.audit import audit_event
from pska_essential.trace_query import TraceQueryError, build_trace_query
from pska_essential.workflow import build_fake_service


class TraceQueryTests(unittest.TestCase):
    def test_eidolia_source_ref_traces_context_and_review_without_embeddings(self):
        service = build_fake_service()
        context = service.eidolia_context_read(
            project_id="novel-x",
            node_id="thought-1",
            node_type="thought",
            text="PSKA should keep Eidolia thought and artifact nodes as canvas primitives.",
            title="Canvas primitives",
            canvas_path="boards/novel-x.canvas",
            role="decision",
        )
        created = service.eidolia_memory_review_create(
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

        result = build_trace_query(service, source_ref=context["source_ref"], audit=False)
        entry_types = {entry["entry_type"] for entry in result["entries"]}
        actions = {
            entry["evidence"].get("action")
            for entry in result["entries"]
            if entry["entry_type"] == "audit_event"
        }

        self.assertEqual(result["schema"], "pska.trace_query.v1")
        self.assertEqual(result["status"], "found")
        self.assertIn("audit_event", entry_types)
        self.assertIn("review_record", entry_types)
        self.assertIn("eidolia.context.read", actions)
        self.assertEqual(result["summary"]["review_count"], 1)
        self.assertIn(created["review"]["review_id"], result["entries"][0]["review_ids"] + result["entries"][1]["review_ids"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertFalse(result["data_flow"]["embedding_required"])

    def test_source_ref_matching_does_not_match_adapter_only(self):
        service = build_fake_service()
        service.store.add_audit_event(
            audit_event(
                "eidolia.context.read",
                "eidolia_node",
                "thought-1",
                project_id="novel-x",
                node_id="thought-1",
            )
        )

        result = build_trace_query(
            service,
            source_ref={"adapter": "eidolia", "source_id": "novel-y", "external_id": "thought-2"},
            audit=False,
        )

        self.assertEqual(result["status"], "empty")
        self.assertEqual(result["entry_count"], 0)

    def test_requires_at_least_one_selector(self):
        service = build_fake_service()

        with self.assertRaises(TraceQueryError):
            build_trace_query(service, audit=False)

    def test_trace_query_records_audit_event(self):
        service = build_fake_service()
        service.store.add_audit_event(audit_event("review.create", "review", "rev-demo", review_id="rev-demo"))

        result = build_trace_query(service, review_id="rev-demo")

        event = service.store.list_audit_events(action="trace.query")[0]
        self.assertEqual(result["status"], "found")
        self.assertEqual(event.target_id, "rev-demo")
        self.assertEqual(event.metadata["entry_count"], result["entry_count"])
        self.assertFalse(event.metadata["writes_memory_directly"])


if __name__ == "__main__":
    unittest.main()
