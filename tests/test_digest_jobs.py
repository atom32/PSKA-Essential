from __future__ import annotations

import unittest

from pska_essential.digest_jobs import enqueue_digest_job, list_digest_jobs, run_digest_job
from pska_essential.workflow import build_fake_service


class _ReadyGateway:
    def list_datasets(self, *, page_size=200, name=None):
        return [{"dataset_id": "demo", "name": "Demo", "document_count": 1, "chunk_count": 1}]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "doc.txt",
                "chunk_count": 1,
                "progress": 1.0,
                "run": "DONE",
            }
        ]


class _ProcessingGateway:
    def list_datasets(self, *, page_size=200, name=None):
        return [{"dataset_id": "demo", "name": "Demo", "document_count": 1, "chunk_count": 0}]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "doc.txt",
                "chunk_count": 0,
                "progress": 0.3,
                "run": "RUNNING",
            }
        ]


class DigestJobTests(unittest.TestCase):
    def test_enqueue_lists_and_runs_ready_digest_job_with_governed_review(self):
        service = build_fake_service()
        queued = enqueue_digest_job(
            service,
            dataset_ids=["demo"],
            question="Digest queued demo scope",
            priority=10,
            limit=1,
            source_inspection_limit=0,
            create_memory_review=True,
            memory_intent="Remember digest job result",
        )

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(queued["job"]["status"], "queued")
        self.assertEqual(queued["digest_job"]["priority"], 10)
        self.assertEqual(list_digest_jobs(service)[0]["job"]["run_id"], queued["job"]["run_id"])

        result = run_digest_job(service, _ReadyGateway())

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["digest_result"]["kind"], "digest_scope")
        self.assertEqual(result["digest_result"]["digest"]["kind"], "digest")
        self.assertEqual(result["digest_result"]["memory_review"]["governance"]["origin"], "digest")
        self.assertEqual(result["digest_result"]["memory_review"]["review"]["status"], "pending")
        self.assertEqual(result["digest_job"]["status"], "completed")
        self.assertEqual(result["digest_job"]["attempt_count"], 1)
        self.assertEqual(result["digest_job"]["result_run_id"], result["digest_result"]["run"]["run_id"])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("digest.job.enqueue", actions)
        self.assertIn("digest.job.run", actions)
        self.assertIn("digest.scope", actions)

    def test_run_digest_job_waits_when_scope_is_not_ready(self):
        service = build_fake_service()
        queued = enqueue_digest_job(service, dataset_ids=["demo"], question="Digest later", priority=1)

        result = run_digest_job(service, _ProcessingGateway(), run_id=queued["job"]["run_id"])

        self.assertEqual(result["status"], "waiting")
        self.assertEqual(result["digest_job"]["status"], "waiting")
        self.assertEqual(result["digest_result"], None)
        self.assertEqual(result["readiness"]["status"], "processing")
        self.assertEqual(service.store.list_reviews(), [])
        actions = [event.action for event in service.store.list_audit_events()]
        self.assertIn("digest.job.waiting", actions)
        self.assertNotIn("digest.scope", actions)

    def test_run_digest_job_reports_empty_queue(self):
        service = build_fake_service()

        result = run_digest_job(service, _ReadyGateway())

        self.assertEqual(result["status"], "empty")
        self.assertIsNone(result["job"])


if __name__ == "__main__":
    unittest.main()
