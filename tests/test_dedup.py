from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pska_essential.dedup import fclones_duplicate_report, parse_fclones_groups
from pska_essential.source_registry import SQLiteSourceRegistry


class DedupAdapterTests(unittest.TestCase):
    def test_parse_fclones_groups_accepts_json_report(self):
        raw = json.dumps(
            {
                "groups": [
                    {
                        "hash": "abc",
                        "size": 12,
                        "files": [
                            {"path": "/tmp/a.txt", "size": 12},
                            {"path": "/tmp/b.txt", "size": 12},
                        ],
                    }
                ]
            }
        )

        groups = parse_fclones_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].content_hash, "abc")
        self.assertEqual([member.path for member in groups[0].members], ["/tmp/a.txt", "/tmp/b.txt"])

    def test_parse_fclones_groups_accepts_list_of_member_lists(self):
        raw = json.dumps(
            [
                [
                    {"path": "/tmp/a.txt", "size": 12},
                    {"path": "/tmp/b.txt", "size": 12},
                ]
            ]
        )

        groups = parse_fclones_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].members), 2)

    def test_parse_fclones_groups_accepts_single_group_with_string_paths(self):
        raw = json.dumps({"hash": "abc", "files": ["/tmp/a.txt", "/tmp/b.txt"]})

        groups = parse_fclones_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual([member.path for member in groups[0].members], ["/tmp/a.txt", "/tmp/b.txt"])

    def test_fclones_report_unavailable_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch("shutil.which", return_value=None):
            report = fclones_duplicate_report([Path(temp_dir)])

        payload = report.to_dict()
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["provider"], "fclones")
        self.assertEqual(payload["group_count"], 0)

    def test_registry_fclones_mode_maps_report_to_indexed_members(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            text = "# Duplicate\n\nSame content.\n"
            first = root_path / "a.md"
            second = root_path / "b.md"
            first.write_text(text, encoding="utf-8")
            second.write_text(text, encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(root_path)
            registry.scan(root["root_id"])
            completed = Mock(
                returncode=0,
                stdout=json.dumps(
                    {
                        "groups": [
                            {
                                "hash": "abc",
                                "size": first.stat().st_size,
                                "files": [
                                    {"path": str(first.resolve()), "size": first.stat().st_size},
                                    {"path": str(second.resolve()), "size": second.stat().st_size},
                                ],
                            }
                        ]
                    }
                ),
                stderr="",
            )

            with patch("shutil.which", return_value="/usr/local/bin/fclones"), patch(
                "subprocess.run", return_value=completed
            ):
                report = registry.duplicate_report({"root_ids": [root["root_id"]]}, mode="fclones_hash")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["provider"], "fclones")
        self.assertEqual(report["group_count"], 1)
        self.assertEqual(sorted(member["path"] for member in report["groups"][0]["members"]), ["a.md", "b.md"])
        self.assertFalse(report["data_flow"]["writes_source_files"])
