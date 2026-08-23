# Hermes WebUI Integration Plan

Related product docs:

- [System Interaction Model](SYSTEM_INTERACTION_MODEL.zh.md)
- [PSKA User Guide](USER_GUIDE.md)
- [Long-Term Stability Design](LONG_TERM_STABILITY_DESIGN.md)
- [Metadata-First Bridge Design](METADATA_FIRST_BRIDGE_DESIGN.md)

This document defines how PSKA should use `hermes-webui` as the v1 frontend
substrate while keeping PSKA as the product API, MCP, governance, and adapter
boundary.

Current runtime routing and LLM ownership are defined in
[System Interaction Model](SYSTEM_INTERACTION_MODEL.zh.md). In short: Hermes is
the reasoner, PSKA does not own a generation LLM, and RAGFlow is used as the
document/retrieval backend rather than as an answer bot.

## Decision

Use `hermes-webui` as the PSKA Agent Workspace foundation.

PSKA should not build a second full conversation frontend. The daily user entry
point should be a Hermes-derived workspace shell that already owns chat,
sessions, streaming, tool-call display, workspace browsing, uploads, profiles,
settings, and MCP visibility.

PSKA remains the control plane behind that shell:

- Product API for frontend panels and workflow state.
- MCP tools for Hermes agent execution.
- Adapter boundary for RAGFlow, Graphiti, embedding providers, LLM providers,
  and future knowledge systems.
- Review, audit, policy, readiness, and canonical contracts.

The frontend must never call RAGFlow, Graphiti, embedding services, LLM
providers, databases, or queues directly. Browser code should call the
Hermes WebUI backend, and the Hermes WebUI backend should call PSKA Product API
or expose PSKA MCP configuration. PSKA adapters are the only place that may call
provider-native APIs.

## Conversation Recall Provider

Runtime history recall uses a dedicated Hermes backend provider, not the browser
extension. The provider is packaged in
`integrations/hermes-webui-recall-provider/` as a `git apply` patch for Hermes
WebUI. It exposes:

```text
POST /api/pska/conversations/search
```

The endpoint is protected by `HERMES_WEBUI_PSKA_RECALL_TOKEN` and returns only
bounded, query-matched snippets. PSKA calls it from
`POST /api/conversation/context-pack` with `PSKA_HERMES_RECALL_TOKEN`.

This keeps the runtime boundary intact:

- `pska-mini` extension selects scope and requests a context pack.
- PSKA owns memory, history, RAG/source search, dedupe, budget, and citation
  assembly.
- Hermes owns the conversation store and returns only scoped recall snippets.
- Recalled titles and snippets are untrusted quoted content, not executable
  instructions.
- The old password-based `/api/sessions/search` fallback is disabled by
  default and must be explicitly opted in for compatibility.

## Current Fit

The local `~/hermes-webui` checkout is a strong frontend base for PSKA because
it already has the hard, everyday workspace surfaces:

| Requirement | `hermes-webui` fit | PSKA action |
| --- | --- | --- |
| Chat as first-class entry | Native chat main view and composer | Keep |
| Session management | Sidebar session list, import/export, branching, search | Keep |
| Streaming responses | `/api/chat/start` plus `/api/chat/stream` SSE | Keep |
| Tool-call UI | Live and persisted tool cards in transcript | Keep |
| Workspace/files | Workspace picker, file tree, preview, upload | Keep for filesystem context |
| MCP visibility | Settings panel lists MCP servers and tools | Reuse for PSKA MCP server |
| Memory panel | Existing read/write memory panel | Replace direct writes with PSKA review flow |
| Settings/profiles | Mature settings and provider/profile surfaces | Keep, add PSKA status |
| Build complexity | Python stdlib server plus vanilla JS, no bundler | Good for controlled fork |

The important gaps are PSKA-specific, not generic frontend gaps:

- Knowledge datasets, documents, ingestion status, and readiness.
- PSKA Review queue for exception handling plus conversation-native memory
  changes for normal add/correct/delete interactions.
- Source reader over PSKA `SourceRef`.
- Agentic Ask workflow status and resumable not-ready runs.
- Durable memory lifecycle backed by PSKA, not Hermes local memory files.
- Normalized component diagnostics for RAGFlow, Graphiti, embedding, and PSKA.

## Target Topology

