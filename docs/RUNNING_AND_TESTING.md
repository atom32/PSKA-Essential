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
should always stay fast.

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
Review, Activity, and Settings. Ask displays explicit PSKA-controlled loop steps,
including KB readiness before retrieval, and includes a dataset/document picker
that syncs to explicit scope IDs. Ask can tune loop depth with max iterations,
required context count, and optional graph retrieval inside the selected scope.
Graph retrieval is passed through PSKA retrieval contracts as a scoped hint and
is visible in loop steps and audit metadata. If the required context count is
not met, Ask returns `insufficient_context`, shows any retrieved partial
context, and does not create a proposal, review, or export. Successful Ask
results prepare a transient sourced brief and artifact without creating workflow
export audit records. Ask results can jump directly to Writing or Review and can
apply accepted memory patches through Product API.
Review decisions and memory apply actions refresh the current Ask/Writing
state, and applied memory state is served back through Review API records.
Reader inspects sources through Product API only. Writing opens workflow state,
work product, source manifest, and context without creating an export, then
exports Markdown or JSON through explicit Product API actions; exports include
the work product, source manifest, supporting context, and traceability
metadata, and create workflow audit records. Activity shows the recent audit
trail, including review and memory apply records with proposal, run, and source
trace metadata. Upload, parsing,
embedding, indexing, and optional graph extraction readiness remain visible
states rather than hidden side effects. After upload, the Knowledge Bases view
can start parsing for loaded unready documents, open optional document
structure graph data through Product API, and refreshes the selected dataset's
document status and readiness until processing reaches a terminal state.
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
pska_kb_ingest_files -> pska_kb_document_status -> pska_kb_readiness
  -> pska_agentic_question_start
```

These tools do not make PSKA-Essential a KB implementation. They call RAGFlow
dataset/document/chunk APIs and return normalized IDs, readiness, and optional
structure graph data.

Treat RAGFlow ingestion as asynchronous. Uploading a document only starts the
chain of parsing, chunking, embedding, and indexing. Frontend and agent flows
must check readiness before assuming retrieval will work.

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
- MCP tool registry
- export
- adapter replacement with company stub
- KB gateway glue without live RAGFlow
- Product API and frontend boundary smoke tests
- agentic Ask loop diagnostics and durable-governance defaults

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
