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
        self.assertIn("/api/pska/conversations/import", patch)
        self.assertIn("HERMES_WEBUI_PSKA_RECALL_TOKEN", patch)
        self.assertIn("def pska_recall_token_auth_ok", patch)
        self.assertIn("def _handle_pska_conversations_search", patch)
        self.assertIn("def _handle_pska_conversations_import", patch)
        self.assertIn("hermes.pska_conversation_recall.v1", patch)
        self.assertIn("hermes.pska_conversation_history_import.v1", patch)
        self.assertIn('"messages" not in item', patch)
        self.assertIn('"returns_full_messages": False', patch)
        self.assertNotIn("PSKA_HERMES_WEBUI_PASSWORD", patch)

    def test_start_script_checks_for_provider_before_hermes_start(self):
        script = (ROOT / "scripts" / "start_pska_workspace.sh").read_text(encoding="utf-8")

        self.assertIn("HERMES_RECALL_PROVIDER_PATCH", script)
        self.assertIn("warn_if_hermes_recall_provider_missing", script)
        self.assertIn("hermes_recall_provider_source_ok", script)
        self.assertIn("git apply ${HERMES_RECALL_PROVIDER_PATCH}", script)
        self.assertIn("HERMES_WEBUI_PSKA_RECALL_TOKEN", script)
        self.assertIn('"/api/pska/conversations/import"', script)
        self.assertIn("def _handle_pska_conversations_import", script)

    def test_install_script_is_idempotent_and_testable(self):
        script_path = ROOT / "scripts" / "install_hermes_recall_provider.sh"
        script = script_path.read_text(encoding="utf-8")

        self.assertTrue(script_path.stat().st_mode & 0o111)
        self.assertIn("provider_source_ok", script)
        self.assertIn("git -C \"${HERMES_WEBUI_HOME}\" apply --check", script)
        self.assertIn("git -C \"${HERMES_WEBUI_HOME}\" apply \"${PATCH_FILE}\"", script)
        self.assertIn("apply --reverse --check", script)
        self.assertIn("python3 -m py_compile api/auth.py api/routes.py", script)
        self.assertIn("tests/test_pska_conversation_recall_provider.py", script)
        self.assertIn('"/api/pska/conversations/import"', script)
        self.assertIn("hermes.pska_conversation_history_import.v1", script)

    def test_env_example_documents_recall_token_pair(self):
        env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

        self.assertIn("PSKA_HERMES_WEBUI_BASE_URL=http://127.0.0.1:8787", env_example)
        self.assertIn("PSKA_HERMES_RECALL_TOKEN=", env_example)
        self.assertIn("HERMES_WEBUI_PSKA_RECALL_TOKEN=", env_example)
        self.assertIn("PSKA_HERMES_LEGACY_RECALL_FALLBACK=1", env_example)


if __name__ == "__main__":
    unittest.main()
