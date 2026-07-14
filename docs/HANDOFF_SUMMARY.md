# PSKA-Essential Handoff Summary

Last updated: 2026-07-15

This document is the handoff point for a fresh Codex conversation.

## Product Direction

PSKA-Essential is now scoped as an Agent Knowledge Workflow Gate, not a full
knowledge base, GraphRAG engine, editor, or agent runtime.

Core product narrative:

- Run the agent knowledge workflow end to end.
- Ship v1 as Hermes-first rather than FastReAct-first.
- Keep PSKA universal: no domain-specific runtime logic or case-hardcoded
  shortcuts.
- Treat upload, parsing, embedding, and indexing as asynchronous product states.
- Keep agentic question loops first-class, but PSKA-controlled.
- Keep retrieval and memory backends replaceable.
- Require review before candidate knowledge enters long-term memory.
- Keep audit trails for retrieval, proposals, review decisions, memory writes,
  and exports.
- Fail explicitly instead of silently falling back to fake data or another
  backend.

The main user-facing story should not be "evidence is important." Evidence is
an internal quality mechanism. The product story is workflow closure and
replaceable infrastructure. Productization requires both a mature frontend and
the PSKA glue layer: the frontend owns human workflows, while the glue layer
owns orchestration, normalized contracts, review gates, audit, and tool access.

## Architecture

Current target architecture:

```text
Hermes Agent
  -> PSKA-Essential MCP
    -> Retrieval Adapter: RAGFlow / Company GraphRAG
    -> Memory Adapter: Graphiti / Company GraphRAG
    -> Review Store: SQLite
    -> Export: Markdown / JSON
```

Important constraints:

- Do not build a custom KB inside PSKA-Essential.
- Do not build a custom GraphRAG inside PSKA-Essential.
- Do not expose Graphiti MCP directly to Hermes.
- Do not expose raw RAGFlow response shape through PSKA MCP contracts.
- Do not migrate current PSKA/FastReAct job or prompt coupling into this repo.
- Do not add silent fallback behavior.
- Do not add hardcoded domain, company, document, or demo-case behavior to
  runtime code.

## Repositories And Paths

Main project:

```bash
/Users/xudawei/PSKA-Essential
```

External components:

```bash
/Users/xudawei/PSKA-Components
/Users/xudawei/PSKA-Components/graphiti
/Users/xudawei/PSKA-Components/ragflow
```

RAGFlow v0.20.3 image experiment:

```bash
/Users/xudawei/PSKA-Components/ragflow-v0.20.3
```

That experiment showed `0xgkd/ragflow-arm64:v0.20.3` is actually `linux/amd64`,
not native ARM64. The image was removed.

## Current PSKA-Essential Status

Implemented:

- Python project skeleton.
- Contract models.
- Ports.
- Fake retrieval and fake memory adapters.
- Explicit fake KB mode stores uploaded text documents and fake retrieval can
  retrieve them, so local upload-to-Ask checks do not require RAGFlow.
- RAGFlow KB gateway glue for dataset creation, document upload, parsing,
  status polling, and optional structure graph read.
- RAGFlow retrieval adapter.
- Graphiti memory adapter.
- Company GraphRAG stub.
- SQLite review store.
- Audit events.
- MCP tool registry.
- Product API over the PSKA workflow and KB gateway.
- Frontend Alpha served by the Product API, including Home, Knowledge Bases,
  Ask, Reader, Writing, Review, and Settings.
- PSKA-controlled agentic Ask loop with explicit loop diagnostics.
- Canonical KB readiness checks for Product API and MCP Ask entry points.
- Frontend Ask scope picker for dataset/document selection through Product API.
- Frontend Ask controls for loop max iterations, required context count, and
  optional graph retrieval within selected scope.
- Graph retrieval is passed through PSKA retrieval options to adapters, including
  the RAGFlow HTTP retrieval path, and is visible in loop/audit metadata.
- Ask searches governed durable memory through the memory adapter and keeps
  matched memory facts separate from external source retrieval.
- Ask returns `insufficient_context` without proposal/review/export when
  retrieved context remains below the required context count.
- Ask returns `not_ready` before retrieval when KB readiness blocks the selected
  scope, and persists that blocked state as a recoverable workflow with
  readiness diagnostics and audit records.
