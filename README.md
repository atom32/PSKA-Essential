# PSKA-Essential

PSKA-Essential is an **Agent Knowledge Workflow Gate**. It does not try to be a
knowledge base, GraphRAG platform, editor, or agent runtime. It connects mature
systems through small adapter contracts and keeps the workflow safe:

```text
Hermes Agent
  -> PSKA-Essential MCP
    -> Retrieval Adapter: RAGFlow / Company GraphRAG
    -> Memory Adapter: Graphiti / Company GraphRAG
    -> Review Store: SQLite
    -> Export: Markdown / JSON
```

The product promise is workflow closure:

- run Hermes-first agent workflows through PSKA MCP tools;
- retrieve context from an external KB;
- optionally create/populate that external KB through thin MCP glue;
- let an agent propose digest, memory, or writing artifacts;
- require review before long-term memory changes;
- keep an audit trail;
- replace RAGFlow/Graphiti later through adapters.

Runtime behavior is universal and explicit: no case-specific shortcuts, no
hardcoded domains, and no silent fallback to fake data or another backend.
Document ingestion and embedding are treated as asynchronous jobs whose status
must be visible to users and agents.

## Quick Start

The code is intentionally stdlib-first so the fake workflow can run before any
external service is installed. In explicit fake mode, uploaded text documents
are stored by the fake KB gateway and are retrievable by the fake retrieval
adapter, so the local upload-to-Ask loop can run without RAGFlow. Fake mode is
text-only: PDF, OCR, binary parsing, embedding, and indexing should use a real
KB provider such as RAGFlow. If a PDF-like file is uploaded to fake KB, PSKA
marks ingestion failed explicitly instead of pretending the scope is ready.

```bash
cd /Users/xudawei/PSKA-Essential
PYTHONPATH=src python3 -m unittest discover -s tests
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PYTHONPATH=src python3 -m pska_essential --list-tools
```

Run the bundled smoke eval:

```bash
PYTHONPATH=src python3 - <<'PY'
from pska_essential.workflow import build_fake_service
print(build_fake_service().eval_run("smoke"))
PY
```

Run the Product API and frontend in explicit local development mode:

```bash
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 \
  PYTHONPATH=src python3 -m pska_essential.product_api
```

Then open:

```bash
open http://127.0.0.1:8765
```

## External Backends

Production mode requires explicit providers:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export PSKA_MEMORY_PROVIDER=graphiti
```

RAGFlow retrieval:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export RAGFLOW_BASE_URL=http://localhost:9380
export RAGFLOW_API_KEY=...
```

After a RAGFlow dataset is uploaded and ready, run a live closed-loop probe:

```bash
export PSKA_LIVE_DATASET_IDS=...
export PSKA_LIVE_QUESTION="Summarize the selected documents with sources."
make live-closed-loop
```

This command does not allow fake KB or fake retrieval providers. A successful
result means the configured live providers completed readiness, retrieval,
agentic Ask, source inspection, and explicit export; the probe reports context,
source, and source-inspection counts.
If the result reports `configure_embedding_provider`, configure the selected
dataset embedding model/provider in RAGFlow and re-parse/re-index the affected
documents before running Ask.
When creating a new RAGFlow-backed dataset through PSKA, `pska_kb_create`,
`pska_kb_ingest_files`, and the Product API accept optional `embedding_model`.
Leave it empty to use the RAGFlow tenant default, or set it to an embedding
model/provider that RAGFlow already has configured.

Graphiti memory:

```bash
export PSKA_MEMORY_PROVIDER=graphiti
export GRAPHITI_BASE_URL=http://localhost:8000
export GRAPHITI_GROUP_ID=pska-essential
```

