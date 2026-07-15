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
upload-to-Ask checks do not need RAGFlow. Fake KB is intentionally text-only:
PDF/OCR/binary parsing, embedding, and indexing should use RAGFlow or another
real KB provider. PDF-like files uploaded to fake KB are marked as failed
ingestion, not fake-ready context.

### 2. Hermes MCP Development

Hermes runs independently and starts PSKA-Essential as a stdio MCP server.

Use this mode to validate agent-facing tool discovery and workflow behavior.
Hermes config should point only at PSKA-Essential MCP, not at RAGFlow or Graphiti
directly.

Example server env:

```yaml
mcp_servers:
  pska-essential:
    command: "python3"
    args:
      - "-m"
      - "pska_essential"
      - "--env-file"
      - "/Users/xudawei/PSKA-Essential/.env.pska"
    env:
      PYTHONPATH: "/Users/xudawei/PSKA-Essential/src"
```

Use `.env.pska` for explicit runtime configuration. For local fake development,
put `PSKA_DEV_FAKE=1` and fake providers in that env file; for live validation,
use RAGFlow/Graphiti values. Do not add RAGFlow or Graphiti MCP servers to the
Hermes workflow.

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
context should cite the uploaded fake document. For PDFs such as annual
reports, switch to RAGFlow-backed KB mode so parsing and embedding are handled
by the external KB.

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

The selected live providers must have their required connection env configured
before Product API, MCP, or component-check startup. RAGFlow retrieval/KB
requires `RAGFLOW_BASE_URL` and `RAGFLOW_API_KEY`; Graphiti memory requires
`GRAPHITI_BASE_URL`. Missing values fail explicitly and are not replaced by
implicit localhost, empty-key, fake, or alternate-provider defaults.
Instead of exporting each value in the shell, copy `.env.example` to an explicit
runtime file such as `.env.pska`, fill in real keys, and pass it with
`--env-file .env.pska` or `make ... ENV_FILE=.env.pska`. PSKA does not
auto-load env files, and the same provider validation still applies.

The Alpha frontend includes Home, Knowledge Bases, Ask, Reader, Writing,
Review, Activity, and Settings. Home shows PSKA workspace next actions for
ready Ask scopes, ingestion waits, resumable Ask workflows, pending reviews,
and accepted durable memory awaiting apply. Home action buttons can prefill Ask
scope and check readiness, start document parsing, resume blocked Ask
workflows, open pending reviews, and apply already accepted durable memory
through Product API routes. The Knowledge Bases upload form can either upload
documents for later Ask or run the file-first ingest loop through
`POST /api/ingest-loop`; the loop uses the configured KB/retrieval/memory
adapters and opens Writing only after a sourced transient work product is
exported. The form's Wait checkbox controls whether Run Loop waits for PSKA
readiness or quickly returns a resumable not-ready workflow for long parsing,
embedding, and indexing jobs. If parsing, embedding, indexing, retrieval, or
export is not ready, the UI keeps the explicit failure/not-ready state and does
not substitute fake context. The upload loop exposes the same PSKA loop controls
as Ask for limit, max iterations, minimum context, additional retrieval queries,
source inspection, proposal kind, optional review, and graph-aware retrieval.
Its Product API result exposes proposal, review, review-decision, memory-apply,
loop, and export fields, so the frontend can continue the Review workflow
directly after a file-first run. If the uploaded scope is still
processing, the frontend opens a resumable blocked Ask with Track & Resume
actions; failed or cancelled ingestion remains an explicit status/cleanup
condition. Ask displays explicit PSKA-controlled loop steps,
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
Writing can create an update review from an explicit MemoryFact when the memory
backend reports update support; update is applied only after review acceptance
and records version metadata.
Writing can create a deletion review from an explicit MemoryFact; deletion is
applied only after review acceptance and produces a `memory.delete` audit record.
Writing can inspect a durable MemoryFact lifecycle from PSKA audit records,
showing reviewed apply/update/delete history without calling backend memory
history APIs.
Reader inspects sources through Product API only. Writing opens workflow state,
work product, source manifest, and context without creating an export, then
exports Markdown or JSON through explicit Product API actions. Ready Ask results
can also trigger the same explicit exports and open Writing. Explicit export
requires a sourced work product; empty diagnostic workflows remain inspectable
but are not exportable briefs until a proposal and source trace exist. Exports
include the work product, source manifest, inspected source snippets,
durable-memory source trace, supporting context, and traceability metadata, and
create workflow audit records. Activity shows the recent audit
trail, including review and memory apply/update/delete records with proposal,
run, and source trace metadata. Upload, parsing,
embedding, indexing, and optional graph extraction readiness remain visible
states rather than hidden side effects. After upload, the Knowledge Bases view
can start parsing for loaded unready documents, open optional document
structure graph data through Product API, and refreshes the selected dataset's
document status, readiness, and normalized ingestion job summary until
processing reaches a terminal state.
Settings shows runtime provider configuration and Product API diagnostics for
review store, KB gateway, retrieval, and memory connectivity. It also loads
`/api/capabilities` as the explicit product capability contract; Review and
Writing durable-memory controls stay disabled until the selected operation is
reported as supported. Runtime diagnostics include a read-only memory search
contract check, while Settings exposes a component check plus focused retrieval,
memory, and live closed-loop probes through Product API routes for explicit
user-triggered checks. Product API health, diagnostics, and audit records
include the runtime workspace/tenant context from `PSKA_WORKSPACE_ID` and
`PSKA_TENANT_ID`, including the derived PSKA `memory_namespace` shown in
Settings. Workflow, review, memory-apply, and audit reads are scoped by the
same workspace/tenant context in the review store. Durable memory search and
reviewed writes receive the same context as a PSKA `memory_namespace`; fake,
company-stub, and Graphiti adapters use it to keep backend memory scoped to the
same workspace boundary.

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