```text
Browser
  |
  v
Hermes WebUI frontend
  |
  v
Hermes WebUI backend
  |-- /api/chat/start, /api/chat/stream --> Hermes runtime
  |                                      |
  |                                      v
  |                                PSKA MCP tools
  |
  |-- /api/pska/* proxy ---------------> PSKA Product API
                                           |
                                           v
                                     PSKA Core
                                          |
                     +---------------------+---------------------+
                     |                     |                     |
                  RAGFlow          Memory Provider          Store
            document evidence      reviewed memory       audit/review
```

Hermes owns the conversation runtime. PSKA owns the knowledge contract. RAGFlow
and the selected memory provider remain behind PSKA adapters. The current local
runtime can use SQLite memory; Graphiti is an optional memory provider rather
than a required daily dependency.

## Data Ownership

One uploaded source document should not be ingested as raw source into both
RAGFlow and the memory provider.

The v1 rule is:

```text
source document -> PSKA ingest -> RAGFlow
reviewed fact / event / relation projection -> PSKA memory apply -> memory provider
```

RAGFlow stores source evidence: documents, chunks, embeddings, retrieval
coordinates, and citations.

The selected memory provider stores governed temporal memory: facts, events,
entities, relations, and source references after PSKA review or workspace policy
approval.

Graph memory providers such as Graphiti may use embeddings internally, but they
embed memory episodes and graph facts, not the full document chunk corpus that
RAGFlow owns.

The linkage between RAGFlow evidence and memory provider records must be
metadata-first: memory records created by PSKA carry upstream PSKA `SourceRef`
provenance. PSKA may cache resolution results, but it must not become the
authoritative fact-to-chunk ledger.

## Frontend Surface Mapping

| Surface | Owner in integrated frontend | Notes |
| --- | --- | --- |
| Chat transcript | Hermes WebUI | Do not fork the core chat loop first. |
| Sessions | Hermes WebUI | PSKA workflow IDs may be referenced from messages/artifacts. |
| Streaming | Hermes WebUI | PSKA operations appear as MCP/tool activity or Product API panel state. |
| Tool cards | Hermes WebUI | PSKA MCP tools should render through existing tool-card UI. |
| Chat attachments | Hermes WebUI | Keep as transient agent context, not knowledge ingestion. |
| Knowledge ingest | PSKA Product API | Separate from Hermes chat attachments; forwards to RAGFlow adapter. |
| Dataset readiness | PSKA Product API | Use `/api/workspace/status`, `/api/kb/readiness`, and ingestion status. |
| Ask over selected knowledge | Hermes agent via PSKA MCP, or PSKA `/api/ask` for panel workflows | Scope must be explicit. Composer chat scope is answer-only and uses `writing_brief`. |
| Digest selected knowledge | PSKA MCP/Product API | Use `pska_digest_scope` or `/api/digest`; never write Graphiti directly. |
| Digest queue | Hermes panel via PSKA Product API, or PSKA MCP | Use the Knowledge panel Digest card or digest job tools/routes for explicit queued digest work; waiting means KB readiness is still provider-owned. |
| Sources | PSKA Product API | Read through `POST /api/sources/read`; never direct RAGFlow chunk calls. |
| Conversation memory | PSKA MCP/Product API | Daily "remember/correct/forget" flow through `pska_memory_change_from_conversation` or `/api/memory/conversation-change`. |
| Review queue | PSKA Product API | Exception inbox for uncertain, risky, conflicting, or batch-derived changes. |
| Durable memory | PSKA Product API and MCP | Direct Hermes memory write UI must not bypass PSKA review. |
| Graph | PSKA Product API future view | Do not expose Graphiti native API to browser or agent. |
| Component health | PSKA Product API | Show normalized health and next actions. |
| MCP configuration | Hermes WebUI settings | Reuse existing MCP server/tool pages for PSKA server visibility. |

## Integration Phases

### Phase 0: Product Boundary Freeze

Define the fork as `pska-workspace` or a PSKA-branded Hermes WebUI distribution,
not as an independent PSKA frontend.

Keep these invariants:

- Browser calls only Hermes WebUI backend routes.
- Hermes WebUI backend calls PSKA Product API through a proxy module.
- Hermes agents call PSKA through MCP tools.
- RAGFlow and Graphiti are not browser-visible product APIs.
- Durable memory and graph writes require PSKA review or policy approval.

### Phase 1: Backend Proxy

Add a small Hermes WebUI backend module, for example `api/pska.py`, that proxies
PSKA Product API endpoints under `/api/pska/*`.

Suggested environment:

