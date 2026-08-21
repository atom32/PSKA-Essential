from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AlphaAcceptanceDocsTests(unittest.TestCase):
    def test_readme_points_to_current_alpha_acceptance_snapshot(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "[PSKA Alpha Acceptance 2026-08-21](docs/PSKA_ALPHA_ACCEPTANCE_2026-08-21.zh.md)",
            readme,
        )

    def test_current_alpha_acceptance_snapshot_names_verified_gates(self):
        snapshot = (ROOT / "docs" / "PSKA_ALPHA_ACCEPTANCE_2026-08-21.zh.md").read_text(
            encoding="utf-8"
        )
        required_terms = [
            "alpha_readiness.status = alpha_ready",
            "product_boundary_contract PASS status=ok",
            "webui_extension_contract    PASS passed=41/41",
            "webui_extension_turn_bridge PASS ok=True forced_context_count=1",
            "make product-boundary-contract",
            "make demo-browser-verify-videos",
            "10 ordered plain Chinese subtitles",
            "product-boundary-contract OK",
            "unittest                  515 tests OK",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, snapshot)


if __name__ == "__main__":
    unittest.main()