Graphiti live memory writes remain review-gated through PSKA. The current
adapter supports reviewed add and reviewed entity-edge delete. Reviewed update
requires a backend with a transactional update contract and fails explicitly for
Graphiti instead of doing hidden delete/add work. Memory operation capabilities
are exposed through the Product API capabilities route, MCP capabilities tool,
health, diagnostics, and workspace status so the frontend and Hermes can avoid
unsupported durable actions before creating review items. Historical accepted
reviews that target unsupported backend operations remain visible as inspect
actions instead of being offered as apply actions. When workspace or tenant
context is configured, the adapter maps PSKA `memory_namespace` to a derived
Graphiti group ID under `GRAPHITI_GROUP_ID`.

Current local component install:

```bash
cd /Users/xudawei/PSKA-Components/graphiti
docker compose -f docker-compose.pska.yml --env-file .env.pska up -d
curl http://127.0.0.1:8000/healthcheck
```

The local Graphiti container needs `OPENAI_API_KEY` in
`/Users/xudawei/PSKA-Components/graphiti/.env.pska` before real memory
extraction/search should be used.
The `/healthcheck` endpoint only proves the Graphiti service is running. Use
runtime diagnostics, `pska_memory_probe`, or `POST /api/runtime/memory-probe`
to prove that the configured Graphiti memory adapter can complete search
through its LLM and embedding provider configuration. The explicit probe
rejects fake memory by default, writes `memory.probe` audit, and surfaces
provider errors explicitly.

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
pska_kb_delete if a bad development dataset should be removed
  -> pska_ingest_loop for the one-call file-to-work-product path
  -> pska_ingest_loop_resume if that loop stopped on processing ingestion
  -> or pska_kb_ingest_files -> pska_kb_document_status -> pska_kb_ingestion_status
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
the selected scope becomes ready. For a blocked `pska_ingest_loop` run, use
`pska_ingest_loop_resume` or
`POST /api/workflows/{run_id}/resume-ingest-loop` so the original upload -> Ask
-> export intent is preserved. Use `pska_agentic_question_resumable` or
`GET /api/workflows/resumable-asks` to list readiness-blocked Ask runs with a
fresh readiness check. The frontend Ask result can refresh a blocked run's
readiness in place and enable resume when the stored scope becomes ready; the
user can also start `Track & Resume` from Ask, Resumable Asks, or Home next
actions to poll readiness and resume automatically.
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
same scope actions and keep Resume Ask or Resume Loop as the preserved-request
path once the scope becomes ready.
Use `pska_capabilities_get` or `GET /api/capabilities` for the stable product
operation capability contract. Use `pska_runtime_diagnostics` or
`GET /api/runtime/diagnostics` for read-only provider and adapter contract
diagnostics. Use `pska_workspace_status` or `GET /api/workspace/status` for the
same product-level next-action summary from Hermes or the frontend without
exposing provider APIs. Each returned action includes stable PSKA tool/API/view
hints and safe parameters, such as ready dataset IDs or the relevant review/run
ID. In a fresh empty workspace, the first product action is
`run_file_to_work_product_loop`, which points Hermes/frontends to
`pska_ingest_loop` / `POST /api/ingest-loop`; lower-level KB ingest remains
available only for manual dataset control. Home opens the Knowledge Bases Run
Loop form for that action and preloads the safe loop defaults.
The frontend refreshes this summary after KB, Ask, review, and memory actions
so Home does not keep stale guidance. Workspace status includes per-dataset
readiness; ready datasets remain actionable even while another selected dataset
is still parsing, embedding, or indexing. It also translates ingestion job
actions such as `start_parse` into stable PSKA product actions such as
`parse_documents`. Home can execute the safe product actions directly:
prefilling Ask scope and checking readiness, starting parse, resuming blocked
Ask workflows, opening reviews, and applying accepted durable memory.
Use `pska-essential-workspace-status --env-file .env.pska` or
`make workspace-status ENV_FILE=.env.pska` for the same next-action contract
from the terminal before choosing a live proof command.

