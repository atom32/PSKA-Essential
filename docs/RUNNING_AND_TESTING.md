# Running and Testing

PSKA-Essential should not be developed as a giant all-in-one stack. Its value is
the adapter boundary, so the runtime model is layered.

## Modes

### 1. Core Development

No external services are required.

Use this mode for contracts, workflow logic, review gate, audit, MCP tool shape,
and export behavior.

```bash
cd /Users/xudawei/PSKA-Essential
PYTHONPATH=src python3 -m unittest discover -s tests
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=:memory: PYTHONPATH=src python3 -m pska_essential --list-tools
```

This mode uses fake adapters only through explicit test helpers or
`PSKA_DEV_FAKE=1`; fake adapters are not runtime fallbacks. Core development
should always stay fast. In explicit fake KB mode, uploaded text documents are
kept in the fake KB gateway and are retrievable by fake retrieval, so local
upload-to-Ask checks do not need RAGFlow.

### 2. Hermes MCP Development

Hermes runs independently and starts PSKA-Essential as a stdio MCP server.

Use this mode to validate agent-facing tool discovery and workflow behavior.
Hermes config should point only at PSKA-Essential MCP, not at RAGFlow or Graphiti
directly.

Example server env:

```yaml
mcp_servers:
  pska-essential:
    command: "/Users/xudawei/PSKA-Essential/.venv/bin/python"
    args: ["-m", "pska_essential"]
    env:
      PYTHONPATH: "/Users/xudawei/PSKA-Essential/src"
      PSKA_DEV_FAKE: "1"
      PSKA_REVIEW_DB: "/Users/xudawei/PSKA-Essential/.pska-essential/review.sqlite3"
      PSKA_RETRIEVAL_PROVIDER: "fake"
      PSKA_MEMORY_PROVIDER: "fake"
```

Hermes test:

```bash
hermes mcp test pska-essential
```

### 3. Product API And Frontend Development

The Product API serves the frontend and exposes stable PSKA routes. The frontend
must call only this API; it must not call external providers directly.

Explicit local fake mode:

```bash
cd /Users/xudawei/PSKA-Essential
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 \
  PYTHONPATH=src python3 -m pska_essential.product_api
open http://127.0.0.1:8765
```

In this mode, create or select a fake dataset, upload a text document, keep
`Parse after upload` enabled, and then Ask against that dataset ID. The returned
context should cite the uploaded fake document.

