from __future__ import annotations

import unittest
from unittest.mock import patch

from pska_essential.migration_manifest import build_migration_manifest
from pska_essential.workflow import build_fake_service


class MigrationManifestTests(unittest.TestCase):
    def test_manifest_inventory_keeps_provider_data_owner_boundaries(self):
        with patch.dict("os.environ", {}, clear=True):
            service = build_fake_service()
            run = service.start("migration manifest workflow", {"dataset_ids": ["demo"]})
            service.context_retrieve(run.run_id, "workflow gate", 1)
            proposal = service.propose(run.run_id, "memory_patch", "remember migration source")
            review = service.review_create(proposal.proposal_id)
            service.review_decide(review.review_id, "accept", "approved for manifest")
            applied = service.memory_apply(review.review_id)
            service.memory_change_from_conversation(
                user_message="Remember that Hermes owns the chat session.",
                text="Hermes owns the chat session.",
                session_id="sess-manifest",
                message_id="msg-manifest",
            )

            manifest = build_migration_manifest(service)

        self.assertEqual(manifest["schema"], "pska.migration_manifest.v1")
        self.assertEqual(manifest["components"]["pska"]["counts"]["workflows"], 2)
        self.assertGreaterEqual(manifest["components"]["pska"]["counts"]["reviews"], 2)
        self.assertIn("fake", manifest["components"]["retrieval_providers"])
        self.assertIn("demo", manifest["components"]["retrieval_providers"]["fake"]["dataset_ids"])
        self.assertIn("fake", manifest["components"]["memory_providers"])
        self.assertIn(applied.target_id, manifest["components"]["memory_providers"]["fake"]["target_ids"])
        self.assertIn("hermes", manifest["components"]["agent_hosts"])
        self.assertIn("sess-manifest", manifest["components"]["agent_hosts"]["hermes"]["session_ids"])
        self.assertIn("raw_documents", manifest["exclusions"])
        self.assertIn("chunks", manifest["exclusions"])
        self.assertTrue(
            all("content_excerpt" not in ref.get("metadata", {}) for ref in manifest["provider_source_refs"])
        )
        self.assertTrue(
            any(ref["adapter"] == "fake" and ref["document_id"] for ref in manifest["provider_source_refs"])
        )

    def test_manifest_limit_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            build_migration_manifest(build_fake_service(), limit=0)


if __name__ == "__main__":
    unittest.main()
