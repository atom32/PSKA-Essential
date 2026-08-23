from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HermesRecallProviderIntegrationTests(unittest.TestCase):
    def test_provider_patch_is_packaged_with_contract_markers(self):
        patch = (
            ROOT
            / "integrations"
            / "hermes-webui-recall-provider"
            / "pska-conversation-recall-provider.patch"
        ).read_text(encoding="utf-8")

        self.assertIn("/api/pska/conversations/search", patch)
        self.assertIn("HERMES_WEBUI_PSKA_RECALL_TOKEN", patch)
        self.assertIn("def pska_recall_token_auth_ok", patch)
        self.assertIn("def _handle_pska_conversations_search", patch)
        self.assertIn("hermes.pska_conversation_recall.v1", patch)
        self.assertIn('"messages" not in item', patch)
        self.assertNotIn("PSKA_HERMES_WEBUI_PASSWORD", patch)

    def test_start_script_checks_for_provider_before_hermes_start(self):
        script = (ROOT / "scripts" / "start_pska_workspace.sh").read_text(encoding="utf-8")

        self.assertIn("HERMES_RECALL_PROVIDER_PATCH", script)
        self.assertIn("warn_if_hermes_recall_provider_missing", script)
        self.assertIn("hermes_recall_provider_source_ok", script)
        self.assertIn("git apply ${HERMES_RECALL_PROVIDER_PATCH}", script)
        self.assertIn("HERMES_WEBUI_PSKA_RECALL_TOKEN", script)


if __name__ == "__main__":
    unittest.main()