Use `pska_retrieval_probe` or `POST /api/runtime/retrieval-probe` against a
selected ready dataset when RAGFlow is reachable but Ask still fails at
retrieval time. The probe first checks PSKA readiness, then runs a limit-1
retrieval through the configured retrieval adapter, records a `retrieval.probe`
audit event, and surfaces provider errors such as missing embedding model
providers explicitly.

Use runtime diagnostics for a read-only memory search contract check when
Graphiti is reachable but memory search or governed memory workflows fail. Use
`pska_memory_probe` or `POST /api/runtime/memory-probe` when that check should
be recorded as an explicit operation. The probe calls the configured memory
adapter through PSKA, records a `memory.probe` audit event, and rejects fake
memory by default so it cannot be mistaken for a live component proof. A
Graphiti health check can pass while LLM or embedding provider configuration
is still missing; diagnostics and the probe report that condition as a provider
error instead of using fallback data.

Use `make live-component-check`, `pska_component_check`, or
`POST /api/runtime/component-check` when the question is whether the configured
components can support the product loop. The component check runs runtime
diagnostics, explicit memory probe, retrieval probe, and live closed-loop probe
in one structured result. It exits successfully only when the full component
proof passes; missing dataset scope, skipped core checks, fake live providers,
memory search failures, and retrieval/Ask/export failures are surfaced as
explicit step failures. Startup configuration errors, such as a selected
RAGFlow provider without `RAGFLOW_API_KEY`, are returned as structured JSON with
a nonzero exit instead of falling through to fake data. A selected scope that is
still parsing, chunking, embedding, or indexing returns `incomplete`, not
`error`, because the next action is to wait for KB readiness.

Use `pska_live_closed_loop_probe`, `POST /api/runtime/closed-loop-probe`, or
`make live-closed-loop` when you only want the sourced Ask/export portion. The
live probe rejects fake KB and fake retrieval providers, then runs readiness,
retrieval, agentic Ask, bounded source inspection, and explicit export for a
transient work product. It does not write durable memory or graph state; use the
normal Ask/review/apply workflow for that. It writes a `closed_loop.probe` audit
record and reports the exact stage that failed, such as `not_ready`,
`retrieval_error`, `agentic_error`, or `export_error`. Successful probes include
context, source, and source-inspection counts.

