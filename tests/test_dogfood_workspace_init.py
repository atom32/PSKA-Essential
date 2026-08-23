from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def _load_script_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "init_dogfood_workspace.py"
    spec = importlib.util.spec_from_file_location("init_dogfood_workspace", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class DogfoodWorkspaceInitTests(unittest.TestCase):
    def test_initialize_workspace_creates_first_user_templates_without_memory_writes(self):
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "PSKA-Dogfood"
            result = module.initialize_workspace(root, date="2026-08-24")
            daily = root / "daily" / "2026-08-24.md"
            health = root / "health" / "2026-08-24.md"
            project_state = root / "projects" / "pska" / "project-state.md"
            manifest = json.loads((root / module.MANIFEST_NAME).read_text(encoding="utf-8"))
            daily_text = daily.read_text(encoding="utf-8")
            health_text = health.read_text(encoding="utf-8")
            project_state_text = project_state.read_text(encoding="utf-8")

            rerun = module.initialize_workspace(root, date="2026-08-24")
            daily_exists = daily.exists()
            health_exists = health.exists()

        self.assertEqual(result["schema"], "pska.dogfood_workspace_init.v1")
        self.assertEqual(result["status"], "created")
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["writes_source_registry"])
        self.assertTrue(daily_exists)
        self.assertTrue(health_exists)
        self.assertIn("今天发生", daily_text)
        self.assertIn("不是医学诊断", health_text)
        self.assertIn("PSKA 没有独立前端", project_state_text)
        self.assertEqual(manifest["schema"], "pska.dogfood_workspace_manifest.v1")
        self.assertFalse(manifest["data_flow"]["writes_memory_directly"])
        self.assertIn("skipped_existing", {item["status"] for item in rerun["files"]})
        self.assertFalse(rerun["data_flow"]["writes_user_template_files"])

    def test_dry_run_does_not_create_workspace(self):
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "PSKA-Dogfood"
            result = module.initialize_workspace(root, date="2026-08-24", dry_run=True)

            self.assertFalse(root.exists())

        self.assertEqual(result["status"], "planned")
        self.assertFalse(result["data_flow"]["writes_user_template_files"])

    def test_registration_roots_default_to_first_week_scope(self):
        module = _load_script_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            roots = module.registration_roots(Path(temp_dir) / "PSKA-Dogfood")

        self.assertEqual(
            [Path(item["relative_path"]).as_posix() for item in roots],
            ["daily", "decisions", "projects/pska", "creative"],
        )
        permissions = {item["relative_path"]: item["permission_mode"] for item in roots}
        self.assertEqual(permissions["daily"], "sidecar_write")
        self.assertEqual(permissions["projects/pska"], "sidecar_write")

    def test_register_source_roots_uses_product_api_and_optional_scan(self):
        module = _load_script_module()
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(
                {
                    "url": request.full_url,
                    "payload": json.loads(request.data.decode("utf-8")),
                    "timeout": timeout,
                }
            )
            if request.full_url.endswith("/api/sources/roots"):
                rel = Path(json.loads(request.data.decode("utf-8"))["path"]).name
                return _Response({"ok": True, "root": {"root_id": f"root-{rel}"}})
            return _Response({"ok": True, "scan": {"counts": {"scanned": 1, "indexed": 1}}})

        roots = [
            {
                "absolute_path": "/tmp/PSKA-Dogfood/daily",
                "permission_mode": "sidecar_write",
                "label": "Daily",
            }
        ]
        result = module.register_source_roots(
            "http://127.0.0.1:8765",
            roots,
            scan=True,
            timeout=3,
            urlopen_fn=fake_urlopen,
        )

        self.assertEqual(result[0]["status"], "registered")
        self.assertEqual(result[0]["root_id"], "root-daily")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["url"], "http://127.0.0.1:8765/api/sources/roots")
        self.assertEqual(calls[0]["payload"]["permission_mode"], "sidecar_write")
        self.assertEqual(calls[1]["url"], "http://127.0.0.1:8765/api/sources/roots/root-daily/scan")


if __name__ == "__main__":
    unittest.main()