- Product API and MCP can resume a readiness-blocked Ask from the stored
  workflow request once the selected scope becomes ready, creating a new audited
  workflow linked to the blocked run.
- Product API and MCP can list readiness-blocked Ask workflows with fresh
  readiness checks so users or Hermes can see which saved Ask requests are ready
  to resume.
- Successful Ask prepares a transient sourced brief/artifact without creating
  workflow export audit records.
- Ask persists the agentic loop summary on workflow metadata, including
  governance action, durable/transient status, review requirement, and steps.
- MCP exposes `pska_workflow_list` so Hermes can recover recent workflow runs
  before opening state, artifacts, briefs, or exports.
- Writing shows matched durable memory facts alongside source context when a run
  is reopened, including each memory fact's supporting source trace.
- Frontend Ask result actions for Writing, Review, and accepted memory apply.
- Frontend review/apply state synchronization across Ask, Review, and Writing,
  backed by Review API memory-apply records.
- Existing sourced transient workflows can be turned into pending durable memory
  reviews through Product API, MCP, and the frontend Writing/Ask Memory Review
  action without re-retrieval or direct memory writes.
- Review queues can be resumed through Product API single-review reads and MCP
  `pska_review_list` / `pska_review_get`; frontend Review actions now open exact
  single-review Product API records by ID.
- Review records expose `source_refs` / `source_count`, and the frontend Review
  queue shows cited sources with Product API Reader actions.
- Frontend Review queue supports status filtering while Home keeps an
  independent pending-review summary.
- Frontend ingestion tracking: upload refreshes document status/readiness until
  terminal processing state.
- Frontend parse action for loaded unready documents through Product API.
- Frontend/Product API optional document structure graph read.
- Product API runtime diagnostics and Settings diagnostics view for provider
  connectivity without frontend provider direct calls.
- Product API, MCP, and frontend Settings expose an explicit retrieval probe
  for selected ready scopes; it writes `retrieval.probe` audit records and
  reports provider/model errors without falling back.
- Runtime workspace/tenant context surfaced in health, diagnostics, Settings,
  and audit metadata.
- Dataset creation, document ingestion, parsing, and graph reads write explicit
  KB audit records through both Product API and MCP.
- Source reads write explicit `source.read` audit records through the shared
  workflow service, covering both Product API and MCP source reads.
- Product API fake mode covers upload -> Ask -> source read against the uploaded
  document through the same PSKA API boundary.
- Workflow-level export audit records and frontend Activity audit trail with
  Product API action filtering.
- MCP exposes `pska_audit_list` so Hermes can inspect PSKA audit records without
  direct database or provider access.
- Frontend Knowledge Base create, upload, and parse actions refresh Activity
  after source-operation audit records are written.
- Frontend user operations focus Activity on their matching audit action
  (`kb.ingest`, `source.read`, `workflow.export`, `memory.apply`, and related
  actions) after records are written.
- Review and memory apply audit records carry proposal, run, and source trace
  metadata for durable knowledge writes.
- Reviews become immutable after durable memory has been applied; further
  durable changes require a new proposal/review.
- Writing opens workflow state, work product, source manifest, and context
  without export side effects; Markdown and JSON buttons perform explicit
  exports.
- Exports are traceable work products: Markdown and JSON include proposal/work
  product content, source manifests, supporting context, and traceability
  metadata, including durable-memory source manifests and the workflow export
  audit event for explicit exports.
- Workspace governance policy for durable memory: manual review, auto accept,
  or auto apply.
- Operational upload-to-agentic-question MCP loop.
- Smoke eval.
- Hermes skill/config examples.
- Docs and runbook.

Validated commands:

```bash
cd /Users/xudawei/PSKA-Essential
make test
make list-tools
make smoke
```

Expected result:

- `make test`: 69 tests pass.
- Product API tests cover health, static frontend serving, scoped Ask, Review,
  memory apply, audit records, KB readiness blocking, diagnostics, document
  graph read, dataset creation, parsing audit, multipart document upload, and
  fake upload-to-Ask source reads.
- Product API/static frontend tests cover Review status filtering, pending
  review summaries, review source trace display, and retrieval probe UI.