- `PSKA_API_BASE_URL`: required for PSKA panels.
- `PSKA_API_TIMEOUT_SECONDS`: request timeout.
- `PSKA_API_KEY`: optional if PSKA later requires auth.

Missing `PSKA_API_BASE_URL` must return an explicit 503 with an actionable
message. It must not silently use fake data or another backend.

Initial proxied routes:

- `GET /api/pska/health`
- `GET /api/pska/capabilities`
- `GET /api/pska/runtime/diagnostics`
- `GET /api/pska/workspace/status`
- `GET /api/pska/reviews`
- `GET /api/pska/reviews/{id}`
- `POST /api/pska/reviews/{id}/decision`
- `POST /api/pska/reviews/{id}/apply-memory`
- `GET /api/pska/kb/datasets`
- `GET /api/pska/kb/datasets/{dataset_id}/documents`
- `POST /api/pska/kb/ingest`
- `POST /api/pska/kb/readiness`
- `POST /api/pska/kb/ingestion-status`
- `POST /api/pska/ask`
- `POST /api/pska/memory/search`
- `POST /api/pska/memory/conversation-change`
- `GET /api/pska/workflows/resumable-asks`
- `POST /api/pska/sources/read`

The proxy should be intentionally narrow at first. Add routes only when a panel
needs them.

### Phase 2: PSKA Status Panel

Add a PSKA/Knowledge panel to the Hermes WebUI side rail or adapt the existing
Memory/Workspaces area.

The first panel should render only PSKA status:

- provider health from `/api/pska/health`
- normalized diagnostics from `/api/pska/runtime/diagnostics`
- datasets and readiness from `/api/pska/workspace/status`
- pending reviews from `/api/pska/reviews?status=pending`
- resumable Ask runs from `/api/pska/workflows/resumable-asks`

This phase proves connectivity without touching the chat stream.

Current implementation note: the local `~/hermes-webui` fork now includes a
`Knowledge` panel that loads PSKA health, workspace status, runtime diagnostics,
pending reviews, accepted-but-unapplied reviews, and resumable workflows through
`/api/pska/*`. It also reads Hermes' existing `/api/mcp/tools` inventory and
filters PSKA MCP tools for visibility. It also reads `/api/mcp/servers`, so the
panel can distinguish "PSKA MCP server is configured but runtime tools are not
hydrated yet" from "PSKA MCP is not configured in Hermes." Review decisions and
memory apply actions are available from the panel, but still go through PSKA
review/apply routes; the panel does not call RAGFlow or Graphiti directly. The
same panel also includes a PSKA ingestion form that submits selected files or
server-side file paths through `POST /api/pska/kb/ingest`, then refreshes PSKA
readiness/status. It now also includes a minimal scoped Ask form that submits
explicit `dataset_ids`, `document_ids`, `use_kg`, and review intent to
`POST /api/pska/ask`, renders the returned PSKA workflow result, brief, and
source packets, and resumes blocked Ask or ingest-loop workflows only through
PSKA workflow resume routes. Source packets can be opened through
`POST /api/pska/sources/read`, and workflow artifacts can be inspected through
`GET /api/pska/workflows/{run_id}` without triggering an export.
The same panel now includes a Conversation Memory section that searches PSKA
memory through `POST /api/pska/memory/search`, lets an operator select a target
fact for correction, and submits user-driven remember/correct/forget changes
through `POST /api/pska/memory/conversation-change`. The panel also loads
`GET /api/pska/capabilities` and disables memory search or conversation writes
when the configured PSKA memory backend does not advertise the required
operation.

### Phase 3: PSKA MCP Toolset

Register the PSKA MCP server in Hermes configuration and expose it through the
existing MCP settings UI.

The default PSKA toolset should include PSKA tools only. Agents must not receive
direct RAGFlow or Graphiti tools for PSKA workflows.

Verified local configuration shape:

```yaml
mcp_servers:
  pska-essential:
    url: "http://127.0.0.1:8766/mcp"
    enabled: true
    timeout: 120
    connect_timeout: 120
```

PSKA MCP should normally run as its own local HTTP service, separate from the
PSKA Product API used by the WebUI extension sidecar:

```bash
cd /Users/xudawei/PSKA-Essential
PYTHONPATH=src .venv/bin/python -m pska_essential \
  --env-file .env.pska \
  --transport streamable-http \
  --host 127.0.0.1 \
  --port 8766 \
  --path /mcp
```