Use `POST /api/ingest-loop`, `pska_ingest_loop`,
`make live-ingest-loop`, or `pska-essential-ingest-loop` when the proof should
start from local files instead of an already-ready dataset. The loop calls the
configured KB gateway to create or select a dataset, upload files, start
parsing, poll PSKA readiness, run the agentic Ask loop, and export a sourced
transient work product. It writes normal `kb.ingest`, `agentic_loop.complete`,
and `workflow.export` audit records when the scope is ready. If parsing, OCR,
embedding, or indexing is still processing, the loop records a resumable blocked
Ask and returns `status=not_ready` without retrieval/export. Failed or cancelled
ingestion returns `status=not_ready` without creating a resumable Ask. Not-ready
upload-loop results include stable `next_actions`; processing-blocked results
also include a `resume` contract pointing to the PSKA resume tool/API. Resume a
processing-blocked upload loop with `pska_ingest_loop_resume`,
`POST /api/workflows/{run_id}/resume-ingest-loop`,
`pska-essential-ingest-loop-resume <run_id>`, or
`PSKA_LOOP_RUN_ID=<run_id> make live-ingest-loop-resume` after readiness reports
the selected scope is ready.

When RAGFlow reports an embedding model binding failure such as a missing
provider for the selected dataset embedding model, PSKA normalizes the KB
readiness failure to `failure_code=embedding_provider_missing` and
`next_actions=["configure_embedding_provider"]`. Configure the embedding
provider or choose an available embedding model in the KB backend, then
re-parse/re-index the affected documents before running Ask again.
For new RAGFlow-backed datasets, `pska_kb_create`, `pska_kb_ingest_files`, and
the Product API accept optional `embedding_model`. Leave it empty to use the
RAGFlow tenant default, or pass a model/provider name that RAGFlow has already
configured. PSKA validates required RAGFlow connection env, but RAGFlow remains
the authority for embedding/model availability.
For development maintenance, if a local dataset is already bound to a bad
embedding model, delete it through `pska_kb_delete` by dataset ID or name,
`DELETE /api/kb/datasets/{dataset_id}`, or the Knowledge Bases Delete All
action for a full development reset, then recreate and re-ingest. Do not rely
on fake adapters or silent provider fallback.

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export PSKA_MEMORY_PROVIDER=graphiti
export RAGFLOW_BASE_URL=http://127.0.0.1:9380
export RAGFLOW_API_KEY=...
export GRAPHITI_BASE_URL=http://127.0.0.1:8000
export GRAPHITI_GROUP_ID=pska-essential
export PSKA_LOOP_DATASET_NAME="live-upload-test"
export PSKA_LOOP_FILE_PATHS="/path/to/document.pdf"
export PSKA_LOOP_QUESTION="Summarize the uploaded documents with sources."
export PSKA_LIVE_DATASET_IDS=...
export PSKA_LIVE_QUESTION="Summarize the selected documents with sources."
make workspace-status
make live-ingest-loop
# If live-ingest-loop returned status=not_ready for a processing upload:
export PSKA_LOOP_RUN_ID=...
make live-ingest-loop-resume
make live-component-check
make live-closed-loop

# Equivalent explicit env-file form:
make workspace-status ENV_FILE=.env.pska
make live-ingest-loop ENV_FILE=.env.pska
make live-ingest-loop-resume ENV_FILE=.env.pska
make live-component-check ENV_FILE=.env.pska
make live-closed-loop ENV_FILE=.env.pska
```

If you are intentionally validating only the RAGFlow retrieval/Ask/export path
before Graphiti is configured, run `PSKA_COMPONENT_SKIP_MEMORY=1 make
live-component-check` or use `make live-closed-loop`. The skipped-memory
component check returns `incomplete`; do not treat a skipped or fake memory
check as proof that durable memory is wired.

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
- explicit memory probe diagnostics that reject fake memory by default
- live closed-loop probe diagnostics that reject fake KB/retrieval providers

Integration tests:

- RAGFlow retrieval mapping against a live RAGFlow instance
- Graphiti reviewed memory apply against a live Graphiti instance
- Graphiti reviewed memory delete through the adapter
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
