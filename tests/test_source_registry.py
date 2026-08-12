from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pska_essential.mcp_server import tool_registry
from pska_essential.source_registry import SQLiteSourceRegistry, SourceRegistryError
from pska_essential.workflow import build_fake_service


class SourceRegistryTests(unittest.TestCase):
    def test_obsidian_vault_scan_search_and_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "PSKA.md").write_text(
                "# PSKA\n\n"
                "## Architecture\n\n"
                "Hermes should search Obsidian source notes before answering project questions.\n\n"
                "## Memory\n\n"
                "Only durable behavior-changing facts should become memory cards.\n",
                encoding="utf-8",
            )
            registry = SQLiteSourceRegistry(":memory:")

            root = registry.register_root(vault, kind="auto", permission_mode="read_only")
            scan = registry.scan(root["root_id"])
            packets = registry.search("Hermes Obsidian", {"root_ids": [root["root_id"]]}, limit=3)
            source = registry.read_source(packets[0].source_ref)

        self.assertEqual(root["kind"], "obsidian_vault")
        self.assertEqual(root["permission_mode"], "read_only")
        self.assertEqual(scan["counts"]["indexed"], 1)
        self.assertFalse(scan["data_flow"]["writes_source_files"])
        self.assertTrue(packets)
        self.assertEqual(packets[0].source_ref.adapter, "obsidian_vault")
        self.assertEqual(packets[0].source_ref.path, "PSKA.md")
        self.assertEqual(packets[0].source_ref.metadata["source_layer"], "personal")
        self.assertIn("Hermes should search Obsidian", source.text)
        self.assertFalse(source.metadata["writes_source_files"])

    def test_neighbors_use_obsidian_links_backlinks_and_same_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "Projects").mkdir()
            (vault / "Index.md").write_text(
                "# Index\n\nCentral map links [[Evidence]] and [Plan](Projects/Plan.md).\n",
                encoding="utf-8",
            )
            (vault / "Evidence.md").write_text(
                "# Evidence\n\nSource evidence for Hermes.\n",
                encoding="utf-8",
            )
            (vault / "Projects" / "Plan.md").write_text(
                "# Plan\n\nExecution plan for PSKA source neighbors.\n",
                encoding="utf-8",
            )
            (vault / "Projects" / "Brief.md").write_text(
                "# Brief\n\nSibling project context.\n",
                encoding="utf-8",
            )
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(vault, kind="auto")
            registry.scan(root["root_id"])

            index_ref = registry.search("Central map", {"root_ids": [root["root_id"]]})[0].source_ref
            evidence_ref = registry.search("Source evidence", {"root_ids": [root["root_id"]]})[0].source_ref
            plan_ref = registry.search("Execution plan", {"root_ids": [root["root_id"]]})[0].source_ref
            outgoing = registry.neighbors(index_ref, strategy="links", limit=5)
            backlinks = registry.neighbors(evidence_ref, strategy="backlinks", limit=5)
            folder = registry.neighbors(plan_ref, strategy="folder", limit=5)

        self.assertEqual([item["path"] for item in outgoing], ["Evidence.md", "Projects/Plan.md"])
        self.assertTrue(all(item["relation"] == "outgoing_link" for item in outgoing))
        self.assertEqual(backlinks[0]["path"], "Index.md")
        self.assertEqual(backlinks[0]["relation"], "backlink")
        self.assertEqual(folder[0]["path"], "Projects/Brief.md")
        self.assertEqual(folder[0]["source_ref"].path, "Projects/Brief.md")
        self.assertFalse(folder[0]["data_flow"]["embedding_required"])

    def test_mcp_source_tools_register_scan_search_and_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "handoff.md").write_text(
                "# Handoff\n\nPSKA local folders can be searched without embeddings.\n",
                encoding="utf-8",
            )
            (root_path / "related.md").write_text(
                "# Related\n\nNeighbor context in the same folder.\n",
                encoding="utf-8",
            )
            service = build_fake_service()
            tools = tool_registry(service)

            root = tools["pska_source_root_register"](str(root_path), label="Project Files")
            scan = tools["pska_source_scan"](root["root_id"])
            packets = tools["pska_source_search"]("without embeddings", {"root_ids": [root["root_id"]]})
            neighbors = tools["pska_source_neighbors"](packets[0]["source_ref"], strategy="folder")
            source = tools["pska_source_read"](packets[0]["source_ref"])

        self.assertEqual(root["label"], "Project Files")
        self.assertEqual(scan["active_object_count"], 2)
        self.assertEqual(packets[0]["source_ref"]["adapter"], "local_folder")
        self.assertEqual(neighbors[0]["path"], "related.md")
        self.assertIn("without embeddings", source["text"])
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("source.root.register", actions)
        self.assertIn("source.scan", actions)
        self.assertIn("source.search", actions)
        self.assertIn("source.neighbors", actions)
        self.assertIn("source.read", actions)

    def test_duplicate_report_and_saved_search_do_not_touch_source_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            duplicate_text = "# Duplicate\n\nSame source body for exact hash duplicate.\n"
            (root_path / "a.md").write_text(duplicate_text, encoding="utf-8")
            (root_path / "copy.md").write_text(duplicate_text, encoding="utf-8")
            (root_path / "other.md").write_text("# Other\n\nDifferent material.\n", encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(root_path)
            registry.scan(root["root_id"])

            report = registry.duplicate_report({"root_ids": [root["root_id"]]}, limit=10)
            saved = registry.saved_search_create(
                "Duplicate notes",
                "exact hash duplicate",
                {"root_ids": [root["root_id"]]},
            )

        self.assertEqual(report["group_count"], 1)
        self.assertEqual(report["duplicate_file_count"], 1)
        self.assertEqual(report["groups"][0]["member_count"], 2)
        self.assertEqual(
            sorted(member["path"] for member in report["groups"][0]["members"]),
            ["a.md", "copy.md"],
        )
        self.assertFalse(report["data_flow"]["writes_source_files"])
        self.assertFalse(report["data_flow"]["delete_move_merge_supported"])
        self.assertEqual(saved["label"], "Duplicate notes")
        self.assertEqual(saved["scope"]["root_ids"], [root["root_id"]])
        self.assertFalse(saved["data_flow"]["writes_source_files"])

    def test_mcp_duplicate_report_and_saved_search_create_audit_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            duplicate_text = "# Duplicate\n\nThe same duplicated source.\n"
            (root_path / "one.md").write_text(duplicate_text, encoding="utf-8")
            (root_path / "two.md").write_text(duplicate_text, encoding="utf-8")
            service = build_fake_service()
            tools = tool_registry(service)
            root = tools["pska_source_root_register"](str(root_path))
            tools["pska_source_scan"](root["root_id"])

            report = tools["pska_duplicate_report"]({"root_ids": [root["root_id"]]})
            saved = tools["pska_saved_search_create"](
                "Duplicated source",
                "duplicated source",
                {"root_ids": [root["root_id"]]},
            )

        self.assertEqual(report["group_count"], 1)
        self.assertEqual(report["groups"][0]["member_count"], 2)
        self.assertEqual(saved["label"], "Duplicated source")
        actions = {event.action for event in service.store.list_audit_events(limit=20)}
        self.assertIn("source.duplicate_report", actions)
        self.assertIn("source.saved_search.create", actions)

    def test_sidecar_tag_and_comment_apply_do_not_touch_source_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            source_path = root_path / "Architecture.md"
            original_text = "# Architecture\n\nHermes needs PSKA source annotations.\n"
            source_path.write_text(original_text, encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(root_path, permission_mode="sidecar_write")
            registry.scan(root["root_id"])
            packet = registry.search("Hermes source annotations", {"root_ids": [root["root_id"]]})[0]

            tag_proposal = registry.propose_tag(packet.source_ref, "project/hermes", reason="matches project scope")
            tag_apply = registry.apply_tag(tag_proposal["proposal_id"])
            tag_apply_again = registry.apply_tag(tag_proposal["proposal_id"])
            comment_proposal = registry.propose_comment(
                packet.source_ref,
                "This note explains how Hermes should use personal source evidence.",
                reason="useful answer context",
            )
            comment_apply = registry.apply_comment(comment_proposal["proposal_id"])
            sidecar_path = root_path / ".pska" / "annotations.jsonl"
            sidecar_entries = [
                json.loads(line)
                for line in sidecar_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            source_after_apply = source_path.read_text(encoding="utf-8")

        self.assertEqual(source_after_apply, original_text)
        self.assertEqual(tag_proposal["status"], "pending")
        self.assertEqual(tag_proposal["data_flow"]["requires_apply"], True)
        self.assertEqual(tag_apply["proposal"]["status"], "applied")
        self.assertEqual(tag_apply["record"]["name"], "project/hermes")
        self.assertFalse(tag_apply["data_flow"]["writes_source_files"])
        self.assertFalse(tag_apply["data_flow"]["writes_original_source_files"])
        self.assertTrue(tag_apply["data_flow"]["writes_sidecar"])
        self.assertTrue(tag_apply_again["already_applied"])
        self.assertFalse(tag_apply_again["data_flow"]["writes_sidecar"])
        self.assertEqual(comment_apply["proposal"]["status"], "applied")
        self.assertIn("Hermes should use personal source evidence", comment_apply["record"]["body"])
        self.assertEqual([entry["action"] for entry in sidecar_entries], ["tag", "comment"])
        self.assertEqual(sidecar_entries[0]["path"], "Architecture.md")
        self.assertEqual(sidecar_entries[0]["payload"]["tag"], "project/hermes")

    def test_read_only_root_can_propose_but_cannot_apply_source_annotation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "note.md").write_text("# Note\n\nHermes source note.\n", encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(root_path, permission_mode="read_only")
            registry.scan(root["root_id"])
            packet = registry.search("Hermes source", {"root_ids": [root["root_id"]]})[0]

            proposal = registry.propose_tag(packet.source_ref, "readonly")
            with self.assertRaisesRegex(SourceRegistryError, "requires permission_mode"):
                registry.apply_tag(proposal["proposal_id"])
            sidecar_created = (root_path / ".pska").exists()

        self.assertFalse(sidecar_created)

    def test_obsidian_moc_proposal_applies_only_with_native_permission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            alpha = vault / "Alpha.md"
            beta = vault / "Beta.md"
            alpha.write_text("# Alpha\n\nHermes should index this note.\n", encoding="utf-8")
            beta.write_text("# Beta\n\nPSKA should collect this note in a MOC.\n", encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(vault, kind="auto", permission_mode="native_write")
            registry.scan(root["root_id"])
            alpha_ref = registry.search("Hermes index", {"root_ids": [root["root_id"]]})[0].source_ref
            beta_ref = registry.search("collect this note", {"root_ids": [root["root_id"]]})[0].source_ref

            proposal = registry.propose_obsidian_moc(
                root["root_id"],
                [alpha_ref, beta_ref],
                moc_path="Maps/PSKA Index",
                title="PSKA Index",
                reason="collect unlinked notes",
            )
            applied = registry.apply_obsidian_moc(proposal["proposal_id"])
            applied_again = registry.apply_obsidian_moc(proposal["proposal_id"])
            moc_text = (vault / "Maps" / "PSKA Index.md").read_text(encoding="utf-8")

        self.assertEqual(proposal["action"], "obsidian_moc")
        self.assertEqual(proposal["write_target"], "obsidian_moc")
        self.assertEqual(proposal["payload"]["link_count"], 2)
        self.assertIn("[[Alpha]]", proposal["payload"]["rendered_block"])
        self.assertIn("[[Beta]]", proposal["payload"]["rendered_block"])
        self.assertTrue(applied["applied"])
        self.assertTrue(applied["data_flow"]["writes_source_files"])
        self.assertTrue(applied["record"]["created_file"])
        self.assertIn("<!-- PSKA:MOC:BEGIN -->", moc_text)
        self.assertIn("[[Alpha]]", moc_text)
        self.assertIn("[[Beta]]", moc_text)
        self.assertTrue(applied_again["already_applied"])
        self.assertFalse(applied_again["data_flow"]["writes_source_files"])

    def test_obsidian_moc_apply_rejects_read_only_vault(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "Alpha.md").write_text("# Alpha\n\nHermes source note.\n", encoding="utf-8")
            registry = SQLiteSourceRegistry(":memory:")
            root = registry.register_root(vault, kind="auto", permission_mode="read_only")
            registry.scan(root["root_id"])
            source_ref = registry.search("Hermes source", {"root_ids": [root["root_id"]]})[0].source_ref
            proposal = registry.propose_obsidian_moc(root["root_id"], [source_ref], moc_path="PSKA MOC.md")

            with self.assertRaisesRegex(SourceRegistryError, "native_write or managed"):
                registry.apply_obsidian_moc(proposal["proposal_id"])
            moc_created = (vault / "PSKA MOC.md").exists()

        self.assertFalse(moc_created)

    def test_mcp_obsidian_moc_tools_create_apply_and_audit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "Alpha.md").write_text("# Alpha\n\nHermes source note for MOC.\n", encoding="utf-8")
            service = build_fake_service()
            tools = tool_registry(service)
            root = tools["pska_source_root_register"](
                str(vault),
                kind="auto",
                permission_mode="native_write",
            )
            tools["pska_source_scan"](root["root_id"])
            packet = tools["pska_source_search"]("Hermes source note", {"root_ids": [root["root_id"]]})[0]

            proposal = tools["pska_obsidian_moc_propose"](
                root["root_id"],
                [packet["source_ref"]],
                moc_path="Maps/Main",
                title="Main MOC",
                reason="MCP MOC writeback",
            )
            applied = tools["pska_obsidian_moc_apply"](proposal["proposal_id"])
            moc_text = (vault / "Maps" / "Main.md").read_text(encoding="utf-8")

        self.assertEqual(proposal["action"], "obsidian_moc")
        self.assertTrue(applied["data_flow"]["writes_source_files"])
        self.assertIn("[[Alpha]]", moc_text)
        actions = {event.action for event in service.store.list_audit_events(limit=40)}
        self.assertIn("source.obsidian_moc.propose", actions)
        self.assertIn("source.obsidian_moc.apply", actions)

    def test_mcp_tag_and_comment_tools_create_audit_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "handoff.md").write_text(
                "# Handoff\n\nHermes can annotate local folder search results through sidecars.\n",
                encoding="utf-8",
            )
            service = build_fake_service()
            tools = tool_registry(service)
            root = tools["pska_source_root_register"](
                str(root_path),
                permission_mode="sidecar_write",
                label="Project Files",
            )
            tools["pska_source_scan"](root["root_id"])
            packet = tools["pska_source_search"]("annotate local folder", {"root_ids": [root["root_id"]]})[0]

            tag_proposal = tools["pska_source_tag_propose"](
                packet["source_ref"],
                "project/handoff",
                reason="project note",
            )
            tag_apply = tools["pska_source_tag_apply"](tag_proposal["proposal_id"])
            comment_proposal = tools["pska_source_comment_propose"](
                packet["source_ref"],
                "Keep this available for Hermes handoff context.",
            )
            comment_apply = tools["pska_source_comment_apply"](comment_proposal["proposal_id"])
            sidecar_text = (root_path / ".pska" / "annotations.jsonl").read_text(encoding="utf-8")

        self.assertEqual(tag_apply["record"]["name"], "project/handoff")
        self.assertIn("Hermes handoff context", comment_apply["record"]["body"])
        self.assertIn("project/handoff", sidecar_text)
        actions = {event.action for event in service.store.list_audit_events(limit=30)}
        self.assertIn("source.tag.propose", actions)
        self.assertIn("source.tag.apply", actions)
        self.assertIn("source.comment.propose", actions)
        self.assertIn("source.comment.apply", actions)

    def test_mcp_source_memory_review_create_promotes_source_route_to_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Project"
            root_path.mkdir()
            (root_path / "routing.md").write_text(
                "# Routing\n\nFor PSKA architecture questions, Hermes should inspect this folder first.\n",
                encoding="utf-8",
            )
            service = build_fake_service()
            tools = tool_registry(service)
            root = tools["pska_source_root_register"](str(root_path), label="Project Files")
            tools["pska_source_scan"](root["root_id"])
            packet = tools["pska_source_search"]("architecture questions", {"root_ids": [root["root_id"]]})[0]

            created = tools["pska_source_memory_review_create"](
                [packet["source_ref"]],
                text="For PSKA architecture questions, Hermes should inspect the Project Files source root first.",
                memory_type="source_route",
                behavior_delta="Route future PSKA architecture questions to this local source root before broad search.",
                memory_scope="project",
                reason="stable source routing rule",
            )

        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertIsNone(created["memory_apply"])
        self.assertEqual(created["memory_card"]["type"], "source_route")
        self.assertEqual(created["memory_card"]["scope"], "project")
        self.assertIn("Route future PSKA architecture", created["memory_card"]["behavior_delta"])
        self.assertEqual(created["proposal"]["memory_patch"]["metadata"]["origin"], "source_promotion")
        self.assertEqual(created["proposal"]["memory_patch"]["metadata"]["memory_type"], "source_route")
        self.assertEqual(created["artifact"]["traceability"]["source_count"], 1)
        actions = {event.action for event in service.store.list_audit_events(limit=40)}
        self.assertIn("source.memory_review.create", actions)
        self.assertIn("review.create", actions)

    def test_mcp_source_audit_reports_duplicates_links_orphans_and_routes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vault = Path(temp_dir) / "Vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            (vault / "Index.md").write_text(
                "# Index\n\nLinks [[Missing Note]] and [[Evidence]].\n",
                encoding="utf-8",
            )
            (vault / "Evidence.md").write_text("# Evidence\n\nLinked source evidence.\n", encoding="utf-8")
            (vault / "Orphan.md").write_text("# Orphan\n\nNo links here.\n", encoding="utf-8")
            duplicate_text = "# Duplicate\n\nSame exact source body.\n"
            (vault / "dup-a.md").write_text(duplicate_text, encoding="utf-8")
            (vault / "dup-b.md").write_text(duplicate_text, encoding="utf-8")
            service = build_fake_service()
            tools = tool_registry(service)
            root = tools["pska_source_root_register"](str(vault), kind="auto", label="Vault")
            tools["pska_source_scan"](root["root_id"])

            audit = tools["pska_source_audit_run"]({"root_ids": [root["root_id"]]}, limit=10)

        self.assertEqual(audit["schema"], "pska.source_audit.v1")
        self.assertEqual(audit["root_count"], 1)
        self.assertEqual(audit["roots"][0]["kind"], "obsidian_vault")
        self.assertEqual(audit["duplicate_preview"]["group_count"], 1)
        self.assertEqual(audit["duplicate_preview"]["duplicate_file_count"], 1)
        self.assertEqual(audit["unresolved_links"]["count"], 1)
        self.assertEqual(audit["unresolved_links"]["items"][0]["target_text"], "Missing Note")
        self.assertGreaterEqual(audit["unlinked_markdown"]["count"], 1)
        self.assertIn("Orphan.md", {item["path"] for item in audit["unlinked_markdown"]["items"]})
        self.assertIn("Index.md", {item["path"] for item in audit["route_candidates"]})
        next_actions = {item["action"] for item in audit["next_actions"]}
        self.assertIn("review_duplicates", next_actions)
        self.assertIn("inspect_unresolved_links", next_actions)
        self.assertIn("inspect_unlinked_notes", next_actions)
        self.assertIn("create_source_route_memory", next_actions)
        self.assertFalse(audit["data_flow"]["writes_source_files"])
        self.assertFalse(audit["data_flow"]["writes_memory_directly"])
        self.assertFalse(audit["data_flow"]["embedding_required"])
        actions = {event.action for event in service.store.list_audit_events(limit=40)}
        self.assertIn("source.audit.run", actions)


if __name__ == "__main__":
    unittest.main()
