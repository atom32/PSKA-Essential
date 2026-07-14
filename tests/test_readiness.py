from __future__ import annotations

import unittest

from pska_essential.readiness import evaluate_kb_readiness


class _Gateway:
    def __init__(self) -> None:
        self.datasets = {
            "ready": {
                "backend": "test",
                "dataset_id": "ready",
                "name": "Ready KB",
                "document_count": 1,
                "chunk_count": 12,
            },
            "processing": {
                "backend": "test",
                "dataset_id": "processing",
                "name": "Processing KB",
                "document_count": 1,
                "chunk_count": 0,
            },
            "failed": {
                "backend": "test",
                "dataset_id": "failed",
                "name": "Failed KB",
                "document_count": 1,
                "chunk_count": 0,
            },
        }
        self.documents = {
            "ready": [
                {
                    "backend": "test",
                    "dataset_id": "ready",
                    "document_id": "doc-ready",
                    "name": "ready.pdf",
                    "chunk_count": 12,
                    "progress": 1.0,
                    "run": "DONE",
                    "status": "ready",
                }
            ],
            "processing": [
                {
                    "backend": "test",
                    "dataset_id": "processing",
                    "document_id": "doc-processing",
                    "name": "processing.pdf",
                    "chunk_count": 0,
                    "progress": 0.2,
                    "run": "RUNNING",
                    "status": "processing",
                }
            ],
            "failed": [
                {
                    "backend": "test",
                    "dataset_id": "failed",
                    "document_id": "doc-failed",
                    "name": "failed.pdf",
                    "chunk_count": 0,
                    "progress": 0.4,
                    "progress_msg": "embedding failed",
                    "run": "FAIL",
                    "status": "failed",
                }
            ],
        }

    def list_datasets(self, *, name=None, page_size=30):
        datasets = list(self.datasets.values())
        if name:
            datasets = [dataset for dataset in datasets if dataset["name"] == name]
        return datasets[:page_size]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        docs = list(self.documents.get(dataset_id, []))
        if document_id:
            docs = [doc for doc in docs if doc["document_id"] == document_id]
        if name:
            docs = [doc for doc in docs if doc["name"] == name]
        return docs[:page_size]


class ReadinessTests(unittest.TestCase):
    def test_dataset_with_chunks_is_ready(self):
        result = evaluate_kb_readiness(_Gateway(), dataset_ids=["ready"])

        self.assertTrue(result["ready"])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["blocking"], [])

    def test_missing_dataset_blocks_ask(self):
        result = evaluate_kb_readiness(_Gateway(), dataset_ids=["missing"])

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "missing")
        self.assertIn("missing", result["blocking"][0])

    def test_dataset_without_chunks_reports_processing(self):
        result = evaluate_kb_readiness(_Gateway(), dataset_ids=["processing"])

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["datasets"][0]["documents"][0]["status"], "processing")
        self.assertEqual(result["ingestion_status"]["status"], "processing")
        self.assertEqual(result["ingestion_status"]["phase"], "processing")
        self.assertEqual(result["ingestion_status"]["progress"], 0.2)
        self.assertEqual(result["ingestion_status"]["next_actions"], ["wait_for_ingestion"])
        self.assertEqual(result["datasets"][0]["documents"][0]["phase"], "processing")
        self.assertEqual(result["datasets"][0]["documents"][0]["next_action"], "wait_for_ingestion")

    def test_specific_document_must_be_ready(self):
        result = evaluate_kb_readiness(
            _Gateway(),
            dataset_ids=["processing"],
            document_ids=["doc-processing"],
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "processing")
        self.assertIn("processing.pdf", result["blocking"][0])
        self.assertEqual(result["ingestion_status"]["document_count"], 1)
        self.assertEqual(result["ingestion_status"]["processing_count"], 1)

    def test_missing_document_blocks_ask(self):
        result = evaluate_kb_readiness(_Gateway(), dataset_ids=["ready"], document_ids=["missing-doc"])

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "missing")
        self.assertIn("missing-doc", result["blocking"][0])

    def test_failed_document_is_explicit(self):
        result = evaluate_kb_readiness(_Gateway(), dataset_ids=["failed"], document_ids=["doc-failed"])

        self.assertFalse(result["ready"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("failed", result["blocking"][0])
        self.assertEqual(result["ingestion_status"]["status"], "failed")
        self.assertEqual(result["ingestion_status"]["failed_count"], 1)
        self.assertEqual(result["datasets"][0]["documents"][0]["phase"], "failed")
        self.assertEqual(result["datasets"][0]["documents"][0]["next_action"], "inspect_failure")
        self.assertEqual(result["datasets"][0]["documents"][0]["failure_reason"], "embedding failed")


if __name__ == "__main__":
    unittest.main()
