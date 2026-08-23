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
            "webui_extension_contract    PASS passed=46/46",
            "webui_extension_turn_bridge PASS ok=True forced_context_count=1",
            "ChatGPT memory summary import creates governed Review candidates",
            "ChatGPT conversation archive import creates Source Root",
            "ChatGPT conversation archive does not write durable memory",
            "ChatGPT import controls visible on Memory page",
            "make product-boundary-contract",
            "make live-product-boundary-contract",
            "WebUI manifest: pska-mini -> http://127.0.0.1:8765",
            "WebUI sidecar consent: pska-mini -> http://127.0.0.1:8765",
            "--include-live-product-boundary-contract",
            "product_boundary_contract.mode = repository_and_live",
            "--include-recovery-boundary",
            "--include-demo-videos",
            "--include-eidolia-bridge",
            "make alpha-acceptance-demo",
            "recovery_boundary PASS status=ok recovery=needs_rehearsal",
            "demo_video_pack PASS status=ok videos=5/5 delivery=yes integrity=yes handoff=yes",
            "eidolia_bridge PASS status=ok review=reject",
            "make demo-browser-verify-videos",
            "10 ordered plain Chinese subtitles",
            "product-boundary-contract OK",
            "live-product-boundary-contract OK",
            "alpha-acceptance-webui    OK, 46/46 contract, visual OK, turn bridge OK, recovery_boundary OK",
            "alpha-acceptance-demo     OK, recovery_boundary OK, demo_video_pack OK, eidolia_bridge OK, 5/5 videos, delivery=yes, integrity=yes, handoff=yes",
            "demo-browser-videos       OK, 5/5 videos, delivery pack, sha256 integrity, handoff note, pure Chinese subtitles",
            "unittest                  565 tests OK",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, snapshot)


if __name__ == "__main__":
    unittest.main()