The Graphiti adapter keeps writes review-gated. It supports reviewed memory
apply and reviewed entity-edge delete through Graphiti; reviewed update fails
explicitly until the backend exposes a transactional fact update contract.
Memory operation capabilities are exposed through the explicit capabilities
contract, health, diagnostics, and workspace status so the frontend and Hermes
can avoid unsupported durable actions before creating review items. Historical
accepted reviews that target
unsupported backend operations remain visible as inspect actions instead of
being offered as apply actions. When a workspace or tenant is configured,
Graphiti memory search/apply uses a derived PSKA memory namespace under the
configured `GRAPHITI_GROUP_ID`.
Use `pska_memory_probe` or `POST /api/runtime/memory-probe` to verify that the
configured memory backend can actually serve search requests. Graphiti
`/healthcheck` only proves the service is running; the probe surfaces LLM or
embedding provider configuration failures explicitly instead of falling back to
fake memory.

Workspace governance policy:

```bash
# manual_review | auto_accept | auto_apply
export PSKA_GOVERNANCE_DURABLE_MEMORY=manual_review
export PSKA_WORKSPACE_ID=default
export PSKA_TENANT_ID=
```

`PSKA_WORKSPACE_ID` and `PSKA_TENANT_ID` scope the local review store. Workflow,
review, memory-apply, and audit lists/read APIs default to the current
workspace/tenant, so two workspaces can share one SQLite file without exposing
each other's PSKA state. Existing unscoped SQLite rows are treated as
`default` workspace records during migration. Durable memory adapters receive
the same context as a PSKA `memory_namespace`, so fake, company-stub, and
Graphiti memory search/write flows stay aligned with the workspace boundary.

Local Graphiti install:

```bash
cd /Users/xudawei/PSKA-Components/graphiti
docker compose -f docker-compose.pska.yml --env-file .env.pska up -d
curl http://127.0.0.1:8000/healthcheck
```

Company GraphRAG replacement stub:

```bash
export PSKA_RETRIEVAL_PROVIDER=company_graphrag_stub
export PSKA_MEMORY_PROVIDER=company_graphrag_stub
```

Explicit local fake mode for tests and tool discovery:

```bash
export PSKA_DEV_FAKE=1
export PSKA_RETRIEVAL_PROVIDER=fake
export PSKA_KB_PROVIDER=fake
export PSKA_MEMORY_PROVIDER=fake
```

With `PSKA_KB_PROVIDER=fake`, uploaded text documents are queryable by later
Ask runs in the same Product API process. PDF annual reports and other binary
documents should be tested through RAGFlow-backed KB mode.

## MCP

The MCP server uses the optional `mcp` package:

```bash
uv sync --extra mcp
uv run pska-essential-mcp
```

Hermes should connect only to PSKA-Essential MCP. Do not expose RAGFlow or
Graphiti MCP servers directly to the agent; that would bypass the review gate.

Operational loop tools:

- `pska_kb_list`
- `pska_kb_create`
- `pska_kb_delete`
- `pska_kb_ingest_files`
- `pska_kb_document_status`
- `pska_kb_readiness`
- `pska_kb_ingestion_status`
- `pska_kb_parse_documents`
- `pska_kb_graph_read`
- `pska_retrieval_probe`
- `pska_memory_probe`
- `pska_live_closed_loop_probe`
- `pska_agentic_question_start`
- `pska_agentic_question_resumable`
- `pska_agentic_question_resume`
- `pska_policy_get`
- `pska_capabilities_get`
- `pska_workspace_status`
- `pska_workflow_list`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_memory_review_from_workflow`
- `pska_memory_update_review`
- `pska_memory_delete_review`
- `pska_memory_lifecycle`
- `pska_review_list`
- `pska_review_get`
- `pska_review_decide`
- `pska_review_revise`
- `pska_memory_apply`
- `pska_export_brief`
- `pska_audit_list`

These tools are thin glue over RAGFlow plus the existing PSKA workflow gate:
KB ingest and parse tools return normalized `readiness` and
`ingestion_status` along with their operation result, so agents can decide
whether to wait, parse, inspect a failure, or Ask without calling provider APIs.
`pska_retrieval_probe` checks whether a ready scope can retrieve context.
`pska_memory_probe` checks whether the configured memory backend can search
through the PSKA memory contract; it rejects fake memory by default for live
component verification and records a `memory.probe` audit event.
`pska_live_closed_loop_probe` is stricter: it rejects fake KB/retrieval
providers and then runs readiness, retrieval, agentic Ask, source inspection,
and explicit export for a transient work product against the configured live
providers. Durable memory or graph changes still use the normal review/apply
workflow.
Dataset creation and ingest tools accept optional `embedding_model` so the
PSKA product layer can request a configured RAGFlow embedding model without
exposing RAGFlow-internal fields.
`pska_kb_delete` is the explicit development/operations cleanup path for bad
datasets; it deletes through the KB adapter and records audit instead of
touching provider databases directly.

```text
upload files -> RAGFlow dataset/documents/chunks -> inspect workspace policy
  -> PSKA scoped retrieve
  -> agent answer/proposal -> Review -> optional memory apply
  -> optional governed memory update review
  -> optional governed memory delete review
  -> inspect durable memory lifecycle
  -> inspect artifact / transient brief -> explicit export
