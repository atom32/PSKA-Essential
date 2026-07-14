# Adapter Contracts

Adapters are the only place where external backend shapes are allowed.

Adapters must fail explicitly. They must not silently switch providers, return
fake data, answer from model memory, or hide backend failures.

## RetrievalPort

```python
retrieve(query, scope, limit, options) -> list[ContextPacket]
read_source(source_ref) -> SourceContext
```

Rules:

- Return PSKA `ContextPacket`, never backend-native chunk objects.
- Every `ContextPacket` must have a `SourceRef`.
- Preserve enough backend coordinates in `SourceRef` to read or debug the source.
- Store short excerpts in metadata only when useful for citation inspection.
- Retrieval adapters must not broaden dataset/document scope unless the caller
  explicitly passes that broader scope.

## MemoryPort

```python
search(query, scope, limit) -> list[MemoryFact]
apply(reviewed_patch) -> MemoryApplyResult
```

Rules:

- `apply` receives only reviewed `MemoryPatch` objects.
- Direct delete, clear, or unreviewed add operations are intentionally absent.
- Graphiti `add_episode` is allowed only inside `apply`.

## Public MCP Contract

The public tool surface is:

- `pska_workflow_start`
- `pska_workflow_state`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_context_retrieve`
- `pska_source_read`
- `pska_propose`
- `pska_review_create`
- `pska_review_list`
- `pska_review_get`
- `pska_review_decide`
- `pska_memory_search`
- `pska_memory_apply`
- `pska_export_brief`
- `pska_audit_list`
- `pska_eval_run`
- `pska_kb_list`
- `pska_kb_create`
- `pska_kb_ingest_files`
- `pska_kb_document_status`
- `pska_kb_readiness`
- `pska_kb_parse_documents`
- `pska_kb_graph_read`
- `pska_agentic_question_start`

Backends must be replaceable without changing these tools.

## KB Gateway

The KB gateway is a thin operational layer over an external KB provider. In v1
that provider is RAGFlow.

Rules:

- PSKA-Essential may create datasets, upload files, start parsing, poll document
  status, and read optional structure graph data through provider APIs.
- PSKA-Essential must not persist raw documents or build its own index.
- Public tools return normalized dataset/document IDs and status fields, not
  raw provider responses.
- Readiness checks return PSKA status language and must not leak provider-native
  task or document payloads outside the gateway.
- Agentic questions should carry explicit `dataset_ids` and optional
  `document_ids` into the normal retrieval workflow.
- Upload, parsing, embedding, indexing, and optional graph extraction are
  asynchronous. Gateway APIs must expose status/readiness instead of implying
  immediate retrieval availability.

## Agentic Loop

The public `pska_agentic_question_start` tool is the first step toward a richer
agentic Ask loop. That loop should remain PSKA-controlled:

```text
start -> check scope/readiness -> retrieve -> inspect sources
  -> optionally retrieve again -> synthesize/propose -> review
  -> make available for explicit export
```

The loop may iterate, but it must not silently change user-selected scope or
write memory/graph state before review.

## Review Gate

Memory write flow:

```text
retrieve -> propose(memory_patch) -> review_create -> review_decide(accept) -> memory_apply
```

`memory_apply` must fail when the review is pending, rejected, or needs edit.
Once reviewed memory has been applied, the review decision is immutable; later
changes require a new governed proposal rather than rewriting the old decision.
