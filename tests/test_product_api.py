from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.config import build_service_from_env
from pska_essential.contracts import MemoryFact, SourceRef
from pska_essential.kb_gateway import KbGatewayError, build_kb_gateway_from_env, reset_fake_kb_gateway
from pska_essential.product_api import build_server
from pska_essential.workflow import build_fake_service


class _FakeGateway:
    def __init__(self) -> None:
        self.uploaded: list[dict[str, str]] = []
        self.parse_calls: list[dict[str, object]] = []
        self.last_created: dict[str, object] | None = None
        self.last_ingest: dict[str, object] | None = None
        self.ready = True
        self.extra_datasets: dict[str, dict[str, object]] = {}

    def list_datasets(self, *, name=None, page_size=30):
        datasets = [
            {
                "backend": "fake-kb",
                "dataset_id": "demo",
                "name": "Demo",
                "document_count": 1,
                "chunk_count": 2 if self.ready else 0,
            }
        ]
        datasets.extend(self.extra_datasets.values())
        if name:
            return [item for item in datasets if item["name"] == name]
        return datasets

    def create_dataset(self, *, name, description="", chunk_method="naive", embedding_model=""):
        self.last_created = {
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
        }
        return {
            "backend": "fake-kb",
            "dataset_id": "created",
            "name": name,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
        }

    def delete_datasets(self, *, dataset_ids=None, dataset_names=None, delete_all=False):
        ids = [str(dataset_id) for dataset_id in dataset_ids or []]
        names = [str(dataset_name) for dataset_name in dataset_names or [] if str(dataset_name).strip()]
        if names and not delete_all:
            for dataset in self.list_datasets(page_size=100):
                if dataset["name"] in names and dataset["dataset_id"] not in ids:
                    ids.append(dataset["dataset_id"])
        deleted_ids = list(self.extra_datasets.keys()) if delete_all else [dataset_id for dataset_id in ids if dataset_id in self.extra_datasets or dataset_id == "demo"]
        if delete_all:
            self.extra_datasets.clear()
        else:
            for dataset_id in ids:
                self.extra_datasets.pop(dataset_id, None)
        return {
            "backend": "fake-kb",
            "dataset_ids": ids,
            "dataset_names": names,
            "deleted_dataset_ids": deleted_ids,
            "delete_all": bool(delete_all),
            "deleted": True,
        }

    def ingest_files(
        self,
        *,
        file_paths,
        dataset_name=None,
        dataset_id=None,
        description="",
        chunk_method="naive",
        embedding_model="",
        priority=0,
        parse=True,
        wait=False,
        timeout_seconds=300.0,
    ):
        self.last_ingest = {
            "dataset_name": dataset_name,
            "dataset_id": dataset_id,
            "description": description,
            "chunk_method": chunk_method,
            "embedding_model": embedding_model,
            "priority": priority,
            "parse": parse,
            "wait": wait,
        }
        self.uploaded = [
            {"name": Path(path).name, "text": Path(path).read_text(encoding="utf-8")} for path in file_paths
        ]
        target_dataset_id = dataset_id or "created"
        self.extra_datasets[target_dataset_id] = {
            "backend": "fake-kb",
            "dataset_id": target_dataset_id,
            "name": dataset_name or "Existing",
            "document_count": len(file_paths),
            "chunk_count": len(file_paths) if self.ready else 0,
            "embedding_model": embedding_model,
        }
        return {
            "backend": "fake-kb",
            "dataset_created": not bool(dataset_id),
            "dataset": {
                "dataset_id": target_dataset_id,
                "name": dataset_name or "Existing",
                "embedding_model": embedding_model,
            },
            "documents": [
                {
                    "dataset_id": target_dataset_id,
                    "document_id": "doc-1",
                    "name": self.uploaded[0]["name"],
                    "progress": 0.0,
                    "run": "UNSTART",
                }
            ],
            "parse": {"parse_started": bool(parse)},
        }

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "backend": "fake-kb",
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "note.txt",
                "chunk_count": 1 if self.ready else 0,
                "progress": 1.0 if self.ready else 0.1,
                "run": "DONE" if self.ready else "RUNNING",
            }
        ]

    def parse_documents(self, *, dataset_id, document_ids, priority=0, wait=False, timeout_seconds=300.0):
        self.parse_calls.append(
            {"dataset_id": dataset_id, "document_ids": document_ids, "priority": priority, "wait": wait}
        )
        return {"backend": "fake-kb", "dataset_id": dataset_id, "document_ids": document_ids, "parse_started": True}

    def document_graph(self, *, dataset_id, document_id):
        return {
            "backend": "fake-kb",
            "dataset_id": dataset_id,
            "document_id": document_id,
            "templates": [{"name": "demo-structure", "nodes": [], "edges": []}],
            "note": "Fake graph for Product API tests.",
        }