```

See:

- `AGENTS.md`
- `docs/PRODUCT_DESIGN.md`
- `docs/FEASIBILITY_AUDIT.md`
- `docs/ADAPTER_CONTRACTS.md`
- `docs/DEMO_RUNBOOK.md`
- `docs/RUNNING_AND_TESTING.md`
- `skills/hermes/SKILL.md`
- `skills/openclaw/SKILL.md`

## Product API And Frontend

The Product API is the frontend-facing boundary. The frontend must call PSKA
Product API routes only; it must not call RAGFlow, Graphiti, embedding services,
LLM providers, databases, or queues directly.

Default local URL:

```text
http://127.0.0.1:8765
```

Implemented Alpha routes:

- `GET /api/health`
- `GET /api/capabilities`
- `GET /api/policy`
- `GET /api/runtime/diagnostics`
- `GET /api/workspace/status`
- `POST /api/runtime/retrieval-probe`
- `POST /api/runtime/memory-probe`
- `POST /api/runtime/closed-loop-probe`
- `GET /api/kb/datasets`
- `POST /api/kb/datasets`
- `DELETE /api/kb/datasets`
- `DELETE /api/kb/datasets/{dataset_id}`
- `POST /api/kb/ingest`
- `POST /api/kb/readiness`
- `POST /api/kb/ingestion-status`
- `GET /api/kb/datasets/{dataset_id}/readiness`
- `GET /api/kb/datasets/{dataset_id}/ingestion-status`
- `GET /api/kb/datasets/{dataset_id}/documents`
- `POST /api/kb/datasets/{dataset_id}/parse`
- `GET /api/kb/datasets/{dataset_id}/documents/{document_id}/graph`
- `POST /api/ask`
- `GET /api/workflows`
- `GET /api/workflows/resumable-asks`
- `GET /api/workflows/{run_id}`
- `POST /api/workflows/{run_id}/resume-ask`
- `POST /api/workflows/{run_id}/memory-review`
- `GET /api/workflows/{run_id}/export`
- `POST /api/sources/read`
- `POST /api/memory/update-review`
- `POST /api/memory/delete-review`
- `GET /api/memory/{memory_target_id}/lifecycle`
- `GET /api/reviews`
- `GET /api/reviews?status={status}`
- `GET /api/reviews/{review_id}`
- `POST /api/reviews/{review_id}/decision`
- `POST /api/reviews/{review_id}/revision`
- `POST /api/reviews/{review_id}/apply-memory`
- `GET /api/audit`
- `GET /api/audit?action={action}`

The bundled frontend exposes Home, Knowledge Bases, Ask, Reader, Writing,
Review, Activity, and Settings. It is served by the Product API and uses only
same-origin `/api/...` calls. Ask responses include explicit loop steps so users
and agents can see scope checks, KB readiness, retrieval, context inspection,
proposal creation, review creation or skipping, and transient brief preparation.
Home loads `/api/workspace/status` to show product-level next actions, including
ready-to-ask scopes, ingestion waits, resumable Ask workflows, pending reviews,
and accepted durable memory awaiting apply. Each next action includes stable
PSKA tool/API/view hints and safe parameters, so Hermes and the frontend can
navigate the workflow without inspecting provider internals. Mutating frontend
actions refresh this status after completion so the Home guidance follows the
current workflow state. Workspace status reports both aggregate KB readiness and
per-dataset readiness, so a newly uploaded processing dataset does not hide
other ready datasets from Ask. Workspace status also translates lower-level
ingestion job actions such as `start_parse` into stable product actions such as
`parse_documents`. Home next-action buttons can prefill Ask scope and check
readiness, start document parsing, resume blocked Ask workflows, open pending
reviews, and apply already accepted durable memory through Product API routes.
Readiness responses include normalized `ingestion_status` job summaries with
phase, progress, counts, next actions, and failure reasons so frontend and agent
flows can distinguish uploaded, parsing, embedding, indexing, ready, failed,
and cancelled scopes.
Settings loads `/api/policy` as the product-level workspace governance surface,
including durable proposal kinds, configured durable-memory action, available
modes, and the fact that transient results skip durable governance. Settings
also loads `/api/capabilities` as the product-level capability contract, and
Writing/Review durable-memory controls stay disabled until the selected memory
operation is explicitly reported as supported.
Ask persists the loop summary on the workflow so Writing can reopen governance
state, durable/transient status, review requirements, and steps later. Ask
includes a dataset/document picker that syncs to explicit scope IDs and result
actions for Writing, Review, and accepted memory application. Ask can tune loop
depth with max iterations, required context count, explicit additional
retrieval queries, bounded source inspection, and optional graph retrieval
inside the selected scope.
Additional retrieval queries come from the user or agent and are recorded in the
PSKA loop; runtime code does not add case-specific query expansion. Source
inspection reads unique retrieved source refs through PSKA adapters, records
`source.inspect` loop metadata, and writes `source.read` audit records. Graph retrieval is passed as a PSKA retrieval hint,
recorded in loop steps and audit metadata, and remains behind adapters. Ask also
searches governed durable memory and keeps memory facts separate from external
source retrieval, so memory can inform later work without acting as a source
fallback. If the required context count is not met, Ask returns
`insufficient_context`, shows any retrieved partial context, and does not create
a proposal, review, or export.
If the selected dataset or document scope is not ready, Ask records a blocked
workflow with readiness diagnostics so Writing, Activity, and MCP tools can
recover the blocked state after ingestion continues. Users and agents can resume
that blocked Ask from the stored workflow when the selected scope becomes ready;
the resumed Ask creates a new audited workflow linked back to the blocked run.
The Ask result view can refresh the blocked workflow's readiness and enable
resume in place when the scope becomes ready, or track readiness and resume
automatically after a user starts tracking.
Users can also turn an existing sourced workflow into a durable memory review
through an explicit Memory Review action; this creates a memory candidate and
governed review path without re-retrieval or direct memory write, following the
workspace policy for manual review, auto accept, or auto apply. The frontend
opens the resulting Review record and focuses Activity on the actual governance
event.
Review links open exact Review API records by ID.
The Review queue can filter by status while Home keeps an independent pending
review summary. Review records expose source trace fields, and Review cards can
open cited sources through the Product API Reader before a durable decision is
made, and can open the originating Writing workflow context. Review cards show
status-specific actions: pending reviews can be decided,
accepted durable reviews can be applied, `needs_edit` reviews can be revised,
and rejected reviews are closed. After a review decision, the frontend keeps the
decided review visible so the next action is available. Reviews marked `needs_edit` can create a revised candidate review while
preserving the original review history; Review API records expose revision
lineage so old and revised candidates can be traced in both directions. Review
decisions and memory apply/update/delete actions refresh the current Ask/Writing
state, and applied memory state is served back through Review API records.
Writing shows the applied durable knowledge result and links to its lifecycle.
Locked/applied Review cards can also open the durable memory lifecycle directly.
Applied memory can be found by later Ask runs through the memory adapter and is
shown in Writing as durable workspace context with its supporting source trace.
Writing can create a governed update review from an explicit MemoryFact when
the selected memory backend reports update support; the update applies only
after the review is accepted and records version metadata in the memory apply
result and `memory.update` audit record.
Writing can create a governed deletion review from an explicit MemoryFact; the
delete applies only after the review is accepted and produces a `memory.delete`
audit record.
Writing can inspect a MemoryFact lifecycle from PSKA audit records, showing the
reviewed apply/update/delete chain without calling a memory backend directly.
Once durable memory has been applied, the accepted review decision is locked;
future changes require a new proposal and review. Activity
shows the recent audit trail with action filtering, including workflow
export records from explicit export actions, review/memory apply/update/delete records
with proposal, run, and source trace metadata, and mechanical source operations
such as dataset creation, ingestion, parsing, source reads, and graph reads.
Knowledge Base create, upload, parse, source read, and graph read actions
refresh Activity and focus the matching action after the source operation completes. If the selected dataset or
document scope is not ready for retrieval, Ask returns a structured `not_ready`
result instead of starting retrieval. The `not_ready` result has a recoverable
workflow run and audit trail rather than a disposable error response. Knowledge Bases shows dataset/document
readiness and normalized ingestion status, can start parsing for loaded unready
documents, offers status actions such as parse, track, and ask when the scope is
ready, automatically refreshes ingestion status after uploads, and preselects a
ready dataset in Ask scope when ingestion completes. Dataset cards can open Ask,
set an existing upload target, or load document status without copying dataset
IDs, and newly created knowledge bases are selected as upload targets
automatically. Upload keeps the resolved target selected for additional files.
Ready document cards can also set a single-document Ask scope directly.
Ask can check selected scope readiness before running the agentic loop,
using the same Product API readiness gate that protects retrieval, and then
offers readiness actions such as Run Ask, Parse Scope, Track Status, and Open
Status without leaving the selected scope. Blocked Ask results reuse those
readiness actions while keeping Resume Ask as the path that preserves the
original workflow request. It can also open optional document
structure graph data through Product API when the KB backend exposes it. Writing
opens workflow state, work product, source manifest, and context without
creating an export, then exports traceable Markdown or JSON work products
through explicit Product API actions; ready Ask results can also trigger those
Markdown/JSON exports directly and open the generated work product in Writing.
Explicit export requires a sourced work product: empty diagnostic workflows can
be inspected in Writing, but they cannot be exported as briefs until a proposal
and source trace exist.
Exported work products include the
workflow export audit event, inspected source snippets, and durable-memory
source trace in their traceability metadata. Settings shows runtime provider
configuration, Product API diagnostics for review store, KB gateway, retrieval,
and memory connectivity, the explicit capability contract, and an explicit
retrieval probe for the selected dataset before running Ask. Settings also
exposes a memory probe for verifying the configured memory backend search path
through PSKA instead of provider-native tools. Runtime diagnostics include a
read-only memory search contract check so a shallow Graphiti health check cannot
be mistaken for a working memory backend. Settings and Product API runtime
context expose the derived memory namespace. Product API health, diagnostics,
explicit probe audit records, and other audit records include the runtime
workspace/tenant context from `PSKA_WORKSPACE_ID` and `PSKA_TENANT_ID`; the
review store uses that same context to scope workflows, reviews, memory apply
records, and audit reads, while memory adapters use it to scope durable memory
backend search and writes.
