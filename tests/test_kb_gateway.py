from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pska_essential.kb_gateway import KbGatewayError, RagflowKnowledgeGateway, build_kb_gateway_from_env


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


class KbGatewayTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
