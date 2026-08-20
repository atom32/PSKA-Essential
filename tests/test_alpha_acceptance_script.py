from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_script_module():
    path = ROOT / "scripts" / "run_alpha_acceptance.py"
    spec = importlib.util.spec_from_file_location("run_alpha_acceptance", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load run_alpha_acceptance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlphaAcceptanceScriptTests(unittest.TestCase):
    def test_selects_explicit_dataset_ids_before_workspace_ready_ids(self):
        module = _load_script_module()
        args = argparse.Namespace(dataset_id=["explicit-a"], dataset_ids="explicit-b, explicit-c")
        workspace = {"workspace_status": {"kb": {"ready_dataset_ids": ["ready-a"]}}}

        self.assertEqual(
            module._selected_dataset_ids(args, workspace),
            ["explicit-a", "explicit-b", "explicit-c"],
        )

    def test_selects_first_ready_workspace_dataset_when_no_explicit_scope(self):
        module = _load_script_module()
        args = argparse.Namespace(dataset_id=[], dataset_ids="")
        workspace = {"workspace_status": {"kb": {"ready_dataset_ids": ["ready-a", "ready-b"]}}}

        self.assertEqual(module._selected_dataset_ids(args, workspace), ["ready-a"])

    def test_summary_markdown_includes_check_status_and_artifacts(self):
        module = _load_script_module()
        markdown = module._summary_markdown(
            {
                "status": "ok",
                "out_dir": "/tmp/pska-alpha-acceptance-test",
                "checks": [
                    {
                        "name": "full_component_proof",
                        "ok": True,
                        "message": "status=ok",
                        "metadata": {"run_id": "run-demo", "dataset_ids": ["ready-a"]},
                    }
                ],
                "artifacts": {"summary": "/tmp/pska-alpha-acceptance-test/summary.json"},
            }
        )

        self.assertIn("Status: `ok`", markdown)
        self.assertIn("`PASS` full_component_proof", markdown)
        self.assertIn("run_id: `run-demo`", markdown)
        self.assertIn("dataset_ids: `ready-a`", markdown)
        self.assertIn("summary.json", markdown)

    def test_run_json_preserves_structured_payload_from_nonzero_command(self):
        module = _load_script_module()

        payload = module._run_json(
            [
                sys.executable,
                "-c",
                "import json, sys; print(json.dumps({'status':'incomplete','detail':'scope missing'})); sys.exit(2)",
            ],
            env=os.environ.copy(),
            timeout=10,
        )

        self.assertEqual(payload["status"], "incomplete")
        self.assertEqual(payload["detail"], "scope missing")
        self.assertEqual(payload["command_returncode"], 2)


if __name__ == "__main__":
    unittest.main()
