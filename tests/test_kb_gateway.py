from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.agentic_loop import run_agentic_question_with_readiness
from pska_essential.config import build_service_from_env
from pska_essential.kb_gateway import (
    KbGatewayError,
    RagflowKnowledgeGateway,
    build_kb_gateway_from_env,
    reset_fake_kb_gateway,
)
from pska_essential.readiness import evaluate_kb_readiness


class _Gateway(RagflowKnowledgeGateway):
    def __init__(self):
        super().__init__(base_url="http://ragflow.local", api_key="test")
        self.parse_calls = []

    def list_datasets(self, *, name=None, page_size=30):
        if name == "existing":
            return [
                {
                    "backend": "ragflow",
                    "dataset_id": "dataset-1",
                    "name": "existing",
                    "document_count": 0,
                    "chunk_count": 0,
                }
            ]
        return []

    def create_dataset(self, *, name, description="", chunk_method="naive", permission="me", parser_config=None):
        return {
            "backend": "ragflow",
            "dataset_id": "dataset-new",
            "name": name,
            "description": description,
            "document_count": 0,
            "chunk_count": 0,
            "chunk_method": chunk_method,
        }

    def upload_documents(self, *, dataset_id, file_paths):
        return [
            {
                "backend": "ragflow",
                "dataset_id": dataset_id,
                "document_id": "doc-1",
                "name": Path(file_paths[0]).name,
                "chunk_count": 0,
                "token_count": 0,
                "progress": 0.0,
                "run": "",
            }
        ]

    def parse_documents(self, *, dataset_id, document_ids, wait=False, timeout_seconds=300.0):
        self.parse_calls.append((dataset_id, document_ids, wait))
        return {
            "backend": "ragflow",
            "dataset_id": dataset_id,
            "document_ids": document_ids,
            "parse_started": True,
        }


class _RequestRecordingRagflowGateway(RagflowKnowledgeGateway):
    def __init__(self):
        super().__init__(base_url="http://ragflow.local", api_key="test")
        self.calls = []

    def _request(self, method, path, *, body=None, headers=None, params=None):
        self.calls.append({"method": method, "path": path, "params": dict(params or {})})
        return []


class KbGatewayTests(unittest.TestCase):
    def test_ragflow_list_operations_cap_page_size_to_provider_limit(self):
        gateway = _RequestRecordingRagflowGateway()

        gateway.list_datasets(page_size=200)
        gateway.list_documents(dataset_id="dataset-1", page_size=500)

        self.assertEqual(gateway.calls[0]["params"]["page_size"], 100)
        self.assertEqual(gateway.calls[1]["params"]["page_size"], 100)

    def test_ingest_files_reuses_existing_dataset_and_starts_parse(self):
        gateway = _Gateway()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("PSKA evidence workflow", encoding="utf-8")
            result = gateway.ingest_files(file_paths=[str(path)], dataset_name="existing")

        self.assertFalse(result["dataset_created"])
        self.assertEqual(result["dataset"]["dataset_id"], "dataset-1")
        self.assertEqual(result["documents"][0]["document_id"], "doc-1")
        self.assertEqual(gateway.parse_calls, [("dataset-1", ["doc-1"], False)])

    def test_ingest_files_can_create_dataset(self):
        gateway = _Gateway()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.txt"
            path.write_text("new kb", encoding="utf-8")
            result = gateway.ingest_files(file_paths=[str(path)], dataset_name="new-kb")

        self.assertTrue(result["dataset_created"])
        self.assertEqual(result["dataset"]["dataset_id"], "dataset-new")

    def test_fake_kb_provider_requires_explicit_dev_mode(self):
        with patch.dict("os.environ", {"PSKA_KB_PROVIDER": "fake"}, clear=True):
            with self.assertRaisesRegex(KbGatewayError, "PSKA_KB_PROVIDER=fake"):
                build_kb_gateway_from_env()

    def test_fake_kb_provider_supports_dev_frontend(self):
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=True):
            gateway = build_kb_gateway_from_env()
            datasets = gateway.list_datasets()

        self.assertEqual(datasets[0]["backend"], "fake")
        self.assertEqual(datasets[0]["dataset_id"], "demo")

    def test_fake_upload_to_ask_retrieves_uploaded_content(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "orchid-policy.txt"
            path.write_text(
                "The uploaded orchid policy says PSKA should cite source packets before durable knowledge.",
                encoding="utf-8",
            )
            gateway = build_kb_gateway_from_env()
            ingested = gateway.ingest_files(file_paths=[str(path)], dataset_name="Uploaded Fake Loop", parse=True)
            dataset_id = ingested["dataset"]["dataset_id"]
            document_id = ingested["documents"][0]["document_id"]
            service = build_service_from_env()

            result = run_agentic_question_with_readiness(
                service,
                gateway,
                question="What does the uploaded orchid policy say?",
                dataset_ids=[dataset_id],
                limit=3,
                proposal_kind="writing_brief",
            )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["context_packets"][0]["source_ref"]["document_id"], document_id)
        self.assertIn("uploaded orchid policy", result["context_packets"][0]["text"])
        self.assertIn("orchid-policy.txt", result["artifact"]["source_manifest"][0]["title"])

    def test_fake_kb_marks_pdf_like_uploads_as_failed_instead_of_ready(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            path = Path(tmp) / "annual-report.pdf"
            path.write_bytes(b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\nbinary fake pdf")
            gateway = build_kb_gateway_from_env()
            ingested = gateway.ingest_files(file_paths=[str(path)], dataset_name=f"Fake PDF {path.stem}", parse=True)
            dataset_id = ingested["dataset"]["dataset_id"]
            document = ingested["documents"][0]
            readiness = evaluate_kb_readiness(gateway, dataset_ids=[dataset_id])

        self.assertEqual(document["status"], "failed")
        self.assertEqual(document["run"], "FAIL")
        self.assertIn("Fake KB can only parse UTF-8 text files", document["progress_msg"])
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["status"], "failed")
        self.assertEqual(readiness["ingestion_status"]["next_actions"], ["inspect_failed_documents"])


if __name__ == "__main__":
    unittest.main()