Stdio MCP remains useful for isolated tool-registry development, but Hermes
WebUI should not spawn PSKA MCP subprocesses during the main demo path.

Current baseline, 2026-08-14: `pska_essential --list-tools` returns 109 PSKA
MCP tools from PSKA's own `tool_registry()`. Older notes that mention 45, 49,
or 51 runtime tools were from earlier registry shapes and should be treated as
historical. Product API route counts are a separate number; they should not be
used to infer the MCP tool surface.

Important runtime distinction: Hermes WebUI's `/api/mcp/servers` and
`/api/mcp/tools` endpoints are read-only inventory views. They display
configured servers and already-hydrated runtime tools, but they do not start or
probe MCP subprocesses from the browser. Actual tool hydration happens in the
Hermes agent runtime through MCP discovery at startup or `/reload-mcp`.

When running the Hermes WebUI fork locally for PSKA integration testing, start
it with the Hermes agent runtime Python, not the WebUI test venv:

```bash
HERMES_HOME=/path/to/hermes-home \
PSKA_API_BASE_URL=http://127.0.0.1:8765 \
HERMES_WEBUI_PORT=8792 \
AWS_EC2_METADATA_DISABLED=true \
/Users/xudawei/.hermes/hermes-agent/venv/bin/python /Users/xudawei/hermes-webui/server.py
```

Using `~/hermes-webui/.venv/bin/python` may run the static WebUI but miss agent
runtime dependencies such as `requests`, `websockets`, and `run_agent`.
`AWS_EC2_METADATA_DISABLED=true` avoids slow local Bedrock/AWS credential
metadata probes during the Hermes model catalog scan when AWS is not part of the
PSKA test path.

The local `pska-mini` WebUI extension now adds a composer PSKA chip instead of
changing Hermes-WebUI core chat code. The chip can enable or disable PSKA for
the next sends, fetch PSKA Product API status through the WebUI extension
sidecar, present ready RAGFlow datasets as checkboxes, and attach a
`PSKA-Mini Runtime Scope` block that forces the Hermes `knowledge-retrieval`
skill for the turn. It also exposes small WebUI-native controls for Jarvis
briefing, agentic context brief, metadata-first source recall, PSKA Memory,
review projection to Hermes Kanban, and the PSKA Digest Runner task.

This is intentionally a small bridge rather than a second PSKA chat surface.
It does not implement upload, an independent PSKA Ask product surface, Eidolia
views, or RAGFlow/Graphiti direct browser calls. Memory and review controls are
thin Product API views/projections; PSKA remains the authority.

Implementation caveat: the current upstream WebUI checkout does not expose an
ephemeral hidden-turn-context hook, so the pure-extension bridge wraps
`/api/chat/start` and cleans the visible transcript afterward. For permanent
upstream integration, add a small WebUI hook that separates hidden agent
instructions from persisted/displayed user text.

A later branded distribution may enable the PSKA chip by default.

Current implementation note: the Knowledge panel now consumes both Hermes MCP
server inventory and MCP tool inventory. This is read-only and follows Hermes
WebUI's existing contract: the WebUI displays already-known configuration and
runtime metadata. If a PSKA MCP server is configured but no PSKA tools are
hydrated in the current WebUI process, the panel exposes an explicit
user-triggered "Reload MCP" action that calls Hermes' existing
`/api/commands/exec` route with `/reload-mcp now`, then refreshes the inventory.

### Phase 4: Knowledge Ingestion And Readiness

Add a Knowledge panel that calls the PSKA proxy:

- list datasets
- create dataset if needed
- upload source files through `POST /api/pska/kb/ingest`
- show ingestion status and readiness
- show per-document failure reasons and next actions
- start parse/resume actions through PSKA routes

Do not reuse Hermes chat attachment upload as knowledge ingestion. Hermes
attachments are transient chat context. PSKA ingestion creates source knowledge
and must expose asynchronous readiness.

### Phase 5: Scoped Ask From Chat

Add explicit scope selection to the workspace:

- selected dataset IDs
- optional selected document IDs
- readiness summary
- source scope chips near the composer

There are two valid execution paths:

1. Hermes chat path: the user asks in chat, Hermes uses PSKA MCP tools such as
   `pska_agentic_question_start`, `pska_source_read`, and `pska_memory_search`.
2. Panel workflow path: the Knowledge/Ask panel calls `POST /api/pska/ask` and
   renders the returned workflow, brief, and sources.

