import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
