from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.audit import audit_event
from pska_essential.contracts import WorkflowRun, to_jsonable
from pska_essential.governance import AUTO_APPLY, MANUAL_REVIEW, build_workspace_policy_from_env
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.runtime_context import build_runtime_workspace_context
from pska_essential.workflow import WorkflowService


class GovernancePolicyTests(unittest.TestCase):
    def test_default_policy_requires_manual_review(self):
        with patch.dict(os.environ, {}, clear=True):
            policy = build_workspace_policy_from_env()
        self.assertEqual(policy.durable_memory, MANUAL_REVIEW)
        self.assertEqual(policy.action_for("memory_patch"), MANUAL_REVIEW)
        self.assertEqual(policy.action_for("memory_delete"), MANUAL_REVIEW)
        self.assertEqual(policy.action_for("memory_update"), MANUAL_REVIEW)
        self.assertEqual(policy.action_for("writing_brief"), "skip")
        snapshot = policy.to_dict()
        self.assertEqual(snapshot["actions"]["memory_patch"], MANUAL_REVIEW)
        self.assertEqual(snapshot["actions"]["memory_update"], MANUAL_REVIEW)
        self.assertEqual(snapshot["actions"]["memory_delete"], MANUAL_REVIEW)
        self.assertEqual(snapshot["transient_results"], "skip")
        self.assertIn("memory_patch", snapshot["durable_proposal_kinds"])

    def test_env_can_configure_auto_apply(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": AUTO_APPLY}, clear=True):
            policy = build_workspace_policy_from_env()
        self.assertEqual(policy.durable_memory, AUTO_APPLY)
        self.assertEqual(policy.action_for("memory_patch"), AUTO_APPLY)
        self.assertEqual(policy.action_for("memory_delete"), AUTO_APPLY)
        self.assertEqual(policy.action_for("memory_update"), AUTO_APPLY)

    def test_invalid_policy_fails_explicitly(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": "silent_magic"}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSKA_GOVERNANCE_DURABLE_MEMORY"):
                build_workspace_policy_from_env()

    def test_runtime_workspace_context_is_explicit_when_unconfigured(self):
        with patch.dict(os.environ, {}, clear=True):
            context = build_runtime_workspace_context()
        self.assertEqual(context.workspace_id, "default")
        self.assertFalse(context.workspace_configured)
        self.assertEqual(context.tenant_id, "")
        self.assertFalse(context.tenant_configured)
        self.assertEqual(context.memory_namespace, "")

    def test_runtime_workspace_context_derives_memory_namespace(self):
        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-a", "PSKA_TENANT_ID": "tenant-a"},
            clear=True,
        ):
            context = build_runtime_workspace_context()

        self.assertEqual(context.workspace_id, "workspace-a")
        self.assertEqual(context.tenant_id, "tenant-a")
        self.assertEqual(context.memory_namespace, "workspace:workspace-a:tenant:tenant-a")
        self.assertEqual(context.to_dict()["memory_namespace"], "workspace:workspace-a:tenant:tenant-a")

    def test_runtime_workspace_context_derives_workspace_only_memory_namespace(self):
        with patch.dict(os.environ, {"PSKA_WORKSPACE_ID": "workspace-a"}, clear=True):
            context = build_runtime_workspace_context()

        self.assertEqual(context.workspace_id, "workspace-a")
        self.assertEqual(context.tenant_id, "")
        self.assertEqual(context.memory_namespace, "workspace:workspace-a")

    def test_audit_event_includes_workspace_context(self):
        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-a", "PSKA_TENANT_ID": "tenant-a"},
            clear=True,
        ):
            event = audit_event("workflow.start", "workflow", "run-1")
        self.assertEqual(event.metadata["workspace_id"], "workspace-a")
        self.assertEqual(event.metadata["tenant_id"], "tenant-a")
        self.assertTrue(event.metadata["workspace_configured"])
        self.assertTrue(event.metadata["tenant_configured"])

    def test_store_lists_are_scoped_by_workspace_and_tenant(self):
        store = SQLiteReviewStore(":memory:")

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            service_a = WorkflowService(FakeRetrievalAdapter(), FakeMemoryAdapter(), store)
            run_a = service_a.start("tenant a run", {"dataset_ids": ["demo"]})
            service_a.context_retrieve(run_a.run_id, "adapter", 1)
            proposal_a = service_a.propose(run_a.run_id, "memory_patch", "tenant a memory")
            review_a = service_a.review_create(proposal_a.proposal_id)
            service_a.review_decide(review_a.review_id, "accept", "tenant a accepts")
            apply_a = service_a.memory_apply(review_a.review_id)

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-b"},
            clear=False,
        ):
            service_b = WorkflowService(FakeRetrievalAdapter(), FakeMemoryAdapter(), store)
            run_b = service_b.start("tenant b run", {"dataset_ids": ["demo"]})
            service_b.context_retrieve(run_b.run_id, "adapter", 1)
            proposal_b = service_b.propose(run_b.run_id, "memory_patch", "tenant b memory")
            review_b = service_b.review_create(proposal_b.proposal_id)
            service_b.review_decide(review_b.review_id, "accept", "tenant b accepts")
            apply_b = service_b.memory_apply(review_b.review_id)

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            self.assertEqual([run.run_id for run in store.list_workflows()], [run_a.run_id])
            self.assertEqual([review["review_id"] for review in store.list_reviews()], [review_a.review_id])
            self.assertEqual(store.get_review_record(review_a.review_id)["memory_apply"]["target_id"], apply_a.target_id)
            self.assertIsNone(store.get_memory_apply(review_b.review_id))
            self.assertEqual(
                {event.metadata["tenant_id"] for event in store.list_audit_events()},
                {"tenant-a"},
            )
            with self.assertRaises(KeyError):
                store.get_workflow(run_b.run_id)
            with self.assertRaises(KeyError):
                store.get_review_record(review_b.review_id)

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-b"},
            clear=False,
        ):
            self.assertEqual([run.run_id for run in store.list_workflows()], [run_b.run_id])
            self.assertEqual([review["review_id"] for review in store.list_reviews()], [review_b.review_id])
            self.assertEqual(store.get_review_record(review_b.review_id)["memory_apply"]["target_id"], apply_b.target_id)
            self.assertIsNone(store.get_memory_apply(review_a.review_id))
            self.assertEqual(
                {event.metadata["tenant_id"] for event in store.list_audit_events()},
                {"tenant-b"},
            )
            with self.assertRaises(KeyError):
                store.get_workflow(run_a.run_id)
            with self.assertRaises(KeyError):
                store.get_review_record(review_a.review_id)

    def test_store_migrates_unscoped_rows_to_default_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "review.sqlite3"
            old_run = WorkflowRun(run_id="run_old", intent="old run", scope={"dataset_ids": ["demo"]})
            conn = sqlite3.connect(db_path)
            conn.execute(
                """
                CREATE TABLE workflows (
                    run_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO workflows(run_id, payload_json, updated_at) VALUES (?, ?, ?)",
                (old_run.run_id, json.dumps(to_jsonable(old_run), ensure_ascii=False), old_run.updated_at),
            )
            conn.commit()
            conn.close()

            with patch.dict(os.environ, {}, clear=True):
                store = SQLiteReviewStore(db_path)
                self.assertEqual([run.run_id for run in store.list_workflows()], [old_run.run_id])
                self.assertEqual(store.get_workflow(old_run.run_id).intent, old_run.intent)

            with patch.dict(
                os.environ,
                {"PSKA_WORKSPACE_ID": "other-workspace"},
                clear=True,
            ):
                self.assertEqual(store.list_workflows(), [])
                with self.assertRaises(KeyError):
                    store.get_workflow(old_run.run_id)

    def test_memory_backend_search_is_scoped_by_workspace_and_tenant(self):
        memory = FakeMemoryAdapter()
        store = SQLiteReviewStore(":memory:")

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            service_a = WorkflowService(FakeRetrievalAdapter(), memory, store)
            run = service_a.start("tenant a memory", {"dataset_ids": ["demo"]})
            service_a.context_retrieve(run.run_id, "adapter", 1)
            proposal = service_a.propose(run.run_id, "memory_patch", "tenant a private memory")
            review = service_a.review_create(proposal.proposal_id)
            service_a.review_decide(review.review_id, "accept", "tenant a accepts")
            service_a.memory_apply(review.review_id)
            self.assertEqual(len(service_a.memory_search("tenant a private memory", {}, 10)), 1)

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-b"},
            clear=False,
        ):
            service_b = WorkflowService(FakeRetrievalAdapter(), memory, store)
            self.assertEqual(service_b.memory_search("tenant a private memory", {}, 10), [])

        with patch.dict(
            os.environ,
            {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-a"},
            clear=False,
        ):
            service_a_again = WorkflowService(FakeRetrievalAdapter(), memory, store)
            self.assertEqual(len(service_a_again.memory_search("tenant a private memory", {}, 10)), 1)


if __name__ == "__main__":
    unittest.main()
