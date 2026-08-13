from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pska_essential.eidolia_import import import_eidolia_project_traces
from pska_essential.trace_query import build_trace_query
from pska_essential.workflow import build_fake_service


class EidoliaImportTests(unittest.TestCase):
    def test_imports_project_workspace_and_agentic_traces_as_audit_refs(self):
        service = build_fake_service()
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
                                "data": {
                                    "kind": "thought",
                                    "title": "Canvas primitives",
                                    "content": "Keep Eidolia user-visible objects to thought and artifact.",
                                    "role": "decision",
                                },
                            },
                            {
                                "id": "artifact-1",
                                "type": "note",
                                "data": {
                                    "kind": "artifact",
                                    "subtype": "evidence",
                                    "title": "Evidence card",
                                    "content": "Evidence should stay as artifact nodes.",
                                },
                            },
                            {"id": "operator-1", "type": "generator", "data": {"kind": "operator"}},
                        ],
                        "edges": [
                            {
                                "id": "e1",
                                "source": "thought-1",
                                "target": "artifact-1",
                                "data": {"relation": "supports"},
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            trace_path = trace_dir / "trace-1.json"
            trace_path.write_text(
                json.dumps(
                    {
                        "kind": "thought_candidate",
                        "run_id": "run-eidolia-1",
                        "title": "Canvas primitives refined",
                        "project_id": "novel-x",
                        "start_node_id": "thought-1",
                        "derived_from_node_ids": ["thought-1"],
                        "supporting_node_ids": ["artifact-1"],
                        "content": "Thought/artifact should remain the two visible primitives.",
                        "created_at": "2026-08-13T00:00:00Z",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = import_eidolia_project_traces(service, project_path=str(project_dir))

        self.assertEqual(result["schema"], "pska.eidolia_project_trace_import.v1")
        self.assertEqual(result["status"], "imported")
        self.assertEqual(result["summary"]["workspace_node_count"], 3)
        self.assertEqual(result["summary"]["imported_node_count"], 2)
        self.assertEqual(result["summary"]["imported_edge_count"], 1)
        self.assertEqual(result["summary"]["imported_trace_count"], 1)
        self.assertEqual(result["nodes"][0]["source_ref"]["adapter"], "eidolia")
        self.assertEqual(result["nodes"][0]["node_type"], "thought")
        self.assertEqual(result["nodes"][1]["artifact_kind"], "evidence")
        self.assertEqual(result["traces"][0]["trace_id"], "run-eidolia-1")
        self.assertEqual(result["traces"][0]["linked_node_ids"], ["thought-1", "artifact-1"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("eidolia.project_trace.import", actions)
        self.assertIn("eidolia.node.import", actions)
        self.assertIn("eidolia.agentic_trace.import", actions)
        trace = build_trace_query(service, source_ref=result["nodes"][0]["source_ref"], audit=False)
        self.assertEqual(trace["status"], "found")
        self.assertGreaterEqual(trace["entry_count"], 2)


if __name__ == "__main__":
    unittest.main()
