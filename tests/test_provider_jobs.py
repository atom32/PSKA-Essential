from __future__ import annotations

import unittest

from pska_essential.digest_jobs import enqueue_digest_job
from pska_essential.provider_jobs import build_provider_job_status
from pska_essential.workflow import build_fake_service
from tests.test_product_api import _FakeGateway


class ProviderJobStatusTests(unittest.TestCase):
    def test_provider_jobs_report_processing_kb_without_owning_queue(self):
        service = build_fake_service()
        gateway = _FakeGateway()
        gateway.ready = False

        status = build_provider_job_status(service, gateway, include_ready=False)

        self.assertEqual(status["schema"], "pska.provider_jobs.v1")
        self.assertEqual(status["status"], "processing")
        self.assertEqual(status["summary"]["processing"], 2)
        self.assertEqual(status["jobs"][0]["kind"], "kb_dataset_ingestion")
        self.assertEqual(status["jobs"][0]["dataset_id"], "demo")
        self.assertEqual(status["jobs"][0]["next_actions"], ["wait_for_ingestion"])
        self.assertIn("does not own", status["note"])

    def test_provider_jobs_include_recent_kb_audit_events(self):
        service = build_fake_service()
        gateway = _FakeGateway()
        from pska_essential.kb_audit import add_kb_ingest_audit

        add_kb_ingest_audit(
            service.store,
            {
                "backend": "fake-kb",
                "dataset_created": True,
                "dataset": {"dataset_id": "demo", "name": "Demo"},
                "documents": [{"document_id": "doc-1", "name": "doc.txt"}],
                "parse": {"parse_started": True},
            },
        )

        status = build_provider_job_status(service, gateway)

        self.assertEqual(status["recent_provider_events"][0]["action"], "kb.ingest")
        self.assertEqual(status["recent_provider_events"][0]["metadata"]["document_ids"], ["doc-1"])

    def test_provider_jobs_report_digest_job_scope_and_data_flow(self):
        service = build_fake_service()
        gateway = _FakeGateway()
        queued = enqueue_digest_job(
            service,
            dataset_ids=["demo"],
            document_ids=["doc-1"],
            question="Digest queued scope",
            priority=7,
            create_memory_review=True,
            memory_intent="Remember important facts only",
        )

        status = build_provider_job_status(service, gateway, include_ready=False)
        digest_job = next(job for job in status["jobs"] if job["kind"] == "pska_digest_job")

        self.assertEqual(digest_job["job_id"], queued["job"]["run_id"])
        self.assertEqual(digest_job["dataset_ids"], ["demo"])
        self.assertEqual(digest_job["document_ids"], ["doc-1"])
        self.assertEqual(digest_job["priority"], 7)
        self.assertEqual(digest_job["attempt_count"], 0)
        self.assertTrue(digest_job["create_memory_review"])
        self.assertEqual(digest_job["memory_intent"], "Remember important facts only")
        self.assertEqual(digest_job["next_actions"], ["run_digest_job"])
        self.assertFalse(digest_job["data_flow"]["writes_memory_directly"])
        self.assertEqual(digest_job["data_flow"]["source"], "kb_ready_scope")
        self.assertEqual(digest_job["data_flow"]["candidate_target"], "exception_review")

    def test_provider_jobs_limit_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "dataset_page_size"):
            build_provider_job_status(build_fake_service(), _FakeGateway(), dataset_page_size=0)


if __name__ == "__main__":
    unittest.main()