Live RAGFlow/Graphiti mode uses the same Product API command after setting
providers explicitly:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export PSKA_MEMORY_PROVIDER=graphiti
export RAGFLOW_BASE_URL=http://127.0.0.1:9380
export RAGFLOW_API_KEY=...
export GRAPHITI_BASE_URL=http://127.0.0.1:8000
export GRAPHITI_GROUP_ID=pska-essential
export PSKA_GOVERNANCE_DURABLE_MEMORY=manual_review
export PSKA_WORKSPACE_ID=default
export PSKA_TENANT_ID=
PYTHONPATH=src python3 -m pska_essential.product_api
```

The Alpha frontend includes Home, Knowledge Bases, Ask, Reader, Writing,
Review, Activity, and Settings. Home shows PSKA workspace next actions for
ready Ask scopes, ingestion waits, resumable Ask workflows, pending reviews,
and accepted durable memory awaiting apply. Ask displays explicit PSKA-controlled loop steps,
including KB readiness before retrieval, and includes a dataset/document picker
that syncs to explicit scope IDs. Ask can tune loop depth with max iterations,
required context count, explicit additional retrieval queries, and optional
graph retrieval inside the selected scope. Additional retrieval queries are
provided by the user or agent, stored with the workflow request, and recorded in
loop steps; PSKA does not add runtime case-specific query expansion.
Ask also inspects a bounded number of unique retrieved sources through the
retrieval adapter. Source inspection snippets are stored on the workflow
artifact and `source.read` audit records are written through the same service
path as manual Reader actions.
Settings loads `/api/policy` to show the workspace governance policy, including
durable proposal kinds, durable-memory action, available modes, and the rule
that transient results skip durable governance.
Graph retrieval is passed through PSKA retrieval contracts as a scoped hint and
is visible in loop steps and audit metadata. Ask also searches governed durable
memory and keeps those facts separate from external source retrieval, so memory
can inform later work without satisfying source readiness or context minimums.
If the required context count is not met, Ask returns `insufficient_context`,
shows any retrieved partial context, and does not create a proposal, review, or
export. If KB readiness blocks the selected scope, Ask returns `not_ready` and
persists a blocked workflow with readiness diagnostics so frontend and MCP
flows can recover it later. Successful Ask results prepare a transient sourced brief and artifact
without creating workflow export audit records. Ready Ask results can trigger
explicit Markdown/JSON exports and open the generated work product in Writing,
or jump directly to Writing or Review, through Product API.
Ask results can apply accepted memory patches through Product API.
Writing can also turn an existing sourced transient workflow into a governed
Memory Review through Product API; this is the explicit transition from
transient work product to durable memory candidate and follows workspace policy
for manual review, auto accept, or auto apply. The frontend opens the resulting
Review record and focuses Activity on the actual governance event.
Durable memory review creation, review acceptance, and memory apply require a
source trace; source-less durable proposals fail explicitly instead of becoming
workspace memory.
Review decisions and memory apply/update/delete actions refresh the current
Ask/Writing state, and applied memory state is served back through Review API
records.
Writing shows the applied durable knowledge result and links to its lifecycle.
Locked/applied Review cards can also open the durable memory lifecycle directly.
Review cards can open the originating Writing workflow context.
Review cards show status-specific actions: pending reviews can be decided,
accepted durable reviews can be applied, `needs_edit` reviews can be revised,
and rejected reviews are closed.
After a review decision, the frontend keeps the decided review visible so the
next action is available.
Reviews marked `needs_edit` can create a revised candidate review from the same
workflow and source trace instead of mutating the original review. Review API
records expose revision lineage so the original and revised candidates remain
traceable.
Later Ask runs can find applied memory through the memory adapter and Writing
shows matched durable memory alongside source context, including the memory
fact's supporting source trace.
Writing can create an update review from an explicit MemoryFact; update is
applied only after review acceptance and records version metadata.
Writing can create a deletion review from an explicit MemoryFact; deletion is
applied only after review acceptance and produces a `memory.delete` audit record.
Writing can inspect a durable MemoryFact lifecycle from PSKA audit records,
showing reviewed apply/update/delete history without calling backend memory
history APIs.
Reader inspects sources through Product API only. Writing opens workflow state,
work product, source manifest, and context without creating an export, then
exports Markdown or JSON through explicit Product API actions. Ready Ask results
can also trigger the same explicit exports and open Writing. Exports include
the work product, source manifest, inspected source snippets, durable-memory
source trace, supporting context, and traceability metadata, and create workflow
audit records. Activity shows the recent audit
trail, including review and memory apply/update/delete records with proposal,
run, and source trace metadata. Upload, parsing,
embedding, indexing, and optional graph extraction readiness remain visible
states rather than hidden side effects. After upload, the Knowledge Bases view
can start parsing for loaded unready documents, open optional document
structure graph data through Product API, and refreshes the selected dataset's
document status, readiness, and normalized ingestion job summary until
processing reaches a terminal state.
Settings shows runtime provider configuration and Product API diagnostics for
review store, KB gateway, retrieval, and memory connectivity. Product API
health, diagnostics, and audit records include the runtime workspace/tenant
context from `PSKA_WORKSPACE_ID` and `PSKA_TENANT_ID`.

Durable memory governance modes:

- `manual_review`: create a pending review before durable memory can be applied.
- `auto_accept`: create and accept a review through workspace policy, but leave
  memory application explicit.
- `auto_apply`: create and accept a review, then apply memory through policy.

After durable memory has been applied, the accepted review decision is locked.
Changing durable knowledge requires a new proposal and review instead of
rewriting the applied decision.

### 4. Adapter Integration Development

RAGFlow and Graphiti run independently. PSKA-Essential only receives env vars
pointing at them.

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

Current local component install:

```bash
cd /Users/xudawei/PSKA-Components/graphiti
docker compose -f docker-compose.pska.yml --env-file .env.pska up -d
curl http://127.0.0.1:8000/healthcheck
```

The local Graphiti container needs `OPENAI_API_KEY` in
`/Users/xudawei/PSKA-Components/graphiti/.env.pska` before real memory
extraction/search should be used.

This is the normal development setup. Do not make PSKA-Essential own those
processes unless the test explicitly targets orchestration.

Install external systems as their own projects. Keep PSKA-Essential dependency
extras only for SDK/client libraries:

```bash
# PSKA-side optional client dependencies
uv sync --extra ragflow
uv sync --extra graphiti
```

RAGFlow itself should be installed from the RAGFlow project, normally with its
Docker Compose setup. Graphiti can either run as its own Docker Compose service
or be used as a library from PSKA-Essential against an independently running
Neo4j/FalkorDB database.

On this Apple Silicon machine, RAGFlow is checked out at
`/Users/xudawei/PSKA-Components/ragflow` and runs from source. Its base
services run through `docker/docker-compose-base.yml`; backend and frontend are
managed by user launchd agents:

```bash
launchctl kickstart -k gui/$(id -u)/com.pska.ragflow
launchctl kickstart -k gui/$(id -u)/com.pska.ragflow.web
```

Local endpoints:

```bash
curl http://127.0.0.1:9380/api/v1/system/ping
open http://127.0.0.1:9222
```

Point `RAGFLOW_BASE_URL` at `http://127.0.0.1:9380`. Retrieval calls still
require a RAGFlow API key.

RAGFlow upload/parse operations use the same API key through PSKA MCP tools:

```text
pska_kb_ingest_files -> pska_kb_document_status -> pska_kb_ingestion_status
  -> pska_kb_readiness
  -> pska_agentic_question_start
  -> pska_agentic_question_resumable to find blocked Ask runs
  -> pska_agentic_question_resume if the first Ask was readiness-blocked
```