class ProductApiStartupTests(unittest.TestCase):
    def test_build_server_requires_workflow_provider_configuration(self):
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, {}, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER is required"):
                build_server(host="127.0.0.1", port=0, static_dir=static_dir)

    def test_build_server_rejects_fake_workflow_provider_without_dev_mode(self):
        env = {
            "PSKA_RETRIEVAL_PROVIDER": "fake",
            "PSKA_MEMORY_PROVIDER": "fake",
            "PSKA_KB_PROVIDER": "fake",
        }
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PSKA_RETRIEVAL_PROVIDER=fake"):
                build_server(host="127.0.0.1", port=0, static_dir=static_dir)

    def test_build_server_allows_explicit_dev_fake_mode(self):
        env = {
            "PSKA_DEV_FAKE": "1",
            "PSKA_REVIEW_DB": ":memory:",
        }
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            server = build_server(host="127.0.0.1", port=0, static_dir=static_dir)
            server.server_close()

    def test_build_server_validates_kb_gateway_configuration(self):
        env = {"PSKA_KB_PROVIDER": "ragflow"}
        with tempfile.TemporaryDirectory() as static_dir, patch.dict(os.environ, env, clear=True):
            Path(static_dir, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
            with self.assertRaisesRegex(KbGatewayError, "RAGFlow KB gateway is missing required env"):
                build_server(
                    host="127.0.0.1",
                    port=0,
                    service=build_fake_service(),
                    static_dir=static_dir,
                )


class ProductApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(os.environ, {"PSKA_WORKSPACE_ID": "", "PSKA_TENANT_ID": ""}, clear=False)
        self.env_patch.start()
        self.gateway = _FakeGateway()
        self.service = build_fake_service()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=self.service,
            kb_gateway_factory=lambda: self.gateway,
            static_dir=self.static_dir.name,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.static_dir.cleanup()
        self.env_patch.stop()

    def test_static_health_ask_review_and_apply_loop(self):
        html = self._get_text("/")
        self.assertIn("PSKA", html)
        health = self._get_json("/api/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["governance"]["durable_memory"], "manual_review")
        self.assertEqual(health["workspace"]["workspace_id"], "default")
        self.assertEqual(health["workspace"]["memory_namespace"], "")
        self.assertFalse(health["workspace"]["workspace_configured"])
        self.assertTrue(health["capabilities"]["memory"]["operations"]["update"]["supported"])
        self.assertTrue(health["capabilities"]["memory"]["operations"]["delete"]["supported"])
        self.assertEqual(health["product_api_contract"]["schema"], "pska.product_api_contract.v1")
        capabilities = self._get_json("/api/capabilities")
        self.assertTrue(capabilities["ok"])
        self.assertEqual(capabilities["capabilities"]["memory"]["backend"], "fake")
        contract_routes = {
            (route["method"], route["path"])
            for route in capabilities["product_api_contract"]["required_routes"]
        }
        self.assertIn(("POST", "/api/memory/search"), contract_routes)
        self.assertIn(("POST", "/api/memory/conversation-change"), contract_routes)
        self.assertIn(("POST", "/api/memory/conversation-candidates"), contract_routes)
        self.assertIn(("POST", "/api/reviews/batch-decision"), contract_routes)
        self.assertIn(("POST", "/api/reviews/merge-candidates"), contract_routes)
        self.assertIn(("GET", "/api/provider/jobs"), contract_routes)
        self.assertIn(("POST", "/api/jarvis/briefing"), contract_routes)
        self.assertIn(("POST", "/api/digest"), contract_routes)
        self.assertIn(("POST", "/api/digest-jobs"), contract_routes)
        self.assertIn(("GET", "/api/digest-jobs"), contract_routes)
        self.assertIn(("POST", "/api/digest-jobs/run-next"), contract_routes)
        self.assertIn(("POST", "/api/digest-jobs/{run_id}/run"), contract_routes)
        self.assertIn(("POST", "/api/workflows/{run_id}/memory-review"), contract_routes)
        self.assertIn(("POST", "/api/sources/audit-jobs"), contract_routes)
        self.assertIn(("GET", "/api/sources/audit-jobs"), contract_routes)
        self.assertIn(("POST", "/api/sources/audit-schedules"), contract_routes)
        self.assertIn(("POST", "/api/sources/audit-jobs/tick"), contract_routes)
        self.assertIn(("POST", "/api/sources/audit-jobs/run-next"), contract_routes)
        self.assertIn(("POST", "/api/sources/audit-jobs/{run_id}/run"), contract_routes)
        self.assertIn(("POST", "/api/sources/extraction-jobs"), contract_routes)
        self.assertIn(("GET", "/api/sources/extraction-jobs"), contract_routes)
        self.assertIn(("POST", "/api/sources/extraction-jobs/run-next"), contract_routes)
        self.assertIn(("POST", "/api/sources/extraction-jobs/{run_id}/run"), contract_routes)
        self.assertIn(("POST", "/api/sources/watch-once"), contract_routes)
        self.assertIn(("GET", "/api/sources/roots"), contract_routes)
        self.assertIn(("POST", "/api/sources/roots"), contract_routes)
        self.assertIn(("POST", "/api/sources/roots/{root_id}/scan"), contract_routes)
        self.assertIn(("POST", "/api/sources/search"), contract_routes)
        self.assertIn(("POST", "/api/sources/neighbors"), contract_routes)
        self.assertIn(("POST", "/api/sources/duplicates"), contract_routes)
        self.assertIn(("POST", "/api/sources/audits/run"), contract_routes)
        self.assertIn(("POST", "/api/sources/saved-searches"), contract_routes)
        self.assertIn(("POST", "/api/sources/tags/proposals"), contract_routes)
        self.assertIn(("POST", "/api/sources/tags/{proposal_id}/apply"), contract_routes)
        self.assertIn(("POST", "/api/sources/comments/proposals"), contract_routes)
        self.assertIn(("POST", "/api/sources/comments/{proposal_id}/apply"), contract_routes)
        self.assertIn(("POST", "/api/sources/obsidian/moc/proposals"), contract_routes)
        self.assertIn(("POST", "/api/sources/obsidian/moc/{proposal_id}/apply"), contract_routes)
        self.assertIn(("POST", "/api/sources/memory-reviews"), contract_routes)
        self.assertIn(("POST", "/api/sources/memory-candidates/from-audit"), contract_routes)
        self.assertIn(("POST", "/api/sources/read"), contract_routes)
        self.assertIn(("POST", "/api/eidolia/context/read"), contract_routes)
        self.assertIn(("POST", "/api/eidolia/memory-reviews"), contract_routes)
        self.assertIn(("POST", "/api/eidolia/project-traces/import"), contract_routes)
        self.assertIn(("GET", "/api/memory/cards"), contract_routes)
        self.assertIn(("GET", "/api/memory/cards/{memory_id}"), contract_routes)
        self.assertIn(("GET", "/api/memory/health"), contract_routes)
        self.assertIn(("GET", "/api/memory/use-traces"), contract_routes)
        self.assertIn(("GET", "/api/memory/candidate-dedup"), contract_routes)
        self.assertIn(("GET", "/api/memory/{memory_id}/use-trace"), contract_routes)
        self.assertIn(("GET", "/api/memory/{memory_id}/why-used"), contract_routes)
        self.assertIn(("GET", "/api/trace/query"), contract_routes)
        self.assertIn(("GET", "/api/workflows/{run_id}/memory-attribution"), contract_routes)
        self.assertIn(("GET", "/api/workflows/{run_id}/memory-suggestions"), contract_routes)
        self.assertIn(("POST", "/api/turn-context"), contract_routes)
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["apply"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["list"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["get"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["update"]["supported"])
        self.assertTrue(capabilities["capabilities"]["memory"]["operations"]["delete"]["supported"])
        source_layer = capabilities["capabilities"]["source_layer"]
        self.assertEqual(source_layer["schema"], "pska.source_layer.v1")
        self.assertEqual(source_layer["status"], "m10_obsidian_moc_writeback")
        self.assertIn("pska_source_search", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_neighbors", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_duplicate_report", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_run", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_enqueue", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_schedule_create", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_list", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_tick", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_run", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_extract_job_enqueue", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_extract_job_list", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_extract_job_run", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_watch_once", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_saved_search_create", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_tag_propose", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_tag_apply", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_comment_propose", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_comment_apply", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_obsidian_moc_propose", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_obsidian_moc_apply", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_memory_review_create", source_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_memory_candidates_from_audit", source_layer["mcp_tools"]["implemented"])
        self.assertFalse(source_layer["embedding_required"])
        self.assertIn("extraction", source_layer["adapter_slots"])
        self.assertIn("builtin_text", source_layer["adapter_slots"]["extraction"])
        self.assertIn("markitdown", source_layer["adapter_slots"]["extraction"])
        self.assertIn("dedup", source_layer["adapter_slots"])
        self.assertIn("fclones", source_layer["adapter_slots"]["dedup"])
        assistant_layer = capabilities["capabilities"]["assistant_layer"]
        self.assertEqual(assistant_layer["schema"], "pska.assistant_layer.v1")
        self.assertEqual(assistant_layer["status"], "m10_jarvis_obsidian_moc_writeback")
        self.assertEqual(assistant_layer["primary_agent"], "Hermes")
        self.assertIn("pska_jarvis_briefing", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_tick", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_audit_job_run", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_extract_job_run", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_watch_once", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_obsidian_moc_propose", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_workflow_memory_attribution", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_workflow_memory_suggestions", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_memory_timeline", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_memory_candidate_dedup", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_review_merge_candidates", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_source_memory_candidates_from_audit", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_eidolia_context_read", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_eidolia_memory_review_create", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_trace_query", assistant_layer["mcp_tools"]["implemented"])
        self.assertIn("pska_eidolia_project_trace_import", assistant_layer["mcp_tools"]["implemented"])
        thought_artifact = capabilities["capabilities"]["adapter_slots"]["slots"]["thought_artifact"]
        self.assertEqual(thought_artifact["providers"][0]["name"], "eidolia_source_ref_bridge")
        self.assertEqual(thought_artifact["providers"][0]["status"], "implemented")
        self.assertEqual(thought_artifact["providers"][1]["name"], "eidolia_project_files")
        self.assertEqual(thought_artifact["providers"][1]["status"], "implemented")
        search_view = capabilities["capabilities"]["memory"]["search_view"]
        self.assertEqual(search_view["schema"], "pska.memory_search_view.v1")
        self.assertTrue(search_view["default_filters_superseded"])
        self.assertIn("display_text", search_view["agent_facing_text"]["metadata_keys"])
        card_view = capabilities["capabilities"]["memory"]["card_view"]
        self.assertEqual(card_view["schema"], "pska.memory_card_view.v1")
        self.assertEqual(card_view["apis"]["list"], "GET /api/memory/cards")
        health_view = capabilities["capabilities"]["memory"]["health_view"]
        self.assertEqual(health_view["schema"], "pska.memory_health_view.v1")
        self.assertEqual(health_view["mcp_tool"], "pska_memory_health_scan")
        review_queue_view = capabilities["capabilities"]["memory"]["review_queue_view"]
        self.assertEqual(review_queue_view["schema"], "pska.memory_review_queue_view.v1")
        self.assertIn("conversation_candidates", review_queue_view["groups"])
        self.assertIn("candidate_quality", review_queue_view["groups"])
        self.assertIn("related_candidates", review_queue_view["groups"])
        self.assertIn("merged_replacements", review_queue_view["groups"])
        self.assertIn("review_conversation_memory_candidate", review_queue_view["next_actions"])
        self.assertIn("review_memory_candidate_quality", review_queue_view["next_actions"])
        self.assertIn("mark_memory_candidate_needs_edit", review_queue_view["next_actions"])
        self.assertIn("accept_review_group", review_queue_view["next_actions"])
        self.assertIn("reject_review_group", review_queue_view["next_actions"])
        self.assertIn("inspect_related_memory_candidates", review_queue_view["next_actions"])
        dedup_view = capabilities["capabilities"]["memory"]["candidate_dedup_view"]
        self.assertEqual(dedup_view["schema"], "pska.memory_candidate_dedup_view.v1")
        self.assertEqual(dedup_view["mcp_tool"], "pska_memory_candidate_dedup")
        self.assertEqual(dedup_view["related_group_schema"], "pska.memory_candidate_related_group.v1")
        self.assertIn("related_threshold", dedup_view["inputs"])
        self.assertIn("merge_candidate_group", dedup_view["next_actions"])
        self.assertFalse(dedup_view["embedding_required"])
        attribution_view = capabilities["capabilities"]["memory"]["attribution_view"]
        self.assertEqual(attribution_view["schema"], "pska.memory_attribution_view.v1")
        self.assertEqual(attribution_view["mcp_tool"], "pska_workflow_memory_attribution")
        suggestion_view = capabilities["capabilities"]["memory"]["suggestion_view"]
        self.assertEqual(suggestion_view["schema"], "pska.memory_suggestion_view.v1")
        self.assertEqual(suggestion_view["mcp_tool"], "pska_workflow_memory_suggestions")
        use_trace_view = capabilities["capabilities"]["memory"]["use_trace_view"]
        self.assertEqual(use_trace_view["schema"], "pska.memory_use_trace_view.v1")
        self.assertEqual(use_trace_view["apis"]["why_used"], "GET /api/memory/{memory_id}/why-used")
        timeline_view = capabilities["capabilities"]["memory"]["timeline_view"]
        self.assertEqual(timeline_view["schema"], "pska.memory_timeline_view.v1")
        self.assertEqual(timeline_view["api"], "GET /api/memory/{memory_id}/timeline")
        trace_view = capabilities["capabilities"]["memory"]["trace_view"]
        self.assertEqual(trace_view["schema"], "pska.trace_query_view.v1")
        self.assertEqual(trace_view["mcp_tool"], "pska_trace_query")
        self.assertFalse(trace_view["data_flow"]["embedding_required"])
        interaction_model = capabilities["capabilities"]["memory"]["interaction_model"]
        self.assertEqual(interaction_model["schema"], "pska.memory_interaction_model.v1")
        self.assertEqual(interaction_model["primary_user_path"], "conversation")
        self.assertEqual(interaction_model["review_queue_role"], "exception_inbox")
        self.assertEqual(interaction_model["visible_memory_editor"], "conversation")
        self.assertEqual(interaction_model["visible_review_role"], "exception_only")
        self.assertTrue(interaction_model["agent_decides_operation"])
        self.assertFalse(interaction_model["target_resolution"]["creates_review_item"])
        self.assertEqual(interaction_model["conversation_change_tool"], "pska_memory_change_from_conversation")
        self.assertIn("conflicting", interaction_model["review_queue_triggers"])
        self.assertIn("ambiguous_destructive", interaction_model["review_queue_triggers"])
        self.assertNotIn("destructive", interaction_model["review_queue_triggers"])
        explicit_changes = interaction_model["conversation_explicit_user_changes"]
        self.assertEqual(explicit_changes["remember"], "conversation_policy")
        self.assertEqual(explicit_changes["correct_clear_target"], "conversation_policy")
        self.assertEqual(explicit_changes["forget_specific_fact"], "conversation_policy")
        self.assertEqual(explicit_changes["missing_or_ambiguous_target"], "needs_target_no_review")
        self.assertEqual(explicit_changes["force_review"], "exception_review")
        inflow = capabilities["capabilities"]["memory"]["inflow"]
        self.assertEqual(inflow["schema"], "pska.memory_inflow.v1")
        self.assertFalse(inflow["upload_behavior"]["writes_memory_provider"])
        inflow_paths = {path["name"]: path for path in inflow["paths"]}
        self.assertEqual(
            inflow_paths["conversation_memory_candidates"]["mcp"],
            "pska_conversation_memory_candidates_create",
        )
        self.assertFalse(inflow_paths["conversation_memory_candidates"]["writes_memory_provider_directly"])
        self.assertFalse(inflow["upload_behavior"]["creates_graph_projection"])
        self.assertIn("digest_job", [path["name"] for path in inflow["paths"]])
        lineage = capabilities["capabilities"]["memory"]["lineage"]
        self.assertEqual(lineage["schema"], "pska.memory_lineage.v1")
        self.assertFalse(lineage["pska_authoritative_mapping_table"])
        self.assertIn("fact_or_edge_metadata", lineage["provider_carriers"])
        adapter_slots = capabilities["capabilities"]["adapter_slots"]
        self.assertEqual(adapter_slots["schema"], "pska.adapter_slots.v1")
        self.assertEqual(adapter_slots["default_dependency_policy"], "stdlib_first_optional_adapters")
        self.assertIn("SourceRef", adapter_slots["core_owns"])
        self.assertIn("Memory Card envelope", adapter_slots["core_owns"])
        self.assertEqual(adapter_slots["slots"]["extraction"]["contract"], "ExtractionPort")
        self.assertEqual(adapter_slots["slots"]["dedup"]["contract"], "DedupPort")
        self.assertEqual(adapter_slots["slots"]["thought_artifact"]["contract"], "ThoughtArtifactPort")
        self.assertEqual(adapter_slots["slots"]["observability"]["contract"], "ObservabilityPort")
        self.assertIn("builtin_text", adapter_slots["summary"]["extraction"]["available"])
        self.assertIn("sqlite_fts5", adapter_slots["summary"]["search_index"]["available"])
        self.assertIn("exact_hash", adapter_slots["summary"]["dedup"]["available"])
        markitdown = _adapter_provider(adapter_slots, "extraction", "markitdown")
        self.assertIn(markitdown["status"], {"available", "unavailable"})
        self.assertNotEqual(markitdown["status"], "planned")
        self.assertEqual(markitdown["integration"], "python_optional_extra")
        docling = _adapter_provider(adapter_slots, "extraction", "docling")
        self.assertIn(docling["status"], {"available", "unavailable"})
        self.assertNotEqual(docling["status"], "planned")
        self.assertEqual(docling["integration"], "python_optional_extra")
        fclones = _adapter_provider(adapter_slots, "dedup", "fclones")
        self.assertIn(fclones["status"], {"available", "unavailable"})
        self.assertEqual(fclones["integration"], "external_cli")
        self.assertFalse(fclones["safety"]["delete_move_merge_supported"])
        czkawka = _adapter_provider(adapter_slots, "dedup", "czkawka")
        self.assertIn(czkawka["status"], {"available", "unavailable"})
        self.assertEqual(czkawka["integration"], "external_cli")
        self.assertEqual(czkawka["env_key"], "PSKA_CZKAWKA_BIN")
        self.assertFalse(czkawka["safety"]["delete_move_merge_supported"])
        self.assertEqual(capabilities["capabilities"]["tool_policy"]["mode"], "soft_constraints")
        self.assertTrue(
            capabilities["capabilities"]["tool_policy"]["tools"]["pska_memory_apply"]["requires_accepted_review"]
        )
        policy = self._get_json("/api/policy")
        self.assertEqual(policy["governance"]["actions"]["memory_patch"], "manual_review")
        self.assertEqual(policy["governance"]["actions"]["memory_update"], "manual_review")
        self.assertEqual(policy["governance"]["actions"]["memory_delete"], "manual_review")
        self.assertEqual(policy["governance"]["transient_results"], "skip")

        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern memory?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertEqual(
            [step["name"] for step in asked["loop"]["steps"][:3]],
            ["scope.check", "governance.policy", "kb.readiness"],
        )
        review_id = asked["review"]["review_id"]
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(asked["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        source = self._post_json("/api/sources/read", {"source_ref": asked["context_packets"][0]["source_ref"]})
        self.assertIn("PSKA-Essential", source["source"]["text"])
        source_audit = self._get_json("/api/audit?limit=10&action=source.read")
        self.assertEqual(source_audit["events"][0]["action"], "source.read")
        self.assertEqual(source_audit["events"][0]["metadata"]["adapter"], "fake")
        self.assertEqual(
            source_audit["events"][0]["metadata"]["document_id"],
            asked["context_packets"][0]["source_ref"]["document_id"],
        )

        workflows = self._get_json("/api/workflows?limit=5")
        self.assertEqual(workflows["workflows"][0]["run_id"], asked["run"]["run_id"])
        self.assertEqual(workflows["workflows"][0]["metadata"]["agentic_loop"]["review_id"], review_id)
        opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["review_id"], review_id)
        self.assertEqual(opened["artifact"]["run"]["metadata"]["agentic_loop"]["governance"]["action"], "manual_review")
        exported = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("## Source Manifest", exported["export"])
        self.assertIn("## Inspected Sources", exported["export"])
        exported_json = self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=json")
        self.assertEqual(exported_json["export"]["traceability"]["context_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["source_inspection_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["source_count"], 1)
        self.assertEqual(exported_json["export"]["traceability"]["export"]["source_inspection_count"], 1)
        self.assertEqual(exported_json["export"]["latest_proposal"]["kind"], "memory_patch")

        reviews = self._get_json("/api/reviews?status=pending")
        self.assertEqual(reviews["reviews"][0]["review_id"], review_id)
        review_record = self._get_json(f"/api/reviews/{review_id}")["review"]
        self.assertEqual(review_record["review_id"], review_id)
        self.assertEqual(review_record["proposal"]["kind"], "memory_patch")
        self.assertEqual(review_record["source_count"], 1)
        self.assertEqual(review_record["source_refs"][0]["adapter"], "fake")
        self.assertIsNone(review_record["memory_apply"])

        decision = self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "accept", "reason": "test"})
        self.assertEqual(decision["decision"]["status"], "accepted")
        accepted_status = self._get_json("/api/workspace/status")["workspace_status"]
        accepted_actions = {action["action"]: action for action in accepted_status["next_actions"]}
        self.assertEqual(accepted_actions["apply_accepted_memory"]["params"]["review_id"], review_id)
        self.assertEqual(accepted_actions["apply_accepted_memory"]["tool"], "pska_memory_apply")

        applied = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertTrue(applied["applied"]["applied"])
        applied_again = self._post_json(f"/api/reviews/{review_id}/apply-memory", {})
        self.assertEqual(applied_again["applied"]["target_id"], applied["applied"]["target_id"])
        followup = self._post_json(
            "/api/ask",
            {
                "question": "Use governed memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(followup["status"], "ready")
        self.assertEqual(len(followup["memory_facts"]), 1)
        self.assertEqual(followup["artifact"]["traceability"]["memory_count"], 1)
        self.assertEqual(followup["artifact"]["traceability"]["memory_source_count"], 1)
        self.assertEqual(followup["artifact"]["memory_source_manifest"][0]["adapter"], "fake")
        self.assertEqual(followup["memory_attribution"]["schema"], "pska.memory_attribution.v1")
        self.assertEqual(followup["memory_attribution"]["used_memory_ids"], [followup["memory_facts"][0]["fact_id"]])
        self.assertEqual(followup["artifact"]["memory_attribution"]["used_memory_ids"], followup["memory_attribution"]["used_memory_ids"])
        self.assertEqual(followup["memory_suggestions"]["schema"], "pska.memory_suggestions.v1")
        self.assertEqual(followup["memory_suggestions"]["suggestions"][0]["next_actions"][0]["tool"], "pska_memory_review_from_workflow")
        self.assertIn("Durable workspace memory", followup["proposal"]["body"])
        followup_export = self._get_json(f"/api/workflows/{followup['run']['run_id']}/export?format=json")
        self.assertEqual(followup_export["export"]["traceability"]["memory_source_count"], 1)
        self.assertEqual(followup_export["export"]["memory_attribution"]["used_memory_ids"], followup["memory_attribution"]["used_memory_ids"])
        attribution = self._get_json(f"/api/workflows/{followup['run']['run_id']}/memory-attribution")
        suggestions = self._get_json(f"/api/workflows/{followup['run']['run_id']}/memory-suggestions")
        self.assertEqual(attribution["memory_attribution"]["used_memory_ids"], followup["memory_attribution"]["used_memory_ids"])
        self.assertEqual(suggestions["memory_suggestions"]["suggestion_count"], 1)
        memory_audit = self._get_json("/api/audit?limit=10&action=memory.search")
        self.assertEqual(memory_audit["events"][0]["metadata"]["count"], 1)
        late_decision = self._post_json_error(
            f"/api/reviews/{review_id}/decision",
            {"decision": "reject", "reason": "too late"},
        )
        self.assertEqual(late_decision["status"], 400)
        self.assertIn("after durable memory has been applied", late_decision["body"]["error"]["message"])

        accepted_reviews = self._get_json("/api/reviews?status=accepted")
        self.assertEqual(accepted_reviews["reviews"][0]["memory_apply"]["target_id"], applied["applied"]["target_id"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("workflow.export", actions)
        self.assertIn("memory.apply", actions)
        self.assertIn("source.read", actions)
        memory_event = next(event for event in audit["events"] if event["action"] == "memory.apply")
        self.assertEqual(memory_event["metadata"]["proposal_kind"], "memory_patch")
        self.assertEqual(memory_event["metadata"]["source_count"], 1)
        self.assertEqual(memory_event["metadata"]["source_refs"][0]["adapter"], "fake")
        self.assertEqual(audit["events"][0]["metadata"]["workspace_id"], "default")

        updated_text = "Updated durable memory says citrinepolicy is governed."
        update_review = self._post_json(
            "/api/memory/update-review",
            {"memory_fact": followup["memory_facts"][0], "text": updated_text, "reason": "clearer wording"},
        )
        self.assertEqual(update_review["proposal"]["kind"], "memory_update")
        self.assertEqual(update_review["proposal"]["memory_update"]["target_id"], applied["applied"]["target_id"])
        update_apply_blocked = self._post_json_error(
            f"/api/reviews/{update_review['review']['review_id']}/apply-memory",
            {},
        )
        self.assertEqual(update_apply_blocked["status"], 400)
        self.assertIn("accepted review", update_apply_blocked["body"]["error"]["message"])

        self._post_json(
            f"/api/reviews/{update_review['review']['review_id']}/decision",
            {"decision": "accept", "reason": "update approved"},
        )
        updated = self._post_json(f"/api/reviews/{update_review['review']['review_id']}/apply-memory", {})
        self.assertTrue(updated["applied"]["applied"])
        self.assertEqual(updated["applied"]["metadata"]["operation"], "update")
        self.assertEqual(updated["applied"]["metadata"]["version"], 2)
        after_update = self._post_json(
            "/api/ask",
            {
                "question": "What does citrinepolicy say?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(after_update["memory_facts"][0]["text"], updated_text)
        self.assertEqual(after_update["memory_facts"][0]["metadata"]["version"], 2)
        update_audit = self._get_json("/api/audit?limit=10&action=memory.update")
        self.assertEqual(update_audit["events"][0]["metadata"]["proposal_kind"], "memory_update")
        self.assertEqual(update_audit["events"][0]["metadata"]["memory_target_id"], applied["applied"]["target_id"])

        delete_review = self._post_json(
            "/api/memory/delete-review",
            {"memory_fact": after_update["memory_facts"][0], "reason": "outdated"},
        )
        self.assertEqual(delete_review["proposal"]["kind"], "memory_delete")
        self.assertEqual(delete_review["proposal"]["memory_delete"]["target_id"], applied["applied"]["target_id"])
        self.assertEqual(delete_review["review"]["status"], "pending")
        delete_apply_blocked = self._post_json_error(
            f"/api/reviews/{delete_review['review']['review_id']}/apply-memory",
            {},
        )
        self.assertEqual(delete_apply_blocked["status"], 400)
        self.assertIn("accepted review", delete_apply_blocked["body"]["error"]["message"])

        self._post_json(
            f"/api/reviews/{delete_review['review']['review_id']}/decision",
            {"decision": "accept", "reason": "delete approved"},
        )
        deleted = self._post_json(f"/api/reviews/{delete_review['review']['review_id']}/apply-memory", {})
        self.assertTrue(deleted["applied"]["applied"])
        self.assertEqual(deleted["applied"]["metadata"]["operation"], "delete")
        after_delete = self._post_json(
            "/api/ask",
            {
                "question": "What does citrinepolicy say?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(after_delete["memory_facts"], [])
        delete_audit = self._get_json("/api/audit?limit=10&action=memory.delete")
        self.assertEqual(delete_audit["events"][0]["metadata"]["proposal_kind"], "memory_delete")
        self.assertEqual(delete_audit["events"][0]["metadata"]["memory_target_id"], applied["applied"]["target_id"])
        lifecycle = self._get_json(f"/api/memory/{applied['applied']['target_id']}/lifecycle")
        self.assertEqual(lifecycle["lifecycle"]["change_count"], 3)
        self.assertEqual(
            [event["action"] for event in lifecycle["lifecycle"]["events"]],
            ["memory.apply", "memory.update", "memory.delete"],
        )
        self.assertEqual(lifecycle["lifecycle"]["latest_event"]["action"], "memory.delete")

    def test_product_api_personal_source_root_scan_search_and_read(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            (root_path / ".obsidian").mkdir()
            (root_path / "Architecture.md").write_text(
                "# Architecture\n\n"
                "## Hermes\n\n"
                "Hermes reads PSKA personal source evidence before synthesizing answers.\n"
                "Related note: [[Evidence]].\n",
                encoding="utf-8",
            )
            (root_path / "Evidence.md").write_text(
                "# Evidence\n\nSource evidence for Hermes product answers.\n",
                encoding="utf-8",
            )

            registered = self._post_json(
                "/api/sources/roots",
                {"path": str(root_path), "kind": "auto", "permission_mode": "native_write"},
            )
            roots = self._get_json("/api/sources/roots")
            scanned = self._post_json(
                f"/api/sources/roots/{registered['root']['root_id']}/scan",
                {"max_files": 10, "extractor": "auto"},
            )
            searched = self._post_json(
                "/api/sources/search",
                {"query": "Hermes personal source", "scope": {"root_ids": [registered["root"]["root_id"]]}},
            )
            architecture_packet = next(
                packet
                for packet in searched["context_packets"]
                if packet["source_ref"]["path"] == "Architecture.md"
            )
            duplicate = self._post_json(
                "/api/sources/duplicates",
                {"scope": {"root_ids": [registered["root"]["root_id"]]}},
            )
            source_audit = self._post_json(
                "/api/sources/audits/run",
                {"scope": {"root_ids": [registered["root"]["root_id"]]}, "limit": 10},
            )
            queued_audit_job = self._post_json(
                "/api/sources/audit-jobs",
                {
                    "scope": {"root_ids": [registered["root"]["root_id"]]},
                    "label": "Daily Hermes source audit",
                    "priority": 5,
                    "limit": 10,
                    "cadence": "daily",
                },
            )
            queued_jobs = self._get_json("/api/sources/audit-jobs?status=queued")
            audit_job_result = self._post_json("/api/sources/audit-jobs/run-next", {})
            rerun_completed_job = self._post_json(
                f"/api/sources/audit-jobs/{queued_audit_job['job']['run_id']}/run",
                {},
            )
            scheduled_audit = self._post_json(
                "/api/sources/audit-schedules",
                {
                    "scope": {"root_ids": [registered["root"]["root_id"]]},
                    "label": "Scheduled Hermes source audit",
                    "priority": 4,
                    "limit": 10,
                    "cadence": "daily",
                    "due_at": "2000-01-01T00:00:00+00:00",
                },
            )
            ticked_audits = self._post_json(
                "/api/sources/audit-jobs/tick",
                {"now": "2000-01-01T00:00:01+00:00", "limit": 5},
            )
            scheduled_audit_run = self._post_json("/api/sources/audit-jobs/run-next", {})
            queued_extraction_job = self._post_json(
                "/api/sources/extraction-jobs",
                {
                    "root_id": registered["root"]["root_id"],
                    "label": "Extract Hermes source files",
                    "priority": 6,
                    "max_files": 10,
                    "extractor": "auto",
                },
            )
            extraction_jobs = self._get_json("/api/sources/extraction-jobs?status=queued")
            extraction_job_result = self._post_json("/api/sources/extraction-jobs/run-next", {})
            jarvis = self._post_json(
                "/api/jarvis/briefing",
                {"source_scope": {"root_ids": [registered["root"]["root_id"]]}, "audit_limit": 10},
            )
            saved = self._post_json(
                "/api/sources/saved-searches",
                {
                    "label": "Hermes source evidence",
                    "query": "Hermes personal source",
                    "scope": {"root_ids": [registered["root"]["root_id"]]},
                },
            )
            source = self._post_json(
                "/api/sources/read",
                {"source_ref": architecture_packet["source_ref"]},
            )
            neighbors = self._post_json(
                "/api/sources/neighbors",
                {"source_ref": architecture_packet["source_ref"], "strategy": "links"},
            )
            tag_proposal = self._post_json(
                "/api/sources/tags/proposals",
                {
                    "target_ref": architecture_packet["source_ref"],
                    "tag": "project/hermes",
                    "reason": "matches project source scope",
                },
            )
            tag_apply = self._post_json(
                f"/api/sources/tags/{tag_proposal['proposal']['proposal_id']}/apply",
                {},
            )
            comment_proposal = self._post_json(
                "/api/sources/comments/proposals",
                {
                    "target_ref": architecture_packet["source_ref"],
                    "body": "Useful source evidence for Hermes answers.",
                },
            )
            comment_apply = self._post_json(
                f"/api/sources/comments/{comment_proposal['proposal']['proposal_id']}/apply",
                {},
            )
            moc_proposal = self._post_json(
                "/api/sources/obsidian/moc/proposals",
                {
                    "root_id": registered["root"]["root_id"],
                    "source_refs": [architecture_packet["source_ref"]],
                    "moc_path": "Maps/PSKA Index",
                    "title": "PSKA Index",
                    "reason": "collect source-route notes",
                },
            )
            moc_apply = self._post_json(
                f"/api/sources/obsidian/moc/{moc_proposal['proposal']['proposal_id']}/apply",
                {},
            )
            memory_review = self._post_json(
                "/api/sources/memory-reviews",
                {
                    "source_refs": [architecture_packet["source_ref"]],
                    "text": "For Hermes source-layer design questions, inspect the Architecture note first.",
                    "memory_type": "source_route",
                    "behavior_delta": "Route future Hermes source-layer design questions to the Architecture note before broad search.",
                    "memory_scope": "project",
                    "reason": "stable project source route",
                },
            )
            memory_candidates = self._post_json(
                "/api/sources/memory-candidates/from-audit",
                {
                    "scope": {"root_ids": [registered["root"]["root_id"]]},
                    "audit_limit": 10,
                    "candidate_limit": 5,
                    "memory_scope": "project",
                },
            )
            memory_candidates_again = self._post_json(
                "/api/sources/memory-candidates/from-audit",
                {
                    "scope": {"root_ids": [registered["root"]["root_id"]]},
                    "audit_limit": 10,
                    "candidate_limit": 5,
                    "memory_scope": "project",
                },
            )
            sidecar_entries = [
                json.loads(line)
                for line in (root_path / ".pska" / "annotations.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            source_after_apply = (root_path / "Architecture.md").read_text(encoding="utf-8")
            moc_text = (root_path / "Maps" / "PSKA Index.md").read_text(encoding="utf-8")

        self.assertTrue(registered["ok"])
        self.assertEqual(registered["root"]["kind"], "obsidian_vault")
        self.assertEqual(registered["root"]["permission_mode"], "native_write")
        self.assertEqual(len(roots["roots"]), 1)
        self.assertEqual(scanned["scan"]["counts"]["indexed"], 2)
        self.assertEqual(scanned["scan"]["extraction"]["extractor"], "auto")
        self.assertGreaterEqual(searched["count"], 1)
        self.assertEqual(duplicate["duplicate_report"]["group_count"], 0)
        self.assertEqual(source_audit["audit"]["schema"], "pska.source_audit.v1")
        self.assertEqual(source_audit["audit"]["root_count"], 1)
        self.assertEqual(source_audit["audit"]["duplicate_preview"]["group_count"], 0)
        self.assertIn("Architecture.md", {item["path"] for item in source_audit["audit"]["route_candidates"]})
        self.assertIn("create_source_memory_candidates_from_audit", {item["action"] for item in source_audit["audit"]["next_actions"]})
        self.assertEqual(queued_audit_job["status"], "queued")
        self.assertEqual(queued_audit_job["source_audit_job"]["request"]["cadence"], "daily")
        self.assertEqual(queued_jobs["source_audit_jobs"][0]["job"]["run_id"], queued_audit_job["job"]["run_id"])
        self.assertEqual(audit_job_result["status"], "completed")
        self.assertEqual(audit_job_result["source_audit"]["schema"], "pska.source_audit.v1")
        self.assertEqual(audit_job_result["source_audit"]["root_count"], 1)
        self.assertEqual(
            audit_job_result["source_audit_job"]["result_audit_id"],
            audit_job_result["source_audit"]["audit_id"],
        )
        self.assertFalse(audit_job_result["source_audit"]["data_flow"]["writes_source_files"])
        self.assertEqual(rerun_completed_job["status"], "completed")
        self.assertIsNone(rerun_completed_job["source_audit"])
        self.assertEqual(scheduled_audit["status"], "waiting")
        self.assertEqual(scheduled_audit["source_audit_job"]["schedule_mode"], "scheduled")
        self.assertEqual(ticked_audits["status"], "activated")
        self.assertEqual(ticked_audits["activated_count"], 1)
        self.assertEqual(scheduled_audit_run["status"], "completed")
        self.assertEqual(scheduled_audit_run["source_audit"]["schema"], "pska.source_audit.v1")
        self.assertEqual(scheduled_audit_run["next_job"]["status"], "waiting")
        self.assertEqual(
            scheduled_audit_run["next_job"]["source_audit_job"]["previous_run_id"],
            scheduled_audit_run["job"]["run_id"],
        )
        self.assertEqual(queued_extraction_job["status"], "queued")
        self.assertEqual(
            extraction_jobs["source_extraction_jobs"][0]["job"]["run_id"],
            queued_extraction_job["job"]["run_id"],
        )
        self.assertEqual(extraction_job_result["status"], "completed")
        self.assertEqual(extraction_job_result["scan"]["counts"]["indexed"], 2)
        self.assertEqual(extraction_job_result["source_extraction_job"]["summary"]["indexed"], 2)
        self.assertEqual(jarvis["briefing"]["schema"], "pska.jarvis_briefing.v1")
        self.assertEqual(jarvis["briefing"]["agent"]["primary"], "Hermes")
        self.assertEqual(jarvis["briefing"]["source_layer"]["root_count"], 1)
        self.assertIn("create_source_memory_candidates_from_audit", {item["action"] for item in jarvis["briefing"]["next_actions"]})
        self.assertFalse(jarvis["briefing"]["data_flow"]["writes_source_files"])
        self.assertEqual(saved["saved_search"]["label"], "Hermes source evidence")
        self.assertEqual(architecture_packet["source_ref"]["adapter"], "obsidian_vault")
        self.assertIn("Hermes reads PSKA personal source evidence", source["source"]["text"])
        self.assertEqual(neighbors["count"], 1)
        self.assertEqual(neighbors["neighbors"][0]["path"], "Evidence.md")
        self.assertEqual(neighbors["neighbors"][0]["relation"], "outgoing_link")
        self.assertEqual(tag_apply["applied"]["proposal"]["status"], "applied")
        self.assertEqual(tag_apply["applied"]["record"]["name"], "project/hermes")
        self.assertEqual(comment_apply["applied"]["proposal"]["status"], "applied")
        self.assertIn("Hermes answers", comment_apply["applied"]["record"]["body"])
        self.assertEqual(moc_proposal["proposal"]["action"], "obsidian_moc")
        self.assertEqual(moc_proposal["proposal"]["payload"]["link_count"], 1)
        self.assertTrue(moc_apply["applied"]["data_flow"]["writes_source_files"])
        self.assertEqual(memory_candidates["schema"], "pska.source_memory_candidates_from_audit.v1")
        self.assertGreaterEqual(memory_candidates["created_count"], 1)
        self.assertFalse(memory_candidates["data_flow"]["writes_memory_directly"])
        self.assertEqual(memory_candidates_again["created_count"], 0)
        self.assertGreaterEqual(memory_candidates_again["skipped_count"], 1)
        self.assertIn("<!-- PSKA:MOC:BEGIN -->", moc_text)
        self.assertIn("[[Architecture|Hermes]]", moc_text)
        self.assertEqual(memory_review["proposal"]["kind"], "memory_patch")
        self.assertEqual(memory_review["review"]["status"], "pending")
        self.assertIsNone(memory_review["memory_apply"])
        self.assertEqual(memory_review["memory_card"]["type"], "source_route")
        self.assertEqual(memory_review["memory_card"]["scope"], "project")
        self.assertIn("Route future Hermes", memory_review["memory_card"]["behavior_delta"])
        self.assertEqual(memory_review["proposal"]["memory_patch"]["metadata"]["origin"], "source_promotion")
        self.assertEqual(memory_review["artifact"]["traceability"]["source_count"], 1)
        self.assertEqual([entry["action"] for entry in sidecar_entries], ["tag", "comment"])
        self.assertIn("Hermes reads PSKA personal source evidence", source_after_apply)
        actions = {event.action for event in self.service.store.list_audit_events(limit=80)}
        self.assertIn("source.audit.run", actions)
        self.assertIn("source.audit_job.enqueue", actions)
        self.assertIn("source.audit_job.due", actions)
        self.assertIn("source.audit_job.run", actions)
        self.assertIn("source.extraction_job.enqueue", actions)
        self.assertIn("source.extraction_job.run", actions)
        self.assertIn("source.obsidian_moc.propose", actions)
        self.assertIn("source.obsidian_moc.apply", actions)

    def test_source_watch_once_route_delegates_to_bounded_watcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir) / "Vault"
            root_path.mkdir()
            registered = self._post_json(
                "/api/sources/roots",
                {"path": str(root_path), "kind": "local_folder", "permission_mode": "read_only"},
            )
            fake_result = {
                "schema": "pska.source_watch_once.v1",
                "status": "no_changes",
                "root_id": registered["root"]["root_id"],
                "event_count": 0,
                "events": [],
                "created_jobs": {},
                "next_actions": [],
                "data_flow": {
                    "watches_authorized_root_only": True,
                    "writes_source_files": False,
                    "writes_memory_directly": False,
                    "queues_jobs_only": True,
                },
            }
            with patch("pska_essential.product_api.watch_source_once", return_value=fake_result) as watcher:
                payload = self._post_json(
                    "/api/sources/watch-once",
                    {
                        "root_id": registered["root"]["root_id"],
                        "duration_seconds": 0,
                        "enqueue_extraction": True,
                        "enqueue_audit": True,
                    },
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema"], "pska.source_watch_once.v1")
        watcher.assert_called_once()
        self.assertEqual(watcher.call_args.kwargs["root_id"], registered["root"]["root_id"])
        self.assertEqual(watcher.call_args.kwargs["duration_seconds"], 0.0)
        self.assertTrue(watcher.call_args.kwargs["enqueue_extraction"])
        self.assertTrue(watcher.call_args.kwargs["enqueue_audit"])

    def test_turn_context_route_assembles_evidence_and_memory_without_ask(self):
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-pska-mini",
                text="PSKA-mini keeps long-term memory behind governance.",
                source_refs=[SourceRef(adapter="conversation", source_id="msg-1", title="Conversation")],
                metadata={"confidence": 0.91},
            )
        )

        payload = self._post_json(
            "/api/turn-context",
            {
                "caller": "hermes-webui",
                "workspace": "eidolia",
                "project_id": "novel-x",
                "user_message": "How should PSKA-mini provide memory and evidence?",
                "mode": "project",
                "scope": {"dataset_ids": ["demo"]},
                "budget": {"max_evidence_blocks": 1, "max_memory_notes": 2},
                "requirements": {"need_citations": True},
            },
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema"], "pska.turn_context_response.v1")
        self.assertTrue(payload["run_id"].startswith("run_"))
        self.assertEqual(payload["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(payload["scope"]["workspace"], "eidolia")
        self.assertEqual(payload["scope"]["project_id"], "novel-x")
        self.assertEqual(payload["requirements"]["need_citations"], True)
        self.assertNotIn("proposal", payload)
        self.assertNotIn("review", payload)

        turn_context = payload["turn_context"]
        evidence_blocks = turn_context["evidence_blocks"]
        memory_notes = turn_context["memory_notes"]
        self.assertEqual(len(evidence_blocks), 1)
        self.assertEqual(evidence_blocks[0]["type"], "evidence")
        self.assertEqual(evidence_blocks[0]["source_ref"]["adapter"], "fake")
        self.assertEqual(len(memory_notes), 1)
        self.assertEqual(memory_notes[0]["type"], "memory")
        self.assertEqual(memory_notes[0]["fact_id"], "mem-pska-mini")
        self.assertGreaterEqual(len(turn_context["citations"]), 2)
        self.assertEqual(turn_context["warnings"], [])

    def test_migration_manifest_endpoint_reports_component_inventory(self):
        run = self.service.start("api migration manifest", {"dataset_ids": ["demo"]})
        self.service.context_retrieve(run.run_id, "workflow gate", 1)
        proposal = self.service.propose(run.run_id, "memory_patch", "manifest memory")
        review = self.service.review_create(proposal.proposal_id)
        self.service.review_decide(review.review_id, "accept", "manifest accepted")
        applied = self.service.memory_apply(review.review_id)

        payload = self._get_json("/api/migration/manifest")
        manifest = payload["migration_manifest"]

        self.assertTrue(payload["ok"])
        self.assertEqual(manifest["schema"], "pska.migration_manifest.v1")
        self.assertIn("fake", manifest["components"]["retrieval_providers"])
        self.assertIn("fake", manifest["components"]["memory_providers"])
        self.assertIn(applied.target_id, manifest["components"]["memory_providers"]["fake"]["target_ids"])
        self.assertFalse(any("content_excerpt" in ref.get("metadata", {}) for ref in manifest["provider_source_refs"]))

    def test_conversation_memory_change_route_auto_applies(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_CONVERSATION_MEMORY": "auto_apply"}, clear=False):
            changed = self._post_json(
                "/api/memory/conversation-change",
                {
                    "user_message": "Remember that my shell is zsh.",
                    "text": "The user's shell is zsh.",
                    "session_id": "sess-api",
                    "message_id": "msg-api",
                },
            )

        self.assertEqual(changed["status"], "applied")
        self.assertEqual(changed["operation"], "memory_patch")
        self.assertEqual(changed["governance"]["origin"], "conversation")
        self.assertEqual(changed["governance"]["action"], "auto_apply")
        self.assertEqual(changed["review"]["status"], "accepted")
        self.assertEqual(changed["proposal"]["source_refs"][0]["adapter"], "hermes")
        self.assertEqual(changed["memory_apply"]["backend"], "fake")
        pending = self._get_json("/api/reviews?status=pending")
        self.assertEqual(pending["reviews"], [])
        audit = self._get_json("/api/audit?limit=10&action=memory.conversation_change")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "applied")

    def test_conversation_memory_candidates_route_creates_pending_reviews(self):
        created = self._post_json(
            "/api/memory/conversation-candidates",
            {
                "session_id": "sess-api-candidates",
                "messages": [
                    {
                        "message_id": "msg-api-candidate",
                        "role": "user",
                        "text": "For PSKA memory, candidate cards must have behavior_delta and source evidence.",
                    }
                ],
                "candidates": [
                    {
                        "text": "PSKA memory candidate cards must include behavior_delta and source evidence.",
                        "memory_type": "working_habit",
                        "memory_scope": "project",
                        "behavior_delta": "When creating PSKA memory candidates, include behavior_delta and source evidence.",
                        "message_ids": ["msg-api-candidate"],
                    }
                ],
            },
        )

        self.assertTrue(created["ok"])
        self.assertEqual(created["schema"], "pska.conversation_memory_candidates.v1")
        self.assertEqual(created["created_count"], 1)
        self.assertFalse(created["data_flow"]["writes_memory_directly"])
        pending = self._get_json("/api/reviews?status=pending")
        self.assertEqual(pending["reviews"][0]["review_id"], created["created"][0]["review_id"])
        queue = self._get_json("/api/memory/review-queue?review_limit=20&health_limit=10&focus_limit=10")
        queue_groups = {group["code"]: group for group in queue["groups"]}
        self.assertEqual(queue["summary"]["conversation_candidate_count"], 1)
        self.assertIn("conversation_candidates", queue_groups)
        self.assertEqual(
            queue_groups["conversation_candidates"]["items"][0]["review_id"],
            created["created"][0]["review_id"],
        )
        self.assertEqual(queue["next_actions"][0]["action"], "review_conversation_memory_candidate")
        facts = self.service.memory_search("behavior_delta", {}, 10)
        self.assertEqual(facts, [])
        audit = self._get_json("/api/audit?limit=10&action=memory.conversation_candidates.create")
        self.assertEqual(audit["events"][0]["metadata"]["created_count"], 1)

    def test_conversation_memory_change_route_returns_needs_target(self):
        with patch.dict(os.environ, {"PSKA_GOVERNANCE_CONVERSATION_MEMORY": "auto_apply"}, clear=False):
            changed = self._post_json(
                "/api/memory/conversation-change",
                {
                    "user_message": "Forget that my favorite tea is oolong.",
                    "operation": "forget",
                    "session_id": "sess-api",
                    "message_id": "msg-api-missing-target",
                },
            )

        self.assertEqual(changed["status"], "needs_target")
        self.assertEqual(changed["operation"], "memory_delete")
        self.assertEqual(changed["governance"]["action"], "needs_target")
        self.assertEqual(changed["target_resolution"]["status"], "not_found")
        self.assertEqual(changed["next_actions"][0]["tool"], "pska_memory_search")
        self.assertIsNone(changed["proposal"])
        pending = self._get_json("/api/reviews?status=pending")
        self.assertEqual(pending["reviews"], [])

    def test_memory_search_route_returns_search_view_and_display_metadata(self):
        self.service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text=(
                        "Memory correction episode.\n"
                        "Current fact: The user's editor is VS Code.\n"
                        "Previous fact: The user's editor is Vim.\n"
                        "Supersedes memory fact: old-editor"
                    ),
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "display_text": "The user's editor is VS Code.",
                        "current_text": "The user's editor is VS Code.",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )

        result = self._post_json("/api/memory/search", {"query": "Vim", "limit": 10})

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["memory_facts"][0]["fact_id"], "new-editor")
        self.assertEqual(result["memory_facts"][0]["metadata"]["display_text"], "The user's editor is VS Code.")
        self.assertEqual(result["search_view"]["schema"], "pska.memory_search_view.v1")
        self.assertTrue(result["search_view"]["default_filters_superseded"])
        audit = self._get_json("/api/audit?limit=10&action=memory.search")
        self.assertEqual(audit["events"][0]["metadata"]["superseded_fact_ids"], ["old-editor"])

    def test_memory_cards_routes_return_card_envelope(self):
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-route",
                text="Use the PSKA architecture note before broad source search.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route future PSKA questions to the architecture note first.",
                    "display_text": "PSKA questions should start from the architecture note.",
                    "confidence": 0.93,
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
        )

        cards = self._get_json("/api/memory/cards?limit=10")
        card = self._get_json("/api/memory/cards/mem-route")

        self.assertTrue(cards["ok"])
        self.assertEqual(cards["schema"], "pska.memory_card_collection.v1")
        self.assertEqual(cards["cards"][0]["memory_id"], "mem-route")
        self.assertEqual(cards["cards"][0]["agent_view"]["why_use"], cards["cards"][0]["behavior_delta"])
        self.assertEqual(card["card"]["memory_type"], "source_route")
        audit = self._get_json("/api/audit?limit=10&action=memory.card.list")
        self.assertEqual(audit["events"][0]["metadata"]["count"], 1)

    def test_memory_use_trace_routes_explain_search_and_card_events(self):
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-route",
                text="Use the PSKA architecture note before broad source search.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route future PSKA questions to the architecture note first.",
                    "display_text": "PSKA questions should start from the architecture note.",
                },
            )
        )

        self._post_json(
            "/api/memory/search",
            {"query": "PSKA architecture", "caller": "api-test", "purpose": "answer_context"},
        )
        traces = self._get_json("/api/memory/mem-route/use-trace?limit=10")
        why_used = self._get_json("/api/memory/mem-route/why-used")
        listed = self._get_json("/api/memory/use-traces?memory_id=mem-route&limit=10")

        self.assertEqual(traces["schema"], "pska.memory_use_trace.v1")
        self.assertEqual(traces["traces"][0]["action"], "memory.search")
        self.assertEqual(traces["traces"][0]["caller"], "api-test")
        self.assertEqual(traces["traces"][0]["memory_ids"], ["mem-route"])
        self.assertEqual(why_used["schema"], "pska.memory_why_used.v1")
        self.assertEqual(why_used["confidence"], "candidate_retrieval")
        self.assertIn("PSKA architecture", why_used["explanation"])
        self.assertEqual(listed["count"], 1)
        audit = self._get_json("/api/audit?limit=10&action=memory.why_used")
        self.assertEqual(audit["events"][0]["target_id"], "mem-route")

    def test_memory_timeline_route_combines_card_trace_and_source_anchor(self):
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-route",
                text="Use the PSKA architecture note before broad source search.",
                source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                metadata={
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route future PSKA questions to the architecture note first.",
                    "display_text": "PSKA questions should start from the architecture note.",
                    "created_at": "2026-01-01T00:00:00+00:00",
                },
            )
        )
        self._post_json(
            "/api/memory/search",
            {"query": "PSKA architecture", "caller": "api-test", "purpose": "answer_context"},
        )

        timeline = self._get_json("/api/memory/mem-route/timeline?limit=10")
        entry_types = [entry["type"] for entry in timeline["entries"]]

        self.assertEqual(timeline["schema"], "pska.memory_timeline.v1")
        self.assertIn("card_snapshot", entry_types)
        self.assertIn("usage_trace", entry_types)
        self.assertIn("source_anchor", entry_types)
        self.assertEqual(timeline["summary"]["usage_trace_count"], 1)
        self.assertEqual(timeline["summary"]["source_anchor_count"], 1)
        audit = self._get_json("/api/audit?limit=10&action=memory.timeline")
        self.assertEqual(audit["events"][0]["target_id"], "mem-route")

    def test_memory_briefing_route_summarizes_attention_items(self):
        self.service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-route",
                    text="Use the PSKA architecture note before broad source search.",
                    source_refs=[SourceRef(adapter="fake", source_id="note-1")],
                    metadata={
                        "memory_type": "source_route",
                        "memory_scope": "project",
                        "behavior_delta": "Route future PSKA questions to the architecture note first.",
                        "display_text": "PSKA questions should start from the architecture note.",
                    },
                ),
                MemoryFact(
                    fact_id="mem-raw",
                    text="Raw memory missing envelope fields.",
                    metadata={},
                ),
            ]
        )
        self._post_json(
            "/api/memory/search",
            {"query": "PSKA architecture", "caller": "api-test", "purpose": "answer_context"},
        )

        briefing = self._get_json("/api/memory/briefing?card_limit=10&health_limit=10&trace_limit=10")
        focus_ids = [item["memory_id"] for item in briefing["focus_items"]]

        self.assertTrue(briefing["ok"])
        self.assertEqual(briefing["schema"], "pska.memory_briefing.v1")
        self.assertIn("mem-route", focus_ids)
        self.assertIn("mem-raw", focus_ids)
        self.assertGreaterEqual(briefing["summary"]["issue_count"], 1)
        self.assertEqual(briefing["summary"]["recent_use_count"], 1)
        self.assertFalse(briefing["data_flow"]["writes_memory_directly"])
        self.assertEqual(briefing["next_actions"][0]["tool"], "pska_memory_health_scan")
        audit = self._get_json("/api/audit?limit=10&action=memory.briefing")
        self.assertEqual(audit["events"][0]["metadata"]["focus_count"], len(briefing["focus_items"]))

    def test_memory_review_queue_route_groups_review_and_health_work(self):
        created = self._post_json(
            "/api/sources/memory-reviews",
            {
                "source_refs": [{"adapter": "fake", "source_id": "review-queue-memory"}],
                "text": "PSKA review queue memory should be applied only after Memory Card quality is explicit.",
                "memory_type": "working_habit",
                "behavior_delta": "When applying review queue memory, require explicit Memory Card fields first.",
                "memory_scope": "project",
                "reason": "qualified candidate",
            },
        )
        review_id = created["review"]["review_id"]
        self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "accept", "reason": "ready"})
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-raw",
                text="Raw memory missing envelope fields.",
                metadata={},
            )
        )

        queue = self._get_json("/api/memory/review-queue?review_limit=20&health_limit=10&focus_limit=10")
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertTrue(queue["ok"])
        self.assertEqual(queue["schema"], "pska.memory_review_queue.v1")
        self.assertEqual(queue["status"], "apply_ready")
        self.assertEqual(groups["accepted_unapplied"]["items"][0]["review_id"], review_id)
        self.assertIn("memory_health", groups)
        self.assertFalse(queue["data_flow"]["writes_memory_directly"])
        self.assertEqual(queue["next_actions"][0]["tool"], "pska_memory_apply")
        audit = self._get_json("/api/audit?limit=10&action=memory.review_queue")
        self.assertEqual(audit["events"][0]["metadata"]["accepted_unapplied_count"], 1)

    def test_review_batch_decision_route_accepts_conversation_candidates(self):
        created = self._post_json(
            "/api/memory/conversation-candidates",
            {
                "session_id": "sess-api-batch",
                "messages": [
                    {"message_id": "msg-api-batch-1", "role": "user", "text": "Remember API batch candidate one."},
                    {"message_id": "msg-api-batch-2", "role": "user", "text": "Remember API batch candidate two."},
                ],
                "candidates": [
                    {
                        "text": "API batch candidate one should stay reviewed.",
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "When reviewing API batch candidates, preserve candidate one.",
                        "message_ids": ["msg-api-batch-1"],
                    },
                    {
                        "text": "API batch candidate two should stay reviewed.",
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "When reviewing API batch candidates, preserve candidate two.",
                        "message_ids": ["msg-api-batch-2"],
                    },
                ],
            },
        )
        review_ids = [item["review_id"] for item in created["created"]]

        batch = self._post_json(
            "/api/reviews/batch-decision",
            {"review_ids": review_ids, "decision": "accept", "reason": "batch accept"},
        )

        self.assertTrue(batch["ok"])
        self.assertEqual(batch["schema"], "pska.review_decide_batch.v1")
        self.assertEqual(batch["decided_count"], 2)
        self.assertEqual(batch["skipped_count"], 0)
        pending = self._get_json("/api/reviews?status=pending")
        self.assertFalse([review for review in pending["reviews"] if review["review_id"] in review_ids])
        queue = self._get_json("/api/memory/review-queue?review_limit=20&health_limit=10&focus_limit=10")
        groups = {group["code"]: group for group in queue["groups"]}
        self.assertIn("accepted_unapplied", groups)
        self.assertEqual(set(groups["accepted_unapplied"]["review_ids"]), set(review_ids))
        self.assertFalse(batch["data_flow"]["writes_memory_directly"])
        audit = self._get_json("/api/audit?limit=10&action=review.decide_batch")
        self.assertEqual(audit["events"][0]["metadata"]["decided_count"], 2)

    def test_review_merge_candidates_route_creates_merged_pending_review(self):
        first = self.service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route one",
        )
        second = self.service.source_memory_review_create(
            [SourceRef(adapter="obsidian_vault", source_id="architecture-v2", path="Architecture.md")],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route two",
        )
        review_ids = [first["review"]["review_id"], second["review"]["review_id"]]

        merged = self._post_json(
            "/api/reviews/merge-candidates",
            {
                "review_ids": review_ids,
                "reason": "merge duplicate route candidates",
                "memory_candidate": {
                    "text": "When this workspace asks about PSKA architecture, inspect Architecture.md first.",
                    "memory_type": "source_route",
                    "memory_scope": "project",
                    "behavior_delta": "Route future PSKA architecture questions to Architecture.md before broad search.",
                },
            },
        )

        self.assertTrue(merged["ok"])
        self.assertEqual(merged["schema"], "pska.review_merge_candidates.v1")
        self.assertEqual(merged["review"]["status"], "pending")
        self.assertEqual(merged["review"]["revision"]["merged_from_review_ids"], review_ids)
        self.assertEqual(merged["proposal"]["memory_patch"]["metadata"]["merged_review_ids"], review_ids)
        self.assertFalse(merged["data_flow"]["writes_memory_directly"])
        old_review = self._get_json(f"/api/reviews/{review_ids[0]}")["review"]
        self.assertEqual(old_review["status"], "needs_edit")
        self.assertEqual(old_review["revision"]["merged_into_review_id"], merged["review"]["review_id"])
        self.assertEqual(self._get_json(f"/api/reviews/{review_ids[1]}")["review"]["status"], "needs_edit")
        audit = self._get_json("/api/audit?limit=10&action=review.merge_candidates")
        self.assertEqual(audit["events"][0]["metadata"]["merged_review_id"], merged["review"]["review_id"])

    def test_memory_candidate_dedup_route_groups_near_duplicate_reviews(self):
        ref = SourceRef(adapter="obsidian_vault", source_id="architecture", path="Architecture.md")
        first = self.service.source_memory_review_create(
            [ref],
            text="When this workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route future PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route one",
        )
        second = self.service.source_memory_review_create(
            [ref],
            text="When the workspace asks about PSKA architecture, inspect Architecture.md first.",
            memory_type="source_route",
            behavior_delta="Route PSKA architecture questions to Architecture.md before broad search.",
            memory_scope="project",
            reason="route two",
        )

        dedup = self._get_json("/api/memory/candidate-dedup?review_limit=20&similarity_threshold=0.8")
        queue = self._get_json("/api/memory/review-queue?review_limit=20&health_limit=10&focus_limit=10")
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertTrue(dedup["ok"])
        self.assertEqual(dedup["schema"], "pska.memory_candidate_dedup.v1")
        self.assertEqual(dedup["summary"]["group_count"], 1)
        self.assertIn("related_groups", dedup)
        self.assertEqual(
            {item["review_id"] for item in dedup["groups"][0]["items"]},
            {first["review"]["review_id"], second["review"]["review_id"]},
        )
        self.assertFalse(dedup["data_flow"]["embedding_required"])
        self.assertIn("duplicate_candidates", groups)
        self.assertEqual(queue["summary"]["duplicate_candidate_group_count"], 1)
        self.assertEqual(groups["duplicate_candidates"]["items"][0]["item_type"], "memory_candidate_duplicate_group")

    def test_memory_candidate_dedup_route_surfaces_cross_scope_related_candidates(self):
        first = self.service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-global", title="Conversation")],
            text="The user prefers concise memory review summaries.",
            memory_type="preference",
            behavior_delta="Keep memory review summaries concise.",
            memory_scope="global",
            reason="global preference candidate",
        )
        second = self.service.source_memory_review_create(
            [SourceRef(adapter="conversation", source_id="msg-project", title="Conversation")],
            text="For PSKA, the user prefers concise memory review summaries.",
            memory_type="preference",
            behavior_delta="Keep PSKA memory review summaries concise.",
            memory_scope="project",
            reason="project preference candidate",
        )

        dedup = self._get_json("/api/memory/candidate-dedup?review_limit=20&related_threshold=0.7")
        queue = self._get_json("/api/memory/review-queue?review_limit=20&health_limit=10&focus_limit=10")
        groups = {group["code"]: group for group in queue["groups"]}

        self.assertEqual(dedup["summary"]["group_count"], 0)
        self.assertEqual(dedup["summary"]["related_group_count"], 1)
        self.assertEqual(dedup["summary"]["scope_collision_group_count"], 1)
        self.assertEqual(dedup["related_groups"][0]["memory_scopes"], ["global", "project"])
        self.assertEqual(
            {item["review_id"] for item in dedup["related_groups"][0]["items"]},
            {first["review"]["review_id"], second["review"]["review_id"]},
        )
        self.assertEqual(queue["summary"]["related_candidate_group_count"], 1)
        self.assertIn("related_candidates", groups)
        self.assertEqual(groups["related_candidates"]["items"][0]["item_type"], "memory_candidate_related_group")

    def test_eidolia_context_and_memory_review_routes_create_sourced_candidate(self):
        context = self._post_json(
            "/api/eidolia/context/read",
            {
                "project_id": "novel-x",
                "node_id": "thought-1",
                "node_type": "thought",
                "text": "PSKA should keep Eidolia thought and artifact nodes as canvas primitives.",
                "title": "Canvas primitives",
                "canvas_path": "boards/novel-x.canvas",
                "role": "decision",
            },
        )
        created = self._post_json(
            "/api/eidolia/memory-reviews",
            {
                "project_id": "novel-x",
                "node_id": "thought-1",
                "node_type": "thought",
                "text": "Eidolia keeps thought and artifact as its only user-visible node types.",
                "behavior_delta": "When discussing Eidolia architecture, keep thought/artifact as the canvas primitives.",
                "title": "Canvas primitives",
                "canvas_path": "boards/novel-x.canvas",
                "role": "decision",
                "memory_type": "project_state",
                "memory_scope": "project",
                "reason": "stable Eidolia ontology decision",
            },
        )

        self.assertTrue(context["ok"])
        self.assertEqual(context["context"]["schema"], "pska.eidolia_context.v1")
        self.assertEqual(context["context"]["source_ref"]["adapter"], "eidolia")
        self.assertEqual(context["context"]["source_ref"]["metadata"]["role"], "decision")
        self.assertTrue(created["ok"])
        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertIsNone(created["memory_apply"])
        self.assertEqual(created["memory_card"]["source_origin"], "eidolia")
        self.assertEqual(created["memory_card"]["source_refs"][0]["metadata"]["node_type"], "thought")
        self.assertFalse(created["governance"]["writes_memory_directly"])
        trace = self._get_json(f"/api/trace/query?review_id={created['review']['review_id']}&limit=20")
        self.assertTrue(trace["ok"])
        self.assertEqual(trace["schema"], "pska.trace_query.v1")
        self.assertEqual(trace["status"], "found")
        self.assertGreaterEqual(trace["summary"]["review_count"], 1)
        self.assertFalse(trace["data_flow"]["writes_memory_directly"])
        actions = {event.action for event in self.service.store.list_audit_events(limit=40)}
        self.assertIn("eidolia.context.read", actions)
        self.assertIn("eidolia.memory_review.create", actions)

    def test_eidolia_project_trace_import_route_reads_project_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "novel-x"
            trace_dir = project_dir / "agentic-traces"
            trace_dir.mkdir(parents=True)
            (project_dir / "canvas-workspace.json").write_text(
                json.dumps(
                    {
                        "projectId": "novel-x",
                        "nodes": [
                            {
                                "id": "thought-1",
                                "type": "thought",
                                "data": {"kind": "thought", "title": "Decision", "content": "Trace imports are read-only."},
                            }
                        ],
                        "edges": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (trace_dir / "trace-1.json").write_text(
                json.dumps(
                    {
                        "kind": "thought_candidate",
                        "run_id": "trace-1",
                        "project_id": "novel-x",
                        "start_node_id": "thought-1",
                        "content": "Imported trace should point back to thought-1.",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            imported = self._post_json(
                "/api/eidolia/project-traces/import",
                {"project_path": str(project_dir), "node_limit": 10, "trace_limit": 10},
            )

        self.assertTrue(imported["ok"])
        self.assertEqual(imported["schema"], "pska.eidolia_project_trace_import.v1")
        self.assertEqual(imported["summary"]["imported_node_count"], 1)
        self.assertEqual(imported["summary"]["imported_trace_count"], 1)
        self.assertFalse(imported["data_flow"]["writes_source_files"])
        trace_ref = quote(json.dumps(imported["nodes"][0]["source_ref"]))
        queried = self._get_json(f"/api/trace/query?source_ref={trace_ref}&limit=10")
        self.assertTrue(queried["ok"])
        self.assertEqual(queried["status"], "found")
        actions = {event.action for event in self.service.store.list_audit_events(limit=20)}
        self.assertIn("eidolia.project_trace.import", actions)
        self.assertIn("eidolia.node.import", actions)
        self.assertIn("eidolia.agentic_trace.import", actions)

    def test_memory_health_route_reports_quality_stale_and_conflict(self):
        self.service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="mem-raw",
                    text="Raw memory missing envelope fields.",
                    metadata={},
                ),
                MemoryFact(
                    fact_id="mem-linux",
                    text="The project deployment target is Linux.",
                    source_refs=[SourceRef(adapter="fake", source_id="linux")],
                    metadata={
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "Use Linux as deployment target.",
                        "display_text": "The project deployment target is Linux.",
                    },
                ),
                MemoryFact(
                    fact_id="mem-windows",
                    text="The project deployment target is Windows.",
                    source_refs=[SourceRef(adapter="fake", source_id="windows")],
                    metadata={
                        "memory_type": "project_state",
                        "memory_scope": "project",
                        "behavior_delta": "Use Windows as deployment target.",
                        "display_text": "The project deployment target is Windows.",
                        "refresh_rule": "review_after_date",
                        "review_after": "2000-01-01T00:00:00+00:00",
                    },
                ),
            ]
        )

        health = self._get_json("/api/memory/health?limit=20")

        self.assertTrue(health["ok"])
        self.assertEqual(health["schema"], "pska.memory_health.v1")
        self.assertEqual(health["summary"]["quality"], 1)
        self.assertEqual(health["summary"]["stale"], 1)
        self.assertGreaterEqual(health["summary"]["conflict"], 1)
        self.assertEqual(health["next_actions"][0]["tool"], "pska_memory_health_scan")
        audit = self._get_json("/api/audit?limit=10&action=memory.health.scan")
        self.assertEqual(audit["events"][0]["metadata"]["issue_count"], health["issue_count"])

    def test_memory_search_route_can_include_superseded_for_diagnostics(self):
        self.service.memory.facts.extend(
            [
                MemoryFact(
                    fact_id="old-editor",
                    text="The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="old-editor")],
                    metadata={"created_at": "2025-01-01T00:00:00+00:00"},
                ),
                MemoryFact(
                    fact_id="new-editor",
                    text="The user's editor is VS Code. Previous fact: The user's editor is Vim.",
                    source_refs=[SourceRef(adapter="fake", source_id="new-editor")],
                    metadata={
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "semantic_operation": "memory_update",
                        "memory_update_strategy": "append_correction_episode",
                        "target_fact_id": "old-editor",
                    },
                ),
            ]
        )

        result = self._post_json(
            "/api/memory/search",
            {
                "query": "editor",
                "scope": {"include_superseded_memory": True},
                "limit": 10,
            },
        )

        self.assertEqual([fact["fact_id"] for fact in result["memory_facts"]], ["new-editor", "old-editor"])
        audit = self._get_json("/api/audit?limit=10&action=memory.search")
        self.assertTrue(audit["events"][0]["metadata"]["include_superseded"])

    def test_digest_route_creates_digest_origin_memory_review(self):
        result = self._post_json(
            "/api/digest",
            {
                "dataset_ids": ["demo"],
                "question": "Digest the demo scope",
                "limit": 1,
                "source_inspection_limit": 0,
                "create_memory_review": True,
            },
        )

        self.assertEqual(result["kind"], "digest_scope")
        self.assertEqual(result["digest"]["kind"], "digest")
        self.assertEqual(result["memory_review"]["review"]["status"], "pending")
        self.assertEqual(result["memory_review"]["governance"]["origin"], "digest")
        audit = self._get_json("/api/audit?limit=10&action=digest.scope")
        self.assertEqual(audit["events"][0]["metadata"]["create_memory_review"], True)

    def test_digest_job_routes_queue_list_and_run_next(self):
        queued = self._post_json(
            "/api/digest-jobs",
            {
                "dataset_ids": ["demo"],
                "question": "Queue demo digest",
                "priority": 4,
                "limit": 1,
                "source_inspection_limit": 0,
                "create_memory_review": True,
            },
        )
        jobs = self._get_json("/api/digest-jobs?status=queued")
        result = self._post_json("/api/digest-jobs/run-next", {})

        self.assertEqual(queued["status"], "queued")
        self.assertEqual(jobs["digest_jobs"][0]["job"]["run_id"], queued["job"]["run_id"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["digest_result"]["memory_review"]["governance"]["origin"], "digest")
        self.assertEqual(result["digest_job"]["result_run_id"], result["digest_result"]["run"]["run_id"])
        audit = self._get_json("/api/audit?limit=10&action=digest.job.run")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "completed")

    def test_workspace_status_route_reports_next_actions(self):
        status = self._get_json("/api/workspace/status")["workspace_status"]

        self.assertEqual(status["kind"], "workspace_status")
        self.assertEqual(status["status"], "ready")
        self.assertEqual(status["kb"]["dataset_count"], 1)
        self.assertEqual(status["kb"]["readiness"]["status"], "ready")
        self.assertEqual(status["kb"]["dataset_readiness"][0]["dataset_ids"], ["demo"])
        self.assertEqual(status["reviews"]["pending_count"], 0)
        self.assertEqual(status["workflows"]["resumable_ask_count"], 0)
        self.assertEqual(status["next_actions"][0]["action"], "run_agentic_question")
        self.assertEqual(status["next_actions"][0]["tool"], "pska_agentic_question_start")
        self.assertEqual(status["next_actions"][0]["api"], "POST /api/ask")
        self.assertEqual(status["next_actions"][0]["view"], "ask")
        self.assertEqual(status["next_actions"][0]["params"]["dataset_ids"], ["demo"])

    def test_turn_context_route_assembles_evidence_and_memory_without_ask(self):
        self.service.memory.facts.append(
            MemoryFact(
                fact_id="mem-pska-mini",
                text="PSKA-mini keeps long-term memory behind governance.",
                source_refs=[SourceRef(adapter="conversation", source_id="msg-1", title="Conversation")],
                metadata={"confidence": 0.91},
            )
        )

        payload = self._post_json(
            "/api/turn-context",
            {
                "caller": "hermes-webui",
                "workspace": "eidolia",
                "project_id": "novel-x",
                "user_message": "How should PSKA-mini provide memory and evidence?",
                "mode": "project",
                "scope": {"dataset_ids": ["demo"]},
                "budget": {"max_evidence_blocks": 1, "max_memory_notes": 2},
                "requirements": {"need_citations": True},
            },
        )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["schema"], "pska.turn_context_response.v1")
        self.assertTrue(payload["run_id"].startswith("run_"))
        self.assertEqual(payload["mode"], "project")
        self.assertEqual(payload["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(payload["scope"]["workspace"], "eidolia")
        self.assertEqual(payload["scope"]["project_id"], "novel-x")
        self.assertEqual(payload["requirements"]["need_citations"], True)
        self.assertFalse(payload["requirements"]["allow_memory_write"])
        self.assertNotIn("proposal", payload)
        self.assertNotIn("review", payload)

        turn_context = payload["turn_context"]
        evidence_blocks = turn_context["evidence_blocks"]
        memory_notes = turn_context["memory_notes"]
        self.assertEqual(len(evidence_blocks), 1)
        self.assertEqual(evidence_blocks[0]["type"], "evidence")
        self.assertEqual(evidence_blocks[0]["source_ref"]["adapter"], "fake")
        self.assertEqual(len(memory_notes), 1)
        self.assertEqual(memory_notes[0]["type"], "memory")
        self.assertEqual(memory_notes[0]["fact_id"], "mem-pska-mini")
        self.assertGreaterEqual(len(turn_context["citations"]), 2)
        self.assertEqual(turn_context["warnings"], [])
        self.assertEqual(self._get_json("/api/reviews?status=pending")["reviews"], [])

    def test_workflow_open_does_not_export_until_explicit_export(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "How does PSKA govern exports?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        run_id = asked["run"]["run_id"]

        def workflow_export_count() -> int:
            audit = self._get_json("/api/audit?limit=50")
            return sum(1 for event in audit["events"] if event["action"] == "workflow.export")

        before_open = workflow_export_count()
        self.assertEqual(before_open, 0)
        opened = self._get_json(f"/api/workflows/{run_id}")
        self.assertEqual(opened["workflow"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["run"]["run_id"], run_id)
        self.assertEqual(opened["artifact"]["latest_proposal"]["kind"], "writing_brief")
        self.assertEqual(opened["artifact"]["traceability"]["context_count"], 1)
        self.assertEqual(opened["artifact"]["traceability"]["source_count"], 1)
        self.assertNotIn("export", opened["artifact"]["traceability"])
        self.assertEqual(workflow_export_count(), before_open)

        exported = self._get_json(f"/api/workflows/{run_id}/export?format=markdown")
        self.assertIn("PSKA-Essential Brief", exported["export"])
        self.assertIn("Export audit event:", exported["export"])
        self.assertEqual(workflow_export_count(), before_open + 1)
        json_exported = self._get_json(f"/api/workflows/{run_id}/export?format=json")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["action"], "workflow.export")
        self.assertEqual(json_exported["export"]["traceability"]["export"]["target_id"], run_id)
        self.assertEqual(json_exported["export"]["traceability"]["export"]["format"], "json")
        self.assertEqual(workflow_export_count(), before_open + 2)

    def test_workflow_export_requires_sourced_work_product(self):
        run = self.service.start("empty product api workflow", {"dataset_ids": ["demo"]})

        failed = self._get_json_error(f"/api/workflows/{run.run_id}/export?format=markdown")

        self.assertEqual(failed["status"], 400)
        self.assertIn("sourced work product", failed["body"]["error"]["message"])

    def test_transient_ask_does_not_create_review_by_default(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 2,
                "min_context_packets": 2,
                "retrieval_queries": ["Adapter Boundary"],
                "source_inspection_limit": 1,
                "proposal_kind": "writing_brief",
                "use_kg": True,
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertFalse(asked["loop"]["review_required"])
        self.assertTrue(asked["run"]["scope"]["use_kg"])
        self.assertEqual(len(asked["context_packets"]), 2)
        self.assertIn("graph.retrieval", [step["name"] for step in asked["loop"]["steps"]])
        retrieve_steps = [step for step in asked["loop"]["steps"] if step["name"] == "context.retrieve"]
        self.assertEqual(len(retrieve_steps), 2)
        self.assertEqual(retrieve_steps[1]["metadata"]["query"], "Adapter Boundary")
        self.assertEqual(asked["loop"]["retrieval_query_plan"][1], "Adapter Boundary")
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["retrieval_queries"], ["Adapter Boundary"])
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["source_inspection_limit"], 1)
        source_step = next(step for step in asked["loop"]["steps"] if step["name"] == "source.inspect")
        self.assertEqual(source_step["metadata"]["inspected_count"], 1)
        self.assertEqual(asked["artifact"]["traceability"]["source_inspection_count"], 1)
        self.assertEqual(len(asked["artifact"]["source_inspections"]), 1)
        self.assertTrue(all(step["metadata"]["use_kg"] for step in retrieve_steps))
        context_audit = self._get_json("/api/audit?limit=10&action=context.retrieve")
        self.assertTrue(context_audit["events"][0]["metadata"]["use_kg"])

    def test_ask_accepts_model_context_budget(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a budgeted sourced brief",
                "dataset_ids": ["demo"],
                "limit": 5,
                "max_iterations": 1,
                "min_context_packets": 1,
                "source_inspection_limit": 2,
                "proposal_kind": "writing_brief",
                "model_context_tokens": 2048,
                "model_profile": "api-small",
            },
        )

        budget = asked["loop"]["context_budget"]
        self.assertEqual(budget["mode"], "model_context")
        self.assertEqual(budget["model_profile"], "api-small")
        self.assertEqual(budget["effective_retrieval_limit"], 1)
        self.assertEqual(budget["effective_source_inspection_limit"], 0)
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["model_context_tokens"], 2048)

    def test_transient_workflow_can_create_memory_review_later(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief before durable memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertEqual(asked["proposal"]["kind"], "writing_brief")

        created = self._post_json(
            f"/api/workflows/{asked['run']['run_id']}/memory-review",
            {"intent": "Remember the sourced workflow boundary"},
        )

        self.assertEqual(created["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["proposal"]["run_id"], asked["run"]["run_id"])
        self.assertLessEqual(len(created["proposal"]["memory_patch"]["text"]), 1600)
        self.assertIn("Evidence source count:", created["proposal"]["memory_patch"]["text"])
        self.assertEqual(created["governance"]["action"], "manual_review")
        self.assertEqual(created["review"]["status"], "pending")
        self.assertIsNone(created["review_decision"])
        self.assertIsNone(created["memory_apply"])
        self.assertEqual(created["review"]["proposal"]["kind"], "memory_patch")
        self.assertEqual(created["review"]["source_count"], 1)
        self.assertEqual(created["artifact"]["latest_proposal"]["kind"], "memory_patch")
        reviews = self._get_json("/api/reviews?status=pending")
        self.assertEqual(reviews["reviews"][0]["review_id"], created["review"]["review_id"])
        audit = self._get_json("/api/audit?limit=10")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("proposal.create", actions)
        self.assertIn("review.create", actions)

    def test_needs_edit_review_can_create_revision(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a memory candidate that needs revision",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )
        review_id = asked["review"]["review_id"]
        self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "edit", "reason": "Make it shorter"})

        revised = self._post_json(f"/api/reviews/{review_id}/revision", {"intent": "Shorter durable memory"})

        self.assertEqual(revised["previous_review"]["status"], "needs_edit")
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertEqual(revised["proposal"]["kind"], "memory_patch")
        self.assertEqual(revised["proposal"]["run_id"], asked["run"]["run_id"])
        self.assertNotEqual(revised["review"]["review_id"], review_id)
        self.assertEqual(revised["review"]["source_count"], 1)
        self.assertEqual(revised["artifact"]["latest_proposal"]["proposal_id"], revised["proposal"]["proposal_id"])
        self.assertEqual(revised["previous_review"]["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(revised["review"]["revision"]["previous_review_id"], review_id)
        old_record = self._get_json(f"/api/reviews/{review_id}")["review"]
        new_record = self._get_json(f"/api/reviews/{revised['review']['review_id']}")["review"]
        self.assertEqual(old_record["revision"]["next_review_id"], revised["review"]["review_id"])
        self.assertEqual(new_record["revision"]["previous_review_id"], review_id)
        audit = self._get_json("/api/audit?limit=10&action=review.revise")
        self.assertEqual(audit["events"][0]["metadata"]["previous_review_id"], review_id)
        self.assertEqual(audit["events"][0]["metadata"]["proposal_kind"], "memory_patch")

    def test_needs_edit_review_can_create_revision_with_memory_candidate_edits(self):
        created = self._post_json(
            "/api/memory/conversation-candidates",
            {
                "session_id": "sess-api-candidate-revision",
                "messages": [
                    {
                        "message_id": "msg-api-candidate-revision",
                        "role": "user",
                        "text": "For PSKA memory, avoid vague summaries and keep behavior changes explicit.",
                    }
                ],
                "candidates": [
                    {
                        "text": "The user wants PSKA memory summaries to avoid vagueness.",
                        "memory_type": "working_habit",
                        "memory_scope": "project",
                        "behavior_delta": "When creating PSKA memory summaries, avoid vagueness.",
                        "message_ids": ["msg-api-candidate-revision"],
                    }
                ],
            },
        )
        review_id = created["created"][0]["review_id"]
        self._post_json(f"/api/reviews/{review_id}/decision", {"decision": "edit", "reason": "too vague"})

        revised = self._post_json(
            f"/api/reviews/{review_id}/revision",
            {
                "intent": "rewrite candidate",
                "memory_candidate": {
                    "text": "For PSKA memory work, keep only explicit behavior-changing summaries.",
                    "memory_type": "preference",
                    "memory_scope": "workspace",
                    "behavior_delta": "When reviewing PSKA memory candidates, ask what future behavior changes.",
                },
            },
        )

        patch = revised["proposal"]["memory_patch"]
        self.assertEqual(revised["previous_review"]["status"], "needs_edit")
        self.assertEqual(revised["review"]["status"], "pending")
        self.assertEqual(patch["text"], "For PSKA memory work, keep only explicit behavior-changing summaries.")
        self.assertEqual(patch["metadata"]["memory_type"], "preference")
        self.assertEqual(patch["metadata"]["memory_scope"], "workspace")
        self.assertEqual(
            patch["metadata"]["behavior_delta"],
            "When reviewing PSKA memory candidates, ask what future behavior changes.",
        )
        self.assertEqual(patch["metadata"]["revision_mode"], "memory_candidate")
        self.assertEqual(patch["source_refs"][0]["adapter"], "hermes")

    def test_review_revision_requires_needs_edit_status(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a memory candidate that is still pending",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "memory_patch",
            },
        )

        failed = self._post_json_error(
            f"/api/reviews/{asked['review']['review_id']}/revision",
            {"intent": "not ready"},
        )

        self.assertEqual(failed["status"], 400)
        self.assertIn("needs_edit", failed["body"]["error"]["message"])

    def test_memory_review_from_workflow_honors_auto_apply_policy(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief before automatic durable memory",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        with patch.dict(os.environ, {"PSKA_GOVERNANCE_DURABLE_MEMORY": "auto_apply"}, clear=False):
            created = self._post_json(
                f"/api/workflows/{asked['run']['run_id']}/memory-review",
                {"intent": "Remember this source-backed claim automatically"},
            )

        self.assertEqual(created["governance"]["action"], "auto_apply")
        self.assertEqual(created["review"]["status"], "accepted")
        self.assertEqual(created["review_decision"]["status"], "accepted")
        self.assertTrue(created["memory_apply"]["applied"])
        self.assertEqual(created["review"]["memory_apply"]["target_id"], created["memory_apply"]["target_id"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("review.decide", actions)
        self.assertIn("memory.apply", actions)

    def test_ask_blocks_when_retrieved_context_is_below_minimum(self):
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "max_iterations": 1,
                "min_context_packets": 2,
                "proposal_kind": "memory_patch",
            },
        )

        self.assertEqual(asked["status"], "insufficient_context")
        self.assertEqual(len(asked["context_packets"]), 1)
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertIn("2 required", asked["message"])
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("agentic_loop.insufficient_context", actions)
        self.assertNotIn("workflow.export", actions)

    def test_readiness_route_reports_scope_status(self):
        payload = self._post_json("/api/kb/readiness", {"dataset_ids": ["demo"]})
        readiness = payload["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["status"], "ready")
        self.assertEqual(payload["ingestion_status"]["status"], "ready")
        self.assertEqual(payload["ingestion_status"]["next_actions"], ["run_ask"])

    def test_product_api_required_lists_trim_and_reject_blank_values(self):
        asked = self._post_json(
            "/api/ask",
            {"question": "Normalize this scope", "dataset_ids": [" demo ", "demo", "  "], "limit": 1},
        )
        self.assertEqual(asked["status"], "ready")
        self.assertEqual(asked["run"]["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(asked["run"]["metadata"]["ask_request"]["dataset_ids"], ["demo"])

        for path, payload, field in [
            ("/api/ask", {"question": "No real scope", "dataset_ids": ["  "]}, "dataset_ids"),
            ("/api/kb/readiness", {"dataset_ids": ["", "  "]}, "dataset_ids"),
            ("/api/kb/datasets/demo/parse", {"document_ids": ["  "]}, "document_ids"),
            ("/api/kb/ingest", {"dataset_name": "Blank Files", "file_paths": ["  "]}, "file_paths"),
        ]:
            with self.subTest(path=path):
                failed = self._post_json_error(path, payload)
                self.assertEqual(failed["status"], 400)
                self.assertIn(f"{field} must be a non-empty list", failed["body"]["error"]["message"])

    def test_dataset_readiness_route_reports_scope_status(self):
        payload = self._get_json("/api/kb/datasets/demo/readiness")
        readiness = payload["readiness"]

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["dataset_ids"], ["demo"])
        self.assertEqual(payload["ingestion_status"]["phase"], "ready")

    def test_ingestion_status_route_reports_normalized_job_status(self):
        self.gateway.ready = False

        payload = self._get_json("/api/kb/datasets/demo/ingestion-status")

        self.assertEqual(payload["readiness"]["status"], "processing")
        self.assertEqual(payload["ingestion_status"]["kind"], "kb_ingestion_status")
        self.assertEqual(payload["ingestion_status"]["status"], "processing")
        self.assertEqual(payload["ingestion_status"]["progress"], 0.1)
        self.assertEqual(payload["ingestion_status"]["next_actions"], ["wait_for_ingestion"])

    def test_provider_jobs_route_reports_workspace_job_inventory(self):
        self.gateway.ready = False

        payload = self._get_json("/api/provider/jobs?include_ready=false")
        jobs = payload["provider_jobs"]

        self.assertTrue(payload["ok"])
        self.assertEqual(jobs["schema"], "pska.provider_jobs.v1")
        self.assertEqual(jobs["status"], "processing")
        self.assertEqual(jobs["summary"]["processing"], 2)
        self.assertEqual(jobs["jobs"][0]["kind"], "kb_dataset_ingestion")
        self.assertEqual(jobs["jobs"][0]["next_actions"], ["wait_for_ingestion"])

    def test_parse_documents_route_uses_product_api_boundary(self):
        parsed = self._post_json(
            "/api/kb/datasets/demo/parse",
            {"document_ids": ["doc-1"], "wait": False},
        )

        self.assertTrue(parsed["parse"]["parse_started"])
        self.assertEqual(parsed["ingestion_status"]["status"], "ready")
        self.assertEqual(
            self.gateway.parse_calls,
            [{"dataset_id": "demo", "document_ids": ["doc-1"], "priority": 0, "wait": False}],
        )
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.parse")
        self.assertEqual(audit["events"][0]["metadata"]["document_ids"], ["doc-1"])

    def test_document_graph_route_uses_product_api_boundary(self):
        graph = self._get_json("/api/kb/datasets/demo/documents/doc-1/graph")

        self.assertEqual(graph["graph"]["dataset_id"], "demo")
        self.assertEqual(graph["graph"]["document_id"], "doc-1")
        self.assertEqual(len(graph["graph"]["templates"]), 1)
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.graph.read")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_id"], "demo")
        self.assertEqual(audit["events"][0]["metadata"]["document_id"], "doc-1")

    def test_runtime_diagnostics_route_reports_product_checks(self):
        payload = self._get_json("/api/runtime/diagnostics")

        self.assertTrue(payload["ok"])
        diagnostics = payload["diagnostics"]
        self.assertEqual(diagnostics["status"], "warning")
        self.assertEqual(diagnostics["workspace"]["workspace_id"], "default")
        checks = {item["name"]: item for item in diagnostics["checks"]}
        self.assertEqual(checks["product_api"]["status"], "ok")
        self.assertEqual(checks["review_store"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["status"], "ok")
        self.assertEqual(checks["kb_gateway"]["metadata"]["dataset_sample_count"], 1)
        self.assertEqual(checks["retrieval_provider"]["metadata"]["provider"], "fake")
        self.assertEqual(checks["memory_provider"]["metadata"]["provider"], "fake")
        self.assertEqual(checks["memory_search_contract"]["metadata"]["provider"], "fake")
        self.assertFalse(checks["memory_search_contract"]["metadata"]["semantic_checked"])

    def test_retrieval_probe_route_checks_ready_scope_and_writes_audit(self):
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "How does PSKA retrieve?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["provider"], "fake")
        self.assertEqual(probe["readiness"]["status"], "ready")
        self.assertEqual(probe["context_count"], 1)
        self.assertEqual(probe["scope"]["dataset_ids"], ["demo"])
        audit = self._get_json("/api/audit?limit=5&action=retrieval.probe")
        self.assertEqual(audit["events"][0]["action"], "retrieval.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")
        self.assertEqual(audit["events"][0]["metadata"]["context_count"], 1)

    def test_retrieval_probe_route_resolves_dataset_names(self):
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "How does PSKA retrieve?", "dataset_names": ["Demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(probe["scope"]["resolved_dataset_names"], [{"name": "Demo", "dataset_id": "demo"}])

    def test_retrieval_probe_does_not_retrieve_unready_scope(self):
        self.gateway.ready = False
        probe = self._post_json(
            "/api/runtime/retrieval-probe",
            {"question": "Can this retrieve?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "not_ready")
        self.assertEqual(probe["context_count"], 0)
        self.assertEqual(probe["readiness"]["status"], "processing")
        self.assertIn("not ready", probe["message"])

    def test_memory_probe_route_rejects_fake_as_live_proof_and_can_run_dev_probe(self):
        blocked = self._post_json("/api/runtime/memory-probe", {"query": "memory", "limit": 1})["probe"]

        self.assertEqual(blocked["status"], "invalid_configuration")
        self.assertEqual(blocked["provider"], "fake")

        dev_probe = self._post_json(
            "/api/runtime/memory-probe",
            {"query": "memory", "limit": 1, "require_live": False},
        )["probe"]

        self.assertEqual(dev_probe["status"], "ok")
        self.assertEqual(dev_probe["provider"], "fake")
        audit = self._get_json("/api/audit?limit=5&action=memory.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

    def test_component_check_route_runs_structured_acceptance_check(self):
        with patch.dict(os.environ, {"PSKA_DEV_FAKE": "1"}, clear=False):
            result = self._post_json(
                "/api/runtime/component-check",
                {
                    "question": "Can the configured components answer?",
                    "dataset_names": ["Demo"],
                    "require_memory": False,
                    "run_closed_loop": False,
                },
            )["component_check"]

        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["scope"]["dataset_ids"], ["demo"])
        self.assertEqual(result["retrieval_probe"]["status"], "ok")
        self.assertIsNone(result["closed_loop_probe"])
        audit = self._get_json("/api/audit?limit=5&action=retrieval.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

    def test_closed_loop_probe_rejects_fake_retrieval_as_product_proof(self):
        probe = self._post_json(
            "/api/runtime/closed-loop-probe",
            {"question": "Can this prove the live loop?", "dataset_ids": ["demo"], "limit": 1},
        )["probe"]

        self.assertEqual(probe["status"], "invalid_configuration")
        self.assertEqual(probe["providers"]["retrieval"], "fake")
        self.assertEqual(probe["context_count"], 0)
        audit = self._get_json("/api/audit?limit=5&action=closed_loop.probe")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "invalid_configuration")
        self.assertFalse(audit["events"][0]["metadata"]["exported"])

    def test_ask_blocks_dataset_that_is_not_ready(self):
        self.gateway.ready = False
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Can this be answered yet?",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "not_ready")
        self.assertIsNotNone(asked["run"])
        self.assertEqual(asked["run"]["status"], "blocked")
        self.assertEqual(asked["run"]["metadata"]["agentic_loop"]["status"], "not_ready")
        self.assertEqual(asked["artifact"]["traceability"]["context_count"], 0)
        self.assertEqual(asked["artifact"]["traceability"]["proposal_count"], 0)
        self.assertIsNone(asked["artifact"]["latest_proposal"])
        self.assertEqual(asked["context_packets"], [])
        self.assertIsNone(asked["proposal"])
        self.assertIsNone(asked["review"])
        self.assertEqual(asked["readiness"]["status"], "processing")
        self.assertEqual(asked["loop"]["steps"][-1]["name"], "kb.readiness")
        workflows = self._get_json("/api/workflows?limit=5")
        self.assertEqual(workflows["workflows"][0]["run_id"], asked["run"]["run_id"])
        opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(opened["workflow"]["status"], "blocked")
        self.assertEqual(opened["artifact"]["run"]["metadata"]["readiness"]["status"], "processing")
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("agentic_loop.not_ready", actions)
        self.assertIn("kb.readiness.blocked", actions)
        blocked_event = next(event for event in audit["events"] if event["action"] == "kb.readiness.blocked")
        self.assertEqual(blocked_event["target_type"], "workflow")
        self.assertEqual(blocked_event["target_id"], asked["run"]["run_id"])
        waiting = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(waiting["resumable_asks"][0]["run"]["run_id"], asked["run"]["run_id"])
        self.assertFalse(waiting["resumable_asks"][0]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["readiness"]["status"], "processing")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["tool"], "pska_agentic_question_resume")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["api"], f"POST /api/workflows/{asked['run']['run_id']}/resume-ask")
        self.assertFalse(waiting["resumable_asks"][0]["resume"]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["next_actions"][-1]["action"], "resume_blocked_ask")

        self.gateway.ready = True
        ready_to_resume = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(ready_to_resume["resumable_asks"][0]["run"]["run_id"], asked["run"]["run_id"])
        self.assertTrue(ready_to_resume["resumable_asks"][0]["can_resume"])
        self.assertTrue(ready_to_resume["resumable_asks"][0]["resume"]["can_resume"])
        self.assertEqual(ready_to_resume["resumable_asks"][0]["ask_request"]["question"], "Can this be answered yet?")
        resumed = self._post_json(f"/api/workflows/{asked['run']['run_id']}/resume-ask", {})

        self.assertEqual(resumed["status"], "ready")
        self.assertNotEqual(resumed["run"]["run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["run"]["metadata"]["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["question"], "Can this be answered yet?")
        self.assertEqual(resumed["run"]["metadata"]["ask_request"]["dataset_ids"], ["demo"])
        self.assertEqual(resumed["run"]["metadata"]["agentic_loop"]["resumed_from_run_id"], asked["run"]["run_id"])
        self.assertEqual(resumed["artifact"]["traceability"]["context_count"], 1)
        old_opened = self._get_json(f"/api/workflows/{asked['run']['run_id']}")
        self.assertEqual(old_opened["workflow"]["status"], "blocked")
        resume_audit = self._get_json("/api/audit?limit=20&action=agentic_loop.resume")
        self.assertEqual(resume_audit["events"][0]["target_id"], resumed["run"]["run_id"])
        self.assertEqual(resume_audit["events"][0]["metadata"]["resumed_from_run_id"], asked["run"]["run_id"])
        retry_ready = self._post_json_error(f"/api/workflows/{resumed['run']['run_id']}/resume-ask", {})
        self.assertEqual(retry_ready["status"], 400)
        self.assertIn("only readiness-blocked", retry_ready["body"]["error"]["message"])

    def test_multipart_ingest_uses_product_api_boundary(self):
        boundary = "pska-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="dataset_name"\r\n\r\n'
            "Uploaded KB\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="embedding_model"\r\n\r\n'
            "text-embedding-3-small@OpenAI\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="note.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
            "trusted workspace notes\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/kb/ingest",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertTrue(payload["ok"])
        self.assertEqual(self.gateway.uploaded, [{"name": "note.txt", "text": "trusted workspace notes"}])
        self.assertEqual(self.gateway.last_ingest["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(payload["ingest"]["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(payload["ingestion_status"]["status"], "ready")
        self.assertEqual(payload["readiness"]["datasets"][0]["documents"][0]["next_action"], "available_for_retrieval")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.ingest")
        self.assertEqual(audit["events"][0]["metadata"]["document_names"], ["note.txt"])
        self.assertTrue(audit["events"][0]["metadata"]["parse_started"])

    def test_dataset_create_writes_kb_audit_record(self):
        created = self._post_json(
            "/api/kb/datasets",
            {
                "name": "New Dataset",
                "description": "notes",
                "chunk_method": "naive",
                "embedding_model": "text-embedding-3-small@OpenAI",
            },
        )

        self.assertEqual(created["dataset"]["dataset_id"], "created")
        self.assertEqual(created["dataset"]["embedding_model"], "text-embedding-3-small@OpenAI")
        self.assertEqual(self.gateway.last_created["embedding_model"], "text-embedding-3-small@OpenAI")
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.create")
        self.assertEqual(audit["events"][0]["target_id"], "created")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_name"], "New Dataset")

    def test_dataset_delete_writes_kb_audit_record(self):
        deleted = self._delete_json("/api/kb/datasets/demo")

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertEqual(deleted["delete"]["dataset_ids"], ["demo"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "demo")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_ids"], ["demo"])

    def test_dataset_delete_all_writes_kb_audit_record(self):
        self.gateway.extra_datasets["scratch"] = {
            "backend": "fake-kb",
            "dataset_id": "scratch",
            "name": "Scratch",
            "document_count": 0,
            "chunk_count": 0,
        }

        deleted = self._delete_json("/api/kb/datasets", {"delete_all": True})

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertTrue(deleted["delete"]["delete_all"])
        self.assertEqual(deleted["delete"]["dataset_ids"], [])
        self.assertEqual(deleted["delete"]["deleted_dataset_ids"], ["scratch"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "scratch")
        self.assertTrue(audit["events"][0]["metadata"]["delete_all"])

    def test_dataset_delete_by_name_writes_kb_audit_record(self):
        self.gateway.extra_datasets["bad"] = {
            "backend": "fake-kb",
            "dataset_id": "bad",
            "name": "Bad Dataset",
            "document_count": 0,
            "chunk_count": 0,
        }

        deleted = self._delete_json("/api/kb/datasets", {"dataset_names": ["Bad Dataset"]})

        self.assertTrue(deleted["delete"]["deleted"])
        self.assertEqual(deleted["delete"]["dataset_names"], ["Bad Dataset"])
        self.assertEqual(deleted["delete"]["dataset_ids"], ["bad"])
        self.assertEqual(deleted["delete"]["deleted_dataset_ids"], ["bad"])
        audit = self._get_json("/api/audit?limit=5")
        self.assertEqual(audit["events"][0]["action"], "kb.dataset.delete")
        self.assertEqual(audit["events"][0]["target_id"], "bad")
        self.assertEqual(audit["events"][0]["metadata"]["dataset_names"], ["Bad Dataset"])

    def test_audit_route_filters_by_action(self):
        self._post_json(
            "/api/kb/datasets",
            {"name": "Filtered Dataset", "description": "", "chunk_method": "naive"},
        )
        asked = self._post_json(
            "/api/ask",
            {
                "question": "Create a sourced brief",
                "dataset_ids": ["demo"],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )
        self._get_json(f"/api/workflows/{asked['run']['run_id']}/export?format=markdown")

        filtered = self._get_json("/api/audit?limit=20&action=workflow.export")

        self.assertTrue(filtered["events"])
        self.assertEqual({event["action"] for event in filtered["events"]}, {"workflow.export"})

    def test_bundled_frontend_contains_reader_view(self):
        html = Path("src/pska_essential/web/index.html").read_text(encoding="utf-8")
        script = Path("src/pska_essential/web/app.js").read_text(encoding="utf-8")
        styles = Path("src/pska_essential/web/styles.css").read_text(encoding="utf-8")
        self.assertIn("来源阅读器", html)
        self.assertIn("ingestion-status", html)
        self.assertIn("ingestion-actions", html)
        self.assertIn("parse-documents", html)
        self.assertIn("audit-action-filter", html)
        self.assertIn("source.read", html)
        self.assertIn("review-status-filter", html)
        self.assertIn("记忆维护队列", html)
        self.assertIn("memory-review-queue-summary", html)
        self.assertIn("reload-memory-review-queue", html)
        self.assertIn("memory.search", html)
        self.assertIn("needs_edit", html)
        self.assertIn("review.revise", html)
        self.assertIn("button.revise", script)
        self.assertIn("ask-dataset-picker", html)
        self.assertIn("ask-document-picker", html)
        self.assertIn("ask-add-dataset", html)
        self.assertIn("ask-load-documents", html)
        self.assertIn("ask-check-readiness", html)
        self.assertIn("ask-readiness-status", html)
        self.assertIn("ask-readiness-actions", html)
        self.assertIn("max_iterations", html)
        self.assertIn("min_context_packets", html)
        self.assertIn("retrieval_queries", html)
        self.assertIn("补充检索问题", html)
        self.assertIn("source_inspection_limit", html)
        self.assertIn("来源检查", html)
        self.assertIn("use_kg", html)
        self.assertIn('data-view="sources"', html)
        self.assertIn('id="sources"', html)
        self.assertIn("资料源", html)
        self.assertIn("source-root-form", html)
        self.assertIn("source-root-filter", html)
        self.assertIn("source-search-form", html)
        self.assertIn("source-search-root", html)
        self.assertIn("source-saved-search-form", html)
        self.assertIn("source-save-root", html)
        self.assertIn("source-annotation-form", html)
        self.assertIn("source-selection-card", html)
        self.assertIn("source-tag-status", html)
        self.assertIn("source-comment-status", html)
        self.assertIn("source-audit-summary", html)
        self.assertIn("source-audit-actions", html)
        self.assertIn("source-audit-details", html)
        self.assertIn("记忆简报", html)
        self.assertIn("memory-briefing-summary", html)
        self.assertIn("reload-memory-briefing", html)
        self.assertIn("时间线与使用痕迹", html)
        self.assertIn("load-memory-timeline", html)
        self.assertIn("run-source-extraction-job", html)
        self.assertIn("队列抽取", script)
        self.assertIn('/api/sources/roots', script)
        self.assertIn('/api/sources/roots/${encodeURIComponent(normalized)}/scan', script)
        self.assertIn('/api/sources/search', script)
        self.assertIn('/api/sources/audits/run', script)
        self.assertIn('/api/sources/extraction-jobs', script)
        self.assertIn('/api/sources/extraction-jobs/run-next', script)
        self.assertIn('/api/sources/extraction-jobs/${encodeURIComponent(runId)}/run', script)
        self.assertIn('/api/sources/audit-jobs/tick', script)
        self.assertIn('/api/sources/audit-jobs/run-next', script)
        self.assertIn('/api/sources/audit-jobs/${encodeURIComponent(runId)}/run', script)
        self.assertIn('/api/sources/saved-searches', script)
        self.assertIn('/api/sources/tags/proposals', script)
        self.assertIn('/api/sources/tags/${encodeURIComponent(proposalId)}/apply', script)
        self.assertIn('/api/sources/comments/proposals', script)
        self.assertIn('/api/sources/comments/${encodeURIComponent(proposalId)}/apply', script)
        self.assertIn('/api/sources/obsidian/moc/proposals', script)
        self.assertIn('/api/sources/memory-reviews', script)
        self.assertIn('/api/memory/briefing?card_limit=30&health_limit=20&trace_limit=30', script)
        self.assertIn('/api/memory/review-queue?review_limit=50&health_limit=20&focus_limit=20', script)
        self.assertIn("对话候选", script)
        self.assertIn('/api/memory/${encodeURIComponent(selected)}/timeline?limit=50', script)
        self.assertIn("function loadSourceRoots", script)
        self.assertIn("function renderSources", script)
        self.assertIn("async function loadMemoryBriefing", script)
        self.assertIn("function memoryBriefingItemCard", script)
        self.assertIn("async function loadMemoryReviewQueue", script)
        self.assertIn("function memoryReviewQueueGroupCard", script)
        self.assertIn("async function runMemoryReviewQueueAction", script)
        self.assertIn("async function openMemoryTimeline", script)
        self.assertIn("function memoryTimelineCard", script)
        self.assertIn("pska.memory_timeline.v1", script)
        self.assertIn("button.timeline", script)
        self.assertIn("function runSourceAudit", script)
        self.assertIn("async function runSourceAuditJob", script)
        self.assertIn("async function enqueueSourceExtractionJob", script)
        self.assertIn("async function runSourceExtractionJob", script)
        self.assertIn("async function tickSourceAuditJobs", script)
        self.assertIn("async function searchSources", script)
        self.assertIn("async function saveSourceSearch", script)
        self.assertIn("async function handleSourceAnnotation", script)
        self.assertIn("async function proposeSourceTag", script)
        self.assertIn("async function applySourceTag", script)
        self.assertIn("async function proposeSourceComment", script)
        self.assertIn("async function applySourceComment", script)
        self.assertIn("async function proposeObsidianMoc", script)
        self.assertIn("function selectSourceForAnnotation", script)
        self.assertIn("async function scanSourceRoot", script)
        self.assertIn("async function createSourceMemoryReview", script)
        self.assertIn('action.action === "scan_source_root"', script)
        self.assertIn('action.action === "propose_obsidian_moc"', script)
        self.assertIn('action.action === "review_duplicates" || action.action === "inspect_unresolved_links"', script)
        self.assertIn('openView("sources");', script)
        self.assertIn('<option value="source.scan">source.scan</option>', html)
        self.assertIn('<option value="source.audit.run">source.audit.run</option>', html)
        self.assertIn('<option value="source.audit_job.enqueue">source.audit_job.enqueue</option>', html)
        self.assertIn('<option value="source.audit_job.due">source.audit_job.due</option>', html)
        self.assertIn('<option value="source.audit_job.run">source.audit_job.run</option>', html)
        self.assertIn('<option value="source.saved_search.create">source.saved_search.create</option>', html)
        self.assertIn('<option value="source.tag.propose">source.tag.propose</option>', html)
        self.assertIn('<option value="source.tag.apply">source.tag.apply</option>', html)
        self.assertIn('<option value="source.comment.propose">source.comment.propose</option>', html)
        self.assertIn('<option value="source.comment.apply">source.comment.apply</option>', html)
        self.assertIn('<option value="source.obsidian_moc.propose">source.obsidian_moc.propose</option>', html)
        self.assertIn('<option value="source.obsidian_moc.apply">source.obsidian_moc.apply</option>', html)
        self.assertIn('<option value="source.memory_review.create">source.memory_review.create</option>', html)
        self.assertIn('data-view="reader"', html)
        self.assertIn('data-view="writing"', html)
        self.assertIn('data-view="activity"', html)
        self.assertIn("写作工作区", html)
        self.assertIn("runtime-diagnostics", html)
        self.assertIn("工作区策略", html)
        self.assertIn("policy-settings", html)
        self.assertIn("component-check-result", html)
        self.assertIn("run-component-check", html)
        self.assertIn("product-eval-result", html)
        self.assertIn("run-product-eval", html)
        self.assertIn("产品验收", html)
        self.assertIn('<option value="eval.run">eval.run</option>', html)
        self.assertIn("retrieval-probe-result", html)
        self.assertIn("run-retrieval-probe", html)
        self.assertIn("memory-probe-result", html)
        self.assertIn("run-memory-probe", html)
        self.assertIn('data-view="memory"', html)
        self.assertIn("memory-cards-list", html)
        self.assertIn("memory-card-search-form", html)
        self.assertIn("memory-card-status-filter", html)
        self.assertIn("reload-memory-cards", html)
        self.assertIn("memory-health-list", html)
        self.assertIn("memory-health-type-filter", html)
        self.assertIn("reload-memory-health", html)
        self.assertIn("heading.memoryAttribution", script)
        self.assertIn("heading.memorySuggestions", script)
        self.assertIn("closed-loop-probe-result", html)
        self.assertIn("run-closed-loop-probe", html)
        self.assertIn("probe-dataset-picker", html)
        self.assertIn("configure_embedding_provider", script)
        self.assertIn("upload-dataset-picker", html)
        self.assertIn("upload-use-dataset", html)
        self.assertIn("run-ingest-loop", html)
        self.assertIn("run_file_to_work_product_loop", script)
        self.assertIn("prepareIngestLoopForm", script)
        self.assertIn('showToast(t("toast.prepareLoop"));', script)
        self.assertIn("loop_question", html)
        self.assertIn("loop_export_format", html)
        self.assertIn("loop_retrieval_queries", html)
        self.assertIn("loop_max_iterations", html)
        self.assertIn("loop_min_context_packets", html)
        self.assertIn("loop_source_inspection_limit", html)
        self.assertIn("loop_proposal_kind", html)
        self.assertNotIn('<option value="memory_patch">memory_patch</option>', html)
        self.assertIn("loop_create_review", html)
        self.assertIn("loop_use_kg", html)
        self.assertIn("Embedding 模型", html)
        self.assertIn("embedding_model", html)
        self.assertIn("embedding_model: form.get(\"embedding_model\")", script)
        self.assertIn('payload.append("embedding_model", form.get("embedding_model") || "");', script)
        self.assertIn("deleteDataset(dataset.dataset_id)", script)
        self.assertIn("delete-all-datasets", html)
        self.assertIn("deleteAllDatasets", script)
        self.assertIn("delete_all: true", script)
        self.assertIn("renderDatasetPickers", script)
        self.assertIn("/api/kb/datasets/${encodeURIComponent(datasetId)}", script)
        self.assertIn("kb.dataset.delete", script)
        self.assertIn("heading.componentCheck", script)
        self.assertIn("retrieval.probe", html)
        self.assertIn("memory.probe", html)
        self.assertIn("create-memory-review", html)
        self.assertIn("创建异常审核", html)
        self.assertIn("home-next-actions", html)
        self.assertIn("下一步", html)
        self.assertIn("home-resumable-asks", html)
        self.assertIn("loadCapabilities", script)
        self.assertIn('/api/capabilities', script)
        self.assertIn("label.capabilityContract", script)
        self.assertIn("workspaceActionButtonLabel", script)
        self.assertIn('apply_accepted_memory: t("button.apply")', script)
        self.assertIn('wait_for_resumable_ask: t("button.track")', script)
        self.assertIn('action.action === "wait_for_resumable_ask"', script)
        self.assertIn('action.action === "activate_due_source_audit_jobs"', script)
        self.assertIn("openBlockedAskRun", script)
        self.assertIn("askResultFromResumableRecord", script)
        self.assertIn("button.openAsk", script)
        self.assertIn('inspect_unsupported_memory_operation: t("button.inspect")', script)
        self.assertIn('action.action === "inspect_unsupported_memory_operation"', script)
        self.assertIn('await applyMemory(params.review_id);', script)
        self.assertIn('await parseDatasetDocuments(datasetId, params.document_ids || []);', script)
        self.assertIn('await checkAskReadiness({ silent: true });', script)
        self.assertIn("memoryCapabilities", script)
        self.assertIn("memoryOperationSupported", script)
        self.assertIn("capability.supported === true", script)
        self.assertIn("能力契约尚未加载。", script)
        self.assertIn("memoryOperationForProposalKind", script)
        self.assertIn("button.unsupportedUpdate", script)
        self.assertIn("button.unsupportedMemoryApply", script)
        self.assertIn("capabilityLabel(memoryCaps, \"update\")", script)
        self.assertIn("label.workspace", script)
        self.assertIn("label.tenant", script)
        self.assertIn("label.memoryNamespace", script)
        self.assertIn("max_iterations", script)
        self.assertIn("min_context_packets", script)
        self.assertIn("retrieval_queries: splitLines", script)
        self.assertIn("function splitLines", script)
        self.assertIn("source_inspection_limit", script)
        self.assertIn("use_kg", script)
        self.assertIn('/api/sources/read', script)
        self.assertIn('/api/audit?limit=50', script)
        self.assertIn('state.auditAction', script)
        self.assertIn('action=${encodeURIComponent(state.auditAction)}', script)
        self.assertIn('auditSummary', script)
        self.assertIn('setAuditActionFilter', script)
        self.assertIn('auditActionForAskResult', script)
        self.assertIn('result.status === "not_ready"', script)
        self.assertIn('resumeAskRun', script)
        self.assertIn('resumeBlockedRun', script)
        self.assertIn('resumeIngestLoopRun', script)
        self.assertIn('resumeContractForResult', script)
        self.assertIn('resumeContractForRun', script)
        self.assertIn('isIngestLoopResume', script)
        self.assertIn('resultNextActions', script)
        self.assertIn('appendResultContractActions', script)
        self.assertIn('record.resume', script)
        self.assertIn('result.resume', script)
        self.assertIn('resume_ingest_loop: t("button.resumeLoop")', script)
        self.assertIn('track_ingestion_status: t("button.track")', script)
        self.assertIn('action.action === "resume_ingest_loop"', script)
        self.assertIn('"track_ingestion_status"', script)
        self.assertIn('params.dataset_id || (params.dataset_ids || [])[0]', script)
        self.assertIn('/resume-ingest-loop', script)
        self.assertIn('hasIngestLoopResume', script)
        self.assertIn('button.resumeLoop', script)
        self.assertIn('refreshBlockedAskReadiness', script)
        self.assertIn('button.checkReadiness', script)
        self.assertIn('startBlockedAskTracking', script)
        self.assertIn('stopBlockedAskTracking', script)
        self.assertIn('button.trackResume', script)
        self.assertIn('知识范围已就绪，正在恢复流程。', script)
        self.assertIn('知识范围已可恢复。', script)
        self.assertIn('toast.kbReadyAskUpdated', script)
        self.assertIn('/resume-ask', script)
        self.assertIn('metadata.blocked_reason === "kb_not_ready"', script)
        self.assertIn('return "agentic_loop.complete"', script)
        self.assertIn('event.action === "source.read"', script)
        self.assertIn("await loadAuditEvents(\"source.read\");\n  document.querySelector('.nav-item[data-view=\"reader\"]').click();", script)
        self.assertIn('await loadAuditEvents("kb.graph.read");', script)
        self.assertIn('await loadAuditEvents("workflow.export");', script)
        self.assertIn('exportWorkflow(result.run.run_id, "markdown", { openWriting: true })', script)
        self.assertIn('exportWorkflow(result.run.run_id, "json", { openWriting: true })', script)
        self.assertIn('async function exportWorkflow', script)
        self.assertIn('state.workflows.find((workflow) => workflow.run_id === selectedRunId)', script)
        self.assertIn('await loadAuditEvents("review.decide");', script)
        self.assertIn('await loadAuditEvents(action);', script)
        self.assertIn('/api/reviews?limit=50', script)
        self.assertIn('/api/reviews?status=pending&limit=50', script)
        self.assertIn('state.reviewStatus', script)
        self.assertIn('state.reviewView', script)
        self.assertIn('pendingReviews', script)
        self.assertIn('status=${encodeURIComponent(state.reviewStatus)}', script)
        self.assertIn('setReviewStatusFilter', script)
        self.assertIn('loadPendingReviews', script)
        self.assertIn("renderUploadDatasetPicker", script)
        self.assertIn("setUploadDatasetFromPicker", script)
        self.assertIn('showToast(t("toast.kbCreatedSelected"));', script)
        self.assertIn('setUploadDataset(payload.dataset.dataset_id);', script)
        self.assertIn('document.getElementById("upload-use-dataset").addEventListener("click", setUploadDatasetFromPicker);', script)
        self.assertIn('document.getElementById("run-ingest-loop").addEventListener("click", runIngestLoopFromUploadForm);', script)
        self.assertIn('/api/ingest-loop', script)
        self.assertIn("openLoopWorkProduct", script)
        self.assertIn("appendIngestLoopControls", script)
        self.assertIn("auditActionForIngestLoop", script)
        self.assertIn("syncReviewRecord(result.review);", script)
        self.assertIn('await loadAuditEvents(auditActionForIngestLoop(result));', script)
        self.assertIn('result.status === "not_ready" && result.run && result.run.run_id', script)
        self.assertIn('await applyAskResult(result, { toast: result.message || t("toast.ingestLoopWaiting") });', script)
        self.assertIn('payload.append("wait_ready", form.get("wait") ? "true" : "false");', script)
        self.assertIn('payload.append("retrieval_queries", form.get("loop_retrieval_queries") || "");', script)
        self.assertIn('payload.append("use_kg", form.get("loop_use_kg") ? "true" : "false");', script)
        self.assertIn('payload.append("create_review", "true");', script)
        self.assertIn('const datasetId = ingestDatasetId(result.ingest);', script)
        self.assertIn('showToast(t("toast.uploadAcceptedSelected"));', script)
        self.assertIn('renderIngestResult(result.ingest, result.readiness);\n    await loadDatasets();\n    await loadAuditEvents("kb.ingest");', script)
        self.assertIn('await loadDocuments(datasetId, { silent: true });\n  await loadWorkspaceStatus();\n  await loadAuditEvents("kb.parse");', script)
        self.assertIn('/api/runtime/diagnostics', script)
        self.assertIn('/api/runtime/component-check', script)
        self.assertIn('/api/runtime/eval', script)
        self.assertIn('runProductEval', script)
        self.assertIn('renderProductEval', script)
        self.assertIn('evalResultCard', script)
        self.assertIn('auditActionForEval', script)
        self.assertIn('return "eval.run"', script)
        self.assertIn('event.action === "eval.run"', script)
        self.assertIn('/api/workspace/status', script)
        self.assertIn('/api/jarvis/briefing', script)
        self.assertIn('function loadJarvisBriefing', script)
        self.assertIn('function renderJarvisBar', script)
        self.assertIn('id="jarvis-bar"', html)
        self.assertIn('loadWorkspaceStatus', script)
        self.assertIn('workspaceActionCard', script)
        self.assertIn('openWorkspaceAction', script)
        self.assertIn('setAskDatasetIds(params.dataset_ids || [])', script)
        self.assertIn('setUploadDataset(params.dataset_ids || [])', script)
        self.assertIn('openDatasetUpload', script)
        self.assertIn('openDatasetStatus', script)
        self.assertIn('nameField.value = "";', script)
        self.assertIn('check_provider_status', script)
        self.assertIn('check_dataset_access', script)
        self.assertIn('upload_documents', script)
        self.assertIn('await loadWorkspaceStatus();\n    await loadAuditEvents("kb.dataset.create");', script)
        self.assertIn('await loadWorkspaceStatus();\n  await loadAuditEvents("review.decide");', script)
        self.assertIn('await loadWorkspaceStatus();\n  await loadAuditEvents(action);', script)
        self.assertIn('await loadResumableAsks();\n  await loadWorkspaceStatus();', script)
        self.assertIn('/api/policy', script)
        self.assertIn('loadPolicy', script)
        self.assertIn('renderPolicy', script)
        self.assertIn('policy.actions', script)
        self.assertIn('/api/runtime/retrieval-probe', script)
        self.assertIn('/api/runtime/memory-probe', script)
        self.assertIn('/api/runtime/closed-loop-probe', script)
        self.assertIn('/memory-review', script)
        self.assertIn('setReviewStatusFilter("");\n  syncReviewRecord(payload.review);', script)
        self.assertIn('await loadAuditEvents(payload.memory_apply ? memoryApplyAction(payload.memory_apply) : "review.create");', script)
        self.assertIn("document.querySelector('.nav-item[data-view=\"review\"]').click();\n  showToast(payload.memory_apply ? memoryApplyToast(payload.memory_apply) : \"异常审核已创建。\");", script)
        self.assertIn('/revision', script)
        self.assertIn('/api/workflows/${encodeURIComponent(runId)}', script)
        self.assertIn('/documents/${encodeURIComponent(documentId)}/graph', script)
        self.assertIn('/api/workflows?limit=20', script)
        self.assertIn('/api/workflows/resumable-asks?limit=20', script)
        self.assertIn('loadResumableAsks', script)
        self.assertIn('resumableAskCard', script)
        self.assertIn('can_resume', script)
        self.assertIn('loop.review_required', script)
        self.assertIn('loop.durable_proposal', script)
        self.assertIn('container.append(loopPanel({ loop }));', script)
        self.assertIn('memoryFactCard', script)
        self.assertIn('loadMemoryCards', script)
        self.assertIn('renderMemoryCards', script)
        self.assertIn('memoryCardCard', script)
        self.assertIn('/api/memory/cards?${params.toString()}', script)
        self.assertIn('loadMemoryHealth', script)
        self.assertIn('renderMemoryHealth', script)
        self.assertIn('memoryHealthIssueCard', script)
        self.assertIn('/api/memory/health?${params.toString()}', script)
        self.assertIn('memoryAttributionPanel', script)
        self.assertIn('memorySuggestionsPanel', script)
        self.assertIn('memory_attribution', script)
        self.assertIn('memory_suggestions', script)
        self.assertIn('artifact.memory_facts', script)
        self.assertIn('sourceInspectionCard', script)
        self.assertIn('artifact.source_inspections', script)
        self.assertIn('heading.inspectedSources', script)
        self.assertIn('heading.durableMemory', script)
        self.assertIn('memory.search', script)
        self.assertIn('/parse', script)
        self.assertIn('/readiness', script)
        self.assertIn('/api/kb/readiness', script)
        self.assertIn('checkAskReadiness', script)
        self.assertIn('renderAskReadinessStatus', script)
        self.assertIn('renderAskReadinessActions', script)
        self.assertIn('handleAskReadinessAction', script)
        self.assertIn('readinessDatasetForAction', script)
        self.assertIn('productReadinessAction', script)
        self.assertIn('submitAskForm', script)
        self.assertIn('includeRunAsk: false', script)
        self.assertIn('fresh && fresh.ask_request', script)
        self.assertIn('askRequest.dataset_ids || readiness.dataset_ids || []', script)
        self.assertIn('askRequest.document_ids || readiness.document_ids || []', script)
        self.assertIn('askScopeKey', script)
        self.assertIn('toast.askScopeReady', script)
        self.assertIn('toast.askScopeNotReady', script)
        self.assertIn('empty.noAskScopeChecked', script)
        self.assertIn('button.runAsk', script)
        self.assertIn('button.parseScope', script)
        self.assertIn('button.openStatus', script)
        self.assertIn('form.requestSubmit();', script)
        self.assertIn('ingestion_status', script)
        self.assertIn('mergeReadinessDocuments', script)
        self.assertIn('renderIngestionActions', script)
        self.assertIn('button.askThisKb', script)
        self.assertIn('button.trackStatus', script)
        self.assertIn('onclick: () => askDocument(datasetId, document)', script)
        self.assertIn('function askDocument(datasetId, document)', script)
        self.assertIn('setAskDocumentIds([documentId]);', script)
        self.assertIn('showToast("文档已加入提问范围。");', script)
        self.assertIn('prepareAskScope(datasetId, documents);', script)
        self.assertIn('prepareAskScope(datasetId, displayDocuments);', script)
        self.assertIn('state.askDocumentsByDataset[normalized] = documents;', script)
        self.assertIn('next_action', script)
        self.assertIn('formatPercent', script)
        self.assertIn('diagnosticCard', script)
        self.assertIn('retrievalProbeCard', script)
        self.assertIn('closedLoopProbeCard', script)
        self.assertIn('auditEventCard', script)
        self.assertIn('source_count', script)
        self.assertIn('memory_target_id', script)
        self.assertIn('readDocumentGraph', script)
        self.assertIn('图谱已加载', script)
        self.assertIn('addAskDataset', script)
        self.assertIn('loadAskDocuments', script)
        self.assertIn('askDocumentCard', script)
        self.assertIn('setAskDatasetIds', script)
        self.assertIn('t("button.ask")', script)
        self.assertIn('t("button.upload")', script)
        self.assertIn('t("button.openStatus")', script)
        self.assertIn('askResultActions', script)
        self.assertIn('createMemoryReviewFromRun', script)
        self.assertIn('openWorkflowRun', script)
        self.assertIn('sourceManifestCard', script)
        self.assertIn('latest_proposal', script)
        self.assertIn('openWritingRun', script)
        self.assertNotIn('function loadBrief', script)
        self.assertIn('openReview', script)
        self.assertIn('/api/reviews/${encodeURIComponent(reviewId)}', script)
        self.assertIn('/api/memory/delete-review', script)
        self.assertIn('/api/memory/update-review', script)
        self.assertIn('/api/memory/${encodeURIComponent(memoryTargetId)}/lifecycle', script)
        self.assertIn('openMemoryLifecycle', script)
        self.assertIn('记忆生命周期已加载。', script)
        self.assertIn('syncReviewRecord', script)
        self.assertIn('reviewSourceRow', script)
        self.assertIn('memoryCandidateForProposal', script)
        self.assertIn('memoryCandidatePanel', script)
        self.assertIn('memoryCandidateEditor', script)
        self.assertIn('memoryCandidateEditorPayload', script)
        self.assertIn('memoryCandidateEvidence', script)
        self.assertIn('MEMORY_CARD_TYPES', script)
        self.assertIn('MEMORY_CARD_SCOPES', script)
        self.assertIn('memory_candidate', script)
        self.assertIn('decideReviewBatch', script)
        self.assertIn('memoryReviewQueueBatchActionButton', script)
        self.assertIn('memoryReviewQueueMergeAction', script)
        self.assertIn('memoryReviewQueueMergeEditor', script)
        self.assertIn('memoryReviewQueueMergeCandidateRow', script)
        self.assertIn('group.candidate_items || []', script)
        self.assertIn('mergeMemoryCandidateGroup(action, { text, behaviorDelta, memoryType, memoryScope })', script)
        self.assertIn('/api/reviews/batch-decision', script)
        self.assertIn('/api/reviews/merge-candidates', script)
        self.assertIn('toast.reviewBatchDecided', script)
        self.assertIn('toast.reviewCandidatesMerged', script)
        self.assertIn('"创建合并审核"', script)
        self.assertIn('button.acceptGroup', script)
        self.assertIn('button.rejectGroup', script)
        self.assertIn('"记忆候选"', script)
        self.assertIn('"候选文本"', script)
        self.assertIn('"行为变化"', script)
        self.assertIn('"消息摘录"', script)
        self.assertIn('metadata.behavior_delta', script)
        self.assertIn('metadata.evidence_quotes', script)
        self.assertIn('metadata.message_ids', script)
        self.assertIn('.memory-candidate-panel', styles)
        self.assertIn('.memory-candidate-header', styles)
        self.assertIn('.memory-candidate-text', styles)
        self.assertIn('.memory-candidate-editor', styles)
        self.assertIn('.merge-candidate-editor', styles)
        self.assertIn('.merge-candidate-list', styles)
        self.assertIn('.merge-candidate-row', styles)
        self.assertIn('.compact-actions', styles)
        self.assertIn('review.source_refs || proposal.source_refs', script)
        self.assertIn('review.revision || {}', script)
        self.assertIn('revision.previous_review_id', script)
        self.assertIn('revision.next_review_id', script)
        self.assertIn('revision.merged_from_review_ids', script)
        self.assertIn('revision.merged_into_review_id', script)
        self.assertIn('item.merged_into_review_id', script)
        self.assertIn('item.issue_types || []', script)
        self.assertIn('const runId = proposal.run_id || (proposal.metadata && proposal.metadata.run_id) || "";', script)
        self.assertIn('onclick: () => openWritingRun(runId)', script)
        self.assertIn('className: "review-source-row"', script)
        self.assertIn('review.status === "pending"', script)
        self.assertIn('review.status === "accepted"', script)
        self.assertIn('review.status === "needs_edit"', script)
        self.assertIn('review.status === "rejected"', script)
        self.assertIn('button.applyMemory', script)
        self.assertIn('button.applyMemoryUpdate', script)
        self.assertIn('button.applyMemoryDelete', script)
        self.assertIn('button.createUpdateReview', script)
        self.assertIn('button.createDeleteReview', script)
        self.assertIn('createMemoryUpdateReview', script)
        self.assertIn('createMemoryDeleteReview', script)
        self.assertIn('memoryApplyLabel', script)
        self.assertIn('memoryApplyAction', script)
        self.assertIn('heading.appliedKnowledge', script)
        self.assertIn('memoryApplyCard', script)
        self.assertIn('openMemoryLifecycle(memoryApply.target_id)', script)
        self.assertIn('if (memoryApply.target_id) {\n      actions.append(\n        el("button", { className: "secondary-button", onclick: () => openMemoryLifecycle(memoryApply.target_id) }, t("button.history")),\n      );\n    }', script)
        self.assertIn('syncReviewDecision', script)
        self.assertIn('state.focusReviewId = reviewId;', script)
        self.assertIn('if (payload.decision && payload.decision.status) {\n    setReviewStatusFilter("");\n  }', script)
        self.assertIn('reviseReview', script)
        self.assertIn('return `Updated durable memory through ${metadata.backend || "memory backend"}.`;', script)
        self.assertIn('return `Deleted durable memory through ${metadata.backend || "memory backend"}.`;', script)
        self.assertIn('<option value="memory.update">memory.update</option>', html)
        self.assertIn('<option value="memory.delete">memory.delete</option>', html)
        self.assertIn('return `Review revision created for ${metadata.proposal_kind || "proposal"}.`;', script)
        self.assertIn('syncMemoryApply', script)
        self.assertIn('记忆已应用', script)
        self.assertIn('label.locked', script)
        self.assertIn('memory_apply', script)
        self.assertIn('heading.retrievedContext', script)
        self.assertIn('parseActiveDocuments', script)
        self.assertIn('parseDatasetDocuments', script)
        self.assertIn('await parseDatasetDocuments(datasetId, documentIds);', script)
        self.assertIn('startIngestionPolling', script)

    def _get_text(self, path: str) -> str:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return response.read().decode("utf-8")

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json_error(self, path: str) -> dict:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=5) as response:
                self.fail(f"expected HTTP error, got {response.status}")
        except HTTPError as exc:
            return {
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))

    def _post_json_error(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                self.fail(f"expected HTTP error, got {response.status}")
        except HTTPError as exc:
            return {
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }

    def _delete_json(self, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload or {}).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))


class ProductApiFakeUploadLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env_patch = patch.dict(
            os.environ,
            {
                "PSKA_DEV_FAKE": "1",
                "PSKA_RETRIEVAL_PROVIDER": "fake",
                "PSKA_KB_PROVIDER": "fake",
                "PSKA_MEMORY_PROVIDER": "fake",
                "PSKA_REVIEW_DB": ":memory:",
                "PSKA_WORKSPACE_ID": "",
                "PSKA_TENANT_ID": "",
            },
            clear=True,
        )
        self.env_patch.start()
        reset_fake_kb_gateway()
        self.static_dir = tempfile.TemporaryDirectory()
        Path(self.static_dir.name, "index.html").write_text("<main>PSKA</main>", encoding="utf-8")
        self.server = build_server(
            host="127.0.0.1",
            port=0,
            service=build_service_from_env(),
            kb_gateway_factory=build_kb_gateway_from_env,
            static_dir=self.static_dir.name,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.static_dir.cleanup()
        self.env_patch.stop()

    def test_eval_route_runs_product_acceptance_suite(self):
        result = self._post_json(
            "/api/runtime/eval",
            {"suite": "product_acceptance"},
        )["eval"]

        self.assertTrue(result["ok"])
        self.assertEqual(result["kind"], "eval")
        self.assertEqual(result["suite"], "product_acceptance")
        self.assertEqual(result["steps"][0]["name"], "upload_loop.ready_export")
        self.assertEqual(result["steps"][-1]["name"], "audit.traceability")
        audit = self._get_json("/api/audit?limit=5&action=eval.run")
        self.assertEqual(audit["events"][0]["metadata"]["suite"], "product_acceptance")
        self.assertEqual(audit["events"][0]["metadata"]["status"], "ok")

    def test_product_api_upload_ask_and_source_read_use_uploaded_fake_document(self):
        dataset_name = f"Uploaded API Loop {uuid4().hex}"
        unique_phrase = f"source governed API loop {uuid4().hex}"
        ingested = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "parse": "true",
                "wait": "false",
            },
            "loop-note.txt",
            f"The uploaded document says {unique_phrase} before durable knowledge is written.",
        )
        dataset_id = ingested["ingest"]["dataset"]["dataset_id"]
        document_id = ingested["ingest"]["documents"][0]["document_id"]

        asked = self._post_json(
            "/api/ask",
            {
                "question": f"What does the uploaded document say about {unique_phrase}?",
                "dataset_ids": [dataset_id],
                "limit": 3,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "ready")
        self.assertIsNone(asked["review"])
        self.assertFalse(asked["loop"]["review_required"])
        self.assertEqual(asked["context_packets"][0]["source_ref"]["dataset_id"], dataset_id)
        self.assertEqual(asked["context_packets"][0]["source_ref"]["document_id"], document_id)
        self.assertIn(unique_phrase, asked["context_packets"][0]["text"])
        self.assertIn("loop-note.txt", asked["artifact"]["source_manifest"][0]["title"])

        source = self._post_json("/api/sources/read", {"source_ref": asked["context_packets"][0]["source_ref"]})
        self.assertIn(unique_phrase, source["source"]["text"])
        source_audit = self._get_json("/api/audit?limit=10&action=source.read")
        self.assertEqual(source_audit["events"][0]["metadata"]["document_id"], document_id)
        ingest_audit = self._get_json("/api/audit?limit=10&action=kb.ingest")
        self.assertEqual(ingest_audit["events"][0]["metadata"]["document_names"], ["loop-note.txt"])

    def test_product_api_ingest_loop_uploads_asks_exports_and_audits(self):
        dataset_name = f"Ingest Loop API {uuid4().hex}"
        unique_phrase = f"product api ingest loop {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": f"What does the uploaded file say about {unique_phrase}?",
                "export_format": "json",
                "poll_interval_seconds": "0.05",
                "limit": "2",
                "max_iterations": "4",
                "min_context_packets": "1",
                "retrieval_queries": "secondary retrieval\ntertiary retrieval",
                "source_inspection_limit": "0",
                "use_kg": "true",
            },
            "loop-note.txt",
            f"The uploaded file says {unique_phrase} inside the PSKA loop.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ask_status"], "ready")
        self.assertTrue(result["readiness"]["ready"])
        self.assertTrue(result["run_id"].startswith("run_"))
        self.assertEqual(result["run"]["run_id"], result["run_id"])
        self.assertEqual(result["proposal"]["kind"], "writing_brief")
        self.assertIsNone(result["review"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(result["loop"]["status"], "ready")
        self.assertEqual(result["export"]["traceability"]["source_count"], 1)
        self.assertEqual(result["export"]["traceability"]["source_inspection_count"], 0)
        ask_request = result["export"]["run"]["metadata"]["ask_request"]
        self.assertEqual(ask_request["limit"], 2)
        self.assertEqual(ask_request["max_iterations"], 4)
        self.assertEqual(ask_request["min_context_packets"], 1)
        self.assertEqual(ask_request["retrieval_queries"], ["secondary retrieval", "tertiary retrieval"])
        self.assertEqual(ask_request["source_inspection_limit"], 0)
        self.assertTrue(ask_request["use_kg"])
        self.assertTrue(result["export"]["run"]["scope"]["use_kg"])
        self.assertIn(unique_phrase, result["export"]["context_packets"][0]["text"])
        ingest_audit = self._get_json("/api/audit?limit=10&action=kb.ingest")
        self.assertEqual(ingest_audit["events"][0]["metadata"]["document_names"], ["loop-note.txt"])
        export_audit = self._get_json("/api/audit?limit=10&action=workflow.export")
        self.assertEqual(export_audit["events"][0]["target_id"], result["run_id"])

    def test_product_api_ingest_loop_exposes_governance_payload_for_review(self):
        dataset_name = f"Ingest Loop Review API {uuid4().hex}"
        unique_phrase = f"product api ingest loop review {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": f"What durable knowledge rule mentions {unique_phrase}?",
                "proposal_kind": "memory_patch",
                "create_review": "true",
                "export_format": "json",
                "poll_interval_seconds": "0.05",
            },
            "review-note.txt",
            f"The durable knowledge rule says {unique_phrase} must be reviewed before memory is written.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["proposal"]["kind"], "memory_patch")
        self.assertEqual(result["review"]["status"], "pending")
        self.assertEqual(result["review"]["proposal_id"], result["proposal"]["proposal_id"])
        self.assertIsNone(result["review_decision"])
        self.assertIsNone(result["memory_apply"])
        self.assertTrue(result["loop"]["review_required"])
        self.assertEqual(result["loop"]["governance"]["action"], "manual_review")
        self.assertEqual(result["export"]["latest_proposal"]["kind"], "memory_patch")
        review_audit = self._get_json("/api/audit?limit=10&action=review.create")
        self.assertEqual(review_audit["events"][0]["target_id"], result["review"]["review_id"])
        memory_audit = self._get_json("/api/audit?limit=10&action=memory.apply")
        self.assertEqual(memory_audit["events"], [])

    def test_product_api_ingest_loop_records_resumable_ask_when_upload_is_processing(self):
        dataset_name = f"Ingest Loop Processing API {uuid4().hex}"
        question = "What should happen after this uploaded file finishes parsing?"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": question,
                "parse": "false",
                "wait_ready": "false",
                "poll_interval_seconds": "0.05",
            },
            "slow-note.txt",
            "This uploaded source is intentionally left unparsed so the Ask can resume later.",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["ask_status"], "not_ready")
        self.assertIsNotNone(result["run"])
        self.assertEqual(result["run"]["status"], "blocked")
        self.assertEqual(result["run"]["metadata"]["blocked_reason"], "kb_not_ready")
        self.assertEqual(result["run"]["metadata"]["ask_request"]["question"], question)
        self.assertEqual(result["run"]["metadata"]["ingest_loop"]["export_format"], "markdown")
        self.assertEqual(result["loop"]["status"], "not_ready")
        self.assertEqual(result["resume"]["tool"], "pska_ingest_loop_resume")
        self.assertEqual(result["resume"]["api"], f"POST /api/workflows/{result['run_id']}/resume-ingest-loop")
        self.assertFalse(result["resume"]["can_resume"])
        self.assertEqual(result["next_actions"][0]["action"], "track_ingestion_status")
        self.assertEqual(result["next_actions"][1]["action"], "resume_ingest_loop")
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIsNone(result["export"])
        waiting = self._get_json("/api/workflows/resumable-asks?limit=5")
        self.assertEqual(waiting["resumable_asks"][0]["run"]["run_id"], result["run_id"])
        self.assertFalse(waiting["resumable_asks"][0]["can_resume"])
        self.assertEqual(waiting["resumable_asks"][0]["ask_request"]["question"], question)
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["tool"], "pska_ingest_loop_resume")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["api"], f"POST /api/workflows/{result['run_id']}/resume-ingest-loop")
        self.assertEqual(waiting["resumable_asks"][0]["resume"]["params"]["export_format"], "markdown")
        self.assertEqual(waiting["resumable_asks"][0]["next_actions"][-1]["action"], "resume_ingest_loop")
        audit = self._get_json("/api/audit?limit=20")
        actions = [event["action"] for event in audit["events"]]
        self.assertIn("kb.ingest", actions)
        self.assertIn("agentic_loop.not_ready", actions)
        self.assertIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)

        dataset_id = result["dataset"]["dataset_id"]
        document_ids = [document["document_id"] for document in result["documents"]]
        parsed = self._post_json(f"/api/kb/datasets/{dataset_id}/parse", {"document_ids": document_ids})
        self.assertEqual(parsed["ingestion_status"]["status"], "ready")

        resumed_payload = self._post_json(f"/api/workflows/{result['run_id']}/resume-ingest-loop", {})
        resumed = resumed_payload["ingest_loop"]

        self.assertEqual(resumed["kind"], "ingest_loop_resume")
        self.assertEqual(resumed["status"], "ok")
        self.assertEqual(resumed["ask_status"], "ready")
        self.assertEqual(resumed["export_format"], "markdown")
        self.assertIsNone(resumed["resume"])
        self.assertEqual(resumed["next_actions"], [])
        self.assertEqual(resumed["ingest"]["resumed_from_run_id"], result["run_id"])
        self.assertIn("This uploaded source is intentionally left unparsed", resumed["brief"])
        self.assertIsInstance(resumed["export"], str)
        resumed_audit = self._get_json("/api/audit?limit=30")
        resumed_actions = [event["action"] for event in resumed_audit["events"]]
        self.assertIn("agentic_loop.resume", resumed_actions)
        self.assertIn("workflow.export", resumed_actions)

    def test_product_api_fake_pdf_upload_reports_ingestion_failure_before_ask(self):
        dataset_name = f"Unsupported Fake PDF {uuid4().hex}"
        ingested = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "parse": "true",
                "wait": "false",
            },
            "annual-report.pdf",
            b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\nbinary fake pdf",
            content_type="application/pdf",
        )
        dataset_id = ingested["ingest"]["dataset"]["dataset_id"]

        self.assertEqual(ingested["ingestion_status"]["status"], "failed")
        self.assertEqual(ingested["ingestion_status"]["next_actions"], ["inspect_failed_documents"])
        self.assertIn("Fake KB can only parse UTF-8 text files", ingested["readiness"]["blocking"][0])

        asked = self._post_json(
            "/api/ask",
            {
                "question": "What is in the unsupported PDF?",
                "dataset_ids": [dataset_id],
                "limit": 1,
                "proposal_kind": "writing_brief",
            },
        )

        self.assertEqual(asked["status"], "not_ready")
        self.assertEqual(asked["readiness"]["status"], "failed")
        self.assertEqual(asked["context_packets"], [])
        self.assertIsNone(asked["proposal"])

    def test_product_api_ingest_loop_stops_before_ask_when_upload_is_not_ready(self):
        dataset_name = f"Unsupported Loop PDF {uuid4().hex}"
        payload = self._post_multipart_ingest(
            {
                "dataset_name": dataset_name,
                "question": "What is in the unsupported PDF?",
                "poll_interval_seconds": "0.05",
            },
            "annual-report.pdf",
            b"%PDF-1.5\n%\xe2\xe3\xcf\xd3\nbinary fake pdf",
            content_type="application/pdf",
            route="/api/ingest-loop",
        )
        result = payload["ingest_loop"]

        self.assertEqual(result["status"], "not_ready")
        self.assertEqual(result["readiness"]["status"], "failed")
        self.assertIsNone(result["ask_status"])
        self.assertIsNone(result["run"])
        self.assertIsNone(result["export"])
        actions = [event["action"] for event in self._get_json("/api/audit?limit=20")["events"]]
        self.assertIn("kb.ingest", actions)
        self.assertNotIn("agentic_loop.not_ready", actions)
        self.assertNotIn("kb.readiness.blocked", actions)
        self.assertNotIn("workflow.export", actions)
        self.assertNotIn("agentic_loop.complete", actions)

    def _post_multipart_ingest(
        self,
        fields: dict[str, str],
        filename: str,
        content: str | bytes,
        *,
        content_type: str = "text/plain",
        route: str = "/api/kb/ingest",
    ) -> dict:
        boundary = f"pska-test-{uuid4().hex}"
        file_content = content.encode("utf-8") if isinstance(content, str) else content
        parts: list[bytes] = []
        for name, value in fields.items():
            parts.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_content,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        request = Request(
            f"{self.base_url}{route}",
            data=b"".join(parts),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            self.fail(exc.read().decode("utf-8"))


def _adapter_provider(adapter_slots: dict, slot_name: str, provider_name: str) -> dict:
    for provider in adapter_slots["slots"][slot_name]["providers"]:
        if provider["name"] == provider_name:
            return provider
    raise AssertionError(f"adapter provider not found: {slot_name}/{provider_name}")


if __name__ == "__main__":
    unittest.main()