Both paths must preserve explicit scope. Neither path may silently broaden from
selected documents to all datasets.

Current implementation note: the Knowledge panel implements the panel workflow
path first. It pre-fills ready dataset IDs from `/api/pska/workspace/status`,
allows optional document IDs, keeps graph-aware retrieval as an explicit `use_kg`
choice, and always sends `proposal_kind=writing_brief`. It does not expose
`memory_patch`, `create_review`, or "promote this answer to memory" controls
from the normal Ask surface. If PSKA returns a not-ready workflow, the workflow
stays resumable through
`POST /api/pska/workflows/{run_id}/resume-ask` or
`POST /api/pska/workflows/{run_id}/resume-ingest-loop`. Ready workflow results
can also open their PSKA artifact and read their source refs through PSKA API
routes, preserving auditability and keeping provider-native details behind
adapters.

The Hermes composer PSKA scope is deliberately narrower than the panel Ask
form. It lets the user choose datasets/documents and whether graph-aware
retrieval participates in the current chat turn, but it does not expose
`memory_patch` or durable proposal creation. Normal chat sends must remain
transient answer workflows (`proposal_kind=writing_brief`). If the user wants
to remember, correct, or forget durable memory, Hermes should use conversation
memory; if the change is uncertain or risky, PSKA can create an exception
Review item through the normal governance path.

The Knowledge panel also includes a Digest card for explicit background
digestion. It queues `POST /api/pska/digest-jobs` with selected
datasets/documents, optional graph-aware retrieval, priority, and an explicit
`create_memory_review` flag. A queued digest job is visible in the Jobs card and
can be run through `POST /api/pska/digest-jobs/{run_id}/run`. This path creates
sourced digest artifacts and optional exception Review items; it does not write
Graphiti memory directly.

The panel also reads `capabilities.memory.inflow` (`pska.memory_inflow.v1`) and
renders it as a Memory inflow card. This card is explanatory and contract-driven:
upload goes to the KB provider only, conversation memory is the normal user
path, digest jobs require ready KB scope, and workflow promotion uses Review
governance. It must not call RAGFlow or Graphiti directly.

### Phase 6: Conversation Memory And Review Exceptions

Use Hermes chat as the normal memory editor. When a user says "remember this",
"that is wrong", or "forget that", Hermes should call PSKA through
`pska_memory_change_from_conversation` or
`POST /api/pska/memory/conversation-change`. Clear corrections can auto-apply
under workspace policy while preserving PSKA proposal, accepted-decision,
apply, and audit records.

Hermes chooses whether the request is an add, correction/update, delete/forget,
or clarification. If PSKA cannot resolve the target memory, Hermes should use
`pska_memory_search` or ask the user a short clarifying question, then retry
with `memory_fact`. Missing target resolution is not a reason to send the user
to Review.

The PSKA panel should support memory search for target selection and diagnostics
through `POST /api/pska/memory/search`. It should not make Review the user's
daily memory workflow.

Current implementation note: the local `~/hermes-webui` fork exposes this as a
Conversation Memory card in the PSKA Knowledge panel. The card uses only the
Hermes `/api/pska/*` proxy routes; it does not call RAGFlow, Graphiti, or a
native Hermes memory write route directly. It reads PSKA capabilities before
enabling memory search or conversation-change buttons, so provider-specific
unsupported operations surface as UI state instead of dead-end calls.
Normal Hermes agent turns also receive a PSKA Conversation Memory system block
when the active profile has a PSKA MCP server configured, so explicit
remember/correct/forget requests can use PSKA MCP without opening the Review
queue as a daily workflow.

Required exception actions:

- list pending reviews
- inspect proposal, source refs, and workflow artifact
- accept, reject, or request revision
- apply accepted memory
- inspect memory lifecycle
- create update/delete reviews from selected memory facts only for broad
  destructive, ambiguous destructive, high-risk, or non-conversation changes

The existing Hermes `/api/memory/write` path writes local memory files directly.
That behavior must not be used for PSKA durable memory. In the PSKA-branded
workspace, ordinary user-driven memory corrections go through PSKA conversation
memory, while uncertain or high-risk durable changes go through PSKA Review and
`apply-memory`.

### Phase 7: Sources And Artifacts

Add a source reader that calls `POST /api/pska/sources/read` with PSKA
`SourceRef`.

Use Hermes WebUI's existing main-view/detail pattern for:

