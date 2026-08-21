import subprocess
import sys
import tempfile
import unittest
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_boundary_module():
    path = ROOT / "scripts" / "verify_product_boundaries.py"
    spec = importlib.util.spec_from_file_location("verify_product_boundaries", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load verify_product_boundaries.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProductBoundaryContractTests(unittest.TestCase):
    def test_product_boundary_contract_script_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/verify_product_boundaries.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Hermes config example uses PSKA HTTP MCP only", result.stdout)
        self.assertIn("pska-mini stays a thin WebUI sidecar extension", result.stdout)
        self.assertIn("demo entrypoint remains Hermes WebUI extension only", result.stdout)

    def test_live_hermes_config_accepts_pska_http_mcp_and_unrelated_servers(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
mcp_servers:
  pska-essential:
    url: http://127.0.0.1:8766/mcp
    enabled: true
  novel-local:
    url: http://127.0.0.1:8799/mcp
    enabled: true
  disabled-provider:
    url: http://127.0.0.1:3131/mcp
    enabled: false
""".lstrip(),
                encoding="utf-8",
            )
            checks = []
            module.verify_live_hermes_config(
                path,
                checks,
                expected_url="http://127.0.0.1:8766/mcp",
            )

        self.assertTrue(checks)
        self.assertIn("live Hermes config uses PSKA HTTP MCP only", checks[0])

    def test_live_hermes_config_rejects_pska_stdio(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
mcp_servers:
  pska-essential:
    command: pska-essential-mcp
    args:
      - --transport
      - stdio
""".lstrip(),
                encoding="utf-8",
            )

            with self.assertRaises(module.BoundaryFailure):
                module.verify_live_hermes_config(
                    path,
                    [],
                    expected_url="http://127.0.0.1:8766/mcp",
                )

    def test_live_hermes_config_rejects_enabled_provider_mcp(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
mcp_servers:
  pska-essential:
    url: http://127.0.0.1:8766/mcp
  gbrain:
    url: http://127.0.0.1:3131/mcp
    enabled: true
""".lstrip(),
                encoding="utf-8",
            )

            with self.assertRaises(module.BoundaryFailure):
                module.verify_live_hermes_config(
                    path,
                    [],
                    expected_url="http://127.0.0.1:8766/mcp",
                )

    def test_live_webui_extension_accepts_pska_sidecar_and_consent(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "extensions.json"
            overrides = root / "extension-overrides.json"
            manifest.write_text(
                """
{
  "extensions": [
    {
      "id": "pska-mini",
      "scripts": ["pska-mini/pska-mini.js"],
      "stylesheets": ["pska-mini/pska-mini.css"],
      "sidecar": {
        "type": "loopback",
        "origin": "http://127.0.0.1:8765",
        "health_path": "/api/health"
      }
    },
    {
      "id": "eidolia",
      "sidecar": {
        "type": "loopback",
        "origin": "http://127.0.0.1:8797",
        "health_path": "/health"
      }
    }
  ]
}
""".lstrip(),
                encoding="utf-8",
            )
            overrides.write_text(
                """
{
  "version": 1,
  "disabled_extensions": [],
  "sidecar_proxy_consents": {
    "pska-mini": "http://127.0.0.1:8765"
  }
}
""".lstrip(),
                encoding="utf-8",
            )
            checks = []
            module.verify_live_webui_extension(
                manifest,
                checks,
                overrides_path=overrides,
                expected_origin="http://127.0.0.1:8765",
            )

        self.assertEqual(len(checks), 2)
        self.assertIn("live WebUI manifest loads pska-mini", checks[0])
        self.assertIn("live WebUI sidecar consent matches PSKA API origin", checks[1])

    def test_live_webui_extension_rejects_wrong_pska_origin(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "extensions.json"
            manifest.write_text(
                """
{
  "extensions": [
    {
      "id": "pska-mini",
      "scripts": ["pska-mini/pska-mini.js"],
      "stylesheets": ["pska-mini/pska-mini.css"],
      "sidecar": {
        "type": "loopback",
        "origin": "http://127.0.0.1:9380",
        "health_path": "/api/health"
      }
    }
  ]
}
""".lstrip(),
                encoding="utf-8",
            )

            with self.assertRaises(module.BoundaryFailure):
                module.verify_live_webui_extension(
                    manifest,
                    [],
                    overrides_path=None,
                    expected_origin="http://127.0.0.1:8765",
                )

    def test_live_webui_extension_rejects_provider_extension(self):
        module = _load_boundary_module()
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "extensions.json"
            manifest.write_text(
                """
{
  "extensions": [
    {
      "id": "pska-mini",
      "scripts": ["pska-mini/pska-mini.js"],
      "stylesheets": ["pska-mini/pska-mini.css"],
      "sidecar": {
        "type": "loopback",
        "origin": "http://127.0.0.1:8765",
        "health_path": "/api/health"
      }
    },
    {
      "id": "ragflow-direct",
      "sidecar": {
        "type": "loopback",
        "origin": "http://127.0.0.1:9380"
      }
    }
  ]
}
""".lstrip(),
                encoding="utf-8",
            )

            with self.assertRaises(module.BoundaryFailure):
                module.verify_live_webui_extension(
                    manifest,
                    [],
                    overrides_path=None,
                    expected_origin="http://127.0.0.1:8765",
                )


if __name__ == "__main__":
    unittest.main()
