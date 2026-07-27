import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "integrations" / "hermes-webui-extension" / "pska-mini"


class HermesWebuiExtensionTests(unittest.TestCase):
    def test_manifest_describes_thin_pska_mini_package(self):
        manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["id"], "pska-mini")
        self.assertEqual(manifest["scripts"], ["pska-mini.js"])
        self.assertEqual(manifest["stylesheets"], ["pska-mini.css"])

    def test_extension_uses_hook_and_turn_context_only(self):
        script = (EXTENSION_DIR / "pska-mini.js").read_text(encoding="utf-8")

        self.assertIn("HermesChatStartHooks", script)
        self.assertIn("context_provider", script)
        self.assertIn('fetch("/api/pska/turn-context"', script)
        self.assertNotRegex(script, re.compile(r'fetch\(["\']/api/pska/(?!turn-context)'))
        for forbidden in [
            "/api/pska/ask",
            "/api/pska/kb/ingest",
            "/api/pska/digest-jobs",
            "/api/pska/memory/search",
            "/api/pska/memory/conversation-change",
            "/api/pska/workflows/",
            "/api/pska/reviews/",
            "/api/pska/sources/read",
            "pska_agentic_question_start",
        ]:
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
