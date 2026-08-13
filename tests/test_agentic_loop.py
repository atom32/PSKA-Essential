from __future__ import annotations

import unittest

from pska_essential.adapters.fake import FakeMemoryAdapter, FakeRetrievalAdapter
from pska_essential.agentic_loop import run_agentic_question, run_digest_scope
from pska_essential.contracts import ContextPacket, MemoryFact, SourceContext, SourceRef
from pska_essential.governance import AUTO_ACCEPT, AUTO_APPLY, WorkspaceGovernancePolicy
from pska_essential.review_store import SQLiteReviewStore
from pska_essential.workflow import WorkflowService, build_fake_service


class _NoContextRetrieval:
    backend_name = "none"

    def retrieve(self, query, scope, limit, options=None):
        return []

    def read_source(self, source_ref):
        return SourceContext(source_ref=source_ref, text="", metadata={"missing": True})


class _QueryRecordingRetrieval:
    backend_name = "query_recording"

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.source_reads: list[SourceRef] = []

    def retrieve(self, query, scope, limit, options=None):
        self.queries.append(query)
        index = len(self.queries)
        return [
            ContextPacket(
                context_id=f"ctx-query-{index}",
                text=f"Context returned for {query}",
                source_ref=SourceRef(adapter=self.backend_name, dataset_id="demo", document_id=f"doc-{index}"),
                title=query,
            )
        ]

    def read_source(self, source_ref):
        self.source_reads.append(source_ref)
        return SourceContext(source_ref=source_ref, text=f"Recorded query source for {source_ref.document_id}")


class _FederatedRetrieval:
    backend_name = "federated"

    def __init__(self) -> None:
        self.source_reads: list[SourceRef] = []

    def retrieve(self, query, scope, limit, options=None):
        return [
            ContextPacket(
                context_id="ctx-direct",
                text="Direct retrieval only returned a general note.",
                source_ref=SourceRef(
                    adapter=self.backend_name,
                    dataset_id="demo",
                    document_id="doc-direct",
                    chunk_id="chunk-direct",
                    title="Direct Source",
                ),
                title="Direct Source",
            )
        ][:limit]

    def read_source(self, source_ref):
        self.source_reads.append(source_ref)
        return SourceContext(
            source_ref=source_ref,
            text=f"Federated source evidence from {source_ref.document_id}.",
            metadata={"title": "Federated Memory Source"},
        )


class _FederatedMemory:
    backend_name = "graphiti"
    memory_capabilities = {"search": True, "apply": False, "update": False, "delete": False}

    def search(self, query, scope, limit):
        return [
            MemoryFact(
                fact_id="mem-graphiti-1",
                text="Graphiti says a related source exists.",
                source_refs=[
                    SourceRef(
                        adapter="federated",
                        dataset_id="demo",
                        document_id="doc-memory",
                        chunk_id="chunk-memory",
                        title="Memory Evidence",
                        metadata={"content_hash": "sha256:memory-source"},
                    )
                ],
                metadata={"lineage_status": "resolved"},
            )
        ][:limit]

    def apply(self, reviewed_patch):
        raise NotImplementedError

    def update(self, reviewed_update):
        raise NotImplementedError

    def delete(self, reviewed_delete):
        raise NotImplementedError


class _ReadyGateway:
    def list_datasets(self, *, page_size=200, name=None):
        return [{"dataset_id": "demo", "name": "Demo", "document_count": 1, "chunk_count": 1}]

    def list_documents(self, *, dataset_id, document_id=None, name=None, page_size=30):
        return [
            {
                "dataset_id": dataset_id,
                "document_id": document_id or "doc-1",
                "name": name or "doc.txt",
                "chunk_count": 1,
                "progress": 1.0,
                "run": "DONE",
            }
        ]