- Product API tests cover Ask loop controls reaching the PSKA-controlled loop.
- Adapter/Workflow/Product API tests cover graph retrieval hint propagation to
  RAGFlow retrieval and audit/loop metadata.
- Agentic loop/Product API tests cover reviewed memory influencing later Ask
  runs without replacing external retrieval requirements.
- Product API and agentic loop tests cover partial-context insufficiency gating.
- Product API tests cover audit action filtering.
- Workflow/Product API/MCP tests cover source-read audit records.
- Product API/MCP tests cover turning transient sourced workflows into durable
  memory reviews.
- Product API/MCP tests cover explicit retrieval probes and their audit records.
- RAGFlow adapter tests cover actionable model-provider retrieval errors.
- Governance/runtime context tests cover explicit default workspace and audit
  workspace/tenant metadata.
- `make list-tools`: lists 29 PSKA MCP tools.
- `make smoke`: fake adapter workflow succeeds.

Key env example:

```bash
/Users/xudawei/PSKA-Essential/.env.example
```

Current local RAGFlow endpoint for PSKA:

```bash
RAGFLOW_BASE_URL=http://127.0.0.1:9380
```

RAGFlow retrieval still needs a RAGFlow API key:

```bash
RAGFLOW_API_KEY=...
```

New operational loop tools:

```text
pska_kb_ingest_files
pska_kb_document_status
pska_kb_readiness
pska_retrieval_probe
pska_agentic_question_start
pska_agentic_question_resumable
pska_agentic_question_resume
pska_workflow_list
pska_workflow_artifact
pska_workflow_brief
pska_memory_review_from_workflow
pska_review_list
pska_review_get
pska_review_decide
pska_memory_apply
pska_export_brief
pska_audit_list
```

This loop lets Hermes upload local documents into a RAGFlow-backed dataset,
wait for parsing/readiness, run a KB-scoped PSKA workflow, propose reviewed
memory or writing artifacts, inspect the transient artifact/brief without
export side effects, and explicitly export a brief. PSKA-Essential still does
not own the KB/index; RAGFlow remains the KB backend.

`fake` adapters are now explicit development/test adapters only. Product runtime
must set providers intentionally. Use `PSKA_DEV_FAKE=1` only for local tests or
tool discovery.

Product API and frontend:

```bash
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 \
  PYTHONPATH=src python3 -m pska_essential.product_api
open http://127.0.0.1:8765
```

The frontend includes Home, Knowledge Bases, Ask, Reader, Writing, Review,
Activity, and Settings. It calls only same-origin `/api/...` routes, shows
explicit Ask loop steps including KB readiness, lets users pick dataset/document
scope through Product API, tunes loop max iterations, required context count,
and optional graph retrieval inside selected scope, opens sources through
Product API Reader, opens workflow state, work product, source manifest, and
context in Writing without export side effects, restores persisted loop
governance/status details, opens related review items, and can apply accepted
memory patches. Explicit exports produce traceable
Markdown/JSON work products with source manifests, supporting context, and
traceability metadata, include the workflow export audit event, and create
workflow export audit records. Review
decisions and memory apply actions refresh the current Ask/Writing state, and
applied memory state is served back through Review API records. Review supports
status filtering without changing the Home pending-review summary. Activity
shows the recent audit trail with action filtering, including workflow export
records, review/memory apply records with proposal, run, and source trace
metadata, and KB/source operation records for dataset creation, ingestion,
parsing, source reads, and graph reads. Knowledge Base create, upload, parse,
source read, and graph read actions refresh Activity and focus the matching
audit action after their source-operation audit records are written. Review,
memory apply, export, and Ask actions also focus Activity on their matching
workflow/governance audit action. Settings shows runtime provider configuration
and Product API diagnostics for review store, KB gateway, retrieval, and memory
connectivity.
Product API health, diagnostics, and audit records include the runtime
workspace/tenant context from `PSKA_WORKSPACE_ID` and `PSKA_TENANT_ID`. If
the selected dataset or document scope is not ready, Ask returns `not_ready` and
does not start retrieval. If retrieved context remains below the required
context count, Ask returns `insufficient_context`, shows any retrieved partial
context, and does not create a proposal, review, or export. The Knowledge Bases
view shows dataset/document
readiness, can start parsing for loaded unready documents, can open optional
document structure graph data through Product API, and automatically refreshes
ingestion status.

