from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class ComponentChannelScriptTests(unittest.TestCase):
    def test_component_channel_script_has_valid_bash_syntax(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["bash", "-n", "scripts/pska_component_channel.sh"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_component_channel_script_keeps_side_by_side_defaults(self):
        text = Path("scripts/pska_component_channel.sh").read_text(encoding="utf-8")

        self.assertIn("com.pska.ragflow.next", text)
        self.assertIn("com.pska.ragflow.web.next", text)
        self.assertIn("com.pska.hermes-webui.next", text)
        self.assertIn("RAGFLOW_NEXT_API", text)
        self.assertIn("http://127.0.0.1:9388", text)
        self.assertIn("http://127.0.0.1:9228", text)
        self.assertIn("http://127.0.0.1:8887", text)
        self.assertIn("pska-run-ragflow-server-v027.sh", text)
        self.assertIn("pska-run-ragflow-web-v027.sh", text)
        self.assertIn("pska-run-hermes-webui-next.sh", text)
        self.assertIn("pska-sync-extension-next.sh", text)
        self.assertIn("promote-ragflow-next", text)
        self.assertIn("rollback-ragflow-env", text)
        self.assertIn("promote-hermes-next", text)
        self.assertIn("rollback-hermes", text)
        self.assertIn("refreshing plist without replacing rollback backup", text)
        self.assertIn("require --apply", text)
        self.assertIn("wait_for_label_unloaded", text)
        self.assertIn("RAGFLOW_NEXT_API_TOKEN must be set", text)
        self.assertIn("RAGFLOW_API_KEY", text)
        self.assertIn("HERMES_WEBUI_STATE_DIR", text)
        self.assertIn("HERMES_WEBUI_EXTENSION_DIR", text)


if __name__ == "__main__":
    unittest.main()