class AgenticLoopTests(unittest.TestCase):
    def test_transient_writing_brief_does_not_create_review_by_default(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Explain the PSKA boundary",
            dataset_ids=["demo"],
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertIsNone(result["review"])
        self.assertFalse(result["loop"]["review_required"])
        self.assertEqual(result["artifact"]["latest_proposal"]["kind"], "writing_brief")
        self.assertIn("brief.prepare", [step["name"] for step in result["loop"]["steps"]])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        artifact_loop = result["artifact"]["run"]["metadata"]["agentic_loop"]
        self.assertEqual(persisted_loop["status"], "ready")
        self.assertEqual(persisted_loop["governance"]["action"], "skip")
        self.assertFalse(persisted_loop["review_required"])
        self.assertFalse(persisted_loop["durable_proposal"])
        self.assertEqual(persisted_loop["proposal_id"], result["proposal"]["proposal_id"])
        self.assertEqual(artifact_loop["proposal_id"], result["proposal"]["proposal_id"])
        self.assertEqual(service.store.list_reviews(), [])
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_agentic_loop_normalizes_scope_ids(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Normalize scope IDs",
            dataset_ids=[" demo ", "demo", "  "],
            document_ids=[" doc-1 ", "doc-1", ""],
            proposal_kind="writing_brief",
        )

        run = service.state(result["run"]["run_id"])
        self.assertEqual(run.scope["dataset_ids"], ["demo"])
        self.assertEqual(run.scope["document_ids"], ["doc-1"])
        self.assertEqual(run.metadata["ask_request"]["dataset_ids"], ["demo"])
        self.assertEqual(run.metadata["ask_request"]["document_ids"], ["doc-1"])

    def test_agentic_loop_uses_explicit_retrieval_query_plan(self):
        retrieval = _QueryRecordingRetrieval()
        service = WorkflowService(
            retrieval=retrieval,
            memory=FakeMemoryAdapter(),
            store=SQLiteReviewStore(":memory:"),
        )

        result = run_agentic_question(
            service,
            question="Primary question",
            dataset_ids=["demo"],
            retrieval_queries=["Secondary angle", "primary question", "Tertiary angle"],
            limit=1,
            max_iterations=3,
            min_context_packets=3,
            source_inspection_limit=2,
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(retrieval.queries, ["Primary question", "Secondary angle", "Tertiary angle"])
        self.assertEqual([ref.document_id for ref in retrieval.source_reads], ["doc-1", "doc-2"])
        self.assertEqual(result["loop"]["retrieval_query_plan"], retrieval.queries)
        retrieve_steps = [step for step in result["loop"]["steps"] if step["name"] == "context.retrieve"]
        self.assertEqual([step["metadata"]["query"] for step in retrieve_steps], retrieval.queries)
        source_step = next(step for step in result["loop"]["steps"] if step["name"] == "source.inspect")
        self.assertEqual(source_step["metadata"]["inspected_count"], 2)
        self.assertEqual(result["artifact"]["traceability"]["source_inspection_count"], 2)
        self.assertEqual(len(result["artifact"]["source_inspections"]), 2)
        ask_request = service.state(result["run"]["run_id"]).metadata["ask_request"]
        self.assertEqual(ask_request["retrieval_queries"], ["Secondary angle", "Tertiary angle"])
        self.assertEqual(ask_request["source_inspection_limit"], 2)
        context_events = service.store.list_audit_events(action="context.retrieve")
        self.assertEqual([event.metadata["query"] for event in context_events], retrieval.queries)
        self.assertEqual(len(service.store.list_audit_events(action="source.read")), 2)

    def test_agentic_loop_federates_graphiti_memory_sources_into_context(self):
        retrieval = _FederatedRetrieval()
        service = WorkflowService(
            retrieval=retrieval,
            memory=_FederatedMemory(),
            store=SQLiteReviewStore(":memory:"),
        )

        result = run_agentic_question(
            service,
            question="Use memory-linked evidence",
            dataset_ids=["demo"],
            limit=1,
            max_iterations=1,
            min_context_packets=2,
            source_inspection_limit=0,
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["context_packets"]), 2)
        self.assertEqual(result["context_packets"][1]["metadata"]["origin"], "memory_source_federation")
        self.assertEqual(result["context_packets"][1]["source_ref"]["document_id"], "doc-memory")
        self.assertIn("Federated source evidence", result["proposal"]["body"])
        self.assertEqual([ref.document_id for ref in retrieval.source_reads], ["doc-memory"])
        federation_step = next(step for step in result["loop"]["steps"] if step["name"] == "memory.source_federation")
        self.assertEqual(federation_step["status"], "complete")
        self.assertEqual(federation_step["metadata"]["candidate_source_count"], 1)
        self.assertEqual(federation_step["metadata"]["added_count"], 1)
        event = service.store.list_audit_events(action="memory.source_federate")[0]
        self.assertEqual(event.metadata["added_count"], 1)

    def test_digest_scope_creates_sourced_digest_without_memory_write_by_default(self):
        service = build_fake_service()

        result = run_digest_scope(
            service,
            _ReadyGateway(),
            dataset_ids=["demo"],
            question="Digest ready demo scope",
            limit=1,
            source_inspection_limit=0,
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["kind"], "digest_scope")
        self.assertEqual(result["digest"]["kind"], "digest")
        self.assertIsNone(result["memory_review"])
        self.assertEqual(service.state(result["run"]["run_id"]).metadata["digest_scope"]["kind"], "digest_scope")
        self.assertEqual(service.store.list_reviews(), [])
        event = service.store.list_audit_events(action="digest.scope")[0]
        self.assertFalse(event.metadata["create_memory_review"])

    def test_digest_scope_can_create_digest_origin_memory_review(self):
        service = build_fake_service()

        result = run_digest_scope(
            service,
            _ReadyGateway(),
            dataset_ids=["demo"],
            question="Digest durable candidates",
            limit=1,
            source_inspection_limit=0,
            create_memory_review=True,
            memory_intent="Remember digest candidate",
        )

        self.assertEqual(result["status"], "ready")
        memory_review = result["memory_review"]
        self.assertEqual(memory_review["review"]["status"], "pending")
        self.assertEqual(memory_review["governance"]["origin"], "digest")
        self.assertEqual(memory_review["governance"]["action"], "manual_review")
        self.assertEqual(memory_review["proposal"]["metadata"]["origin"], "digest")
        self.assertEqual(len(service.store.list_reviews(status="pending")), 1)

    def test_durable_memory_patch_creates_review_even_when_caller_does_not_force_it(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember the review gate",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            create_review=False,
        )

        self.assertEqual(result["status"], "ready")
        self.assertIsNotNone(result["review"])
        self.assertTrue(result["loop"]["review_required"])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        self.assertEqual(persisted_loop["governance"]["action"], "manual_review")
        self.assertTrue(persisted_loop["durable_proposal"])
        self.assertTrue(persisted_loop["review_required"])
        self.assertEqual(persisted_loop["review_id"], result["review"]["review_id"])
        self.assertEqual(len(service.store.list_reviews(status="pending")), 1)
        audit_actions = [event.action for event in service.store.list_audit_events()]
        self.assertNotIn("workflow.export", audit_actions)

    def test_memory_lifecycle_changes_are_not_agentic_question_proposal_kinds(self):
        service = build_fake_service()

        for proposal_kind in ["memory_delete", "memory_update"]:
            with self.subTest(proposal_kind=proposal_kind):
                with self.assertRaisesRegex(ValueError, "explicit memory fact"):
                    run_agentic_question(
                        service,
                        question="Change a memory somehow",
                        dataset_ids=["demo"],
                        proposal_kind=proposal_kind,
                    )

    def test_no_context_returns_insufficient_context_without_proposal(self):
        service = WorkflowService(
            retrieval=_NoContextRetrieval(),
            memory=FakeMemoryAdapter(),
            store=SQLiteReviewStore(":memory:"),
        )
        result = run_agentic_question(
            service,
            question="What is unsupported?",
            dataset_ids=["empty"],
            proposal_kind="memory_patch",
        )

        self.assertEqual(result["status"], "insufficient_context")
        self.assertEqual(result["context_packets"], [])
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertIn("No context", result["message"])
        persisted_loop = service.state(result["run"]["run_id"]).metadata["agentic_loop"]
        self.assertEqual(persisted_loop["status"], "insufficient_context")
        self.assertEqual(persisted_loop["governance"]["action"], "skip")
        self.assertEqual(persisted_loop["requested_governance_action"], "manual_review")
        self.assertEqual(persisted_loop["required_context_count"], 1)

    def test_partial_context_below_minimum_does_not_create_proposal(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Explain adapter boundaries",
            dataset_ids=["demo"],
            limit=1,
            max_iterations=1,
            min_context_packets=2,
            proposal_kind="memory_patch",
        )

        self.assertEqual(result["status"], "insufficient_context")
        self.assertEqual(len(result["context_packets"]), 1)
        self.assertIsNone(result["proposal"])
        self.assertIsNone(result["review"])
        self.assertEqual(service.store.list_reviews(), [])
        self.assertIn("2 required", result["message"])

    def test_auto_accept_policy_accepts_review_without_applying_memory(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember the policy boundary",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_ACCEPT),
        )

        self.assertEqual(result["loop"]["governance"]["action"], AUTO_ACCEPT)
        self.assertEqual(result["review"]["status"], "accepted")
        self.assertEqual(result["review_decision"]["status"], "accepted")
        self.assertIsNone(result["memory_apply"])
        self.assertEqual(service.memory_search("policy boundary"), [])

    def test_auto_apply_policy_applies_memory_after_accepted_review(self):
        service = build_fake_service()
        result = run_agentic_question(
            service,
            question="Remember automatic governed memory",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_APPLY),
        )

        self.assertEqual(result["loop"]["governance"]["action"], AUTO_APPLY)
        self.assertEqual(result["review"]["status"], "accepted")
        self.assertEqual(result["review_decision"]["status"], "accepted")
        self.assertTrue(result["memory_apply"]["applied"])
        self.assertEqual(len(service.memory_search("automatic governed memory")), 1)

    def test_model_context_budget_caps_retrieval_and_source_inspection(self):
        corpus = [
            {
                "id": f"budget-doc-{index}",
                "title": f"Budget Doc {index}",
                "text": f"Budget scoped context packet {index}.",
            }
            for index in range(1, 6)
        ]
        service = WorkflowService(
            FakeRetrievalAdapter(corpus=corpus),
            FakeMemoryAdapter(),
            SQLiteReviewStore(":memory:"),
        )

        result = run_agentic_question(
            service,
            question="Budget scoped context",
            dataset_ids=["demo"],
            limit=5,
            max_iterations=1,
            min_context_packets=1,
            source_inspection_limit=3,
            model_context_tokens=2048,
            model_profile="small-test-model",
        )

        budget = result["loop"]["context_budget"]
        self.assertEqual(budget["mode"], "model_context")
        self.assertEqual(budget["model_context_tokens"], 2048)
        self.assertEqual(budget["model_profile"], "small-test-model")
        self.assertEqual(budget["requested_limit"], 5)
        self.assertEqual(budget["effective_retrieval_limit"], 1)
        self.assertEqual(budget["effective_source_inspection_limit"], 0)
        self.assertEqual(len(result["context_packets"]), 1)
        self.assertEqual(result["loop"]["source_inspection_count"], 0)
        retrieve_step = next(step for step in result["loop"]["steps"] if step["name"] == "context.retrieve")
        self.assertEqual(retrieve_step["metadata"]["requested_limit"], 1)
        ask_request = service.state(result["run"]["run_id"]).metadata["ask_request"]
        self.assertEqual(ask_request["context_budget"]["effective_retrieval_limit"], 1)

    def test_reviewed_memory_influences_later_agentic_questions(self):
        service = build_fake_service()
        run_agentic_question(
            service,
            question="Remember reusable durable policy context",
            dataset_ids=["demo"],
            proposal_kind="memory_patch",
            workspace_policy=WorkspaceGovernancePolicy(durable_memory=AUTO_APPLY),
        )

        result = run_agentic_question(
            service,
            question="Use reusable durable policy context",
            dataset_ids=["demo"],
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["memory_facts"]), 1)
        expected_memory_source_count = len(result["memory_facts"][0]["source_refs"])
        self.assertEqual(result["artifact"]["traceability"]["memory_count"], 1)
        self.assertEqual(result["artifact"]["traceability"]["memory_source_count"], expected_memory_source_count)
        self.assertEqual(result["memory_attribution"]["schema"], "pska.memory_attribution.v1")
        self.assertEqual(result["memory_attribution"]["used_memory_ids"], [result["memory_facts"][0]["fact_id"]])
        self.assertEqual(
            result["artifact"]["memory_attribution"]["used_memory_ids"],
            result["memory_attribution"]["used_memory_ids"],
        )
        self.assertEqual(result["memory_suggestions"]["schema"], "pska.memory_suggestions.v1")
        self.assertEqual(result["memory_suggestions"]["suggestions"][0]["next_actions"][0]["tool"], "pska_memory_review_from_workflow")
        self.assertEqual(len(result["artifact"]["memory_source_manifest"]), expected_memory_source_count)
        self.assertEqual(result["artifact"]["memory_source_manifest"][0]["adapter"], "fake")
        self.assertEqual(result["artifact"]["memory_facts"][0]["fact_id"], result["memory_facts"][0]["fact_id"])
        self.assertIn("Durable workspace memory", result["proposal"]["body"])
        exported = service.export_brief(result["run"]["run_id"], "markdown")
        self.assertIn("## Inspected Sources", exported)
        self.assertIn("## Durable Workspace Memory", exported)
        self.assertIn("| Source | Adapter | Dataset | Document | Chunk/Source |", exported)
        self.assertIn("| 1 | fake |", exported)
        exported_json = service.export_brief(result["run"]["run_id"], "json")
        self.assertEqual(exported_json["traceability"]["source_inspection_count"], 2)
        self.assertEqual(exported_json["traceability"]["export"]["source_inspection_count"], 2)
        self.assertEqual(exported_json["traceability"]["memory_source_count"], expected_memory_source_count)
        self.assertEqual(exported_json["memory_attribution"]["used_memory_ids"], [result["memory_facts"][0]["fact_id"]])
        export_events = [
            event for event in service.store.list_audit_events() if event.action == "workflow.export"
        ]
        self.assertEqual(export_events[-1].metadata["source_inspection_count"], 2)
        self.assertEqual(export_events[-1].metadata["memory_count"], 1)
        self.assertEqual(export_events[-1].metadata["memory_source_count"], expected_memory_source_count)
        memory_step = next(step for step in result["loop"]["steps"] if step["name"] == "memory.search")
        self.assertEqual(memory_step["metadata"]["returned_count"], 1)
        memory_search_events = [
            event for event in service.store.list_audit_events() if event.action == "memory.search"
        ]
        self.assertGreaterEqual(len(memory_search_events), 2)
        self.assertEqual(memory_search_events[-1].metadata["count"], 1)
        complete_event = next(
            event
            for event in service.store.list_audit_events(action="agentic_loop.complete")
            if event.target_id == result["run"]["run_id"]
        )
        self.assertEqual(complete_event.metadata["used_memory_ids"], [result["memory_facts"][0]["fact_id"]])

    def test_correction_episode_memory_uses_display_text_in_agent_facing_outputs(self):
        memory = FakeMemoryAdapter()
        memory.facts.append(
            MemoryFact(
                fact_id="editor-correction",
                text=(
                    "Memory correction episode.\n"
                    "Current fact: The user's editor is VS Code.\n"
                    "Previous fact: The user's editor is Vim.\n"
                    "Supersedes memory fact: editor-old"
                ),
                source_refs=[SourceRef(adapter="fake", dataset_id="demo", document_id="memory-doc")],
                metadata={
                    "display_text": "The user's editor is VS Code.",
                    "current_text": "The user's editor is VS Code.",
                    "previous_text": "The user's editor is Vim.",
                    "semantic_operation": "memory_update",
                    "memory_update_strategy": "append_correction_episode",
                    "target_fact_id": "editor-old",
                },
            )
        )
        service = WorkflowService(FakeRetrievalAdapter(), memory, SQLiteReviewStore(":memory:"))

        result = run_agentic_question(
            service,
            question="Use editor preference",
            dataset_ids=["demo"],
            proposal_kind="writing_brief",
        )

        self.assertEqual(result["status"], "ready")
        self.assertIn("Memory correction episode.", result["memory_facts"][0]["text"])
        self.assertEqual(result["memory_facts"][0]["metadata"]["display_text"], "The user's editor is VS Code.")
        self.assertIn("- The user's editor is VS Code.", result["proposal"]["body"])
        self.assertNotIn("Memory correction episode.", result["proposal"]["body"])
        self.assertNotIn("Previous fact: The user's editor is Vim.", result["proposal"]["body"])
        exported = service.export_brief(result["run"]["run_id"], "markdown")
        self.assertIn("The user's editor is VS Code.", exported)
        self.assertNotIn("Memory correction episode.", exported)


if __name__ == "__main__":
    unittest.main()