## Local Toolchain Status

Docker Desktop:

- Installed Apple Silicon Docker Desktop.
- Docker CLI and Compose are ARM64.
- `docker run --rm hello-world` passed.

Native Homebrew:

```bash
which brew
# /opt/homebrew/bin/brew

brew --prefix
# /opt/homebrew
```

Confirmed config:

```text
HOMEBREW_PREFIX: /opt/homebrew
macOS: 26.5.2-arm64
Rosetta 2: false
```

Old Intel/Rosetta Homebrew under `/usr/local` still exists but is no longer the
default. Do not delete it casually because `/usr/local/bin` belongs to another
user on this machine and may contain unrelated tools.

Command Line Tools:

- Updated from old `MacOSX10.15.sdk` to current SDK.
- Old SDK did not support ARM64 system headers and caused C extension build
  failures.
- New minimal ARM64 C compile passes.

Installed native brew deps:

```bash
brew install pkg-config jemalloc cmake libomp unixodbc
```

## Graphiti Status

Graphiti is running through Docker Compose.

Path:

```bash
/Users/xudawei/PSKA-Components/graphiti
```

Compose files:

```bash
/Users/xudawei/PSKA-Components/graphiti/docker-compose.pska.yml
/Users/xudawei/PSKA-Components/graphiti/.env.pska
```

Services:

- Graphiti API: `http://127.0.0.1:8000`
- Neo4j Browser: `http://127.0.0.1:7474`

Health check:

```bash
curl http://127.0.0.1:8000/healthcheck
```

Expected result:

```json
{"status":"healthy"}
```

Start:

```bash
cd /Users/xudawei/PSKA-Components/graphiti
docker compose -f docker-compose.pska.yml --env-file .env.pska up -d
```

Stop:

```bash
cd /Users/xudawei/PSKA-Components/graphiti
docker compose -f docker-compose.pska.yml --env-file .env.pska down
```

Important:

- Add `OPENAI_API_KEY` to `.env.pska` before doing real Graphiti memory
  extraction/search.
- PSKA-Essential should call Graphiti only through `GraphitiMemoryAdapter`.
- Do not expose Graphiti MCP directly to Hermes.

## RAGFlow Status

RAGFlow is running from source on Apple Silicon.

Path:

```bash
/Users/xudawei/PSKA-Components/ragflow
```

Current RAGFlow commit:

```text
2a482f3
```

Local mode:

- Base services: Docker Compose.
- Backend/API: local Python source, managed by user launchd.
- Frontend: Vite dev server, managed by user launchd.

URLs:

- Frontend: `http://127.0.0.1:9222`
- Backend/API: `http://127.0.0.1:9380`
- Health: `http://127.0.0.1:9380/api/v1/system/ping`

Health check:

```bash
curl http://127.0.0.1:9380/api/v1/system/ping
```

Expected result:

```text
pong
```

Base service compose:

```bash
cd /Users/xudawei/PSKA-Components/ragflow
docker compose -f docker/docker-compose-base.yml up -d
docker compose -f docker/docker-compose-base.yml ps
```

Base services currently used:

- Elasticsearch on `127.0.0.1:1200`
- MySQL on `127.0.0.1:3306`
- MinIO on `127.0.0.1:9000` / console `9001`
- Valkey/Redis on `127.0.0.1:6379`

RAGFlow backend launchd service:

```bash
/Users/xudawei/Library/LaunchAgents/com.pska.ragflow.plist
/Users/xudawei/PSKA-Components/ragflow/pska-run-ragflow-server.sh
```

RAGFlow frontend launchd service:

```bash
/Users/xudawei/Library/LaunchAgents/com.pska.ragflow.web.plist
/Users/xudawei/PSKA-Components/ragflow/pska-run-ragflow-web.sh
```

Start backend/frontend:

```bash
launchctl kickstart -k gui/$(id -u)/com.pska.ragflow
launchctl kickstart -k gui/$(id -u)/com.pska.ragflow.web
```

Stop backend/frontend:

