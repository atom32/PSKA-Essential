from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class StartWorkspaceScriptTests(unittest.TestCase):
    def test_start_workspace_script_has_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", "scripts/start_pska_workspace.sh"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_start_workspace_script_detects_stale_product_api_contract(self):
        text = Path("scripts/start_pska_workspace.sh").read_text(encoding="utf-8")

        self.assertIn("pska_api_contract_ok", text)
        self.assertIn("/api/capabilities", text)
        self.assertIn("pska.product_api_contract.v1", text)
        self.assertIn("pska.memory_interaction_model.v1", text)
        self.assertIn("primary_user_path", text)
        self.assertIn("review_queue_role", text)
        self.assertIn("visible_memory_editor", text)
        self.assertIn("visible_review_role", text)
        self.assertIn("agent_decides_operation", text)
        self.assertIn("creates_review_item", text)
        self.assertIn("ambiguous_destructive", text)
        self.assertIn("broad_destructive", text)
        self.assertIn("conversation_explicit_user_changes", text)
        self.assertIn("correct_clear_target", text)
        self.assertIn("forget_specific_fact", text)
        self.assertIn("needs_target_no_review", text)
        self.assertIn("pska.memory_inflow.v1", text)
        self.assertIn("writes_memory_provider", text)
        self.assertIn("pska.memory_lineage.v1", text)
        self.assertIn("pska_authoritative_mapping_table", text)
        self.assertIn("/api/memory/search", text)
        self.assertIn("/api/memory/conversation-change", text)
        self.assertIn("/api/provider/jobs", text)
        self.assertIn("/api/digest", text)
        self.assertIn("/api/digest-jobs", text)
        self.assertIn("/api/digest-jobs/run-next", text)
        self.assertIn("/api/digest-jobs/{run_id}/run", text)
        self.assertIn("/api/workflows/{run_id}/memory-review", text)
        self.assertIn("STALE %s", text)
        self.assertIn("stop_pska_api_port_processes", text)
        self.assertIn("PSKA Product API contract is current", text)


if __name__ == "__main__":
    unittest.main()
