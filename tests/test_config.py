from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pska_essential.config import build_service_from_env


class ConfigTests(unittest.TestCase):
    def test_provider_config_is_required(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER is required"):
                build_service_from_env()

    def test_fake_provider_requires_explicit_dev_mode(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER=fake"):
                build_service_from_env()

    def test_explicit_dev_fake_mode_builds_service(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict(os.environ, env, clear=True):
            service = build_service_from_env()
        self.assertEqual(service.retrieval.backend_name, "fake")
        self.assertEqual(service.memory.backend_name, "fake")

    def test_ragflow_retrieval_requires_backend_env(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "ragflow",
            "PSKA_MEMORY_PROVIDER": "company_graphrag_stub",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "RAGFlow retrieval is missing required env"):
                build_service_from_env()

    def test_graphiti_memory_requires_backend_env(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "company_graphrag_stub",
            "PSKA_MEMORY_PROVIDER": "graphiti",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(ValueError, "Graphiti memory is missing required env: GRAPHITI_BASE_URL"):
                build_service_from_env()

    def test_live_provider_config_builds_without_network_probe(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "ragflow",
            "PSKA_MEMORY_PROVIDER": "graphiti",
            "RAGFLOW_BASE_URL": "http://ragflow.local",
            "RAGFLOW_API_KEY": "test-key",
            "GRAPHITI_BASE_URL": "http://graphiti.local",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with patch.dict(os.environ, env, clear=True):
            service = build_service_from_env()

        self.assertEqual(service.retrieval.backend_name, "ragflow")
        self.assertEqual(service.memory.backend_name, "graphiti")


if __name__ == "__main__":
    unittest.main()
