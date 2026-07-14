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

These tools are thin glue over RAGFlow plus the existing PSKA workflow gate:

```text
upload files -> RAGFlow dataset/documents/chunks -> PSKA scoped retrieve
  -> agent answer/proposal -> Review -> optional memory apply -> export
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
- `GET /api/kb/datasets`
- `POST /api/kb/datasets`
- `POST /api/kb/ingest`
- `POST /api/kb/readiness`
- `GET /api/kb/datasets/{dataset_id}/readiness`
- `GET /api/kb/datasets/{dataset_id}/documents`
- `POST /api/kb/datasets/{dataset_id}/parse`
- `POST /api/ask`
- `GET /api/workflows`
- `GET /api/workflows/{run_id}/export`
- `GET /api/reviews`
- `POST /api/reviews/{review_id}/decision`
- `POST /api/reviews/{review_id}/apply-memory`
- `GET /api/audit`

The bundled frontend exposes Home, Knowledge Bases, Ask, Reader, Writing,
Review, and Settings. It is served by the Product API and uses only same-origin
`/api/...` calls. Ask responses include explicit loop steps so users and agents
can see scope checks, KB readiness, retrieval, context inspection, proposal
creation, review creation or skipping, and export preparation. Ask includes a
dataset/document picker that syncs to explicit scope IDs and result actions for
Writing, Review, and accepted memory application. Review decisions and memory
apply actions refresh the current Ask/Writing state, and applied memory state is
served back through Review API records. If the selected dataset or
document scope is not ready for retrieval, Ask returns a structured `not_ready`
result instead of starting retrieval. Knowledge Bases shows dataset/document
readiness, can start parsing for loaded unready documents, and automatically
refreshes ingestion status after uploads. Writing opens sourced briefs from
recent workflow runs and exports Markdown or JSON through Product API.
