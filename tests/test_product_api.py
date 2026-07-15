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
from pska_essential.kb_gateway import KbGatewayError, build_kb_gateway_from_env, reset_fake_kb_gateway
from pska_essential.product_api import build_server
from pska_essential.workflow import build_fake_service


class _FakeGateway:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, str]] = []
        self.parse_calls: list[dict[str, object]] = []
        self.last_created: dict[str, object] | None = None
        self.last_ingest: dict[str, object] | None = None
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

    def create_dataset(self, *, name, description="", chunk_method="naive", embedding_model=""):
        self.last_created = {
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
        }
        return {
            "backend": "fake-kb",
            "dataset_id": "created",
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
        }

    def delete_datasets(self, *, dataset_ids=None, dataset_names=None, delete_all=False):
        ids = [str(dataset_id) for dataset_id in dataset_ids or []]
        names = [str(dataset_name) for dataset_name in dataset_names or [] if str(dataset_name).strip()]
        if names and not delete_all:
            for dataset in self.list_datasets(page_size=100):
                if dataset["name"] in names and dataset["dataset_id"] not in ids:
                    ids.append(dataset["dataset_id"])
        deleted_ids = list(self.extra_datasets.keys()) if delete_all else [dataset_id for dataset_id in ids if dataset_id in self.extra_datasets or dataset_id == "demo"]
        if delete_all:
            self.extra_datasets.clear()
        else:
            for dataset_id in ids:
                self.extra_datasets.pop(dataset_id, None)
        return {
            "backend": "fake-kb",
            "dataset_ids": ids,
            "dataset_names": names,
            "deleted_dataset_ids": deleted_ids,
            "delete_all": bool(delete_all),
            "deleted": True,
        }

    def ingest_files(
        self,
        *,
        file_paths,
        dataset_name=None,
        dataset_id=None,
        description="",
        chunk_method="naive",
        embedding_model="",
        parse=True,
        wait=False,
        timeout_seconds=300.0,
    ):
        self.last_ingest = {
            "dataset_name": dataset_name,
            "dataset_id": dataset_id,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
            "parse": parse,
            "wait": wait,
        }
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
            "embedding_model": embedding_model,
        }
        return {
            "backend": "fake-kb",
            "dataset_created": not bool(dataset_id),
            "dataset": {
                "dataset_id": target_dataset_id,
                "name": dataset_name or "Existing",
                "embedding_model": embedding_model,
            },
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


class ProductApiStartupTests(unittest.TestCase):
    def test_build_server_requires_workflow_provider_configuration(self):
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, {}, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER is required"):
                build_server(host="127.0.0.1", port=0, static_dir=static_dir)

    def test_build_server_rejects_fake_workflow_provider_without_dev_mode(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
        }
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER=fake"):
                build_server(host="127.0.0.1", port=0, static_dir=static_dir)

    def test_build_server_allows_explicit_dev_fake_mode(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            server = build_server(host="127.0.0.1", port=0, static_dir=static_dir)
            server.server_close()

    def test_build_server_validates_kb_gateway_configuration(self):
        env = {"PSKA_KB_PROVIDER": "ragflow"}
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(KbGatewayError, "RAGFlow KB gateway is missing required env"):
                build_server(
                    host="127.0.0.1",
                    port=0,
                    service=build_fake_service(),
                    static_dir=static_dir,
                )


class ProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"PSKA_WORKSPACE_ID": "", "PSKA_TENANT_ID": ""}, clear=False)
        self.env_patch.start()
        self.gateway = _FakeGateway()
        self.service = build_fake_service()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=self.service,
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

    def test_workflow_export_requires_sourced_work_product(self):
        run = self.service.start("empty product api workflow", {"dataset_ids": ["demo"]})

        failed = self._get_json_error(f"/api/workflows/{run.run_id}/export?format=markdown")

        self.assertEqual(failed["status"], 400)
        self.assertIn("sourced work product", failed["body"]["error"]["message"])

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

    def test_product_api_required_lists_trim_and_reject_blank_values(self):
        asked = self._post_json(
            "/api/ask",
            {"question": "Normalize this scope", "dataset_ids": [" demo ", "demo", "  "], "limit": 1},
        )
        self.assertEqual(asked["status"], "ready")
        self.assertEqual(asked["run"]["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["dataset_ids"], ["demo"])

        for path, payload, field in [
            ("/api/ask", {"question": "No real scope", "dataset_ids": ["  "]}, "dataset_ids"),
            ("/api/kb/readiness", {"dataset_ids": ["", "  "]}, "dataset_ids"),
            ("/api/kb/datasets/demo/parse", {"document_ids": ["  "]}, "document_ids"),
            ("/api/kb/ingest", {"dataset_name": "Blank Files", "file_paths": ["  "]}, "file_paths"),
        ]:
            with self.subTest(path=path):
                failed = self._post_json_error(path, payload)
                self.assertEqual(failed["status"], 400)
                self.assertIn(f"{field} must be a non-empty list", failed["body"]["error"]["message"])

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
        self.assertEqual(checks["memory_search_contract"]["metadata"]["provider"], "fake")
        self.assertFalse(checks["memory_search_contract"]["metadata"]["semantic_checked"])

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

    def test_retrieval_probe_route_resolves_dataset_names(self):
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "How does PSKA retrieve?", "dataset_names": ["Demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(probe["scope"]["resolved_dataset_names"], [{"name": "Demo", "dataset_id": "demo"}])

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

    def test_memory_probe_route_rejects_fake_as_live_proof_and_can_run_dev_probe(self):
        blocked = self._post_json("/api/runtime/memory-probe", {"query": "memory", "limit": 1})["probe"]

        self.assertEqual(blocked["status"], "invalid_configuration")
        self.assertEqual(blocked["provider"], "fake")

        dev_probe = self._post_json(
            "/api/runtime/memory-probe",
            {"query": "memory", "limit": 1, "require_live": False},
        )["probe"]

        self.assertEqual(dev_probe["status"], "ok")
        self.assertEqual(dev_probe["provider"], "fake")
        audit = self._get_json("/api/audit?limit=5&action=memory.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

    def test_component_check_route_runs_structured_acceptance_check(self):
        with patch.dict(os.environ, {"PSKA_DEV_FAKE": "1"}, clear=False):
            result = self._post_json(
                "/api/runtime/component-check",
                {
                    "question": "Can the configured components answer?",
                    "dataset_names": ["Demo"],
                    "require_memory": False,
                    "run_closed_loop": False,
                },
            )["component_check"]

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(result["retrieval_probe"]["status"], "ok")
        self.assertIsNone(result["closed_loop_probe"])
        audit = self._get_json("/api/audit?limit=5&action=retrieval.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

    def test_closed_loop_probe_rejects_fake_retrieval_as_product_proof(self):
        probe = self._post_json(
            "/api/runtime/closed-loop-probe",
            {"question": "Can this prove the live loop?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertEqual(probe["providers"]["retrieval"], "fake")
        self.assertEqual(probe["context_count"], 0)
        audit = self._get_json("/api/audit?limit=5&action=closed_loop.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "invalid_configuration")
        self.assertFalse(audit["events"][0]["metadata"]["exported"])

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
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["tool"], "pska_agentic_question_resume")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["api"], f"POST /api/workflows/{asked['run']['run_id']}/resume-ask")
        self.assertFalse(waiting["resumable_asks"][0]["resume"]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["next_actions"][-1]["action"], "resume_blocked_ask")

        self.gateway.ready = True
        ready_to_resume = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(ready_to_resume["resumable_asks"][0]["run"]["run_id"], asked["run"]["run_id"])
        self.assertTrue(ready_to_resume["resumable_asks"][0]["can_resume"])
        self.assertTrue(ready_to_resume["resumable_asks"][0]["resume"]["can_resume"])
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
            'Content-Disposition: form-data; name="embedding_model"\r\n\r\n'
            "text-embedding-3-small@OpenAI\r\n"
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
        self.assertEqual(self.gateway.last_ingest["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(payload["ingest"]["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(payload["ingestion_status"]["status"], "ready")
        self.assertEqual(payload["readiness"]["datasets"][0]["documents"][0]["next_action"], "available_for_retrieval")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.ingest")
        self.assertEqual(audit["events"][0]["metadata"]["document_names"], ["note.txt"])
        self.assertTrue(audit["events"][0]["metadata"]["parse_started"])

    def test_dataset_create_writes_kb_audit_record(self):
        created = self._post_json(
            "/api/kb/datasets",
            {
                "name": "New Dataset",
                "description": "notes",
                "chunk_method": "naive",
                "embedding_model": "text-embedding-3-small@OpenAI",
            },
        )

        self.assertEqual(created["dataset"]["dataset_id"], "created")
        self.assertEqual(created["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(self.gateway.last_created["embedding_model"], "text-embedding-3-small@OpenAI")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.create")
        self.assertEqual(audit["events"][0]["target_id"], "created")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_name"], "New Dataset")

    def test_dataset_delete_writes_kb_audit_record(self):
        deleted = self._delete_json("/api/kb/datasets/demo")

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertEqual(deleted["delete"]["dataset_ids"], ["demo"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "demo")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_ids"], ["demo"])

    def test_dataset_delete_all_writes_kb_audit_record(self):
        self.gateway.extra_datasets["scratch"] = {
            "backend": "fake-kb",
            "dataset_id": "scratch",
            "name": "Scratch",
            "document_count": 0,
            "chunk_count": 0,
        }

        deleted = self._delete_json("/api/kb/datasets", {"delete_all": True})

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertTrue(deleted["delete"]["delete_all"])
        self.assertEqual(deleted["delete"]["dataset_ids"], [])
        self.assertEqual(deleted["delete"]["deleted_dataset_ids"], ["scratch"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "scratch")
        self.assertTrue(audit["events"][0]["metadata"]["delete_all"])

    def test_dataset_delete_by_name_writes_kb_audit_record(self):
        self.gateway.extra_datasets["bad"] = {
            "backend": "fake-kb",
            "dataset_id": "bad",
            "name": "Bad Dataset",
            "document_count": 0,
            "chunk_count": 0,
        }

        deleted = self._delete_json("/api/kb/datasets", {"dataset_names": ["Bad Dataset"]})

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertEqual(deleted["delete"]["dataset_names"], ["Bad Dataset"])
        self.assertEqual(deleted["delete"]["dataset_ids"], ["bad"])
        self.assertEqual(deleted["delete"]["deleted_dataset_ids"], ["bad"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "bad")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_names"], ["Bad Dataset"])

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
        self.assertIn("来源阅读器", html)
        self.assertIn("ingestion-status", html)
        self.assertIn("ingestion-actions", html)
        self.assertIn("parse-documents", html)
        self.assertIn("audit-action-filter", html)
        self.assertIn("source.read", html)
        self.assertIn("review-status-filter", html)
        self.assertIn("memory.search", html)
        self.assertIn("needs_edit", html)
        self.assertIn("review.revise", html)
        self.assertIn("button.revise", script)
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
        self.assertIn("补充检索问题", html)
        self.assertIn("source_inspection_limit", html)
        self.assertIn("来源检查", html)
        self.assertIn("use_kg", html)
        self.assertIn('data-view="reader"', html)
        self.assertIn('data-view="writing"', html)
        self.assertIn('data-view="activity"', html)
        self.assertIn("写作工作区", html)
        self.assertIn("runtime-diagnostics", html)
        self.assertIn("工作区策略", html)
        self.assertIn("policy-settings", html)
        self.assertIn("component-check-result", html)
        self.assertIn("run-component-check", html)
        self.assertIn("product-eval-result", html)
        self.assertIn("run-product-eval", html)
        self.assertIn("产品验收", html)
        self.assertIn('<option value="eval.run">eval.run</option>', html)
        self.assertIn("retrieval-probe-result", html)
        self.assertIn("run-retrieval-probe", html)
        self.assertIn("memory-probe-result", html)
        self.assertIn("run-memory-probe", html)
        self.assertIn("closed-loop-probe-result", html)
        self.assertIn("run-closed-loop-probe", html)
        self.assertIn("probe-dataset-picker", html)
        self.assertIn("configure_embedding_provider", script)
        self.assertIn("upload-dataset-picker", html)
        self.assertIn("upload-use-dataset", html)
        self.assertIn("run-ingest-loop", html)
        self.assertIn("run_file_to_work_product_loop", script)
        self.assertIn("prepareIngestLoopForm", script)
        self.assertIn('showToast(t("toast.prepareLoop"));', script)
        self.assertIn("loop_question", html)
        self.assertIn("loop_export_format", html)
        self.assertIn("loop_retrieval_queries", html)
        self.assertIn("loop_max_iterations", html)
        self.assertIn("loop_min_context_packets", html)
        self.assertIn("loop_source_inspection_limit", html)
        self.assertIn("loop_proposal_kind", html)
        self.assertIn("loop_create_review", html)
        self.assertIn("loop_use_kg", html)
        self.assertIn("Embedding 模型", html)
        self.assertIn("embedding_model", html)
        self.assertIn("embedding_model: form.get(\"embedding_model\")", script)
        self.assertIn('payload.append("embedding_model", form.get("embedding_model") || "");', script)
        self.assertIn("deleteDataset(dataset.dataset_id)", script)
        self.assertIn("delete-all-datasets", html)
        self.assertIn("deleteAllDatasets", script)
        self.assertIn("delete_all: true", script)
        self.assertIn("renderDatasetPickers", script)
        self.assertIn("/api/kb/datasets/${encodeURIComponent(datasetId)}", script)
        self.assertIn("kb.dataset.delete", script)
        self.assertIn("heading.componentCheck", script)
        self.assertIn("retrieval.probe", html)
        self.assertIn("memory.probe", html)
        self.assertIn("create-memory-review", html)
        self.assertIn("记忆审核", html)
        self.assertIn("home-next-actions", html)
        self.assertIn("下一步", html)
        self.assertIn("home-resumable-asks", html)
        self.assertIn("loadCapabilities", script)
        self.assertIn('/api/capabilities', script)
        self.assertIn("label.capabilityContract", script)
        self.assertIn("workspaceActionButtonLabel", script)
        self.assertIn('apply_accepted_memory: t("button.apply")', script)
        self.assertIn('wait_for_resumable_ask: t("button.track")', script)
        self.assertIn('action.action === "wait_for_resumable_ask"', script)
        self.assertIn("openBlockedAskRun", script)
        self.assertIn("askResultFromResumableRecord", script)
        self.assertIn("button.openAsk", script)
        self.assertIn('inspect_unsupported_memory_operation: t("button.inspect")', script)
        self.assertIn('action.action === "inspect_unsupported_memory_operation"', script)
        self.assertIn('await applyMemory(params.review_id);', script)
        self.assertIn('await parseDatasetDocuments(datasetId, params.document_ids || []);', script)
        self.assertIn('await checkAskReadiness({ silent: true });', script)
        self.assertIn("memoryCapabilities", script)
        self.assertIn("memoryOperationSupported", script)
        self.assertIn("capability.supported === true", script)
        self.assertIn("能力契约尚未加载。", script)
        self.assertIn("memoryOperationForProposalKind", script)
        self.assertIn("button.unsupportedUpdate", script)
        self.assertIn("button.unsupportedMemoryApply", script)
        self.assertIn("capabilityLabel(memoryCaps, \"update\")", script)
        self.assertIn("label.workspace", script)
        self.assertIn("label.tenant", script)
        self.assertIn("label.memoryNamespace", script)
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
        self.assertIn('resumeBlockedRun', script)
        self.assertIn('resumeIngestLoopRun', script)
        self.assertIn('resumeContractForResult', script)
        self.assertIn('resumeContractForRun', script)
        self.assertIn('isIngestLoopResume', script)
        self.assertIn('resultNextActions', script)
        self.assertIn('appendResultContractActions', script)
        self.assertIn('record.resume', script)
        self.assertIn('result.resume', script)
        self.assertIn('resume_ingest_loop: t("button.resumeLoop")', script)
        self.assertIn('track_ingestion_status: t("button.track")', script)
        self.assertIn('action.action === "resume_ingest_loop"', script)
        self.assertIn('"track_ingestion_status"', script)
        self.assertIn('params.dataset_id || (params.dataset_ids || [])[0]', script)
        self.assertIn('/resume-ingest-loop', script)
        self.assertIn('hasIngestLoopResume', script)
        self.assertIn('button.resumeLoop', script)
        self.assertIn('refreshBlockedAskReadiness', script)
        self.assertIn('button.checkReadiness', script)
        self.assertIn('startBlockedAskTracking', script)
        self.assertIn('stopBlockedAskTracking', script)
        self.assertIn('button.trackResume', script)
        self.assertIn('知识范围已就绪，正在恢复流程。', script)
        self.assertIn('知识范围已可恢复。', script)
        self.assertIn('toast.kbReadyAskUpdated', script)
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
        self.assertIn('showToast(t("toast.kbCreatedSelected"));', script)
        self.assertIn('setUploadDataset(payload.dataset.dataset_id);', script)
        self.assertIn('document.getElementById("upload-use-dataset").addEventListener("click", setUploadDatasetFromPicker);', script)
        self.assertIn('document.getElementById("run-ingest-loop").addEventListener("click", runIngestLoopFromUploadForm);', script)
        self.assertIn('/api/ingest-loop', script)
        self.assertIn("openLoopWorkProduct", script)
        self.assertIn("appendIngestLoopControls", script)
        self.assertIn("auditActionForIngestLoop", script)
        self.assertIn("syncReviewRecord(result.review);", script)
        self.assertIn('await loadAuditEvents(auditActionForIngestLoop(result));', script)
        self.assertIn('result.status === "not_ready" && result.run && result.run.run_id', script)
        self.assertIn('await applyAskResult(result, { toast: result.message || t("toast.ingestLoopWaiting") });', script)
        self.assertIn('payload.append("wait_ready", form.get("wait") ? "true" : "false");', script)
        self.assertIn('payload.append("retrieval_queries", form.get("loop_retrieval_queries") || "");', script)
        self.assertIn('payload.append("use_kg", form.get("loop_use_kg") ? "true" : "false");', script)
        self.assertIn('payload.append("create_review", "true");', script)
        self.assertIn('const datasetId = ingestDatasetId(result.ingest);', script)
        self.assertIn('showToast(t("toast.uploadAcceptedSelected"));', script)
        self.assertIn('renderIngestResult(result.ingest, result.readiness);\n    await loadDatasets();\n    await loadAuditEvents("kb.ingest");', script)
        self.assertIn('await loadDocuments(datasetId, { silent: true });\n  await loadWorkspaceStatus();\n  await loadAuditEvents("kb.parse");', script)
        self.assertIn('/api/runtime/diagnostics', script)
        self.assertIn('/api/runtime/component-check', script)
        self.assertIn('/api/runtime/eval', script)
        self.assertIn('runProductEval', script)
        self.assertIn('renderProductEval', script)
        self.assertIn('evalResultCard', script)
        self.assertIn('auditActionForEval', script)
        self.assertIn('return "eval.run"', script)
        self.assertIn('event.action === "eval.run"', script)
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
        self.assertIn('/api/runtime/memory-probe', script)
        self.assertIn('/api/runtime/closed-loop-probe', script)
        self.assertIn('/memory-review', script)
        self.assertIn('setReviewStatusFilter("");\n  syncReviewRecord(payload.review);', script)
        self.assertIn('await loadAuditEvents(payload.memory_apply ? memoryApplyAction(payload.memory_apply) : "review.create");', script)
        self.assertIn("document.querySelector('.nav-item[data-view=\"review\"]').click();\n  showToast(payload.memory_apply ? memoryApplyToast(payload.memory_apply) : \"记忆审核已创建。\");", script)
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
        self.assertIn('heading.inspectedSources', script)
        self.assertIn('heading.durableMemory', script)
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
        self.assertIn('toast.askScopeReady', script)
        self.assertIn('toast.askScopeNotReady', script)
        self.assertIn('empty.noAskScopeChecked', script)
        self.assertIn('button.runAsk', script)
        self.assertIn('button.parseScope', script)
        self.assertIn('button.openStatus', script)
        self.assertIn('form.requestSubmit();', script)
        self.assertIn('ingestion_status', script)
        self.assertIn('mergeReadinessDocuments', script)
        self.assertIn('renderIngestionActions', script)
        self.assertIn('button.askThisKb', script)
        self.assertIn('button.trackStatus', script)
        self.assertIn('onclick: () => askDocument(datasetId, document)', script)
        self.assertIn('function askDocument(datasetId, document)', script)
        self.assertIn('setAskDocumentIds([documentId]);', script)
        self.assertIn('showToast("文档已加入提问范围。");', script)
        self.assertIn('prepareAskScope(datasetId, documents);', script)
        self.assertIn('prepareAskScope(datasetId, displayDocuments);', script)
        self.assertIn('state.askDocumentsByDataset[normalized] = documents;', script)
        self.assertIn('next_action', script)
        self.assertIn('formatPercent', script)
        self.assertIn('diagnosticCard', script)
        self.assertIn('retrievalProbeCard', script)
        self.assertIn('closedLoopProbeCard', script)
        self.assertIn('auditEventCard', script)
        self.assertIn('source_count', script)
        self.assertIn('memory_target_id', script)
        self.assertIn('readDocumentGraph', script)
        self.assertIn('图谱已加载', script)
        self.assertIn('addAskDataset', script)
        self.assertIn('loadAskDocuments', script)
        self.assertIn('askDocumentCard', script)
        self.assertIn('setAskDatasetIds', script)
        self.assertIn('t("button.ask")', script)
        self.assertIn('t("button.upload")', script)
        self.assertIn('t("button.openStatus")', script)
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
        self.assertIn('记忆生命周期已加载。', script)
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
        self.assertIn('button.applyMemory', script)
        self.assertIn('button.applyMemoryUpdate', script)
        self.assertIn('button.applyMemoryDelete', script)
        self.assertIn('button.createUpdateReview', script)
        self.assertIn('button.createDeleteReview', script)
        self.assertIn('createMemoryUpdateReview', script)
        self.assertIn('createMemoryDeleteReview', script)
        self.assertIn('memoryApplyLabel', script)
        self.assertIn('memoryApplyAction', script)
        self.assertIn('heading.appliedKnowledge', script)
        self.assertIn('memoryApplyCard', script)
        self.assertIn('openMemoryLifecycle(memoryApply.target_id)', script)
        self.assertIn('if (memoryApply.target_id) {\n      actions.append(\n        el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(memoryApply.target_id) }, t("button.history")),\n      );\n    }', script)
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
        self.assertIn('记忆已应用', script)
        self.assertIn('label.locked', script)
        self.assertIn('memory_apply', script)
        self.assertIn('heading.retrievedContext', script)
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

    def _get_json_error(self, path: str) -> dict:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=5) as response:
                self.fail(f"expected HTTP error, got {response.status}")
        except HTTPError as exc:
            return {
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }

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

    def _delete_json(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))


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
        reset_fake_kb_gateway()
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

    def test_eval_route_runs_product_acceptance_suite(self):
        result = self._post_json(
            "/api/runtime/eval",
            {"suite": "product_acceptance"},
        )["eval"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["suite"], "product_acceptance")
        self.assertEqual(result["steps"][0]["name"], "upload_loop.ready_export")
        self.assertEqual(result["steps"][-1]["name"], "audit.traceability")
        audit = self._get_json("/api/audit?limit=5&action=eval.run")
        self.assertEqual(audit["events"][0]["metadata"]["suite"], "product_acceptance")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

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

    def test_product_api_ingest_loop_uploads_asks_exports_and_audits(self):
        dataset_name = f"Ingest Loop API {uuid4().hex}"
        unique_phrase = f"product api ingest loop {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": f"What does the uploaded file say about {unique_phrase}?",
                "export_format": "json",
                "poll_interval_seconds": "0.05",
                "limit": "2",
                "max_iterations": "4",
                "min_context_packets": "1",
                "retrieval_queries": "secondary retrieval\ntertiary retrieval",
                "source_inspection_limit": "0",
                "use_kg": "true",
            },
            "loop-note.txt",
            f"The uploaded file says {unique_phrase} inside the PSKA loop.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ask_status"], "ready")
        self.assertTrue(result["readiness"]["ready"])
        self.assertTrue(result["run_id"].startswith("run_"))
        self.assertEqual(result["run"]["run_id"], result["run_id"])
        self.assertEqual(result["proposal"]["kind"], "writing_brief")
        self.assertIsNone(result["review"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(result["loop"]["status"], "ready")
        self.assertEqual(result["export"]["traceability"]["source_count"], 1)
        self.assertEqual(result["export"]["traceability"]["source_inspection_count"], 0)
        ask_request = result["export"]["run"]["metadata"]["ask_request"]
        self.assertEqual(ask_request["limit"], 2)
        self.assertEqual(ask_request["max_iterations"], 4)
        self.assertEqual(ask_request["min_context_packets"], 1)
        self.assertEqual(ask_request["retrieval_queries"], ["secondary retrieval", "tertiary retrieval"])
        self.assertEqual(ask_request["source_inspection_limit"], 0)
        self.assertTrue(ask_request["use_kg"])
        self.assertTrue(result["export"]["run"]["scope"]["use_kg"])
        self.assertIn(unique_phrase, result["export"]["context_packets"][0]["text"])
        ingest_audit = self._get_json("/api/audit?limit=10&action=kb.ingest")
        self.assertEqual(ingest_audit["events"][0]["metadata"]["document_names"], ["loop-note.txt"])
        export_audit = self._get_json("/api/audit?limit=10&action=workflow.export")
        self.assertEqual(export_audit["events"][0]["target_id"], result["run_id"])

    def test_product_api_ingest_loop_exposes_governance_payload_for_review(self):
        dataset_name = f"Ingest Loop Review API {uuid4().hex}"
        unique_phrase = f"product api ingest loop review {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": f"What durable knowledge rule mentions {unique_phrase}?",
                "proposal_kind": "memory_patch",
                "create_review": "true",
                "export_format": "json",
                "poll_interval_seconds": "0.05",
            },
            "review-note.txt",
            f"The durable knowledge rule says {unique_phrase} must be reviewed before memory is written.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertEqual(result["review"]["proposal_id"], result["proposal"]["proposal_id"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertTrue(result["loop"]["review_required"])
        self.assertEqual(result["loop"]["governance"]["action"], "manual_review")
        self.assertEqual(result["export"]["latest_proposal"]["kind"], "memory_patch")
        review_audit = self._get_json("/api/audit?limit=10&action=review.create")
        self.assertEqual(review_audit["events"][0]["target_id"], result["review"]["review_id"])
        memory_audit = self._get_json("/api/audit?limit=10&action=memory.apply")
        self.assertEqual(memory_audit["events"], [])

    def test_product_api_ingest_loop_records_resumable_ask_when_upload_is_processing(self):
        dataset_name = f"Ingest Loop Processing API {uuid4().hex}"
        question = "What should happen after this uploaded file finishes parsing?"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": question,
                "parse": "false",
                "wait_ready": "false",
                "poll_interval_seconds": "0.05",
            },
            "slow-note.txt",
            "This uploaded source is intentionally left unparsed so the Ask can resume later.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["ask_status"], "not_ready")
        self.assertIsNotNone(result["run"])
        self.assertEqual(result["run"]["status"], "blocked")
        self.assertEqual(result["run"]["metadata"]["blocked_reason"], "kb_not_ready")
        self.assertEqual(result["run"]["metadata"]["ask_request"]["question"], question)
        self.assertEqual(result["run"]["metadata"]["ingest_loop"]["export_format"], "markdown")
        self.assertEqual(result["loop"]["status"], "not_ready")
        self.assertEqual(result["resume"]["tool"], "pska_ingest_loop_resume")
        self.assertEqual(result["resume"]["api"], f"POST /api/workflows/{result['run_id']}/resume-ingest-loop")
        self.assertFalse(result["resume"]["can_resume"])
        self.assertEqual(result["next_actions"][0]["action"], "track_ingestion_status")
        self.assertEqual(result["next_actions"][1]["action"], "resume_ingest_loop")
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIsNone(result["export"])
        waiting = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(waiting["resumable_asks"][0]["run"]["run_id"], result["run_id"])
        self.assertFalse(waiting["resumable_asks"][0]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["ask_request"]["question"], question)
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["tool"], "pska_ingest_loop_resume")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["api"], f"POST /api/workflows/{result['run_id']}/resume-ingest-loop")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["params"]["export_format"], "markdown")
        self.assertEqual(waiting["resumable_asks"][0]["next_actions"][-1]["action"], "resume_ingest_loop")
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("kb.ingest", actions)
        self.assertIn("agentic_loop.not_ready", actions)
        self.assertIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)

        dataset_id = result["dataset"]["dataset_id"]
        document_ids = [document["document_id"] for document in result["documents"]]
        parsed = self._post_json(f"/api/kb/datasets/{dataset_id}/parse", {"document_ids": document_ids})
        self.assertEqual(parsed["ingestion_status"]["status"], "ready")

        resumed_payload = self._post_json(f"/api/workflows/{result['run_id']}/resume-ingest-loop", {})
        resumed = resumed_payload["ingest_loop"]

        self.assertEqual(resumed["kind"], "ingest_loop_resume")
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["ask_status"], "ready")
        self.assertEqual(resumed["export_format"], "markdown")
        self.assertIsNone(resumed["resume"])
        self.assertEqual(resumed["next_actions"], [])
        self.assertEqual(resumed["ingest"]["resumed_from_run_id"], result["run_id"])
        self.assertIn("This uploaded source is intentionally left unparsed", resumed["brief"])
        self.assertIsInstance(resumed["export"], str)
        resumed_audit = self._get_json("/api/audit?limit=30")
        resumed_actions = [event["action"] for event in resumed_audit["events"]]
        self.assertIn("agentic_loop.resume", resumed_actions)
        self.assertIn("workflow.export", resumed_actions)

    def test_product_api_fake_pdf_upload_reports_ingestion_failure_before_ask(self):
        dataset_name = f"Unsupported Fake PDF {uuid4().hex}"
        ingested = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "parse": "true",
                "wait": "false",
            },
            "annual-report.pdf",
            b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\nbinary fake pdf",
            content_type="application/pdf",
        )
        dataset_id = ingested["ingest"]["dataset"]["dataset_id"]

        self.assertEqual(ingested["ingestion_status"]["status"], "failed")
        self.assertEqual(ingested["ingestion_status"]["next_actions"], ["inspect_failed_documents"])
        self.assertIn("Fake KB can only parse UTF-8 text files", ingested["readiness"]["blocking"][0])

        asked = self._post_json(
            "/api/ask",
            {
                "question": "What is in the unsupported PDF?",
                "dataset_ids": [dataset_id],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "not_ready")
        self.assertEqual(asked["readiness"]["status"], "failed")
        self.assertEqual(asked["context_packets"], [])
        self.assertIsNone(asked["proposal"])

    def test_product_api_ingest_loop_stops_before_ask_when_upload_is_not_ready(self):
        dataset_name = f"Unsupported Loop PDF {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": "What is in the unsupported PDF?",
                "poll_interval_seconds": "0.05",
            },
            "annual-report.pdf",
            b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\nbinary fake pdf",
            content_type="application/pdf",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["readiness"]["status"], "failed")
        self.assertIsNone(result["ask_status"])
        self.assertIsNone(result["run"])
        self.assertIsNone(result["export"])
        actions = [event["action"] for event in self._get_json("/api/audit?limit=20")["events"]]
        self.assertIn("kb.ingest", actions)
        self.assertNotIn("agentic_loop.not_ready", actions)
        self.assertNotIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)
        self.assertNotIn("agentic_loop.complete", actions)

    def _post_multipart_ingest(
        self,
        fields: dict[str, str],
        filename: str,
        content: str | bytes,
        *,
        content_type: str = "text/plain",
        route: str = "/api/kb/ingest",
    ) -> dict:
        boundary = f"pska-test-{uuid4().hex}"
        file_content = content.encode("utf-8") if isinstance(content, str) else content
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
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_content,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        request = Request(
            f"{self.base_url}{route}",
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
