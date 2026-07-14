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
update(reviewed_update) -> MemoryApplyResult
delete(reviewed_delete) -> MemoryApplyResult
```

Rules:

- `apply` receives only reviewed `MemoryPatch` objects.
- `update` receives only reviewed `MemoryUpdate` objects from PSKA review flow.
- `delete` receives only reviewed `MemoryDelete` objects from PSKA review flow.
- Direct clear, unreviewed add, or provider-native delete operations are
  intentionally absent from public tools.
- Graphiti `add_episode` is allowed only inside `apply`.

## Public MCP Contract

The public tool surface is:

- `pska_workflow_start`
- `pska_workflow_list`
- `pska_workflow_state`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_context_retrieve`
- `pska_source_read`
- `pska_policy_get`
- `pska_propose`
- `pska_review_create`
- `pska_review_list`
- `pska_review_get`
- `pska_review_decide`
- `pska_review_revise`
- `pska_memory_search`
- `pska_memory_apply`
- `pska_memory_review_from_workflow`
- `pska_memory_update_review`
- `pska_memory_delete_review`
- `pska_memory_lifecycle`
- `pska_export_brief`
- `pska_audit_list`
- `pska_retrieval_probe`
- `pska_eval_run`
- `pska_kb_list`
- `pska_kb_create`
- `pska_kb_ingest_files`
- `pska_kb_document_status`
- `pska_kb_readiness`
- `pska_kb_ingestion_status`
- `pska_kb_parse_documents`
- `pska_kb_graph_read`
- `pska_agentic_question_start`
- `pska_agentic_question_resumable`
- `pska_agentic_question_resume`

Backends must be replaceable without changing these tools.
`pska_policy_get` returns PSKA workspace governance policy; agents must use it
for product policy awareness instead of inferring review behavior from backend
capabilities.

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
- Ingestion status is the product-facing job summary for upload, parse,
  embedding, and indexing readiness. It must expose phase, progress, counts,
  next actions, and failure reasons in PSKA language.
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
write memory/graph state before review. Additional retrieval rounds may use
explicit `retrieval_queries` supplied by the user or agent; PSKA records the
query plan and each scoped retrieval step, but must not add domain-specific
query expansion in runtime code.
After retrieval, PSKA may inspect a bounded number of unique retrieved
`SourceRef`s through the retrieval adapter. Source inspection is transient
workflow evidence, records `source.inspect` loop metadata, and uses normal
`source.read` audit records.
If readiness blocks the selected scope, PSKA must persist the blocked workflow,
surface it through a resumable Ask list with a fresh readiness check, and allow
a later resume to create a new audited Ask workflow from the stored request.

## Review Gate

Memory write flow:

```text
retrieve -> propose(memory_patch) -> review_create -> review_decide(accept) -> memory_apply
```

Memory delete flow:

```text
memory_search -> pska_memory_delete_review(MemoryFact) -> review_decide(accept) -> memory_apply
```

Memory update flow:

```text
memory_search -> pska_memory_update_review(MemoryFact, text) -> review_decide(accept) -> memory_apply
```

Durable memory lifecycle inspection:

```text
pska_memory_lifecycle(memory_target_id) -> PSKA audit-derived apply/update/delete history
```

`memory_apply` must fail when the review is pending, rejected, or needs edit.
Durable memory review creation, review acceptance, and memory apply must fail
when the durable proposal has no PSKA `SourceRef` trace.
Once reviewed memory has been applied, the review decision is immutable; later
changes require a new governed proposal rather than rewriting the old decision.
Lifecycle history is derived from PSKA audit records and must not require direct
provider history APIs.
