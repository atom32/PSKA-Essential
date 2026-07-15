from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.config import build_service_from_env
from pska_essential.kb_gateway import build_kb_gateway_from_env
from pska_essential.product_api import build_server
from pska_essential.workflow import build_fake_service


class _FakeGateway:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, str]] = []
        self.parse_calls: list[dict[str, object]] = []
        self.ready = True
        self.extra_datasets: dict[str, dict[str, object]] = {}

    def list_datasets(self, *, name=None, page_size=30):
        datasets = [
            {
                "backend": "fake-kb",
                "dataset_id": "demo",
                "name": "Demo",
                "document_count": 1,
                "chunk_count": 2 if self.ready else 0,
            }
        ]
        datasets.extend(self.extra_datasets.values())
        if name:
            return [item for item in datasets if item["name"] == name]
        return datasets

    def create_dataset(self, *, name, description="", chunk_method="naive"):
        return {
            "backend": "fake-kb",
            "dataset_id": "created",
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
        }

    def ingest_files(
        self,
        *,
        file_paths,
        dataset_name=None,
        dataset_id=None,
        description="",
        chunk_method="naive",
        parse=True,
        wait=False,
        timeout_seconds=300.0,
    ):
        self.uploaded = [
            {"name": Path(path).name, "text": Path(path).read_text(encoding="utf-8")} for path in file_paths
        ]
        target_dataset_id = dataset_id or "created"
        self.extra_datasets[target_dataset_id] = {
            "backend": "fake-kb",
            "dataset_id": target_dataset_id,
            "name": dataset_name or "Existing",
            "document_count": len(file_paths),
            "chunk_count": len(file_paths) if self.ready else 0,
        }
        return {
            "backend": "fake-kb",
            "dataset_created": not bool(dataset_id),
            "dataset": {"dataset_id": target_dataset_id, "name": dataset_name or "Existing"},
            "documents": [
                {
                    "dataset_id": target_dataset_id,
                    "document_id": "doc-1",
                    "name": self.uploaded[0]["name"],
                    "progress": 0.0,
                    "run": "UNSTART",
                }
            ],
            "parse": {"parse_started": bool(parse)},
        }

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "fake-kb",
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "note.txt",
                "chunk_count": 1 if self.ready else 0,
                "progress": 1.0 if self.ready else 0.1,
                "run": "DONE" if self.ready else "RUNNING",
            }
        ]

    def parse_documents(self, *, dataset_id, document_ids, wait=False, timeout_seconds=300.0):
        self.parse_calls.append({"dataset_id": dataset_id, "document_ids": document_ids, "wait": wait})
        return {"backend": "fake-kb", "dataset_id": dataset_id, "document_ids": document_ids, "parse_started": True}

    def document_graph(self, *, dataset_id, document_id):
        return {
            "backend": "fake-kb",
            "dataset_id": dataset_id,
            "document_id": document_id,
            "templates": [{"name": "demo-structure", "nodes": [], "edges": []}],
            "note": "Fake graph for Product API tests.",
        }


class ProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"PSKA_WORKSPACE_ID": "", "PSKA_TENANT_ID": ""}, clear=False)
        self.env_patch.start()
        self.gateway = _FakeGateway()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=build_fake_service(),
            kb_gateway_factory=lambda: self.gateway,
            static_dir=self.static_dir.name,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.static_dir.cleanup()
        self.env_patch.stop()

    def test_static_health_ask_review_and_apply_loop(self):
        html = self._get_text("/")
        self.assertIn("PSKA", html)
        health = self._get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["governance"]["durable_memory"], "manual_review")
        self.assertEqual(health["workspace"]["workspace_id"], "default")
        self.assertEqual(health["workspace"]["memory_namespace"], "")
        self.assertFalse(health["workspace"]["workspace_configured"])
        self.assertTrue(health["capabilities"]["memory"]["operations"]["update"]["supported"])
        self.assertTrue(health["capabilities"]["memory"]["operations"]["delete"]["supported"])
        capabilities = self._get_json("/api/capabilities")
        self.assertTrue(capabilities["ok"])
        self.assertEqual(capabilities["capabilities"]["memory"]["backend"], "fake")
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["apply"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["update"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["delete"]["supported"])
        policy = self._get_json("/api/policy")
        self.assertEqual(policy["governance"]["actions"]["memory_patch"], "manual_review")
        self.assertEqual(policy["governance"]["actions"]["memory_update"], "manual_review")
        self.assertEqual(policy["governance"]["actions"]["memory_delete"], "manual_review")
        self.assertEqual(policy["governance"]["transient_results"], "skip")

        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern memory?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertEqual(
            [step["name"] for step in asked["loop"]["steps"][:3]],
            ["scope.check", "governance.policy", "kb.readiness"],
        )
        review_id = asked["review"]["review_id"]
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(asked["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        source = self._post_json("/api/sources/read", {"source_ref": asked["context_packets"][0]["source_ref"]})
        self.assertIn("PSKA-Essential", source["source"]["text"])
        source_audit = self._get_json("/api/audit?limit=10&action=source.read")
        self.assertEqual(source_audit["events"][0]["action"], "source.read")
        self.assertEqual(source_audit["events"][0]["metadata"]["adapter"], "fake")
        self.assertEqual(
            source_audit["events"][0]["metadata"]["document_id"],
            asked["context_packets"][0]["source_ref"]["document_id"],
        )
        workflows = self._get_json("/api/workflows?limit=5")
        self.assertEqual(workflows["workflows"][0]["run_id"], asked["run"]["run_id"])
        self.assertEqual(workflows["workflows"][0]["metadata"]["agentic_loop"]["review_id"], review_id)
        opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        exported = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("## Source Manifest", exported["export"])
        self.assertIn("## Inspected Sources", exported["export"])
        exported_json = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=json")
        self.assertEqual(exported_json["export"]["traceability"]["context_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["source_inspection_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["source_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["export"]["source_inspection_count"], 1)
        self.assertEqual(exported_json["export"]["latest_proposal"]["kind"], "memory_patch")

        reviews = self._get_json("/api/reviews?status=pending")
        self.assertEqual(reviews["reviews"][0]["review_id"], review_id)
        review_record = self._get_json(f"/api/reviews/{review_id}")["review"]
        self.assertEqual(review_record["review_id"], review_id)
        self.assertEqual(review_record["proposal"]["kind"], "memory_patch")
        self.assertEqual(review_record["source_count"], 1)
        self.assertEqual(review_record["source_refs"][0]["adapter"], "fake")
        self.assertIsNone(review_record["memory_apply"])

        decision = self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "accept", "reason": "test"})
        self.assertEqual(decision["decision"]["status"], "accepted")
        accepted_status = self._get_json("/api/workspace/status")["workspace_status"]
        accepted_actions = {action["action"]: action for action in accepted_status["next_actions"]}
        self.assertEqual(accepted_actions["apply_accepted_memory"]["params"]["review_id"], review_id)
        self.assertEqual(accepted_actions["apply_accepted_memory"]["tool"], "pska_memory_apply")

        applied = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertTrue(applied["applied"]["applied"])
        applied_again = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertEqual(applied_again["applied"]["target_id"], applied["applied"]["target_id"])
        followup = self._post_json(
            "/api/ask",
            {
                "question": "Use governed memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(followup["status"], "ready")
        self.assertEqual(len(followup["memory_facts"]), 1)
        self.assertEqual(followup["artifact"]["traceability"]["memory_count"], 1)
        self.assertEqual(followup["artifact"]["traceability"]["memory_source_count"], 1)
        self.assertEqual(followup["artifact"]["memory_source_manifest"][0]["adapter"], "fake")
        self.assertIn("Durable workspace memory", followup["proposal"]["body"])
        followup_export = self._get_json(f"/api/workflows/{followup['run']['run_id']}/export?format=json")
        self.assertEqual(followup_export["export"]["traceability"]["memory_source_count"], 1)
        memory_audit = self._get_json("/api/audit?limit=10&action=memory.search")
        self.assertEqual(memory_audit["events"][0]["metadata"]["count"], 1)
        late_decision = self._post_json_error(
            f"/api/reviews/{review_id}/decision",
            {"decision": "reject", "reason": "too late"},
        )
        self.assertEqual(late_decision["status"], 400)
        self.assertIn("after durable memory has been applied", late_decision["body"]["error"]["message"])

        accepted_reviews = self._get_json("/api/reviews?status=accepted")
        self.assertEqual(accepted_reviews["reviews"][0]["memory_apply"]["target_id"], applied["applied"]["target_id"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("workflow.export", actions)
        self.assertIn("memory.apply", actions)
        self.assertIn("source.read", actions)
        memory_event = next(event for event in audit["events"] if event["action"] == "memory.apply")
        self.assertEqual(memory_event["metadata"]["proposal_kind"], "memory_patch")
        self.assertEqual(memory_event["metadata"]["source_count"], 1)
        self.assertEqual(memory_event["metadata"]["source_refs"][0]["adapter"], "fake")
        self.assertEqual(audit["events"][0]["metadata"]["workspace_id"], "default")

        updated_text = "Updated durable memory says citrinepolicy is governed."
        update_review = self._post_json(
            "/api/memory/update-review",
            {"memory_fact": followup["memory_facts"][0], "text": updated_text, "reason": "clearer wording"},
        )
        self.assertEqual(update_review["proposal"]["kind"], "memory_update")
        self.assertEqual(update_review["proposal"]["memory_update"]["target_id"], applied["applied"]["target_id"])
        update_apply_blocked = self._post_json_error(
            f"/api/reviews/{update_review['review']['review_id']}/apply-memory",
            {},
        )
        self.assertEqual(update_apply_blocked["status"], 400)
        self.assertIn("accepted review", update_apply_blocked["body"]["error"]["message"])

        self._post_json(
            f"/api/reviews/{update_review['review']['review_id']}/decision",
            {"decision": "accept", "reason": "update approved"},
        )
        updated = self._post_json(f"/api/reviews/{update_review['review']['review_id']}/apply-memory", {})
        self.assertTrue(updated["applied"]["applied"])
        self.assertEqual(updated["applied"]["metadata"]["operation"], "update")
        self.assertEqual(updated["applied"]["metadata"]["version"], 2)
        after_update = self._post_json(
            "/api/ask",
            {
                "question": "What does citrinepolicy say?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(after_update["memory_facts"][0]["text"], updated_text)
        self.assertEqual(after_update["memory_facts"][0]["metadata"]["version"], 2)
        update_audit = self._get_json("/api/audit?limit=10&action=memory.update")
        self.assertEqual(update_audit["events"][0]["metadata"]["proposal_kind"], "memory_update")
        self.assertEqual(update_audit["events"][0]["metadata"]["memory_target_id"], applied["applied"]["target_id"])

        delete_review = self._post_json(
            "/api/memory/delete-review",
            {"memory_fact": after_update["memory_facts"][0], "reason": "outdated"},
        )
        self.assertEqual(delete_review["proposal"]["kind"], "memory_delete")
        self.assertEqual(delete_review["proposal"]["memory_delete"]["target_id"], applied["applied"]["target_id"])
        self.assertEqual(delete_review["review"]["status"], "pending")
        delete_apply_blocked = self._post_json_error(
            f"/api/reviews/{delete_review['review']['review_id']}/apply-memory",
            {},
        )
        self.assertEqual(delete_apply_blocked["status"], 400)
        self.assertIn("accepted review", delete_apply_blocked["body"]["error"]["message"])

        self._post_json(
            f"/api/reviews/{delete_review['review']['review_id']}/decision",
            {"decision": "accept", "reason": "delete approved"},
        )
        deleted = self._post_json(f"/api/reviews/{delete_review['review']['review_id']}/apply-memory", {})
        self.assertTrue(deleted["applied"]["applied"])
        self.assertEqual(deleted["applied"]["metadata"]["operation"], "delete")
        after_delete = self._post_json(
            "/api/ask",
            {
                "question": "What does citrinepolicy say?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(after_delete["memory_facts"], [])
        delete_audit = self._get_json("/api/audit?limit=10&action=memory.delete")
        self.assertEqual(delete_audit["events"][0]["metadata"]["proposal_kind"], "memory_delete")
        self.assertEqual(delete_audit["events"][0]["metadata"]["memory_target_id"], applied["applied"]["target_id"])
        lifecycle = self._get_json(f"/api/memory/{applied['applied']['target_id']}/lifecycle")
        self.assertEqual(lifecycle["lifecycle"]["change_count"], 3)
        self.assertEqual(
            [event["action"] for event in lifecycle["lifecycle"]["events"]],
            ["memory.apply", "memory.update", "memory.delete"],
        )
        self.assertEqual(lifecycle["lifecycle"]["latest_event"]["action"], "memory.delete")

    def test_workspace_status_route_reports_next_actions(self):
        status = self._get_json("/api/workspace/status")["workspace_status"]

        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["dataset_count"], 1)
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["kb"]["dataset_readiness"][0]["dataset_ids"], ["demo"])
        self.assertEqual(status["reviews"]["pending_count"], 0)
        self.assertEqual(status["workflows"]["resumable_ask_count"], 0)
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertEqual(status["next_actions"][0]["api"], "POST /api/ask")
        self.assertEqual(status["next_actions"][0]["view"], "ask")
        self.assertEqual(status["next_actions"][0]["params"]["dataset_ids"], ["demo"])

    def test_workflow_open_does_not_export_until_explicit_export(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern exports?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        run_id = asked["run"]["run_id"]

        def workflow_export_count() -> int:
            audit = self._get_json("/api/audit?limit=50")
            return sum(1 for event in audit["events"] if event["action"] == "workflow.export")

        before_open = workflow_export_count()
        self.assertEqual(before_open, 0)
        opened = self._get_json(f"/api/workflows/{run_id}")
        self.assertEqual(opened["workflow"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["run"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["latest_proposal"]["kind"], "writing_brief")
        self.assertEqual(opened["artifact"]["traceability"]["context_count"], 1)
        self.assertEqual(opened["artifact"]["traceability"]["source_count"], 1)
        self.assertNotIn("export", opened["artifact"]["traceability"])
        self.assertEqual(workflow_export_count(), before_open)

        exported = self._get_json(f"/api/workflows/{run_id}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("Export audit event:", exported["export"])
        self.assertEqual(workflow_export_count(), before_open + 1)
        json_exported = self._get_json(f"/api/workflows/{run_id}/export?format=json")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["action"], "workflow.export")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["target_id"], run_id)
        self.assertEqual(json_exported["export"]["traceability"]["export"]["format"], "json")
        self.assertEqual(workflow_export_count(), before_open + 2)

    def test_transient_ask_does_not_create_review_by_default(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 2,
                "min_context_packets": 2,
                "retrieval_queries": ["Adapter Boundary"],
                "source_inspection_limit": 1,
                "proposal_kind": "writing_brief",
                "use_kg": True,
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertFalse(asked["loop"]["review_required"])
        self.assertTrue(asked["run"]["scope"]["use_kg"])
        self.assertEqual(len(asked["context_packets"]), 2)
        self.assertIn("graph.retrieval", [step["name"] for step in asked["loop"]["steps"]])
        retrieve_steps = [step for step in asked["loop"]["steps"] if step["name"] == "context.retrieve"]
        self.assertEqual(len(retrieve_steps), 2)
        self.assertEqual(retrieve_steps[1]["metadata"]["query"], "Adapter Boundary")
        self.assertEqual(asked["loop"]["retrieval_query_plan"][1], "Adapter Boundary")
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["retrieval_queries"], ["Adapter Boundary"])
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["source_inspection_limit"], 1)
        source_step = next(step for step in asked["loop"]["steps"] if step["name"] == "source.inspect")
        self.assertEqual(source_step["metadata"]["inspected_count"], 1)
        self.assertEqual(asked["artifact"]["traceability"]["source_inspection_count"], 1)
        self.assertEqual(len(asked["artifact"]["source_inspections"]), 1)
        self.assertTrue(all(step["metadata"]["use_kg"] for step in retrieve_steps))
        context_audit = self._get_json("/api/audit?limit=10&action=context.retrieve")
        self.assertTrue(context_audit["events"][0]["metadata"]["use_kg"])

    def test_transient_workflow_can_create_memory_review_later(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief before durable memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertEqual(asked["proposal"]["kind"], "writing_brief")

        created = self._post_json(
            f"/api/workflows/{asked['run']['run_id']}/memory-review",
            {"intent": "Remember the sourced workflow boundary"},
        )

        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["proposal"]["run_id"], asked["run"]["run_id"])
        self.assertEqual(created["governance"]["action"], "manual_review")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertIsNone(created["review_decision"])
        self.assertIsNone(created["memory_apply"])
        self.assertEqual(created["review"]["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["review"]["source_count"], 1)
        self.assertEqual(created["artifact"]["latest_proposal"]["kind"], "memory_patch")
        reviews = self._get_json("/api/reviews?status=pending")
        self.assertEqual(reviews["reviews"][0]["review_id"], created["review"]["review_id"])
        audit = self._get_json("/api/audit?limit=10")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("proposal.create", actions)
        self.assertIn("review.create", actions)

    def test_needs_edit_review_can_create_revision(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a memory candidate that needs revision",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )
        review_id = asked["review"]["review_id"]
        self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "edit", "reason": "Make it shorter"})

        revised = self._post_json(f"/api/reviews/{review_id}/revision", {"intent": "Shorter durable memory"})

        self.assertEqual(revised["previous_review"]["status"], "needs_edit")
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertEqual(revised["proposal"]["kind"], "memory_patch")
        self.assertEqual(revised["proposal"]["run_id"], asked["run"]["run_id"])
        self.assertNotEqual(revised["review"]["review_id"], review_id)
        self.assertEqual(revised["review"]["source_count"], 1)
        self.assertEqual(revised["artifact"]["latest_proposal"]["proposal_id"], revised["proposal"]["proposal_id"])
        self.assertEqual(revised["previous_review"]["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(revised["review"]["revision"]["previous_review_id"], review_id)
        old_record = self._get_json(f"/api/reviews/{review_id}")["review"]
        new_record = self._get_json(f"/api/reviews/{revised['review']['review_id']}")["review"]
        self.assertEqual(old_record["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(new_record["revision"]["previous_review_id"], review_id)
        audit = self._get_json("/api/audit?limit=10&action=review.revise")
        self.assertEqual(audit["events"][0]["metadata"]["previous_review_id"], review_id)
        self.assertEqual(audit["events"][0]["metadata"]["proposal_kind"], "memory_patch")

    def test_review_revision_requires_needs_edit_status(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a memory candidate that is still pending",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )

        failed = self._post_json_error(
            f"/api/reviews/{asked['review']['review_id']}/revision",
            {"intent": "not ready"},
        )

        self.assertEqual(failed["status"], 400)
        self.assertIn("needs_edit", failed["body"]["error"]["message"])

    def test_memory_review_from_workflow_honors_auto_apply_policy(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief before automatic durable memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": "auto_apply"}, clear=False):
            created = self._post_json(
                f"/api/workflows/{asked['run']['run_id']}/memory-review",
                {"intent": "Remember this source-backed claim automatically"},
            )

        self.assertEqual(created["governance"]["action"], "auto_apply")
        self.assertEqual(created["review"]["status"], "accepted")
        self.assertEqual(created["review_decision"]["status"], "accepted")
        self.assertTrue(created["memory_apply"]["applied"])
        self.assertEqual(created["review"]["memory_apply"]["target_id"], created["memory_apply"]["target_id"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("review.decide", actions)
        self.assertIn("memory.apply", actions)

    def test_ask_blocks_when_retrieved_context_is_below_minimum(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 1,
                "min_context_packets": 2,
                "proposal_kind": "memory_patch",
            },
        )

        self.assertEqual(asked["status"], "insufficient_context")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertIn("2 required", asked["message"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("agentic_loop.insufficient_context", actions)
        self.assertNotIn("workflow.export", actions)

    def test_readiness_route_reports_scope_status(self):
        payload = self._post_json("/api/kb/readiness", {"dataset_ids": ["demo"]})
        readiness = payload["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(payload["ingestion_status"]["status"], "ready")
        self.assertEqual(payload["ingestion_status"]["next_actions"], ["run_ask"])

    def test_dataset_readiness_route_reports_scope_status(self):
        payload = self._get_json("/api/kb/datasets/demo/readiness")
        readiness = payload["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["dataset_ids"], ["demo"])
        self.assertEqual(payload["ingestion_status"]["phase"], "ready")

    def test_ingestion_status_route_reports_normalized_job_status(self):
        self.gateway.ready = False

        payload = self._get_json("/api/kb/datasets/demo/ingestion-status")

        self.assertEqual(payload["readiness"]["status"], "processing")
        self.assertEqual(payload["ingestion_status"]["kind"], "kb_ingestion_status")
        self.assertEqual(payload["ingestion_status"]["status"], "processing")
        self.assertEqual(payload["ingestion_status"]["progress"], 0.1)
        self.assertEqual(payload["ingestion_status"]["next_actions"], ["wait_for_ingestion"])

    def test_parse_documents_route_uses_product_api_boundary(self):
        parsed = self._post_json(
            "/api/kb/datasets/demo/parse",
            {"document_ids": ["doc-1"], "wait": False},
        )

        self.assertTrue(parsed["parse"]["parse_started"])
        self.assertEqual(parsed["ingestion_status"]["status"], "ready")
        self.assertEqual(self.gateway.parse_calls, [{"dataset_id": "demo", "document_ids": ["doc-1"], "wait": False}])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.parse")
        self.assertEqual(audit["events"][0]["metadata"]["document_ids"], ["doc-1"])

    def test_document_graph_route_uses_product_api_boundary(self):
        graph = self._get_json("/api/kb/datasets/demo/documents/doc-1/graph")

        self.assertEqual(graph["graph"]["dataset_id"], "demo")
        self.assertEqual(graph["graph"]["document_id"], "doc-1")
        self.assertEqual(len(graph["graph"]["templates"]), 1)
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.graph.read")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_id"], "demo")
        self.assertEqual(audit["events"][0]["metadata"]["document_id"], "doc-1")

    def test_runtime_diagnostics_route_reports_product_checks(self):
        payload = self._get_json("/api/runtime/diagnostics")

        self.assertTrue(payload["ok"])
        diagnostics = payload["diagnostics"]
        self.assertEqual(diagnostics["status"], "warning")
        self.assertEqual(diagnostics["workspace"]["workspace_id"], "default")
        checks = {item["name"]: item for item in diagnostics["checks"]}
        self.assertEqual(checks["product_api"]["status"], "ok")
        self.assertEqual(checks["review_store"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["metadata"]["dataset_sample_count"], 1)
        self.assertEqual(checks["retrieval_provider"]["metadata"]["provider"], "fake")
        self.assertEqual(checks["memory_provider"]["metadata"]["provider"], "fake")

    def test_retrieval_probe_route_checks_ready_scope_and_writes_audit(self):
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "How does PSKA retrieve?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["provider"], "fake")
        self.assertEqual(probe["readiness"]["status"], "ready")
        self.assertEqual(probe["context_count"], 1)
        self.assertEqual(probe["scope"]["dataset_ids"], ["demo"])
        audit = self._get_json("/api/audit?limit=5&action=retrieval.probe")
        self.assertEqual(audit["events"][0]["action"], "retrieval.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")
        self.assertEqual(audit["events"][0]["metadata"]["context_count"], 1)

    def test_retrieval_probe_does_not_retrieve_unready_scope(self):
        self.gateway.ready = False
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "Can this retrieve?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "not_ready")
        self.assertEqual(probe["context_count"], 0)
        self.assertEqual(probe["readiness"]["status"], "processing")
        self.assertIn("not ready", probe["message"])

    def test_ask_blocks_dataset_that_is_not_ready(self):
        self.gateway.ready = False
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Can this be answered yet?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "not_ready")
        self.assertIsNotNone(asked["run"])
        self.assertEqual(asked["run"]["status"], "blocked")
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["status"], "not_ready")
        self.assertEqual(asked["artifact"]["traceability"]["context_count"], 0)
        self.assertEqual(asked["artifact"]["traceability"]["proposal_count"], 0)
        self.assertIsNone(asked["artifact"]["latest_proposal"])
        self.assertEqual(asked["context_packets"], [])
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertEqual(asked["readiness"]["status"], "processing")
        self.assertEqual(asked["loop"]["steps"][-1]["name"], "kb.readiness")
        workflows = self._get_json("/api/workflows?limit=5")
        self.assertEqual(workflows["workflows"][0]["run_id"], asked["run"]["run_id"])
        opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(opened["workflow"]["status"], "blocked")
        self.assertEqual(opened["artifact"]["run"]["metadata"]["readiness"]["status"], "processing")
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("agentic_loop.not_ready", actions)
        self.assertIn("kb.readiness.blocked", actions)
        blocked_event = next(event for event in audit["events"] if event["action"] == "kb.readiness.blocked")
        self.assertEqual(blocked_event["target_type"], "workflow")
        self.assertEqual(blocked_event["target_id"], asked["run"]["run_id"])
        waiting = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(waiting["resumable_asks"][0]["run"]["run_id"], asked["run"]["run_id"])
        self.assertFalse(waiting["resumable_asks"][0]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["readiness"]["status"], "processing")

        self.gateway.ready = True
        ready_to_resume = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(ready_to_resume["resumable_asks"][0]["run"]["run_id"], asked["run"]["run_id"])
        self.assertTrue(ready_to_resume["resumable_asks"][0]["can_resume"])
        self.assertEqual(ready_to_resume["resumable_asks"][0]["ask_request"]["question"], "Can this be answered yet?")
        resumed = self._post_json(f"/api/workflows/{asked['run']['run_id']}/resume-ask", {})

        self.assertEqual(resumed["status"], "ready")
        self.assertNotEqual(resumed["run"]["run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["run"]["metadata"]["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["question"], "Can this be answered yet?")
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["dataset_ids"], ["demo"])
        self.assertEqual(resumed["run"]["metadata"]["agentic_loop"]["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["artifact"]["traceability"]["context_count"], 1)
        old_opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(old_opened["workflow"]["status"], "blocked")
        resume_audit = self._get_json("/api/audit?limit=20&action=agentic_loop.resume")
        self.assertEqual(resume_audit["events"][0]["target_id"], resumed["run"]["run_id"])
        self.assertEqual(resume_audit["events"][0]["metadata"]["resumed_from_run_id"], asked["run"]["run_id"])
        retry_ready = self._post_json_error(f"/api/workflows/{resumed['run']['run_id']}/resume-ask", {})
        self.assertEqual(retry_ready["status"], 400)
        self.assertIn("only readiness-blocked", retry_ready["body"]["error"]["message"])

    def test_multipart_ingest_uses_product_api_boundary(self):
        boundary = "pska-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dataset_name"\r\n\r\n'
            "Uploaded KB\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "trusted workspace notes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/kb/ingest",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(self.gateway.uploaded, [{"name": "note.txt", "text": "trusted workspace notes"}])
        self.assertEqual(payload["ingestion_status"]["status"], "ready")
        self.assertEqual(payload["readiness"]["datasets"][0]["documents"][0]["next_action"], "available_for_retrieval")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.ingest")
        self.assertEqual(audit["events"][0]["metadata"]["document_names"], ["note.txt"])
        self.assertTrue(audit["events"][0]["metadata"]["parse_started"])

    def test_dataset_create_writes_kb_audit_record(self):
        created = self._post_json(
            "/api/kb/datasets",
            {"name": "New Dataset", "description": "notes", "chunk_method": "naive"},
        )

        self.assertEqual(created["dataset"]["dataset_id"], "created")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.create")
        self.assertEqual(audit["events"][0]["target_id"], "created")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_name"], "New Dataset")

    def test_audit_route_filters_by_action(self):
        self._post_json(
            "/api/kb/datasets",
            {"name": "Filtered Dataset", "description": "", "chunk_method": "naive"},
        )
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")

        filtered = self._get_json("/api/audit?limit=20&action=workflow.export")

        self.assertTrue(filtered["events"])
        self.assertEqual({event["action"] for event in filtered["events"]}, {"workflow.export"})

    def test_bundled_frontend_contains_reader_view(self):
        html = Path("src/pska_essential/web/index.html").read_text(encoding="utf-8")
        script = Path("src/pska_essential/web/app.js").read_text(encoding="utf-8")
        self.assertIn("Source Reader", html)
        self.assertIn("ingestion-status", html)
        self.assertIn("ingestion-actions", html)
        self.assertIn("parse-documents", html)
        self.assertIn("audit-action-filter", html)
        self.assertIn("source.read", html)
        self.assertIn("review-status-filter", html)
        self.assertIn("memory.search", html)
        self.assertIn("needs_edit", html)
        self.assertIn("review.revise", html)
        self.assertIn("Revise", script)
        self.assertIn("ask-dataset-picker", html)
        self.assertIn("ask-document-picker", html)
        self.assertIn("ask-add-dataset", html)
        self.assertIn("ask-load-documents", html)
        self.assertIn("ask-check-readiness", html)
        self.assertIn("ask-readiness-status", html)
        self.assertIn("ask-readiness-actions", html)
        self.assertIn("max_iterations", html)
        self.assertIn("min_context_packets", html)
        self.assertIn("retrieval_queries", html)
        self.assertIn("Additional Retrieval Queries", html)
        self.assertIn("source_inspection_limit", html)
        self.assertIn("Source Inspect", html)
        self.assertIn("use_kg", html)
        self.assertIn('data-view="reader"', html)
        self.assertIn('data-view="writing"', html)
        self.assertIn('data-view="activity"', html)
        self.assertIn("Brief Workspace", html)
        self.assertIn("runtime-diagnostics", html)
        self.assertIn("Workspace Policy", html)
        self.assertIn("policy-settings", html)
        self.assertIn("retrieval-probe-result", html)
        self.assertIn("run-retrieval-probe", html)
        self.assertIn("probe-dataset-picker", html)
        self.assertIn("upload-dataset-picker", html)
        self.assertIn("upload-use-dataset", html)
        self.assertIn("retrieval.probe", html)
        self.assertIn("create-memory-review", html)
        self.assertIn("Memory Review", html)
        self.assertIn("home-next-actions", html)
        self.assertIn("Next Actions", html)
        self.assertIn("home-resumable-asks", html)
        self.assertIn("loadCapabilities", script)
        self.assertIn('/api/capabilities', script)
        self.assertIn("Capability Contract", script)
        self.assertIn("workspaceActionButtonLabel", script)
        self.assertIn('apply_accepted_memory: "Apply"', script)
        self.assertIn('inspect_unsupported_memory_operation: "Inspect"', script)
        self.assertIn('action.action === "inspect_unsupported_memory_operation"', script)
        self.assertIn('await applyMemory(params.review_id);', script)
        self.assertIn('await parseDatasetDocuments(datasetId, params.document_ids || []);', script)
        self.assertIn('await checkAskReadiness({ silent: true });', script)
        self.assertIn("memoryCapabilities", script)
        self.assertIn("memoryOperationSupported", script)
        self.assertIn("capability.supported === true", script)
        self.assertIn("Capability contract is not loaded.", script)
        self.assertIn("memoryOperationForProposalKind", script)
        self.assertIn("Update Unsupported", script)
        self.assertIn("Memory Apply Unsupported", script)
        self.assertIn("capabilityLabel(memoryCaps, \"update\")", script)
        self.assertIn("Workspace", script)
        self.assertIn("Tenant", script)
        self.assertIn("Memory Namespace", script)
        self.assertIn("max_iterations", script)
        self.assertIn("min_context_packets", script)
        self.assertIn("retrieval_queries: splitLines", script)
        self.assertIn("function splitLines", script)
        self.assertIn("source_inspection_limit", script)
        self.assertIn("use_kg", script)
        self.assertIn('/api/sources/read', script)
        self.assertIn('/api/audit?limit=50', script)
        self.assertIn('state.auditAction', script)
        self.assertIn('action=${encodeURIComponent(state.auditAction)}', script)
        self.assertIn('auditSummary', script)
        self.assertIn('setAuditActionFilter', script)
        self.assertIn('auditActionForAskResult', script)
        self.assertIn('result.status === "not_ready"', script)
        self.assertIn('resumeAskRun', script)
        self.assertIn('refreshBlockedAskReadiness', script)
        self.assertIn('Check Readiness', script)
        self.assertIn('startBlockedAskTracking', script)
        self.assertIn('stopBlockedAskTracking', script)
        self.assertIn('Track & Resume', script)
        self.assertIn('Knowledge scope is ready; resuming Ask.', script)
        self.assertIn('Knowledge scope is ready to resume.', script)
        self.assertIn('Knowledge base is ready. Ask scope updated.', script)
        self.assertIn('/resume-ask', script)
        self.assertIn('metadata.blocked_reason === "kb_not_ready"', script)
        self.assertIn('return "agentic_loop.complete"', script)
        self.assertIn('event.action === "source.read"', script)
        self.assertIn("await loadAuditEvents(\"source.read\");\n  document.querySelector('.nav-item[data-view=\"reader\"]').click();", script)
        self.assertIn('await loadAuditEvents("kb.graph.read");', script)
        self.assertIn('await loadAuditEvents("workflow.export");', script)
        self.assertIn('exportWorkflow(result.run.run_id, "markdown", { openWriting: true })', script)
        self.assertIn('exportWorkflow(result.run.run_id, "json", { openWriting: true })', script)
        self.assertIn('async function exportWorkflow', script)
        self.assertIn('state.workflows.find((workflow) => workflow.run_id === selectedRunId)', script)
        self.assertIn('await loadAuditEvents("review.decide");', script)
        self.assertIn('await loadAuditEvents(action);', script)
        self.assertIn('/api/reviews?limit=50', script)
        self.assertIn('/api/reviews?status=pending&limit=50', script)
        self.assertIn('state.reviewStatus', script)
        self.assertIn('state.reviewView', script)
        self.assertIn('pendingReviews', script)
        self.assertIn('status=${encodeURIComponent(state.reviewStatus)}', script)
        self.assertIn('setReviewStatusFilter', script)
        self.assertIn('loadPendingReviews', script)
        self.assertIn("renderUploadDatasetPicker", script)
        self.assertIn("setUploadDatasetFromPicker", script)
        self.assertIn('showToast("Knowledge base created and selected for upload.");', script)
        self.assertIn('setUploadDataset(payload.dataset.dataset_id);', script)
        self.assertIn('document.getElementById("upload-use-dataset").addEventListener("click", setUploadDatasetFromPicker);', script)
        self.assertIn('const datasetId = ingestDatasetId(result.ingest);', script)
        self.assertIn('showToast("Upload accepted. Target kept for more files.");', script)
        self.assertIn('renderIngestResult(result.ingest, result.readiness);\n    await loadDatasets();\n    await loadAuditEvents("kb.ingest");', script)
        self.assertIn('await loadDocuments(datasetId, { silent: true });\n  await loadWorkspaceStatus();\n  await loadAuditEvents("kb.parse");', script)
        self.assertIn('/api/runtime/diagnostics', script)
        self.assertIn('/api/workspace/status', script)
        self.assertIn('loadWorkspaceStatus', script)
        self.assertIn('workspaceActionCard', script)
        self.assertIn('openWorkspaceAction', script)
        self.assertIn('setAskDatasetIds(params.dataset_ids || [])', script)
        self.assertIn('setUploadDataset(params.dataset_ids || [])', script)
        self.assertIn('openDatasetUpload', script)
        self.assertIn('openDatasetStatus', script)
        self.assertIn('nameField.value = "";', script)
        self.assertIn('check_provider_status', script)
        self.assertIn('check_dataset_access', script)
        self.assertIn('upload_documents', script)
        self.assertIn('await loadWorkspaceStatus();\n    await loadAuditEvents("kb.dataset.create");', script)
        self.assertIn('await loadWorkspaceStatus();\n  await loadAuditEvents("review.decide");', script)
        self.assertIn('await loadWorkspaceStatus();\n  await loadAuditEvents(action);', script)
        self.assertIn('await loadResumableAsks();\n  await loadWorkspaceStatus();', script)
        self.assertIn('/api/policy', script)
        self.assertIn('loadPolicy', script)
        self.assertIn('renderPolicy', script)
        self.assertIn('policy.actions', script)
        self.assertIn('/api/runtime/retrieval-probe', script)
        self.assertIn('/memory-review', script)
        self.assertIn('setReviewStatusFilter("");\n  syncReviewRecord(payload.review);', script)
        self.assertIn('await loadAuditEvents(payload.memory_apply ? memoryApplyAction(payload.memory_apply) : "review.create");', script)
        self.assertIn("document.querySelector('.nav-item[data-view=\"review\"]').click();\n  showToast(payload.memory_apply ? memoryApplyToast(payload.memory_apply) : \"Memory review created.\");", script)
        self.assertIn('/revision', script)
        self.assertIn('/api/workflows/${encodeURIComponent(runId)}', script)
        self.assertIn('/documents/${encodeURIComponent(documentId)}/graph', script)
        self.assertIn('/api/workflows?limit=20', script)
        self.assertIn('/api/workflows/resumable-asks?limit=20', script)
        self.assertIn('loadResumableAsks', script)
        self.assertIn('resumableAskCard', script)
        self.assertIn('can_resume', script)
        self.assertIn('loop.review_required', script)
        self.assertIn('loop.durable_proposal', script)
        self.assertIn('container.append(loopPanel({ loop }));', script)
        self.assertIn('memoryFactCard', script)
        self.assertIn('artifact.memory_facts', script)
        self.assertIn('sourceInspectionCard', script)
        self.assertIn('artifact.source_inspections', script)
        self.assertIn('Inspected Sources', script)
        self.assertIn('Durable Memory', script)
        self.assertIn('memory.search', script)
        self.assertIn('/parse', script)
        self.assertIn('/readiness', script)
        self.assertIn('/api/kb/readiness', script)
        self.assertIn('checkAskReadiness', script)
        self.assertIn('renderAskReadinessStatus', script)
        self.assertIn('renderAskReadinessActions', script)
        self.assertIn('handleAskReadinessAction', script)
        self.assertIn('readinessDatasetForAction', script)
        self.assertIn('productReadinessAction', script)
        self.assertIn('submitAskForm', script)
        self.assertIn('includeRunAsk: false', script)
        self.assertIn('fresh && fresh.ask_request', script)
        self.assertIn('askRequest.dataset_ids || readiness.dataset_ids || []', script)
        self.assertIn('askRequest.document_ids || readiness.document_ids || []', script)
        self.assertIn('askScopeKey', script)
        self.assertIn('Ask scope is ready.', script)
        self.assertIn('Ask scope is not ready.', script)
        self.assertIn('Ask scope readiness has not been checked.', script)
        self.assertIn('"Run Ask"', script)
        self.assertIn('"Parse Scope"', script)
        self.assertIn('"Open Status"', script)
        self.assertIn('form.requestSubmit();', script)
        self.assertIn('ingestion_status', script)
        self.assertIn('mergeReadinessDocuments', script)
        self.assertIn('renderIngestionActions', script)
        self.assertIn('Ask This KB', script)
        self.assertIn('Track Status', script)
        self.assertIn('onclick: () => askDocument(datasetId, document)', script)
        self.assertIn('function askDocument(datasetId, document)', script)
        self.assertIn('setAskDocumentIds([documentId]);', script)
        self.assertIn('showToast("Document selected for Ask.");', script)
        self.assertIn('prepareAskScope(datasetId, documents);', script)
        self.assertIn('prepareAskScope(datasetId, displayDocuments);', script)
        self.assertIn('state.askDocumentsByDataset[normalized] = documents;', script)
        self.assertIn('next_action', script)
        self.assertIn('formatPercent', script)
        self.assertIn('diagnosticCard', script)
        self.assertIn('retrievalProbeCard', script)
        self.assertIn('auditEventCard', script)
        self.assertIn('source_count', script)
        self.assertIn('memory_target_id', script)
        self.assertIn('readDocumentGraph', script)
        self.assertIn('Graph loaded', script)
        self.assertIn('addAskDataset', script)
        self.assertIn('loadAskDocuments', script)
        self.assertIn('askDocumentCard', script)
        self.assertIn('setAskDatasetIds', script)
        self.assertIn('}, "Ask")', script)
        self.assertIn('}, "Upload")', script)
        self.assertIn('}, "Status")', script)
        self.assertIn('askResultActions', script)
        self.assertIn('createMemoryReviewFromRun', script)
        self.assertIn('openWorkflowRun', script)
        self.assertIn('sourceManifestCard', script)
        self.assertIn('latest_proposal', script)
        self.assertIn('openWritingRun', script)
        self.assertNotIn('function loadBrief', script)
        self.assertIn('openReview', script)
        self.assertIn('/api/reviews/${encodeURIComponent(reviewId)}', script)
        self.assertIn('/api/memory/delete-review', script)
        self.assertIn('/api/memory/update-review', script)
        self.assertIn('/api/memory/${encodeURIComponent(memoryTargetId)}/lifecycle', script)
        self.assertIn('openMemoryLifecycle', script)
        self.assertIn('Memory lifecycle loaded.', script)
        self.assertIn('syncReviewRecord', script)
        self.assertIn('reviewSourceRow', script)
        self.assertIn('review.source_refs || proposal.source_refs', script)
        self.assertIn('review.revision || {}', script)
        self.assertIn('revision.previous_review_id', script)
        self.assertIn('revision.next_review_id', script)
        self.assertIn('const runId = proposal.run_id || (proposal.metadata && proposal.metadata.run_id) || "";', script)
        self.assertIn('onclick: () => openWritingRun(runId)', script)
        self.assertIn('className: "review-source-row"', script)
        self.assertIn('review.status === "pending"', script)
        self.assertIn('review.status === "accepted"', script)
        self.assertIn('review.status === "needs_edit"', script)
        self.assertIn('review.status === "rejected"', script)
        self.assertIn('Apply Memory', script)
        self.assertIn('Apply Memory Update', script)
        self.assertIn('Apply Memory Delete', script)
        self.assertIn('Create Update Review', script)
        self.assertIn('Create Delete Review', script)
        self.assertIn('createMemoryUpdateReview', script)
        self.assertIn('createMemoryDeleteReview', script)
        self.assertIn('memoryApplyLabel', script)
        self.assertIn('memoryApplyAction', script)
        self.assertIn('Applied Durable Knowledge', script)
        self.assertIn('memoryApplyCard', script)
        self.assertIn('openMemoryLifecycle(memoryApply.target_id)', script)
        self.assertIn('if (memoryApply.target_id) {\n      actions.append(\n        el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(memoryApply.target_id) }, "History"),\n      );\n    }', script)
        self.assertIn('syncReviewDecision', script)
        self.assertIn('state.focusReviewId = reviewId;', script)
        self.assertIn('if (payload.decision && payload.decision.status) {\n    setReviewStatusFilter("");\n  }', script)
        self.assertIn('reviseReview', script)
        self.assertIn('return `Updated durable memory through ${metadata.backend || "memory backend"}.`;', script)
        self.assertIn('return `Deleted durable memory through ${metadata.backend || "memory backend"}.`;', script)
        self.assertIn('<option value="memory.update">memory.update</option>', html)
        self.assertIn('<option value="memory.delete">memory.delete</option>', html)
        self.assertIn('return `Review revision created for ${metadata.proposal_kind || "proposal"}.`;', script)
        self.assertIn('syncMemoryApply', script)
        self.assertIn('Memory applied', script)
        self.assertIn('Locked', script)
        self.assertIn('memory_apply', script)
        self.assertIn('Retrieved Context', script)
        self.assertIn('parseActiveDocuments', script)
        self.assertIn('parseDatasetDocuments', script)
        self.assertIn('await parseDatasetDocuments(datasetId, documentIds);', script)
        self.assertIn('startIngestionPolling', script)

    def _get_text(self, path: str) -> str:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.read().decode("utf-8")

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))

    def _post_json_error(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                self.fail(f"expected HTTP error, got {response.status}")
        except HTTPError as exc:
            return {
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }


class ProductApiFakeUploadLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {
                "PSKA_DEV_FAKE": "1",
                "PSKA_RETRIEVAL_PROVIDER": "fake",
                "PSKA_KB_PROVIDER": "fake",
                "PSKA_MEMORY_PROVIDER": "fake",
                "PSKA_REVIEW_DB": ":memory:",
                "PSKA_WORKSPACE_ID": "",
                "PSKA_TENANT_ID": "",
            },
            clear=True,
        )
        self.env_patch.start()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=build_service_from_env(),
            kb_gateway_factory=build_kb_gateway_from_env,
            static_dir=self.static_dir.name,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.static_dir.cleanup()
        self.env_patch.stop()

    def test_product_api_upload_ask_and_source_read_use_uploaded_fake_document(self):
        dataset_name = f"Uploaded API Loop {uuid4().hex}"
        unique_phrase = f"source governed API loop {uuid4().hex}"
        ingested = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "parse": "true",
                "wait": "false",
            },
            "loop-note.txt",
            f"The uploaded document says {unique_phrase} before durable knowledge is written.",
        )
        dataset_id = ingested["ingest"]["dataset"]["dataset_id"]
        document_id = ingested["ingest"]["documents"][0]["document_id"]

        asked = self._post_json(
            "/api/ask",
            {
                "question": f"What does the uploaded document say about {unique_phrase}?",
                "dataset_ids": [dataset_id],
                "limit": 3,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertFalse(asked["loop"]["review_required"])
        self.assertEqual(asked["context_packets"][0]["source_ref"]["dataset_id"], dataset_id)
        self.assertEqual(asked["context_packets"][0]["source_ref"]["document_id"], document_id)
        self.assertIn(unique_phrase, asked["context_packets"][0]["text"])
        self.assertIn("loop-note.txt", asked["artifact"]["source_manifest"][0]["title"])

        source = self._post_json("/api/sources/read", {"source_ref": asked["context_packets"][0]["source_ref"]})
        self.assertIn(unique_phrase, source["source"]["text"])
        source_audit = self._get_json("/api/audit?limit=10&action=source.read")
        self.assertEqual(source_audit["events"][0]["metadata"]["document_id"], document_id)
        ingest_audit = self._get_json("/api/audit?limit=10&action=kb.ingest")
        self.assertEqual(ingest_audit["events"][0]["metadata"]["document_names"], ["loop-note.txt"])

    def _post_multipart_ingest(self, fields: dict[str, str], filename: str, text: str) -> dict:
        boundary = f"pska-test-{uuid4().hex}"
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
                b"Content-Type: text/plain\r\n\r\n",
                text.encode("utf-8"),
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        request = Request(
            f"{self.base_url}/api/kb/ingest",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
