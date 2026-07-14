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
- require review before long-term memory writes;
- keep an audit trail;
- replace RAGFlow/Graphiti later through adapters.

Runtime behavior is universal and explicit: no case-specific shortcuts, no
hardcoded domains, and no silent fallback to fake data or another backend.
Document ingestion and embedding are treated as asynchronous jobs whose status
must be visible to users and agents.

## Quick Start

The code is intentionally stdlib-first so the fake workflow can run before any
external service is installed.

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

Graphiti memory:

```bash
export PSKA_MEMORY_PROVIDER=graphiti
export GRAPHITI_BASE_URL=http://localhost:8000
export GRAPHITI_GROUP_ID=pska-essential
```

Workspace governance policy:

```bash
# manual_review | auto_accept | auto_apply
export PSKA_GOVERNANCE_DURABLE_MEMORY=manual_review
export PSKA_WORKSPACE_ID=default
export PSKA_TENANT_ID=
```

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
- `pska_kb_ingest_files`
- `pska_kb_document_status`
- `pska_kb_readiness`
- `pska_kb_parse_documents`
- `pska_kb_graph_read`
- `pska_agentic_question_start`
- `pska_agentic_question_resumable`
- `pska_agentic_question_resume`
- `pska_workflow_list`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_review_list`
- `pska_review_get`
- `pska_export_brief`
- `pska_audit_list`

These tools are thin glue over RAGFlow plus the existing PSKA workflow gate:

```text
upload files -> RAGFlow dataset/documents/chunks -> PSKA scoped retrieve
  -> agent answer/proposal -> Review -> optional memory apply
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
- `GET /api/policy`
- `GET /api/runtime/diagnostics`
- `GET /api/kb/datasets`
- `POST /api/kb/datasets`
- `POST /api/kb/ingest`
- `POST /api/kb/readiness`
- `GET /api/kb/datasets/{dataset_id}/readiness`
- `GET /api/kb/datasets/{dataset_id}/documents`
- `POST /api/kb/datasets/{dataset_id}/parse`
- `GET /api/kb/datasets/{dataset_id}/documents/{document_id}/graph`
- `POST /api/ask`
- `GET /api/workflows`
- `GET /api/workflows/resumable-asks`
- `GET /api/workflows/{run_id}`
- `POST /api/workflows/{run_id}/resume-ask`
- `GET /api/workflows/{run_id}/export`
- `POST /api/sources/read`
- `GET /api/reviews`
- `GET /api/reviews?status={status}`
- `GET /api/reviews/{review_id}`
- `POST /api/reviews/{review_id}/decision`
- `POST /api/reviews/{review_id}/apply-memory`
- `GET /api/audit`
- `GET /api/audit?action={action}`

The bundled frontend exposes Home, Knowledge Bases, Ask, Reader, Writing,
Review, Activity, and Settings. It is served by the Product API and uses only
same-origin `/api/...` calls. Ask responses include explicit loop steps so users
and agents can see scope checks, KB readiness, retrieval, context inspection,
proposal creation, review creation or skipping, and transient brief preparation.
Ask persists the loop summary on the workflow so Writing can reopen governance
state, durable/transient status, review requirements, and steps later. Ask
includes a dataset/document picker that syncs to explicit scope IDs and result
actions for Writing, Review, and accepted memory application. Ask can tune loop
depth with max iterations, required context count, and optional graph retrieval
inside the selected scope. Graph retrieval is passed as a PSKA retrieval hint,
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
Review links open exact Review API records by ID.
The Review queue can filter by status while Home keeps an independent pending
review summary. Review records expose source trace fields, and Review cards can
open cited sources through the Product API Reader before a durable decision is
made. Review decisions and memory apply actions refresh the current Ask/Writing
state, and applied memory state is served back through Review API records.
Applied memory can be found by later Ask runs through the memory adapter and is
shown in Writing as durable workspace context with its supporting source trace.
Once durable memory has been applied, the accepted review decision is locked;
future changes require a new proposal and review. Activity
shows the recent audit trail with action filtering, including workflow
export records from explicit export actions, review/memory apply records
with proposal, run, and source trace metadata, and mechanical source operations
such as dataset creation, ingestion, parsing, source reads, and graph reads.
Knowledge Base create, upload, parse, source read, and graph read actions
refresh Activity and focus the matching action after the source operation completes. If the selected dataset or
document scope is not ready for retrieval, Ask returns a structured `not_ready`
result instead of starting retrieval. The `not_ready` result has a recoverable
workflow run and audit trail rather than a disposable error response. Knowledge Bases shows dataset/document
readiness, can start parsing for loaded unready documents, and automatically
refreshes ingestion status after uploads. It can also open optional document
structure graph data through Product API when the KB backend exposes it. Writing
opens workflow state, work product, source manifest, and context without
creating an export, then exports traceable Markdown or JSON work products
through explicit Product API actions. Exported work products include the
workflow export audit event and durable-memory source trace in their
traceability metadata. Settings shows
runtime provider configuration and Product API diagnostics for review store, KB
gateway, retrieval, and memory connectivity. Product API health, diagnostics,
and audit records include the runtime workspace/tenant context from `PSKA_WORKSPACE_ID`
and `PSKA_TENANT_ID`.
