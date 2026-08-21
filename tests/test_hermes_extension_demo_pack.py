import argparse
import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "verify_hermes_extension_demo_pack.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_hermes_extension_demo_pack", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HermesExtensionDemoPackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verifier = load_verifier()

    def test_core_demo_defaults_to_short_smoke_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_extension_demo",
            case="",
            min_duration=None,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 30.0)

    def test_long_core_demo_defaults_to_long_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_extension_demo_long",
            case="",
            min_duration=None,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 180.0)

    def test_known_business_cases_default_to_two_minute_floor(self):
        for case_id, basename in [
            ("finance_report_research", "hermes_pska_finance_case_demo"),
            ("webnovel_author", "hermes_pska_webnovel_case_demo"),
        ]:
            with self.subTest(case_id=case_id):
                args = argparse.Namespace(
                    basename=basename,
                    case=case_id,
                    min_duration=None,
                )
                self.assertEqual(self.verifier.resolve_min_duration(args), 120.0)

    def test_explicit_min_duration_cannot_lower_builtin_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_webnovel_case_demo",
            case="webnovel_author",
            min_duration=45.0,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 120.0)

    def test_explicit_min_duration_can_raise_builtin_floor(self):
        args = argparse.Namespace(
            basename="hermes_pska_webnovel_case_demo",
            case="webnovel_author",
            min_duration=150.0,
        )
        self.assertEqual(self.verifier.resolve_min_duration(args), 150.0)

    def test_all_video_packs_cover_expected_assets(self):
        packs = self.verifier.DEMO_VIDEO_PACKS
        self.assertEqual(
            [(pack["basename"], pack["case"]) for pack in packs],
            [
                ("hermes_pska_extension_demo", ""),
                ("hermes_pska_extension_demo_long", ""),
                ("hermes_pska_finance_case_demo", "finance_report_research"),
                ("hermes_pska_webnovel_case_demo", "webnovel_author"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
