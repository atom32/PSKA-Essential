from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pska_essential.embedding_component import build_embedding_component_status


class EmbeddingComponentTests(unittest.TestCase):
    def test_local_infinity_dev_mode_is_a_ragflow_side_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "infinity-emb" / ".venv").mkdir(parents=True)

            status = build_embedding_component_status(
                environ={
                    "PSKA_COMPONENTS_ROOT": str(root),
                    "PSKA_EMBEDDING_RUNTIME": "local_infinity",
                    "PSKA_EMBEDDING_BASE_URL": "http://127.0.0.1:6380",
                    "PSKA_EMBEDDING_MODEL_ID": "BAAI/bge-m3",
                }
            )

        self.assertEqual(status["schema"], "pska.embedding_component_status.v1")
        self.assertEqual(status["mode"], "local_infinity_dev")
        self.assertEqual(status["status"], "configured")
        self.assertEqual(status["model"]["configured"], "BAAI/bge-m3")
        self.assertFalse(status["runtime"]["direct_pska_dependency"])
        self.assertFalse(status["governance"]["hermes_calls_embedding_directly"])
        self.assertEqual(status["endpoints"]["host_health_url"], "http://127.0.0.1:6380/health")
        self.assertEqual(status["endpoints"]["ragflow_expected_url"], "http://127.0.0.1:6380")

    def test_delivery_tei_mode_uses_compose_private_ragflow_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            status = build_embedding_component_status(
                environ={
                    "PSKA_COMPONENTS_ROOT": tmp,
                    "EMBEDDING_ENABLED": "1",
                    "EMBEDDING_IMAGE": "ghcr.io/huggingface/text-embeddings-inference:cpu-1.8",
                    "EMBEDDING_MODEL_ID": "BAAI/bge-small-en-v1.5",
                    "EMBEDDING_HOST_PORT": "6380",
                }
            )

        self.assertEqual(status["mode"], "tei_container_delivery")
        self.assertEqual(status["delivery"]["runtime"], "tei_container")
        self.assertEqual(status["delivery"]["ragflow_private_url"], "http://pska-embedding:80")
        self.assertEqual(status["endpoints"]["ragflow_expected_url"], "http://pska-embedding:80")
        self.assertEqual(status["model"]["configured"], "BAAI/bge-small-en-v1.5")

    def test_disabled_mode_surfaces_configuration_next_action(self):
        status = build_embedding_component_status(environ={"EMBEDDING_ENABLED": "0"})

        self.assertEqual(status["mode"], "disabled")
        self.assertEqual(status["status"], "disabled")
        self.assertEqual(status["next_actions"][0]["action"], "configure_embedding_provider")


if __name__ == "__main__":
    unittest.main()