```bash
launchctl bootout gui/$(id -u) /Users/xudawei/Library/LaunchAgents/com.pska.ragflow.plist
launchctl bootout gui/$(id -u) /Users/xudawei/Library/LaunchAgents/com.pska.ragflow.web.plist
```

Logs:

```bash
tail -f /Users/xudawei/PSKA-Components/ragflow/.pska-ragflow-server.log
tail -f /Users/xudawei/PSKA-Components/ragflow/.pska-ragflow-web.log
```

RAGFlow source setup already completed:

```bash
cd /Users/xudawei/PSKA-Components/ragflow
uv sync --python 3.13 --frozen
uv run python3 ragflow_deps/download_deps.py
cd web
npm install
```

Note:

- The RAGFlow homepage at backend `/` returns 404 in source-backend mode. This
  is fine. Use the frontend at `http://127.0.0.1:9222`.
- The backend health endpoint returns `pong`.
- Create RAGFlow datasets/API keys through the RAGFlow UI before PSKA uses live
  retrieval.

## Hermes Status

Hermes is installed and was previously connected to PSKA-Essential MCP.

Hermes binary observed earlier:

```bash
/Users/xudawei/.local/bin/hermes
```

Use Hermes only against PSKA-Essential MCP tools. Do not connect Hermes directly
to Graphiti or RAGFlow if doing the PSKA workflow-gate demo.

PSKA MCP command shape:

```bash
cd /Users/xudawei/PSKA-Essential
uv sync --extra mcp
uv run pska-essential-mcp
```

If using explicit local fake mode:

```bash
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=:memory: PYTHONPATH=src python3 -m pska_essential --list-tools
```

## Current Verification Snapshot

These passed at the end of setup:

```bash
curl http://127.0.0.1:8000/healthcheck
# {"status":"healthy"}

curl http://127.0.0.1:9380/api/v1/system/ping
# pong

curl -I http://127.0.0.1:9222/
# HTTP/1.1 200 OK

cd /Users/xudawei/PSKA-Essential
make test
make list-tools
```

## Next Recommended Steps

1. Open RAGFlow UI:

   ```bash
   open http://127.0.0.1:9222
   ```

2. Create or import a small test dataset in RAGFlow.

3. Create a RAGFlow API key.

4. Configure PSKA-Essential for live KB operations and retrieval:

   ```bash
   export PSKA_RETRIEVAL_PROVIDER=ragflow
   export PSKA_KB_PROVIDER=ragflow
   export RAGFLOW_BASE_URL=http://127.0.0.1:9380
   export RAGFLOW_API_KEY=...
   ```

5. Configure memory explicitly. Use Graphiti for live product flow; reserve
   fake memory for `PSKA_DEV_FAKE=1` development tests only:

   ```bash
   export PSKA_MEMORY_PROVIDER=graphiti
   export GRAPHITI_BASE_URL=http://127.0.0.1:8000
   export GRAPHITI_GROUP_ID=pska-essential
   ```

6. Run an end-to-end upload-to-question PSKA workflow:

   ```text
   upload -> parse/status -> agentic question -> propose -> review -> apply -> explicit export
   ```

   In explicit fake mode this can be tested with text files only: fake KB stores
   uploaded text, fake retrieval returns it as context, and PSKA still owns the
   workflow/review/export gates.

7. Validate that Graphiti writes are still review-gated and that Hermes cannot
   bypass PSKA by calling Graphiti directly.

## Known Gotchas

- RAGFlow source backend needs base services running first.
- RAGFlow live retrieval needs a dataset and API key.
- RAGFlow ingestion can be slow because parsing, chunking, embedding, and
  indexing are long-running jobs. Check document status before asking.
- Graphiti needs `OPENAI_API_KEY` in `.env.pska` before real memory extraction.
- Docker Desktop is currently configured around 8 GB RAM. This is enough for the
  current source-run setup, but heavy RAGFlow ingestion can still be slow.
- The third-party image `0xgkd/ragflow-arm64:v0.20.3` is not ARM64 despite its
  name. Do not use it as the Apple Silicon backend.
- Do not replace the PSKA adapter boundary with direct Graphiti/RAGFlow MCP
  exposure.
