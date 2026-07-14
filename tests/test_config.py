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


if __name__ == "__main__":
    unittest.main()
