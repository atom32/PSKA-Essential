from __future__ import annotations

import json
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
        self.create_calls = []

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

    def create_dataset(
        self,
        *,
        name,
        description="",
        chunk_method="naive",
        embedding_model="",
        permission="me",
        parser_config=None,
    ):
        self.create_calls.append(
            {
                "name": name,
                "description": description,
                "chunk_method": chunk_method,
                "embedding_model": embedding_model,
            }
        )
        return {
            "backend": "ragflow",
            "dataset_id": "dataset-new",
            "name": name,
            "description": description,
            "document_count": 0,
            "chunk_count": 0,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
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
        self.scan_page_size = 2

    def _request(self, method, path, *, body=None, headers=None, params=None):
        self.calls.append({"method": method, "path": path, "params": dict(params or {}), "body": body})
        if method == "GET" and path == "/datasets":
            page = int((params or {}).get("page") or 1)
            if page == 2:
                return [
                    {"id": "dataset-page-2", "name": "Page Two Dataset"},
                ]
            if page > 2:
                return []
            return [
                {"id": "dataset-by-name", "name": "Bad Embedding Dataset"},
                {"id": "other-dataset", "name": "Other"},
            ]
        if method == "GET" and path == "/datasets/dataset-1/documents":
            page = int((params or {}).get("page") or 1)
            if page == 2:
                return {
                    "total": 3,
                    "docs": [
                        {
                            "id": "doc-page-2",
                            "name": "page-two.txt",
                            "dataset_id": "dataset-1",
                            "chunk_count": 1,
                            "run": "DONE",
                        }
                    ],
                }
            if page > 2:
                return {"total": 3, "docs": []}
            return {
                "total": 3,
                "docs": [
                    {
                        "id": "doc-page-1",
                        "name": "page-one.txt",
                        "dataset_id": "dataset-1",
                        "chunk_count": 1,
                        "run": "DONE",
                    },
                    {
                        "id": "doc-other",
                        "name": "other.txt",
                        "dataset_id": "dataset-1",
                        "chunk_count": 1,
                        "run": "DONE",
                    },
                ],
            }
        if method == "POST" and path == "/datasets":
            payload = json.loads((body or b"{}").decode("utf-8"))
            return {
                "id": "dataset-created",
                "name": payload.get("name", ""),
                "embedding_model": payload.get("embedding_model", ""),
            }
        return []


class KbGatewayTests(unittest.TestCase):
    def test_ragflow_list_operations_cap_page_size_to_provider_limit(self):
        gateway = _RequestRecordingRagflowGateway()

        gateway.list_datasets(page_size=200)
        gateway.list_documents(dataset_id="dataset-1", page_size=500)

        self.assertEqual(gateway.calls[0]["params"]["page_size"], 100)
        self.assertEqual(gateway.calls[1]["params"]["page_size"], 100)

    def test_ragflow_create_dataset_sends_embedding_model_contract(self):
        gateway = _RequestRecordingRagflowGateway()

        dataset = gateway.create_dataset(name="Reports", embedding_model="text-embedding-3-small@OpenAI")

        sent = json.loads(gateway.calls[0]["body"].decode("utf-8"))
        self.assertEqual(sent["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertNotIn("embd_id", sent)
        self.assertEqual(dataset["embedding_model"], "text-embedding-3-small@OpenAI")

    def test_ragflow_delete_dataset_uses_public_delete_contract(self):
        gateway = _RequestRecordingRagflowGateway()

        result = gateway.delete_datasets(dataset_ids=["0876c5b87f4a11f189366f73247a116f"])

        sent = json.loads(gateway.calls[0]["body"].decode("utf-8"))
        self.assertEqual(gateway.calls[0]["method"], "DELETE")
        self.assertEqual(gateway.calls[0]["path"], "/datasets")
        self.assertEqual(sent["ids"], ["0876c5b87f4a11f189366f73247a116f"])
        self.assertFalse(sent["delete_all"])
        self.assertTrue(result["deleted"])

    def test_ragflow_delete_dataset_can_resolve_dataset_names(self):
        gateway = _RequestRecordingRagflowGateway()

        result = gateway.delete_datasets(dataset_names=["Bad Embedding Dataset"])

        sent = json.loads(gateway.calls[-1]["body"].decode("utf-8"))
        self.assertEqual(gateway.calls[-1]["method"], "DELETE")
        self.assertEqual(sent["ids"], ["dataset-by-name"])
        self.assertEqual(result["dataset_names"], ["Bad Embedding Dataset"])
        self.assertEqual(result["dataset_ids"], ["dataset-by-name"])
        self.assertEqual(result["deleted_dataset_ids"], ["dataset-by-name"])

    def test_ragflow_dataset_name_resolution_scans_visible_pages(self):
        gateway = _RequestRecordingRagflowGateway()

        result = gateway.delete_datasets(dataset_names=["Page Two Dataset"])

        self.assertEqual(result["dataset_ids"], ["dataset-page-2"])
        dataset_pages = [
            call["params"]["page"]
            for call in gateway.calls
            if call["method"] == "GET" and call["path"] == "/datasets"
        ]
        self.assertEqual(dataset_pages, [1, 2])

    def test_ragflow_ingest_dataset_id_lookup_scans_visible_pages(self):
        gateway = _RequestRecordingRagflowGateway()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("PSKA live RAGFlow lookup", encoding="utf-8")

            result = gateway.ingest_files(file_paths=[str(path)], dataset_id="dataset-page-2", parse=False)

        self.assertEqual(result["dataset"]["name"], "Page Two Dataset")
        self.assertFalse(result["dataset_created"])

    def test_ragflow_delete_dataset_name_fails_when_not_found(self):
        gateway = _RequestRecordingRagflowGateway()

        with self.assertRaisesRegex(KbGatewayError, "no dataset matched name"):
            gateway.delete_datasets(dataset_names=["Missing Dataset"])

    def test_ragflow_document_id_lookup_scans_visible_pages(self):
        gateway = _RequestRecordingRagflowGateway()

        docs = gateway.list_documents(dataset_id="dataset-1", document_id="doc-page-2", page_size=1)

        self.assertEqual([doc["document_id"] for doc in docs], ["doc-page-2"])
        document_pages = [
            call["params"]["page"]
            for call in gateway.calls
            if call["method"] == "GET" and call["path"] == "/datasets/dataset-1/documents"
        ]
        self.assertEqual(document_pages, [1, 2])

    def test_ragflow_parse_uses_current_document_parse_endpoint(self):
        gateway = _RequestRecordingRagflowGateway()

        result = gateway.parse_documents(dataset_id="dataset-1", document_ids=["doc-1"], wait=False)

        self.assertTrue(result["parse_started"])
        self.assertEqual(gateway.calls[0]["method"], "POST")
        self.assertEqual(gateway.calls[0]["path"], "/datasets/dataset-1/documents/parse")
        self.assertEqual(json.loads(gateway.calls[0]["body"].decode("utf-8")), {"document_ids": ["doc-1"]})

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
            result = gateway.ingest_files(
                file_paths=[str(path)],
                dataset_name="new-kb",
                embedding_model="text-embedding-3-small@OpenAI",
            )

        self.assertTrue(result["dataset_created"])
        self.assertEqual(result["dataset"]["dataset_id"], "dataset-new")
        self.assertEqual(result["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(gateway.create_calls[0]["embedding_model"], "text-embedding-3-small@OpenAI")

    def test_fake_kb_provider_requires_explicit_dev_mode(self):
        with patch.dict("os.environ", {"PSKA_KB_PROVIDER": "fake"}, clear=True):
            with self.assertRaisesRegex(KbGatewayError, "PSKA_KB_PROVIDER=fake"):
                build_kb_gateway_from_env()

    def test_ragflow_kb_provider_requires_backend_env(self):
        with patch.dict("os.environ", {"PSKA_KB_PROVIDER": "ragflow"}, clear=True):
            with self.assertRaisesRegex(KbGatewayError, "RAGFlow KB gateway is missing required env"):
                build_kb_gateway_from_env()

    def test_ragflow_kb_provider_uses_explicit_backend_env(self):
        env = {
            "PSKA_KB_PROVIDER": "ragflow",
            "RAGFLOW_BASE_URL": "http://ragflow.local",
            "RAGFLOW_API_KEY": "test-key",
        }
        with patch.dict("os.environ", env, clear=True):
            gateway = build_kb_gateway_from_env()

        self.assertEqual(gateway.backend_name, "ragflow")
        self.assertEqual(gateway.base_url, "http://ragflow.local")
        self.assertEqual(gateway.api_key, "test-key")

    def test_fake_kb_provider_starts_empty_for_dev_frontend(self):
        with patch.dict("os.environ", {"PSKA_DEV_FAKE": "1", "PSKA_KB_PROVIDER": "fake"}, clear=True):
            reset_fake_kb_gateway()
            gateway = build_kb_gateway_from_env()
            datasets = gateway.list_datasets()

        self.assertEqual(datasets, [])

    def test_fake_retrieval_with_kb_loader_does_not_fallback_to_builtin_corpus(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict("os.environ", env, clear=True):
            reset_fake_kb_gateway()
            service = build_service_from_env()

            packets = service.retrieval.retrieve("PSKA", {"dataset_ids": ["missing"]}, 3)

        self.assertEqual(packets, [])

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
