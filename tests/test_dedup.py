from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pska_essential.capabilities import adapter_slots_contract
from pska_essential.dedup import (
    DedupGroup,
    DedupMember,
    DedupReport,
    czkawka_command_path,
    czkawka_duplicate_report,
    fclones_command_path,
    fclones_duplicate_report,
    image_phash_duplicate_report,
    parse_czkawka_groups,
    parse_fclones_groups,
)
from pska_essential.source_registry import SQLiteSourceRegistry


class DedupAdapterTests(unittest.TestCase):
    def test_image_phash_report_unavailable_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "pska_essential.dedup._imagehash_modules_available",
            return_value=False,
        ):
            report = image_phash_duplicate_report([Path(temp_dir)])

        payload = report.to_dict()
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["provider"], "imagehash")
        self.assertEqual(payload["group_count"], 0)
        self.assertIn("image-phash", payload["metadata"]["install_hint"])

    def test_image_phash_groups_similar_images_without_embeddings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            first = root_path / "first.png"
            second = root_path / "second.png"
            far = root_path / "far.png"
            first.write_bytes(b"image-a")
            second.write_bytes(b"image-b")
            far.write_bytes(b"image-c")
            fake_hashes = {
                str(first): _FakeHash("0000", {"0001": 1, "ffff": 16}),
                str(second): _FakeHash("0001", {"0000": 1, "ffff": 15}),
                str(far): _FakeHash("ffff", {"0000": 16, "0001": 15}),
            }

            def fake_candidates(_roots, *, threshold):
                return {
                    "items": [
                        {
                            "path": str(first),
                            "hash": "0000",
                            "hash_obj": fake_hashes[str(first)],
                            "size": first.stat().st_size,
                        },
                        {
                            "path": str(second),
                            "hash": "0001",
                            "hash_obj": fake_hashes[str(second)],
                            "size": second.stat().st_size,
                        },
                        {
                            "path": str(far),
                            "hash": "ffff",
                            "hash_obj": fake_hashes[str(far)],
                            "size": far.stat().st_size,
                        },
                    ],
                    "skipped": [],
                    "threshold": threshold,
                    "image_count": 3,
                }

            with patch("pska_essential.dedup._imagehash_modules_available", return_value=True), patch(
                "pska_essential.dedup._image_phash_candidates",
                side_effect=fake_candidates,
            ):
                report = image_phash_duplicate_report([root_path], threshold=2)

        payload = report.to_dict()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "image_phash")
        self.assertEqual(payload["provider"], "imagehash")
        self.assertEqual(payload["group_count"], 1)
        self.assertEqual(payload["metadata"]["hamming_threshold"], 2)
        self.assertFalse(payload["metadata"]["embedding_required"])
        self.assertTrue(payload["metadata"]["perceptual_hash_required"])
        self.assertEqual(payload["groups"][0]["metadata"]["max_distance"], 1)
        self.assertEqual(
            [Path(member["path"]).name for member in payload["groups"][0]["members"]],
            ["first.png", "second.png"],
        )

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

    def test_parse_czkawka_groups_accepts_json_report(self):
        raw = json.dumps(
            {
                "groups": [
                    {
                        "hash": "abc",
                        "size": 12,
                        "files": [
                            {"path": "/tmp/a.txt", "size": 12, "hash": "abc"},
                            {"path": "/tmp/b.txt", "size": 12, "hash": "abc"},
                        ],
                    }
                ]
            }
        )

        groups = parse_czkawka_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].method, "czkawka_hash")
        self.assertEqual(groups[0].content_hash, "abc")
        self.assertEqual([member.path for member in groups[0].members], ["/tmp/a.txt", "/tmp/b.txt"])

    def test_parse_czkawka_groups_accepts_entry_lists(self):
        raw = json.dumps(
            {
                "duplicates": [
                    [
                        {"path": "/tmp/a.txt", "size": 12},
                        {"path": "/tmp/b.txt", "size": 12},
                    ]
                ]
            }
        )

        groups = parse_czkawka_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].members), 2)

    def test_parse_czkawka_groups_accepts_hash_size_map(self):
        raw = json.dumps(
            {
                "12": [
                    [
                        {"path": "/tmp/a.txt", "size": 12, "hash": "abc"},
                        {"path": "/tmp/b.txt", "size": 12, "hash": "abc"},
                    ]
                ]
            }
        )

        groups = parse_czkawka_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].size, 12)
        self.assertEqual([member.path for member in groups[0].members], ["/tmp/a.txt", "/tmp/b.txt"])

    def test_parse_czkawka_groups_accepts_wrapped_hash_size_map(self):
        raw = json.dumps(
            {
                "files_with_identical_hashes": {
                    "12": [
                        [
                            {"path": "/tmp/a.txt", "size": 12, "hash": "abc"},
                            {"path": "/tmp/b.txt", "size": 12, "hash": "abc"},
                        ]
                    ]
                }
            }
        )

        groups = parse_czkawka_groups(raw)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].size, 12)
        self.assertEqual(len(groups[0].members), 2)

    def test_fclones_report_unavailable_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True), patch(
            "shutil.which", return_value=None
        ):
            report = fclones_duplicate_report([Path(temp_dir)])

        payload = report.to_dict()
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["provider"], "fclones")
        self.assertEqual(payload["group_count"], 0)
        self.assertIn("PSKA_FCLONES_BIN", payload["metadata"]["install_hint"])

    def test_czkawka_report_unavailable_is_structured(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict("os.environ", {}, clear=True), patch(
            "shutil.which", return_value=None
        ):
            report = czkawka_duplicate_report([Path(temp_dir)])

        payload = report.to_dict()
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["provider"], "czkawka")
        self.assertEqual(payload["group_count"], 0)
        self.assertIn("PSKA_CZKAWKA_BIN", payload["metadata"]["install_hint"])

    def test_fclones_env_override_controls_command_discovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "fclones"
            fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_bin.chmod(0o755)
            with patch.dict("os.environ", {"PSKA_FCLONES_BIN": str(fake_bin)}, clear=False), patch(
                "shutil.which", return_value=None
            ):
                path = fclones_command_path()
                provider = next(
                    item
                    for item in adapter_slots_contract()["slots"]["dedup"]["providers"]
                    if item["name"] == "fclones"
                )

        self.assertEqual(path, str(fake_bin))
        self.assertEqual(provider["status"], "available")
        self.assertEqual(provider["path"], str(fake_bin))
        self.assertEqual(provider["path_source"], "env")
        self.assertEqual(provider["env_key"], "PSKA_FCLONES_BIN")

    def test_czkawka_env_override_controls_command_discovery(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "czkawka_cli"
            fake_bin.write_text("#!/bin/sh\n", encoding="utf-8")
            fake_bin.chmod(0o755)
            with patch.dict("os.environ", {"PSKA_CZKAWKA_BIN": str(fake_bin)}, clear=False), patch(
                "shutil.which", return_value=None
            ):
                path = czkawka_command_path()
                provider = next(
                    item
                    for item in adapter_slots_contract()["slots"]["dedup"]["providers"]
                    if item["name"] == "czkawka"
                )

        self.assertEqual(path, str(fake_bin))
        self.assertEqual(provider["status"], "available")
        self.assertEqual(provider["path"], str(fake_bin))
        self.assertEqual(provider["path_source"], "env")
        self.assertEqual(provider["env_key"], "PSKA_CZKAWKA_BIN")

    def test_czkawka_env_override_requires_executable_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_bin = Path(temp_dir) / "czkawka_cli"
            fake_bin.write_text("partial download", encoding="utf-8")
            fake_bin.chmod(0o644)
            with patch.dict("os.environ", {"PSKA_CZKAWKA_BIN": str(fake_bin)}, clear=False), patch(
                "shutil.which", return_value=None
            ):
                path = czkawka_command_path()
                provider = next(
                    item
                    for item in adapter_slots_contract()["slots"]["dedup"]["providers"]
                    if item["name"] == "czkawka"
                )

        self.assertIsNone(path)
        self.assertEqual(provider["status"], "unavailable")
        self.assertNotIn("path", provider)

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

    def test_registry_czkawka_mode_maps_report_to_indexed_members(self):
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
            completed = Mock(returncode=0, stdout="", stderr="")

            def fake_run(command, **_kwargs):
                output_path = Path(command[-1])
                output_path.write_text(
                    json.dumps(
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
                    encoding="utf-8",
                )
                return completed

            with patch("shutil.which", return_value="/usr/local/bin/czkawka_cli"), patch(
                "subprocess.run", side_effect=fake_run
            ):
                report = registry.duplicate_report({"root_ids": [root["root_id"]]}, mode="czkawka_hash")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["provider"], "czkawka")
        self.assertEqual(report["group_count"], 1)
        self.assertEqual(sorted(member["path"] for member in report["groups"][0]["members"]), ["a.md", "b.md"])
        self.assertFalse(report["data_flow"]["writes_source_files"])

    def test_registry_image_phash_mode_maps_report_to_indexed_members(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            first = root_path / "Screenshot.png"
            second = root_path / "Screenshot edited.png"
            first.write_bytes(b"\x89PNG\r\n\x1a\n" + b"a" * 100)
            second.write_bytes(b"\x89PNG\r\n\x1a\n" + b"b" * 100)
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(root_path)
            registry.scan(root["root_id"])
            adapter_report = DedupReport(
                mode="image_phash",
                provider="imagehash",
                status="ok",
                groups=[
                    DedupGroup(
                        method="image_phash",
                        confidence=0.88,
                        size=max(first.stat().st_size, second.stat().st_size),
                        members=[
                            DedupMember(
                                path=str(first.resolve()),
                                absolute_path=str(first.resolve()),
                                size=first.stat().st_size,
                                metadata={"phash": "abc"},
                            ),
                            DedupMember(
                                path=str(second.resolve()),
                                absolute_path=str(second.resolve()),
                                size=second.stat().st_size,
                                metadata={"phash": "abd"},
                            ),
                        ],
                        metadata={"algorithm": "phash", "min_distance": 1, "max_distance": 1, "threshold": 6},
                    )
                ],
                metadata={"algorithm": "phash", "hamming_threshold": 6, "embedding_required": False},
            )

            with patch("pska_essential.source_registry.image_phash_duplicate_report", return_value=adapter_report):
                report = registry.duplicate_report({"root_ids": [root["root_id"]]}, mode="image_phash")

        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["provider"], "imagehash")
        self.assertEqual(report["group_count"], 1)
        self.assertEqual(report["groups"][0]["method"], "image_phash")
        self.assertEqual(report["groups"][0]["metadata"]["max_distance"], 1)
        self.assertEqual(
            sorted(member["path"] for member in report["groups"][0]["members"]),
            ["Screenshot edited.png", "Screenshot.png"],
        )
        member_by_path = {member["path"]: member for member in report["groups"][0]["members"]}
        self.assertEqual(member_by_path["Screenshot edited.png"]["dedup_metadata"]["phash"], "abd")
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["embedding_required"])


class _FakeHash:
    def __init__(self, value: str, distances: dict[str, int]) -> None:
        self.value = value
        self.distances = distances

    def __sub__(self, other):
        return self.distances[other.value]

    def __str__(self) -> str:
        return self.value
