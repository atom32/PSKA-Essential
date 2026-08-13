from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.adapters.fake import FakeRetrievalAdapter
from pska_essential.adapters.sqlite import SQLiteMemoryAdapter
from pska_essential.config import build_service_from_env
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowError, WorkflowService


class SQLiteMemoryAdapterTests(unittest.TestCase):
    def test_sqlite_memory_persists_reviewed_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            memory_path = Path(temp_dir) / "memory.sqlite3"
            review_path = Path(temp_dir) / "review.sqlite3"
            service = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(memory_path),
                SQLiteReviewStore(review_path),
            )
            run = service.start("sqlite memory workflow", {"dataset_ids": ["demo"]})
            service.context_retrieve(run.run_id, "adapter memory review", 1)
            proposal = service.propose(run.run_id, "memory_patch", "remember sqlite memory")
            review = service.review_create(proposal.proposal_id)

            with self.assertRaises(WorkflowError):
                service.memory_apply(review.review_id)

            service.review_decide(review.review_id, "accept", "approved")
            applied = service.memory_apply(review.review_id)
            self.assertEqual(applied.backend, "sqlite")

            reopened = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(memory_path),
                SQLiteReviewStore(review_path),
            )
            facts = reopened.memory_search("sqlite memory", {}, 10)
            self.assertEqual(len(facts), 1)
            self.assertEqual(facts[0].fact_id, applied.target_id)
            self.assertEqual(facts[0].source_refs[0].adapter, "fake")
            self.assertEqual(facts[0].metadata["proposal_id"], proposal.proposal_id)
            self.assertEqual(facts[0].metadata["review_id"], review.review_id)

    def test_sqlite_memory_update_and_delete_are_review_gated(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            service = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(Path(temp_dir) / "memory.sqlite3"),
                SQLiteReviewStore(Path(temp_dir) / "review.sqlite3"),
            )
            run = service.start("sqlite update delete workflow", {"dataset_ids": ["demo"]})
            service.context_retrieve(run.run_id, "adapter memory review", 1)
            proposal = service.propose(run.run_id, "memory_patch", "remember obsoletephrase")
            review = service.review_create(proposal.proposal_id)
            service.review_decide(review.review_id, "accept", "approved")
            applied = service.memory_apply(review.review_id)

            fact = service.memory_search("obsoletephrase", {}, 10)[0]
            update_result = service.memory_update_review(fact, "Current sqlite fact", "better wording")
            update_review_id = update_result["review"]["review_id"]
            with self.assertRaises(WorkflowError):
                service.memory_apply(update_review_id)
            service.review_decide(update_review_id, "accept", "update approved")
            updated = service.memory_apply(update_review_id)

            self.assertEqual(updated.target_id, applied.target_id)
            self.assertEqual(updated.metadata["version"], 2)
            self.assertEqual(service.memory_search("obsoletephrase", {}, 10), [])
            updated_fact = service.memory_search("Current sqlite fact", {}, 10)[0]
            self.assertEqual(updated_fact.text, "Current sqlite fact")
            self.assertEqual(updated_fact.metadata["display_text"], "Current sqlite fact")
            self.assertEqual(updated_fact.metadata["current_text"], "Current sqlite fact")
            self.assertEqual(updated_fact.metadata["versions"][0]["text"], proposal.memory_patch.text)

            delete_result = service.memory_delete_review(updated_fact, "outdated")
            delete_review_id = delete_result["review"]["review_id"]
            with self.assertRaises(WorkflowError):
                service.memory_apply(delete_review_id)
            service.review_decide(delete_review_id, "accept", "delete approved")
            deleted = service.memory_apply(delete_review_id)

            self.assertEqual(deleted.target_id, applied.target_id)
            self.assertEqual(service.memory_search("Current sqlite fact", {}, 10), [])

    def test_scoped_sqlite_memory_create_update_delete_are_review_gated(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            service = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(Path(temp_dir) / "memory.sqlite3"),
                SQLiteReviewStore(Path(temp_dir) / "review.sqlite3"),
            )
            scope = {"dataset_ids": ["demo"], "memory_namespace": "project:eidolia-smoke"}
            run = service.start("scoped sqlite update delete workflow", scope)
            service.context_retrieve(run.run_id, "adapter memory review", 1)
            proposal = service.propose(run.run_id, "memory_patch", "remember scoped obsoletephrase")
            review = service.review_create(proposal.proposal_id)
            with self.assertRaises(WorkflowError):
                service.memory_apply(review.review_id)
            service.review_decide(review.review_id, "accept", "approved")
            applied = service.memory_apply(review.review_id)

            self.assertEqual(service.memory_search("obsoletephrase", {}, 10), [])
            fact = service.memory_search("obsoletephrase", scope, 10)[0]
            self.assertEqual(fact.fact_id, applied.target_id)
            self.assertEqual(fact.metadata["memory_namespace"], "project:eidolia-smoke")

            update_result = service.memory_update_review(fact, "Current scoped sqlite fact", "better wording")
            update_review_id = update_result["review"]["review_id"]
            with self.assertRaises(WorkflowError):
                service.memory_apply(update_review_id)
            service.review_decide(update_review_id, "accept", "update approved")
            updated = service.memory_apply(update_review_id)

            self.assertEqual(updated.target_id, applied.target_id)
            self.assertEqual(service.memory_search("obsoletephrase", scope, 10), [])
            updated_fact = service.memory_search("Current scoped sqlite fact", scope, 10)[0]
            self.assertEqual(updated_fact.fact_id, applied.target_id)
            self.assertEqual(updated_fact.metadata["display_text"], "Current scoped sqlite fact")
            self.assertEqual(updated_fact.metadata["current_text"], "Current scoped sqlite fact")
            self.assertEqual(updated_fact.metadata["memory_namespace"], "project:eidolia-smoke")

            delete_result = service.memory_delete_review(updated_fact, "outdated")
            delete_review_id = delete_result["review"]["review_id"]
            with self.assertRaises(WorkflowError):
                service.memory_apply(delete_review_id)
            service.review_decide(delete_review_id, "accept", "delete approved")
            deleted = service.memory_apply(delete_review_id)

            self.assertEqual(deleted.target_id, applied.target_id)
            self.assertEqual(service.memory_search("Current scoped sqlite fact", scope, 10), [])

    def test_sqlite_memory_is_scoped_by_workspace_and_tenant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.sqlite3"
            review_path = Path(temp_dir) / "review.sqlite3"

            with patch.dict(
                os.environ,
                {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-a"},
                clear=True,
            ):
                service_a = WorkflowService(
                    FakeRetrievalAdapter(),
                    SQLiteMemoryAdapter(memory_path),
                    SQLiteReviewStore(review_path),
                )
                result = service_a.memory_change_from_conversation(
                    user_message="Remember tenant a sqlite preference.",
                    text="Tenant A prefers sqlite memory.",
                )
                self.assertEqual(result["status"], "applied")
                self.assertEqual(len(service_a.memory_search("sqlite memory", {}, 10)), 1)

            with patch.dict(
                os.environ,
                {"PSKA_WORKSPACE_ID": "workspace-shared", "PSKA_TENANT_ID": "tenant-b"},
                clear=True,
            ):
                service_b = WorkflowService(
                    FakeRetrievalAdapter(),
                    SQLiteMemoryAdapter(memory_path),
                    SQLiteReviewStore(review_path),
                )
                self.assertEqual(service_b.memory_search("sqlite memory", {}, 10), [])

    def test_conversation_memory_respects_explicit_memory_namespace_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(os.environ, {}, clear=True):
            service = WorkflowService(
                FakeRetrievalAdapter(),
                SQLiteMemoryAdapter(Path(temp_dir) / "memory.sqlite3"),
                SQLiteReviewStore(Path(temp_dir) / "review.sqlite3"),
            )
            scope = {"memory_namespace": "project:eidolia-smoke"}
            result = service.memory_change_from_conversation(
                user_message="Remember explicit namespace sqlite preference.",
                text="Explicit namespace prefers sqlite memory.",
                scope=scope,
            )

            self.assertEqual(result["status"], "applied")
            self.assertEqual(service.memory_search("sqlite memory", {}, 10), [])
            self.assertEqual(len(service.memory_search("sqlite memory", scope, 10)), 1)
            self.assertEqual(service.memory_search("sqlite memory", {"memory_namespace": "other"}, 10), [])

    def test_build_service_from_env_accepts_sqlite_memory_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {
                "PSKA_DEV_FAKE": "1",
                "PSKA_RETRIEVAL_PROVIDER": "fake",
                "PSKA_KB_PROVIDER": "fake",
                "PSKA_MEMORY_PROVIDER": "sqlite",
                "PSKA_REVIEW_DB": str(Path(temp_dir) / "review.sqlite3"),
                "PSKA_MEMORY_DB": str(Path(temp_dir) / "memory.sqlite3"),
            }
            with patch.dict(os.environ, env, clear=True):
                service = build_service_from_env()

            self.assertEqual(service.memory.backend_name, "sqlite")


if __name__ == "__main__":
    unittest.main()