- retrieved source excerpts
- source manifests
- exported briefs
- workflow artifacts
- review evidence

Artifacts created by PSKA should reference workflow IDs and source refs, not
RAGFlow-native payloads.

### Phase 8: Optional Admin Graph View

Only after the core workflow is stable, add an admin-only graph view backed by
PSKA normalized graph/read APIs.

This is not a user-facing Graphiti console. It is a diagnostic view for accepted
durable knowledge and source-backed relations.

## Minimal v1 User Flows

### Flow A: Ask Over Existing Ready Dataset

```text
Open PSKA Workspace
  -> Knowledge panel shows ready dataset
  -> select dataset scope
  -> ask in chat
  -> Hermes calls PSKA MCP
  -> PSKA retrieves from RAGFlow and searches reviewed memory in Graphiti
  -> PSKA reads missing RAGFlow evidence referenced by memory provenance
  -> Hermes displays answer, tool cards, and sources
```

### Flow B: Upload Document Then Ask

```text
Knowledge panel upload
  -> PSKA Product API
  -> RAGFlow ingest/parse/index
  -> readiness shows processing
  -> Ask is disabled or returns not_ready
  -> readiness becomes ready
  -> user asks over explicit dataset/document scope
  -> optional: queue Digest from the Knowledge panel
```

### Flow C: Correct Memory In Chat

```text
User says "that is wrong; change it to X"
  -> Hermes calls PSKA conversation memory tool/API
  -> PSKA resolves the target memory fact or returns needs_target
  -> clear correction auto-applies under conversation policy
  -> Graphiti receives a correction episode or supported update
  -> future Ask hides superseded facts by default
```

### Flow D: Exception Review From Batch Or Risky Knowledge

Review is not the daily memory editor. It is used when PSKA, Hermes, policy, or
the user deliberately escalates uncertain, risky, conflicting, ambiguous
destructive, broad destructive, or batch-derived durable knowledge. A clear
user-requested correction or specific forget operation stays in PSKA
conversation memory by default.

```text
Digest/batch extraction or risky conversation memory change
  -> create exception review
  -> Review panel shows evidence and proposed memory patch
  -> user accepts
  -> apply-memory
  -> PSKA adapter writes reviewed projection to Graphiti
  -> audit records lifecycle
```

## Verification Gates

Before calling the integrated frontend usable, verify:

- Static frontend contains no direct calls to RAGFlow, Graphiti, Neo4j,
  embedding services, or LLM provider APIs.
- Hermes backend provider calls for PSKA panels go through the PSKA proxy module.
- PSKA MCP server is visible in Hermes MCP settings and PSKA tools are listed.
- A ready RAGFlow dataset can answer through PSKA MCP or `/api/pska/ask`.
- A Graphiti memory fact with upstream source refs can pull missing KB evidence
  back into Ask context through PSKA, without a PSKA-side fact ledger.
- A not-ready dataset is shown as not ready and does not produce a fake answer.
- A document upload enters RAGFlow once; Graphiti receives only reviewed memory
  projections.
- Pending reviews can be accepted, rejected, revised, and applied through PSKA.
- Direct durable memory writes are not exposed as the PSKA memory path.
- `python -m pytest tests/test_adapters.py tests/test_graphiti_gate.py -q`
  passes in PSKA.
- Hermes WebUI static JS lint passes after frontend edits.

## What Not To Do

- Do not embed RAGFlow as the primary daily UI.
- Do not call Graphiti from browser code.
- Do not expose RAGFlow/Graphiti API keys to Hermes WebUI frontend code.
- Do not turn Hermes local memory files into PSKA durable memory.
- Do not let chat attachments automatically become governed knowledge.
- Do not write durable graph or memory state as a side effect of retrieval,
  ingestion, or answering.
- Do not add fake PSKA data when the PSKA backend is missing.

## Near-Term Implementation Order

1. Add Hermes WebUI backend PSKA proxy.
2. Add PSKA status panel.
3. Register and verify PSKA MCP server/toolset in Hermes.
4. Add Knowledge dataset/readiness panel.
5. Add scoped Ask path. (Initial Knowledge-panel path implemented.)
6. Add Review and apply-memory panel. (Initial review gate implemented.)
7. Add source reader and workflow artifact rendering. (Initial Knowledge-panel
   rendering implemented.)
8. Add optional admin graph diagnostics.

This order maximizes reuse of Hermes WebUI while moving PSKA-specific value into
the smallest number of frontend additions.