These tools do not make PSKA-Essential a KB implementation. They call RAGFlow
dataset/document/chunk APIs and return normalized IDs, readiness, ingestion
status, and optional structure graph data.
`pska_kb_ingest_files` and `pska_kb_parse_documents` include normalized
`readiness` and `ingestion_status` in their returned operation payloads.

Treat RAGFlow ingestion as asynchronous. Uploading a document only starts the
chain of parsing, chunking, embedding, and indexing. Frontend and agent flows
must check readiness before assuming retrieval will work. Readiness-blocked
Ask calls are persisted as blocked workflows with audit records rather than
discarded one-off errors. Use `pska_agentic_question_resume` or
`POST /api/workflows/{run_id}/resume-ask` to retry the stored Ask request after
the selected scope becomes ready. Use `pska_agentic_question_resumable` or
`GET /api/workflows/resumable-asks` to list readiness-blocked Ask runs with a
fresh readiness check. The frontend Ask result can refresh a blocked run's
readiness in place and enable resume when the stored scope becomes ready; the
user can also start `Track & Resume` to poll readiness and resume automatically.
Use `pska_kb_ingestion_status`, `POST /api/kb/ingestion-status`, or
`GET /api/kb/datasets/{dataset_id}/ingestion-status` when the user or agent
needs a normalized job summary with phase, progress, next actions, and failure
reasons before deciding whether to wait, parse, inspect a failure, or Ask.
The frontend Knowledge Bases view renders those next actions as explicit status
buttons when possible. When ingestion polling observes a ready dataset, the
frontend preselects that dataset in Ask scope but still waits for the user or
agent to provide the question. Dataset cards expose Ask, Upload, and Status
actions so users can continue the workflow without copying dataset IDs between
forms, and newly created knowledge bases are selected as upload targets
automatically. Upload keeps the resolved target selected for additional files.
Ready document cards can also set a single-document Ask scope directly.
Ask exposes a scope readiness check that calls the Product API readiness
gate before the agentic loop starts; submitting Ask still performs the backend
readiness gate and returns a resumable blocked workflow when needed. The Ask
readiness preview renders explicit actions for the checked scope, including Run
Ask, Parse Scope, Track Status, and Open Status. Blocked Ask results reuse the
same scope actions and keep Resume Ask as the preserved-request path once the
scope becomes ready.
Use `pska_workspace_status` or `GET /api/workspace/status` for the same
product-level next-action summary from Hermes or the frontend without exposing
provider APIs. Each returned action includes stable PSKA tool/API/view hints
and safe parameters, such as ready dataset IDs or the relevant review/run ID.
The frontend refreshes this summary after KB, Ask, review, and memory actions
so Home does not keep stale guidance. Workspace status includes per-dataset
readiness; ready datasets remain actionable even while another selected dataset
is still parsing, embedding, or indexing. It also translates ingestion job
actions such as `start_parse` into stable PSKA product actions such as
`parse_documents`.

Use `pska_retrieval_probe` or `POST /api/runtime/retrieval-probe` against a
selected ready dataset when RAGFlow is reachable but Ask still fails at
retrieval time. The probe first checks PSKA readiness, then runs a limit-1
retrieval through the configured retrieval adapter, records a `retrieval.probe`
audit event, and surfaces provider errors such as missing embedding model
providers explicitly.

### 5. Full Demo / Deployment

Use Docker Compose or another yaml-based orchestrator only for full-stack demo,
CI integration, or deployment packaging.

The compose file should start:

- PSKA-Essential MCP server
- Graphiti backend and graph database
- RAGFlow backend and its dependencies
- optional Hermes container or host-side Hermes config

This is intentionally not the default development path because it slows down the
inner loop and hides adapter boundaries.

## Test Pyramid

Core tests:

- fake adapter E2E
- review gate
- reviewed memory update/version lifecycle
- reviewed memory deletion lifecycle
- MCP tool registry
- export
- adapter replacement with company stub
- KB gateway glue without live RAGFlow
- Product API and frontend boundary smoke tests
- agentic Ask loop diagnostics and durable-governance defaults
- explicit retrieval probe diagnostics for selected ready scopes

Integration tests:

- RAGFlow retrieval mapping against a live RAGFlow instance
- Graphiti reviewed memory apply against a live Graphiti instance
- Hermes MCP discovery and smoke workflow
- Product API against live RAGFlow KB operations

Full-stack tests:

- one command starts the whole demo stack
- Hermes completes the workflow through MCP
- RAGFlow and Graphiti can be swapped for company GraphRAG without changing MCP
  tools
- backend failures do not fall back to fake data or another provider

## Rule of Thumb

If you are changing PSKA contracts or workflow behavior, use core development.
If you are validating one external component, run only that component plus
PSKA-Essential. If you are proving the product demo, use the full yaml stack.

Never rely on implicit provider defaults. Set providers intentionally for every
runtime mode.
