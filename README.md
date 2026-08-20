# PSKA-Essential

PSKA-Essential is an **Agent Knowledge Workflow Gate**. It does not try to be a
knowledge base, GraphRAG platform, editor, or agent runtime. It connects mature
systems through small adapter contracts and keeps the workflow safe:

```text
Hermes Agent
  -> PSKA-Essential MCP
    -> Retrieval Adapter: RAGFlow / Local folders / Obsidian / Company GraphRAG
    -> Memory Adapter: SQLite / Graphiti / Company GraphRAG
    -> Review Store: SQLite
    -> Export: Markdown / JSON
```

The product promise is workflow closure:

- run Hermes-first agent workflows through PSKA MCP tools;
- retrieve context from an external KB;
- retrieve context from user-authorized local folders and Obsidian vaults
  through a metadata-first source layer;
- optionally create/populate that external KB through thin MCP glue;
- let an agent propose digest, memory, or writing artifacts;
- govern and audit long-term memory changes, with pending review reserved for
  uncertain, risky, conflicting, or batch-derived changes;
- keep an audit trail;
- replace RAGFlow/Graphiti later through adapters.

Runtime behavior is universal and explicit: no case-specific shortcuts, no
hardcoded domains, and no silent fallback to fake data or another backend.
Document ingestion and embedding are treated as asynchronous jobs whose status
must be visible to users and agents.

## Product Guides

Read these first when deciding how to use or extend the project:

- [PSKA Alpha Acceptance 2026-08-20](docs/PSKA_ALPHA_ACCEPTANCE_2026-08-20.zh.md):
  current local dogfood acceptance snapshot, including `alpha_ready`,
  full-component proof, Hermes WebUI extension checks, memory governance state,
  and locked optional boundaries.
- [Alpha v1 Baseline 2026-08-04](docs/ALPHA_V1_BASELINE_2026-08-04.zh.md):
  frozen componentized Alpha baseline, component commits, runtime boundary,
  sealed scope, and next-stage backlog.
- [Alpha Compose Deployment](docs/ALPHA_COMPOSE_DEPLOYMENT.zh.md):
  Docker Compose Alpha A for Hermes-WebUI + PSKA Product API + Eidolia, with
  external RAGFlow and explicit Alpha B runtime boundaries.
- [Full Compose v0](deploy/full-compose/README.zh.md): one-stop connected-machine
  deployment for RAGFlow upstream compose plus Hermes Agent, Hermes-WebUI,
  PSKA Product API/MCP, and Eidolia.
- [Demo Baseline 2026-08-03](docs/DEMO_BASELINE_2026-08-03.zh.md):
  historical local demo freeze for Hermes WebUI, Eidolia, PSKA-Essential,
  RAGFlow, SQLite memory, and SQLite review. The current dogfood memory
  provider has since moved to GBrain.
- [System Interaction Model](docs/SYSTEM_INTERACTION_MODEL.zh.md): current
  Hermes WebUI, Eidolia, PSKA, RAGFlow, memory, review, and LLM routing rules.
- [PSKA User Guide](docs/USER_GUIDE.md): daily Hermes WebUI workflow, ingestion,
  Ask, review, configured memory provider, and troubleshooting.
- [Hermes WebUI Integration](docs/HERMES_WEBUI_INTEGRATION.md): plan for using
  Hermes WebUI as the only v1 user workspace, with PSKA behind proxy/API/MCP
  boundaries.
- [Frontend Boundary Audit 2026-08-15](docs/FRONTEND_BOUNDARY_AUDIT_2026-08-15.zh.md):
  current audit of Hermes WebUI extension vs the legacy local diagnostic UI,
  including duplicated surfaces and the correct demo path.
- [Long-Term Stability Design](docs/LONG_TERM_STABILITY_DESIGN.md): temporal
  knowledge, conflict handling, review triage, context budgets, background
  jobs, permissions, and migration.
- [Personal Knowledge Architecture](docs/PERSONAL_KNOWLEDGE_ARCHITECTURE.zh.md):
  vNext design for Obsidian, local folders, no-embedding retrieval, file
  tagging/commenting/dedup, and Hermes-first personal assistant workflows.
- [PSKA Agentic System Technical Proposal](docs/PSKA_AGENTIC_SYSTEM_TECHNICAL_PROPOSAL.zh.md):
  complete Chinese technical proposal for the agentic cognitive system,
  including characteristics, target users, scenarios, architecture, memory,
  RAG strategy, governance, open-source component strategy, and roadmap.
- [PSKA Agentic System Upgrade Plan](docs/PSKA_AGENTIC_SYSTEM_UPGRADE_PLAN.zh.md):
  engineering plan for upgrading the current PSKA-Essential M32 baseline into
  the proposal through adapter-first changes, mature component reuse,
  build-vs-buy decisions, schema/API/MCP/WebUI deltas, and phased acceptance
  gates.
- [Metadata-First Bridge Design](docs/METADATA_FIRST_BRIDGE_DESIGN.md): the
  no-central-ledger data ownership model and the Graphiti-to-RAGFlow provenance
  contract.
- [Conversation-Native Memory Design](docs/CONVERSATION_NATIVE_MEMORY_DESIGN.md):
  daily chat-based memory add/correct/delete flow and the reduced role of the
  Review queue.
- [Review And Memory Protocol](docs/REVIEW_MEMORY_PROTOCOL.md): canonical
  review/memory lifecycle, status model, provider contract, and lightweight
  SQLite baseline.

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

Run the local product acceptance eval with explicit fake dev adapters:

```bash
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake \
  PSKA_MEMORY_PROVIDER=fake PSKA_REVIEW_DB=:memory: \
  make eval
```

This verifies the PSKA upload -> readiness -> Ask/export loop, resumable
not-ready upload flow, governed durable memory transition, and audit trail
without using fake as a live-provider fallback. Successful and failed eval runs
record `eval.run` audit events.

Run the full local Hermes workspace stack:

```bash
make start-workspace
```

This checks configured components such as RAGFlow, the selected memory provider,
PSKA Product API, and Hermes WebUI; starts missing local services where this
machine has a known startup path; then opens Hermes WebUI as the v1 product
workspace. The PSKA Product API check validates the lightweight Product API
contract, not just `/api/health`, so a stale local 8765 process that lacks
routes such as `/api/memory/search` is reported as `STALE` and restarted. With
the current GBrain dogfood profile, this does not auto-start Graphiti; use
`scripts/start_pska_workspace.sh --with-graphiti` only when validating the
optional graph memory provider. For status without starting services:

```bash
make start-workspace START_WORKSPACE_ARGS=--status-only
```

To run only PSKA's legacy local diagnostic UI directly:

```bash
PSKA_DEV_FAKE=1 PSKA_RETRIEVAL_PROVIDER=fake PSKA_KB_PROVIDER=fake PSKA_MEMORY_PROVIDER=fake \
  PSKA_REVIEW_DB=.pska-essential/dev.sqlite3 \
  PYTHONPATH=src python3 -m pska_essential.product_api
```

For the legacy diagnostic UI only, open:

```bash
open http://127.0.0.1:8765
```

For the v1 product experience, open the Hermes WebUI fork and let it call PSKA
through `/api/pska/*` and PSKA MCP tools.

## External Backends

Production/live mode requires explicit providers. The current local dogfood
baseline uses RAGFlow plus GBrain memory:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export PSKA_MEMORY_PROVIDER=gbrain
export GBRAIN_MCP_URL=http://127.0.0.1:3131/mcp
export GBRAIN_MCP_TOKEN=...
```

Selected live providers also require their connection environment variables at
startup. PSKA fails explicitly when a provider is selected without the required
URL/key instead of starting with an implicit localhost or empty-key default.
CLI entry points can load an explicit env file with `--env-file .env.pska`, and
the Make targets accept `ENV_FILE=.env.pska`. This is only configuration
loading; PSKA still fails when required providers or keys are absent.

Graphiti can be selected later with `PSKA_MEMORY_PROVIDER=graphiti`, but it is
not required for evidence retrieval, PSKA review, or the current GBrain memory
loop.

RAGFlow retrieval:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export RAGFLOW_BASE_URL=http://localhost:9380
export RAGFLOW_API_KEY=...
```

Before choosing a dataset, run a connectivity check to verify the selected live
providers and memory adapter:

```bash
make workspace-status ENV_FILE=.env.pska
make live-connectivity-check ENV_FILE=.env.pska
```

After a RAGFlow dataset is uploaded and ready, run the full live component
proof:

```bash
export PSKA_COMPONENT_DATASET_IDS=...
# or:
export PSKA_COMPONENT_DATASET_NAMES="ready dataset name"
export PSKA_COMPONENT_QUESTION="Summarize the selected documents with sources."
make live-component-check
# or:
make live-component-check ENV_FILE=.env.pska
```

The connectivity check runs runtime diagnostics and memory search verification
without requiring a dataset scope. The full component proof runs runtime
diagnostics, memory search verification, retrieval
probe, and the live closed-loop probe in one structured result. It does not use
fake providers as proof. A successful result means the configured live
providers completed readiness, retrieval, agentic Ask, source inspection, and
explicit export; the result reports the exact failing step when a component is
not wired. Component and live probes accept either dataset IDs or dataset names;
PSKA resolves names through the KB gateway and reports canonical dataset IDs in
the returned scope.
`make workspace-status` or `pska-essential-workspace-status` prints the same
PSKA next-action summary used by Home and Hermes, including whether to upload,
parse, wait, resume, review, apply memory, or ask over ready datasets.
Use `make live-closed-loop` when you only want the sourced Ask/export portion.
If the result reports `configure_embedding_provider`, configure the selected
dataset embedding model/provider in RAGFlow and re-parse/re-index the affected
documents before running Ask.
When creating a new RAGFlow-backed dataset through PSKA, `pska_kb_create`,
`pska_kb_ingest_files`, and the Product API accept optional `embedding_model`.
Leave it empty to use the RAGFlow tenant default, or set it to an embedding
model/provider that RAGFlow already has configured. The RAGFlow KB gateway
scans visible dataset/document pages when resolving IDs or names, and starts
parsing through RAGFlow's current `/datasets/{dataset_id}/documents/parse`
contract.

Run the file-to-work-product loop when you want PSKA to create/populate the KB
scope first, wait for readiness, ask, and export a sourced transient artifact:

```bash
export PSKA_LOOP_DATASET_NAME="annual-report-test"
export PSKA_LOOP_FILE_PATHS="/path/to/document.pdf"
export PSKA_LOOP_QUESTION="Summarize the uploaded documents with sources."
make live-ingest-loop
# or:
make live-ingest-loop ENV_FILE=.env.pska
```

This path still uses the configured KB/retrieval/memory adapters and the same
readiness gate. If ingestion or embedding is not ready, it stops before Ask
instead of producing an unsourced answer. When the result includes a blocked
`run_id`, resume the same upload -> Ask -> export intent after readiness with
`PSKA_LOOP_RUN_ID=<run_id> make live-ingest-loop-resume` or
`pska-essential-ingest-loop-resume <run_id>`.

SQLite memory fallback:

```bash
export PSKA_MEMORY_PROVIDER=sqlite
export PSKA_MEMORY_DB=/Users/xudawei/PSKA-Essential/.pska-essential/memory.sqlite3
```

The SQLite memory adapter is the lightweight local fallback. It persists only
reviewed PSKA memory facts, source refs, metadata, and versions. It is useful
for isolated tests or when a workspace needs a small durable memory provider
without GBrain or a graph service. It is not the current dogfood memory
provider, a document store, vector index, or Review UI.

Graphiti memory:

```bash
export PSKA_MEMORY_PROVIDER=graphiti
export GRAPHITI_BASE_URL=http://localhost:8000
export GRAPHITI_GROUP_ID=pska-essential
```

The Graphiti adapter keeps writes review-gated. It supports reviewed memory
apply and reviewed entity-edge delete through Graphiti; reviewed update fails
explicitly until the backend exposes a transactional fact update contract.
Conversation-native corrections can still work with Graphiti: PSKA keeps the
user-facing operation as `memory_update`, but records
`proposal_operation=memory_patch` and
`memory_update_strategy=append_correction_episode`, then appends a reviewed
correction episode with current text, previous text, target/provenance metadata,
and stable target coordinates. This is an explicit temporal memory strategy, not
a hidden adapter fallback; Graphiti advertises it through
`conversation_update_strategies` in the PSKA capabilities contract. Agent-facing
briefs and proposals prefer `display_text`/`current_text` over the raw correction
episode body.
Memory operation capabilities are exposed through the explicit capabilities
contract, health, diagnostics, and workspace status so the frontend and Hermes
can avoid unsupported durable actions before creating review items. Historical
accepted reviews that target
unsupported backend operations remain visible as inspect actions instead of
being offered as apply actions. When a workspace or tenant is configured,
Graphiti memory search/apply uses a derived PSKA memory namespace under the
configured `GRAPHITI_GROUP_ID`.
The capabilities contract also includes a soft tool-policy manifest that labels
read/write tools, readiness requirements, durable actions, provider writes, and
review gates for Hermes and UI controls. It is product guidance, not auth.
Use `pska_memory_probe` or `POST /api/runtime/memory-probe` to verify that the
configured memory backend can actually serve search requests. Graphiti
`/healthcheck` only proves the service is running; the probe surfaces LLM or
embedding provider configuration failures explicitly instead of falling back to
fake memory.

Workspace governance policy:

```bash
# manual_review | auto_accept | auto_apply
export PSKA_GOVERNANCE_DURABLE_MEMORY=manual_review
export PSKA_GOVERNANCE_DIGEST_MEMORY=manual_review
export PSKA_GOVERNANCE_CONVERSATION_MEMORY=auto_apply
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
cp .env.example .env.pska
# Fill in real RAGFlow/Graphiti keys, then:
uv run pska-essential-mcp --env-file .env.pska
```

For Docker/full-compose deployments, run PSKA MCP as an internal streamable
HTTP service and point Hermes Agent at its URL:

```bash
uv run pska-essential-mcp --env-file .env.pska --transport streamable-http --host 0.0.0.0 --port 8766 --path /mcp
```

Hermes should connect only to PSKA-Essential MCP. Do not expose RAGFlow or
Graphiti MCP servers directly to the agent; that would bypass the review gate.
For local fake development, create a separate explicit fake env file with
`PSKA_DEV_FAKE=1` instead of editing Hermes to call provider tools directly.

Operational loop tools:

- `pska_kb_list`
- `pska_kb_create`
- `pska_kb_delete`
- `pska_kb_ingest_files`
- `pska_ingest_loop`
- `pska_ingest_loop_resume`
- `pska_digest_scope`
- `pska_digest_job_enqueue`
- `pska_digest_job_list`
- `pska_digest_job_run`
- `pska_kb_document_status`
- `pska_kb_readiness`
- `pska_kb_ingestion_status`
- `pska_kb_parse_documents`
- `pska_kb_graph_read`
- `pska_component_check`
- `pska_workspace_status`
- `pska_alpha_readiness`
- `pska_alpha_trial_guide`
- `pska_alpha_recovery_plan`
- `pska_alpha_first_run_session`
- `pska_alpha_first_run_item_update`
- `pska_retrieval_probe`
- `pska_memory_probe`
- `pska_live_closed_loop_probe`
- `pska_eval_run`
- `pska_agentic_question_start`
- `pska_agentic_question_resumable`
- `pska_agentic_question_resume`
- `pska_policy_get`
- `pska_capabilities_get`
- `pska_runtime_diagnostics`
- `pska_jarvis_briefing`
- `pska_agentic_context_brief`
- `pska_agentic_context_brief_list`
- `pska_workflow_list`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_source_root_list`
- `pska_source_root_register`
- `pska_source_scan`
- `pska_source_search`
- `pska_source_neighbors`
- `pska_source_read`
- `pska_duplicate_report`
- `pska_source_audit_run`
- `pska_source_audit_job_enqueue`
- `pska_source_audit_schedule_create`
- `pska_source_audit_job_list`
- `pska_source_audit_job_tick`
- `pska_source_audit_job_run`
- `pska_source_extract_job_enqueue`
- `pska_source_extract_job_list`
- `pska_source_extract_job_run`
- `pska_source_watch_once`
- `pska_saved_search_create`
- `pska_source_tag_propose`
- `pska_source_tag_apply`
- `pska_source_comment_propose`
- `pska_source_comment_apply`
- `pska_obsidian_moc_propose`
- `pska_obsidian_moc_apply`
- `pska_source_memory_review_create`
- `pska_source_memory_candidates_from_audit`
- `pska_eidolia_context_read`
- `pska_eidolia_memory_review_create`
- `pska_eidolia_project_trace_import`
- `pska_memory_candidate_dedup`
- `pska_memory_card_list`
- `pska_memory_card_get`
- `pska_memory_briefing`
- `pska_memory_review_queue`
- `pska_memory_health_scan`
- `pska_memory_use_trace`
- `pska_memory_why_used`
- `pska_memory_timeline`
- `pska_trace_query`
- `pska_workflow_memory_attribution`
- `pska_workflow_memory_suggestions`
- `pska_memory_change_from_conversation`
- `pska_conversation_memory_candidates_create`
- `pska_memory_review_from_workflow`
- `pska_memory_refresh_review`
- `pska_memory_update_review`
- `pska_memory_delete_review`
- `pska_memory_lifecycle`
- `pska_review_list`
- `pska_review_get`
- `pska_review_decide`
- `pska_review_decide_batch`
- `pska_review_merge_candidates`
- `pska_review_revise`
- `pska_memory_apply`
- `pska_export_brief`
- `pska_audit_list`

These tools are thin glue over RAGFlow plus the existing PSKA workflow gate:
KB ingest and parse tools return normalized `readiness` and
`ingestion_status` along with their operation result, so agents can decide
whether to wait, parse, inspect a failure, or Ask without calling provider APIs.
`pska_ingest_loop` is the file-first macro tool for Hermes: it ingests local
files through the configured KB adapter, waits for PSKA readiness, runs the
agentic Ask loop, and exports a sourced transient work product. If ingestion is
still processing, it records a resumable blocked Ask before stopping short of
retrieval/export; failed or cancelled ingestion stops without creating a
resumable Ask. Not-ready results return stable `next_actions` and a `resume`
contract when the upload loop can be resumed, so agents and frontends do not
need to infer the recovery path from provider state. `pska_ingest_loop_resume`
resumes those blocked upload loops after parsing, embedding, and indexing
finish, preserving the original Ask and export intent. The same resume path is
available from the CLI as
`pska-essential-ingest-loop-resume <run_id>` or
`PSKA_LOOP_RUN_ID=<run_id> make live-ingest-loop-resume`.
`pska_digest_scope` runs an explicit low-frequency digest over a ready
dataset/document scope. It creates a sourced digest work product and, only when
requested with `create_memory_review=true`, turns that digest into a governed
memory candidate; it does not write the memory provider directly.
`pska_digest_job_enqueue`, `pska_digest_job_list`, and `pska_digest_job_run`
provide an explicit lightweight scheduler surface for digest work. Jobs live as
PSKA workflow metadata, respect KB readiness before running, and still route any
durable memory through Review. Provider job status reports each digest job with
its selected `dataset_ids`, `document_ids`, `priority`, `attempt_count`,
readiness snapshot, result run, and `data_flow.writes_memory_directly=false` so
operators can see that document digestion is not a hidden memory write.
Hermes WebUI exposes the same path through the PSKA Knowledge panel: the Digest
card queues the job, and the Jobs card can run queued or waiting digest jobs.
The personal source tools provide the M1-M21 no-embedding local source loop:
register a user-authorized local folder or Obsidian vault, scan rebuildable
metadata and SQLite FTS5 text into `PSKA_SOURCE_DB` (default
`.pska-essential/sources.sqlite3`), search it with `pska_source_search`, and
read exact source sections through the existing `pska_source_read`. This path
writes PSKA index metadata only; it does not modify source files, write memory,
or require embeddings. M2 adds `pska_duplicate_report` for exact hash duplicate
groups and `pska_saved_search_create` for reusable local source views; M16 adds
the core `size_name_version` duplicate mode for same normalized filename,
copy/version suffix, and similar-size candidates. M17 adds the core
`text_similarity` duplicate mode over already indexed text using token Jaccard,
without embeddings. M20 adds the core `media_metadata` mode for image, video,
and audio candidate groups using media family, normalized filenames, and
similar file sizes, again without embeddings or perceptual hashes. These
reports write only PSKA registry metadata and never
delete, move, merge, or edit source files. External
M21 adds optional `image_phash` reports through ImageHash/Pillow. Install
`.[image-phash]` to enable image perceptual hash grouping by Hamming distance;
when the optional package is absent the mode returns structured `unavailable`.
External
fclones reports use `PSKA_FCLONES_BIN` when it points to
an executable binary, then fall back to `PATH`; external Czkawka reports use
`PSKA_CZKAWKA_BIN`, then `PATH`. `make live-fclones-smoke` and
`make live-czkawka-smoke` verify the CLI-backed `fclones_hash`/`czkawka_hash`
duplicate paths when the optional CLIs are installed and exit 77 when
unavailable. M3 adds `pska_source_tag_propose`/`pska_source_tag_apply` and
`pska_source_comment_propose`/`pska_source_comment_apply`; the default
tag/comment apply path writes only `.pska/annotations.jsonl` for roots with
sidecar/native/managed permission, and still leaves the original source files
untouched. M4 adds `pska_source_neighbors` for outgoing links, backlinks, and
same-folder neighbors from local Markdown or Obsidian notes, again without
embeddings or source-file writes. M5 adds
`pska_source_memory_review_create`, which turns explicit source refs into a
governed Memory Card candidate with `memory_type`, `behavior_delta`, and Review;
it does not write the memory provider directly. P2-1 adds
`pska_memory_card_list` and `pska_memory_card_get` as the provider-neutral
Memory Card inventory view. It wraps durable provider facts with
`display_text`, `memory_type`, `memory_scope`, `behavior_delta`, quality, source
refs, lifecycle, and agent-facing why-use fields; it does not replace the
memory provider or bypass review-gated update/delete flows. P2-2 adds
`pska_memory_use_trace` and `pska_memory_why_used`, which turn `memory.search`
and Memory Card inspection audit events into an explicit explanation of when a
memory was surfaced as candidate context. P2-3 adds `pska_memory_health_scan`
and `GET /api/memory/health`, a conservative Memory Card health scan for missing
envelope fields, refresh/stale candidates, and likely active-card conflicts.
P2-4 adds answer-level `memory_attribution`/`used_memory_ids` and governed
`memory_suggestions` on Ask/workflow artifacts, plus
`pska_workflow_memory_attribution` and `pska_workflow_memory_suggestions`.
Attribution records memory context supplied to the work product; suggestions
remain review candidates and never write durable memory directly. P2-5 adds
`pska_memory_timeline` and `GET /api/memory/{memory_id}/timeline`, a derived
ledger view that combines the Memory Card snapshot, lifecycle change audit,
candidate-use traces, and SourceRef anchors. It does not create another memory
store or claim hidden model causality. Hermes WebUI exposes it from the Memory
panel beside use traces, so operators can inspect a card's ledger without
leaving the daily memory surface. P2-6 adds `pska_memory_briefing` and
`GET /api/memory/briefing`, a derived memory attention view for Hermes/Jarvis
and WebUI that summarizes active cards, health issues, recent use traces, focus
items, and safe next actions without writing durable memory. P2-7 adds
`pska_memory_review_queue` and `GET /api/memory/review-queue`, a
read-only grouped maintenance view over pending/accepted Review records, Memory
Briefing focus items, and health issues. Hermes/Jarvis and the WebUI Review
page can use it to triage memory work without approving, applying, or writing
memory directly. Existing Memory Card refresh/update Reviews surface as a
dedicated `refresh_reviews` group with `refresh_review_count` and
`review_memory_refresh`, so stale/conflict/card-maintenance work does not
disappear into generic pending reviews. P2-8 adds `pska_memory_candidate_dedup` and
`GET /api/memory/candidate-dedup`, an embedding-free duplicate-candidate view
over Review records. It groups possible duplicate durable memory candidates
with normalized text, lexical token overlap, SourceRef fingerprints, and
behavior-delta fingerprints; it only produces review hints and never merges,
rejects, approves, applies, or writes memory. It also surfaces `related_groups`
for cross-scope scope collisions, such as the same preference appearing as both
global and project memory, so reviewers can choose whether to merge, narrow,
widen, or reject candidates through the normal Review flow. The explicit merge
path is `pska_review_merge_candidates` /
`POST /api/reviews/merge-candidates`: it requires caller-supplied merged
candidate text and behavior_delta, creates a new pending Review with merged
source refs, marks replaced pending candidates as `needs_edit`, and still does
not write durable memory directly. Review records expose merge lineage through
`merged_from_review_ids` and `merged_into_review_id`, so agents and the WebUI do
not need to scrape audit events to trace replacements. Memory Review Queue
separates those replaced candidates into a low-priority `merged_replacements`
lineage group and excludes them from active duplicate/related candidate dedup,
so merged-away reviews stay traceable without becoming false `needs_edit`
work. Ordinary revised reviews get the same hygiene through a low-priority
`revised_replacements` group keyed by `next_review_id`, so an old `needs_edit`
review does not remain active after a successor Review exists. Memory Review
Queue also includes a `candidate_quality` gate for pending or accepted
memory_patch reviews that are missing `memory_type`,
`memory_scope`, `behavior_delta`, source evidence, or clear behavior impact; it
surfaces review/edit next actions before apply so vague memory summaries do not
quietly become durable Memory Cards. `pska_memory_apply` uses the same quality
gate for memory_patch writes, while conversation/workflow-derived memory
proposals now attach a conservative Memory Card envelope before review.
Workspace status uses the same filter, so Hermes/Jarvis sees quality-review
next actions instead of `apply_accepted_memory` for accepted but low-quality
candidates. The review queue payload now carries quality candidate draft fields
(`text`, missing fields, Memory Card type/scope, behavior_delta), and the WebUI
exposes inline quality-fix controls that mark a candidate `needs_edit` and submit
a revised governed Review without writing memory directly. Queue summaries also
include `candidate_quality_breakdown` by issue type, missing field, status, and
severity so Hermes/WebUI can choose the most useful batch-first repair path.
The `candidate_quality` group exposes a batch edit action that marks all quality
issues as `needs_edit` through `pska_review_decide_batch`; it still does not
write memory or create revised Reviews by itself. Active `needs_edit`
memory_patch queue items now also carry a `memory_candidate` draft plus an
inline revision capability, so the WebUI can submit the edited Memory Card
candidate directly from the queue after batch routing. The WebUI also exposes a
lightweight inline merge editor on duplicate/related candidate queue groups; it
shows member candidate texts and behavior deltas before the merged Review is
created. M6 adds
`pska_source_audit_run`, a read-only folder/vault audit that reports root
summaries, exact duplicate previews, unresolved Markdown/Obsidian links,
unlinked Markdown notes, source-route candidates, and concrete `next_actions`
for Hermes/WebUI to follow. M6-1 adds
`pska_source_memory_candidates_from_audit` and
`POST /api/sources/memory-candidates/from-audit`, which turn route-like audit
findings into deduped governed Memory Card review candidates. It reruns the
same read-only audit, skips existing pending/accepted candidates with matching
source refs and behavior deltas, never writes source files, never writes memory
directly, and does not require embeddings.
M7 adds `pska_jarvis_briefing`, a Hermes-facing briefing contract that composes
workspace status, source audit findings, memory/review cues, and prioritized
`next_actions` into a dashboard-ready payload. It does not generate answer text,
write source files, write memory directly, or require embeddings.
M31 adds `pska_agentic_context_brief` and `POST /api/agentic/context-brief`, a
read-only pre-answer context entry for Hermes. It composes KB evidence, local
source recall, relevant Memory Cards, memory/source trace signals, specialist
roles, and next actions without creating reviews, writing memory, editing source
files, requiring embeddings, or generating final answer text.
M32 persists a bounded snapshot of each Agentic Context Brief into the
transient workflow ledger and exposes `pska_agentic_context_brief_list` plus
`GET /api/agentic/context-briefs`. This makes pre-answer context recoverable
across page refreshes and later Hermes turns without turning PSKA into another
knowledge store.
M8 adds `pska_source_audit_job_enqueue`, `pska_source_audit_job_list`, and
`pska_source_audit_job_run` as the Jarvis-friendly proactive audit surface. Jobs
live as PSKA workflow metadata, can be listed through `pska_provider_jobs` and
workspace status, run the same read-only audit, never write source files or
memory directly, and do not require embeddings. M9 adds
`pska_source_audit_schedule_create` and `pska_source_audit_job_tick`: scheduled
jobs wait on `due_at`, the tick turns due jobs into queued jobs, and recurring
cadences create the next waiting job after a run completes. This gives Hermes a
wall-clock scheduler contract without a hidden background source-file scanner.
P4 begins the Eidolia bridge with `pska_eidolia_context_read` and
`pska_eidolia_memory_review_create`: Eidolia `thought`/`artifact` payloads are
normalized into `SourceRef(adapter="eidolia")`, can become governed Memory Card
review candidates, and never mutate the canvas, copy project files, or write
durable memory directly. P4-1 adds `pska_trace_query` and
`GET /api/trace/query`, a read-only derived trace view over audit and Review
records. It can query by review, proposal, memory, target, action, or SourceRef,
including Eidolia SourceRefs, without embeddings, source-file writes, durable
memory writes, or hidden-causality claims. P4-2 adds
`pska_eidolia_project_trace_import` and
`POST /api/eidolia/project-traces/import`, a read-only file adapter for explicit
Eidolia project folders, `canvas-workspace.json`, and `agentic-traces/*.json`.
It imports SourceRef/audit trace references only; PSKA still does not own or
mutate the canvas.
P1 adapter work adds `pska_source_extract_job_enqueue`,
`pska_source_extract_job_list`, and `pska_source_extract_job_run` as the
Jarvis-friendly source extraction queue. Jobs run `pska_source_scan` with the
selected extractor, update rebuildable source index metadata/FTS sections, never
write source files or memory directly, and do not require embeddings.
P3-1 installs and validates the MarkItDown optional extra inside the project
virtual environment, so broad local file extraction can be tested without
promoting MarkItDown to a core dependency. Use
`make live-markitdown-smoke PYTHON=.venv/bin/python`. The smoke verifies both
`adapter_slots.summary.extraction.available` and an actual MarkItDown-backed
conversion through `extract_source_file`.
P3-4 adds a Docling optional extraction adapter for PDF/layout/table-sensitive
sources and installs Docling 2.119.0 in the project `.venv`. Use
`make live-docling-smoke PYTHON=.venv/bin/python`; the target now verifies a
real Docling-backed HTML and PDF conversion and reports `docling` in the
available extraction adapters.
P3-2 installs and validates the watchdog optional extra and adds
`pska_source_watch_once`, a bounded authorized-root event bridge. It listens for
a short explicit interval, then queues source extraction and/or audit jobs; it
does not run as a hidden daemon, scan full disk, edit source files, write memory,
or require embeddings. Use `make live-watchdog-smoke PYTHON=.venv/bin/python`
to verify a real filesystem event queues both job types.
M10 adds `pska_obsidian_moc_propose` and `pska_obsidian_moc_apply` for governed
Obsidian MOC writeback. Proposal builds a preview from explicit source refs and
writes only PSKA registry metadata; apply requires an `obsidian_vault` root with
`native_write` or `managed` permission and updates only the PSKA-managed MOC
block in the target Markdown note. It does not rewrite the rest of the note,
write memory directly, or require embeddings.
M11 extends `pska_source_tag_propose`/`pska_source_tag_apply` with explicit
`write_target="obsidian_frontmatter"` for Obsidian Markdown tags. Proposal is
still metadata-only; apply requires an `obsidian_vault` root with `native_write`
or `managed` permission and appends a unique value to YAML frontmatter `tags`
without touching note body text or creating a sidecar. Existing tags are
treated as no-op applies.
M12 extends `pska_source_comment_propose`/`pska_source_comment_apply` with
explicit `write_target="obsidian_markdown_comment"` for Obsidian Markdown notes.
Proposal is metadata-only; apply requires `native_write` or `managed` permission
and appends a visible PSKA Comment marker block to the note without changing
existing body text.
M13 adds `pska_source_collection_create`, `pska_source_collection_list`, and
`pska_source_collection_resolve`: a named collection can hold explicit
SourceRefs or a reusable no-embedding search selector, then resolve back into
normal `ContextPacket` payloads for Hermes/RAG use. Collections write only PSKA
registry metadata, never copy, move, delete, or edit user source files.
M14 improves `pska_source_search` without embeddings: SQLite FTS5 results now
use a weighted BM25/title/path/heading ranking envelope, return plain and
highlighted snippets, expose `match_reason`, `lexical_rank`, and `rank_boost`
metadata, and fall back to path/title/body LIKE matches when the strict FTS
query misses filename-style routes.
M15 extends governed Obsidian MOC proposal/apply with `group_by` support for
`none`, `folder`, `tag`, `topic`, and `project`. Proposals include grouped link
payloads and rendered Markdown previews; apply still edits only the PSKA-managed
MOC marker block in the target note.
M16 adds the built-in `size_name_version` duplicate report mode for local
folder/vault management. It finds same-name version/copy candidates with similar
sizes, marks them as lower-confidence review signals, and still performs no
source-file changes.
M17 adds built-in `text_similarity` duplicate reports over indexed source text.
It uses token Jaccard with configurable `scope.similarity_threshold`, requires
no embeddings, and remains a dry-run review signal.
M18 adds duplicate candidate review workflow through
`pska_duplicate_review_list`, `pska_duplicate_group_mark`, and the Sources
panel. Users can mark candidate groups as `reported`, `keep_reviewing`,
`reviewed`, or `ignored` with notes; the action writes only PSKA registry/audit
metadata and still performs no source-file cleanup.
M19 adds `pska_duplicate_cleanup_propose`, a dry-run cleanup proposal generator
for reviewed duplicate groups. It chooses a keep candidate through explicit
strategies such as `keep_first`, `keep_largest`, `keep_newest`, or
`keep_selected`, records would-archive candidates, and still cannot apply,
delete, move, merge, or edit files.
M20 adds built-in `media_metadata` duplicate reports for image, video, and audio
files. It groups same-media-family files by normalized filename and similar
size, requires no embeddings or perceptual hash, and remains a dry-run review
signal.
M21 adds optional `image_phash` duplicate reports through ImageHash/Pillow for
local image perceptual hash candidates. It uses `scope.phash_threshold` or the
default Hamming threshold, requires no embeddings, and remains review-only.
M22 adds `pska_memory_refresh_review` and
`POST /api/memory/cards/{memory_id}/refresh-review`, a Memory Card refresh
entrypoint that creates a pending `memory_update` Review from an existing
durable memory card. It records refresh reason, previous/proposed text, and
no-text-change refresh requests, but never writes durable memory until an
accepted Review is explicitly applied.
M23 surfaces those refresh Reviews as first-class queue work: Memory Review
Queue now has a `refresh_reviews` group, `refresh_review_count` summary, and
`review_memory_refresh` next action; Jarvis/WebUI prioritize the same signal.
M24 adds a WebUI refresh-review workbench card that shows source memory id,
previous text, proposed text, no-text-change refresh checks, and the exact
Review action inline inside Memory Review Queue.
M25 adds `pska_alpha_readiness` and `GET /api/alpha/readiness`, a read-only
trial gate that aggregates runtime diagnostics, workspace status, source safety,
memory governance, KB readiness, memory health, and UX gaps into
`alpha_ready` / `technical_alpha` / `not_ready` guidance.
M26 adds `pska_alpha_trial_guide` and `GET /api/alpha/trial-guide`, a read-only
first-run guide that turns the readiness result into guarded phases for
environment setup, one-scope knowledge trial, sourced Ask, memory review,
writeback backup checks, and broader-alpha exit criteria.
M28 adds `pska_alpha_recovery_plan` and `GET /api/alpha/recovery-plan`, a
read-only backup/restore boundary report for alpha trials. It names PSKA-owned
SQLite ledgers, user-owned source roots, provider-owned KB/memory state, manual
restore drills, and writeback preflight checks without creating backups or
restoring data.
M29 adds `pska_alpha_first_run_session`,
`pska_alpha_first_run_item_update`, `GET /api/alpha/first-run-session`, and
`POST /api/alpha/first-run-session/items/{item_id}`. It persists the guided
alpha first-run checklist in the PSKA local ledger so an operator can mark
runtime checks, read-only source scope, sourced Ask, memory review, and
writeback-lock checks as done or skipped. It writes only checklist state and
audit events; it does not execute the underlying trial step, scan source
folders, write source files, create backups, restore data, or apply durable
memory.
The bundled WebUI exposes this through Home's Jarvis Bar, a Home Alpha Trial
Guide card with persisted first-run checklist, and a dedicated Sources panel:
users can register local folders or Obsidian vaults, scan them, run
read-only audits, inspect duplicate/link/route candidates, search through
SQLite FTS5 with ranking/snippet cues, save reusable searches and source collections, select exact source
sections for tag/comment proposals, apply sidecar annotations when permitted, explicitly
apply Obsidian frontmatter tags and PSKA Comment blocks when native write is
authorized, and promote source-route candidates into Review without hidden memory
writes. Obsidian MOC actions from source audits create a governed, optionally
grouped MOC proposal before any native vault write is applied.
`pska_retrieval_probe` checks whether a ready scope can retrieve context.
`pska_memory_change_from_conversation` is the daily Hermes path for user-driven
memory add, correction, clarification, or deletion. It still creates proposal,
review decision, memory apply, and audit records, but conversation policy
defaults to auto-apply so ordinary corrections do not leave a pending Review
queue item. Use `force_review=true` for uncertain, risky, destructive, or
ambiguous memory changes.
`pska_conversation_memory_candidates_create` is the safer extraction path for
stable preferences, decisions, working habits, source routes, and corrections
that Hermes notices in a conversation when the user did not explicitly say
"remember". It accepts structured candidates with `text`, `memory_type`,
`memory_scope`, `behavior_delta`, and message evidence, creates pending Review
items, dedupes obvious repeats, and never writes durable memory directly.
Memory Review Queue surfaces these as a dedicated `conversation_candidates`
group with a stable `review_conversation_memory_candidate` next action, so
daily memory capture does not disappear into generic pending reviews.
`pska_memory_probe` checks whether the configured memory backend can search
through the PSKA memory contract; it rejects fake memory by default for live
component verification and records a `memory.probe` audit event.
`pska_component_check` is the full component proof path by default; if memory
or closed-loop checks are skipped, the result is `incomplete` rather than a
full success. Set `PSKA_COMPONENT_CONNECTIVITY_ONLY=1` or use
`make live-connectivity-check` when you only need runtime/provider/memory
connectivity without a dataset scope. Component-check, workspace-status, and
live closed-loop CLI startup configuration errors are returned as structured
JSON with a nonzero exit. A processing KB scope also returns `incomplete`, so
long-running parsing, embedding, or indexing is reported as a readiness wait
rather than a provider fallback or backend failure.
`pska_alpha_readiness` is the product trial gate: it does not run writes or a
closed-loop probe, but tells operators whether the current instance is ready for
owner dogfooding, guided technical alpha, or only demo/development use.
`pska_alpha_trial_guide` turns that verdict into an executable-looking but
non-executing first-run plan: it recommends read-only scope selection, lists
actions/tools/views for each phase, keeps native writeback locked behind backup
verification, and never registers roots, scans files, applies memory, or writes
source files by itself. Home renders the same guide as phase cards, guardrails,
and next-action buttons so operators can see the trial path before moving into
Sources, Ask, Review, or Settings.
`pska_alpha_recovery_plan` is the companion recovery contract: it separates
PSKA-local state that can be copied from provider-owned state that must use
RAG/KG/memory backend tooling, and Home renders its backup objects and writeback
preflight checks inside the Alpha Trial Guide panel.
`pska_alpha_first_run_session` is the persisted operator checklist for that
guide. It lets Hermes or WebUI mark individual first-run items as complete,
pending, skipped, blocked, or needing attention while preserving the safety
boundary: the update call records progress only and never runs the named source,
Ask, writeback, backup, restore, or memory operation.
M30 makes that first-run checklist usable for real alpha rehearsal: each WebUI
item now has an operator note field for confirmation evidence, anomalies, and
retrospective notes. Saving a note uses the same
`pska_alpha_first_run_item_update` / first-run session route and still writes
only PSKA checklist/audit state, not user source files or durable memory.
M31 makes agentic intervention concrete: Hermes/WebUI can request a one-shot
Agentic Context Brief before answering or acting. The brief starts a transient
workflow, retrieves bounded evidence, searches local source indexes, searches
governed memory with audit-backed use traces, and returns safe action hints for
Ask, Reader, Memory Card, and Trace surfaces.
`pska_live_closed_loop_probe` is stricter: it rejects fake KB/retrieval
providers and then runs readiness, retrieval, agentic Ask, source inspection,
and explicit export for a transient work product against the configured live
providers. Durable memory or graph changes still use the normal review/apply
workflow. Retrieval, component, and live probes accept `dataset_names` as an
input convenience, but PSKA resolves them into canonical dataset IDs before
retrieval or Ask.
Dataset creation and ingest tools accept optional `embedding_model` so the
PSKA product layer can request a configured RAGFlow embedding model without
exposing RAGFlow-internal fields.
`pska_kb_delete` is the explicit development maintenance path for bad local
datasets; it can delete selected datasets by ID, by name, or all datasets
through the KB adapter and records audit instead of touching provider databases
directly.

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
- `docs/SYSTEM_ARCHITECTURE_VISION.zh.md`
- `docs/FEASIBILITY_AUDIT.md`
- `docs/ADAPTER_CONTRACTS.md`
- `docs/DEMO_RUNBOOK.md`
- `docs/RUNNING_AND_TESTING.md`
- `skills/hermes/SKILL.md`
- `skills/hermes/knowledge-retrieval/SKILL.md`
- `skills/openclaw/SKILL.md`
- `integrations/hermes-webui-extension/pska-mini/README.md`

## Product API And Hermes WebUI

The Product API is the Hermes WebUI-facing boundary. Hermes WebUI calls PSKA
through its backend proxy routes, and those proxy routes call PSKA Product API
routes only. Browser code and Hermes agents must not call RAGFlow, Graphiti,
embedding services, LLM providers, databases, or queues directly.
Product API startup validates both workflow providers and the KB gateway before
serving; missing provider env or unauthorized fake mode fails explicitly instead
of starting a partially wired integration.

Default local URL:

```text
http://127.0.0.1:8765
```

Implemented Alpha routes:

- `GET /api/health`
- `GET /api/capabilities`
- `GET /api/alpha/readiness`
- `GET /api/alpha/trial-guide`
- `GET /api/alpha/recovery-plan`
- `GET /api/migration/manifest`
- `GET /api/policy`
- `GET /api/runtime/diagnostics`
- `GET /api/workspace/status`
- `POST /api/runtime/component-check`
- `POST /api/runtime/eval`
- `POST /api/runtime/retrieval-probe`
- `POST /api/runtime/memory-probe`
- `POST /api/runtime/closed-loop-probe`
- `POST /api/ingest-loop`
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
- `POST /api/turn-context`
- `POST /api/agentic/context-brief`
- `POST /api/digest`
- `POST /api/digest-jobs`
- `GET /api/digest-jobs`
- `POST /api/digest-jobs/run-next`
- `POST /api/digest-jobs/{run_id}/run`
- `POST /api/jarvis/briefing`
- `GET /api/provider/jobs`
- `GET /api/workflows`
- `GET /api/workflows/resumable-asks`
- `GET /api/workflows/{run_id}`
- `POST /api/workflows/{run_id}/resume-ask`
- `POST /api/workflows/{run_id}/memory-review`
- `GET /api/workflows/{run_id}/export`
- `GET /api/sources/roots`
- `POST /api/sources/roots`
- `POST /api/sources/roots/{root_id}/scan`
- `POST /api/sources/search`
- `POST /api/sources/neighbors`
- `POST /api/sources/duplicates`
- `POST /api/sources/duplicate-review`
- `POST /api/sources/duplicate-groups/{group_id}/mark`
- `POST /api/sources/duplicate-groups/{group_id}/cleanup-proposals`
- `POST /api/sources/audits/run`
- `POST /api/sources/audit-jobs`
- `GET /api/sources/audit-jobs`
- `POST /api/sources/audit-schedules`
- `POST /api/sources/audit-jobs/tick`
- `POST /api/sources/audit-jobs/run-next`
- `POST /api/sources/audit-jobs/{run_id}/run`
- `POST /api/sources/extraction-jobs`
- `GET /api/sources/extraction-jobs`
- `POST /api/sources/extraction-jobs/run-next`
- `POST /api/sources/extraction-jobs/{run_id}/run`
- `POST /api/sources/watch-once`
- `POST /api/sources/saved-searches`
- `POST /api/sources/tags/proposals`
- `POST /api/sources/tags/{proposal_id}/apply`
- `POST /api/sources/comments/proposals`
- `POST /api/sources/comments/{proposal_id}/apply`
- `POST /api/sources/obsidian/moc/proposals`
- `POST /api/sources/obsidian/moc/{proposal_id}/apply`
- `POST /api/sources/memory-reviews`
- `POST /api/sources/memory-candidates/from-audit`
- `POST /api/sources/read`
- `POST /api/eidolia/context/read`
- `POST /api/eidolia/memory-reviews`
- `POST /api/eidolia/project-traces/import`
- `POST /api/memory/search`
- `POST /api/memory/conversation-change`
- `POST /api/memory/conversation-candidates`
- `POST /api/memory/cards/{memory_id}/refresh-review`
- `POST /api/memory/update-review`
- `POST /api/memory/delete-review`
- `GET /api/memory/{memory_target_id}/lifecycle`
- `GET /api/memory/{memory_id}/timeline`
- `GET /api/trace/query`
- `GET /api/reviews`
- `GET /api/reviews?status={status}`
- `GET /api/reviews/{review_id}`
- `POST /api/reviews/{review_id}/decision`
- `POST /api/reviews/{review_id}/revision`
- `POST /api/reviews/{review_id}/apply-memory`
- `GET /api/audit`
- `GET /api/audit?action={action}`

The repository still contains a bundled local UI for development diagnostics and
smoke testing. It is not the v1 product workspace. The v1 user-facing workspace
is the Hermes WebUI fork, with PSKA-specific panels calling Hermes backend proxy
routes under `/api/pska/*`.

The diagnostic UI exposes Home, Knowledge Bases, Ask, Reader, Writing, Review,
Activity, and Settings. It is served by the Product API and uses only
same-origin `/api/...` calls. The same workflow contracts are intended to be
consumed by Hermes WebUI through its PSKA proxy. Ask responses include explicit
loop steps so users and agents can see scope checks, KB readiness, retrieval,
context inspection, proposal creation, review creation or skipping, and
transient brief preparation.
Knowledge Bases can also run the file-first ingest loop from an empty
workspace: the upload form posts files to `POST /api/ingest-loop`, uses the
same PSKA KB readiness gate, and opens Writing with the exported sourced work
product only when the configured adapters complete successfully. The form's
Wait checkbox
controls whether Run Loop blocks for readiness or quickly returns a resumable
not-ready workflow for long parsing, embedding, and indexing jobs. Processing
or failed ingestion remains visible as not-ready status instead of falling back
to fake data or an unsourced answer. Explicit fake KB mode also starts empty;
tests and demos create source knowledge through upload instead of relying on
preloaded demo datasets. The same form exposes PSKA-owned loop
controls for limit, max iterations, minimum context, additional retrieval
queries, source inspection, proposal kind, optional review, and graph-aware
retrieval; these are Product API fields, not provider-native calls. When the
loop creates a durable
knowledge candidate, the response includes the proposal, review decision, and
memory-apply state so the frontend can continue the Review workflow without
inspecting workflow internals. When the uploaded scope is still processing, the
frontend opens the blocked Ask result with Track & Resume actions; failed or
cancelled ingestion stays a cleanup/status issue instead of becoming a fake
answer. Knowledge Bases exposes explicit Delete and Delete All cleanup actions
through Product API for development maintenance, not as the demo/product start
path.
Home loads `/api/workspace/status` and `/api/jarvis/briefing`. The Jarvis Bar
shows Hermes-ready priorities across workspace status, personal source audit,
review, and memory cues; it also exposes the first safe next actions without
requiring the UI to inspect provider internals. Workspace status still shows
product-level next actions, including ready-to-ask scopes, ingestion waits,
resumable Ask workflows, pending reviews, and accepted durable memory awaiting
apply. Each next action includes stable PSKA tool/API/view hints and safe
parameters. In an empty workspace, the first action points to the full
file-to-work-product loop (`pska_ingest_loop` / `POST /api/ingest-loop`) rather
than a provider-native setup step; Home opens the Knowledge Bases Run Loop form
with the safe loop defaults ready. Mutating frontend actions refresh this status
after completion so the Home guidance follows the current workflow state.
Home also exposes a manual Agentic Context Brief control. It calls
`/api/agentic/context-brief` only when requested, then shows selected evidence,
local source recall, relevant memory, trace signals, and next actions without
running a full Ask or creating Review items. Recent context briefs are loaded
from `/api/agentic/context-briefs` as workflow snapshots and can be restored
without re-running retrieval.
Workspace status reports both aggregate KB readiness and per-dataset readiness,
so a newly uploaded processing dataset does not hide
other ready datasets from Ask. Workspace status also translates lower-level
ingestion job actions such as `start_parse` into stable product actions such as
`parse_documents`. Home next-action buttons can prefill Ask scope and check
readiness, start document parsing, open and track blocked Ask workflows, resume
ready blocked Ask workflows, open pending reviews, and apply already accepted
durable memory through Product API routes.

The Sources panel is the landing surface for personal source actions from
Jarvis: `register_source_root` opens registration, `scan_source_root` scans the
selected root, duplicate/link actions rerun source audit, and source-route
actions create governed Review candidates through
`/api/sources/memory-candidates/from-audit` or the single-candidate
`/api/sources/memory-reviews` fallback.
The same panel lets users save a source search and run explicit tag/comment
proposal -> apply paths through `/api/sources/tags/*` and
`/api/sources/comments/*`. Tags default to sidecar apply, with
`write_target=obsidian_frontmatter` available for authorized Obsidian Markdown
notes; comments default to sidecar apply, with
`write_target=obsidian_markdown_comment` available for authorized Obsidian
Markdown notes. Obsidian MOC actions create governed proposals through
`/api/sources/obsidian/moc/proposals`; apply is a separate native-write route
and only updates the PSKA-managed marker block in the target note.
Readiness responses include normalized `ingestion_status` job summaries with
phase, progress, counts, next actions, and failure reasons so frontend and agent
flows can distinguish uploaded, parsing, embedding, indexing, ready, failed,
and cancelled scopes.
`pska_provider_jobs` and `GET /api/provider/jobs` expose a workspace-level job
inventory across KB ingestion/readiness, PSKA digest jobs, and recent provider
audit events. Workspace status includes a compact `jobs` summary for Home and
Activity views and exposes queued/waiting digest work as a `run_digest_job`
next action.
Settings loads `/api/policy` as the product-level workspace governance surface,
including durable proposal kinds, configured durable-memory action, available
modes, and the fact that transient results skip durable governance. Settings
also loads `/api/capabilities` as the product-level capability contract, and
Writing/Review durable-memory controls stay disabled until the selected memory
operation is explicitly reported as supported.
The same capability response exposes the soft tool-policy manifest so Hermes
WebUI can label read-only, provider-writing, readiness-gated, and
review-required actions without learning provider-native APIs.
It also exposes `memory.search_view`, the stable contract for superseded-memory
filtering and agent-facing text fields such as `display_text` and
`current_text`.
`pska_migration_manifest` and `GET /api/migration/manifest` expose a scoped
component migration inventory: PSKA control records, provider source refs,
memory targets, agent-host refs, exclusions, and migration steps. It is a map
for provider-owned exports, not a raw document/chunk/graph dump.
Ask persists the loop summary on the workflow so Writing can reopen governance
state, durable/transient status, review requirements, and steps later. Ask
includes a dataset/document picker that syncs to explicit scope IDs and result
actions for Writing, Review, and accepted memory application. Ask can tune loop
depth with max iterations, required context count, explicit additional
retrieval queries, bounded source inspection, and optional graph retrieval
inside the selected scope. Ask, Digest, MCP, Product API, and upload-to-Ask
loops can also accept `model_context_tokens` and `model_profile`; when a model
context size is provided, PSKA records `loop.context_budget` and uses effective
Top-N limits for retrieval, memory search, and source inspection.
Additional retrieval queries come from the user or agent and are recorded in the
PSKA loop; runtime code does not add case-specific query expansion. Source
inspection reads unique retrieved source refs through PSKA adapters, records
`source.inspect` loop metadata, and writes `source.read` audit records. Graph retrieval is passed as a PSKA retrieval hint,
recorded in loop steps and audit metadata, and remains behind adapters. Ask also
searches governed durable memory and keeps memory facts separate from external
source retrieval. When a memory fact carries readable upstream source refs, Ask
can federate those refs back through the retrieval adapter, append missing KB
evidence as context, and record `memory.source_federate`; this is not a provider
fallback and it does not create a PSKA-side fact ledger. If the required context
count is not met, Ask returns
`insufficient_context`, shows any retrieved partial context, and does not create
a proposal, review, or export.
If the selected dataset or document scope is not ready, Ask records a blocked
workflow with readiness diagnostics so Writing, Activity, and MCP tools can
recover the blocked state after ingestion continues. Users and agents can resume
that blocked Ask from the stored workflow when the selected scope becomes ready;
the resumed Ask creates a new audited workflow linked back to the blocked run.
The resumable Ask list returns a fresh readiness check plus stable `resume` and
`next_actions` contracts, including the correct PSKA resume tool/API for plain
Ask workflows versus upload loops.
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
The Review queue is an exception inbox for uncertain, risky, conflicting, or
batch-derived memory changes. Ordinary user corrections should go through the
conversation-native memory API/tool and usually auto-apply under workspace
policy. Non-conversation memory candidates probe existing scoped memory before
durable write; possible conflicts are recorded in proposal metadata and can
downgrade `auto_apply` to pending Review. The Memory Review Queue exposes
group-level accept/reject actions for pending and conversation-derived
candidates through WebUI, Product API, and `pska_review_decide_batch`; the batch
decision changes Review state only and still requires `pska_memory_apply` before
durable memory is written. Existing Memory Card refresh/update Reviews are
shown as `refresh_reviews`, with `review_memory_refresh` pointing to the exact
Review record before any accept/apply step. The Review queue can filter by status while Home keeps an independent
pending review summary. Review records expose source trace fields, and Review cards can
open cited sources through the Product API Reader before a durable decision is
made, and can open the originating Writing workflow context. Review cards show
status-specific actions: pending reviews can be decided,
accepted durable reviews can be applied, `needs_edit` reviews can be revised,
and rejected reviews are closed. After a review decision, the frontend keeps the
decided review visible so the next action is available. Reviews marked
`needs_edit` can create a revised candidate review while preserving the original
review history; for memory_patch candidates the WebUI/API/MCP revision path can
also submit edited candidate text, memory type, memory scope, and
`behavior_delta` while retaining the original evidence refs. Review API records
expose revision lineage so old and revised candidates can be traced in both
directions. Review
decisions and memory apply/update/delete actions refresh the current Ask/Writing
state, and applied memory state is served back through Review API records.
Writing shows the applied durable knowledge result and links to its lifecycle.
Locked/applied Review cards can also open the durable memory lifecycle directly.
Applied memory can be found by later Ask runs through the memory adapter and is
shown in Writing as durable workspace context with its supporting source trace.
When Graphiti fact provenance resolves to KB source refs, Ask may read those
sources and include them as federated supporting context so the answer can cite
evidence rather than relying on the memory text alone.
Writing can create a governed update review from an explicit MemoryFact when
the selected memory backend reports update support; the update applies only
after the review is accepted and records version metadata in the memory apply
result and `memory.update` audit record.
Writing can create a governed deletion review from an explicit MemoryFact; the
delete applies only after the review is accepted and produces a `memory.delete`
audit record.
Writing can inspect a MemoryFact's PSKA decision lifecycle from PSKA audit
records, showing the reviewed apply/update/delete chain without calling a memory
backend directly. This audit lifecycle is governance history, not the
authoritative provider data lineage; fact-to-source lineage should be resolved
from provider-carried provenance such as Graphiti episode metadata.
For temporal correction episodes, lifecycle lookup also follows semantic target
metadata such as `target_fact_id`, so inspecting the old fact can show the later
correction episode that superseded it.
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
workflow run, `next_actions`, optional `resume` contract, and audit trail rather
than a disposable error response. Knowledge Bases shows dataset/document
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
readiness actions while keeping Resume Ask or Resume Loop as the path that
preserves the original workflow request. It can also open optional document
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
and memory connectivity, the explicit capability contract, and a component
check that aggregates runtime diagnostics, memory probe, retrieval probe, and
closed-loop probe. Settings also exposes product acceptance eval, focused
retrieval probes, and memory probes for verifying backend paths through PSKA
instead of provider-native tools. Product acceptance starts by ingesting fresh
temporary source files; outside explicit all-fake development mode it leaves
manual-review durable memory candidates pending instead of applying them
automatically. Runtime diagnostics include a read-only memory
search contract check so
a shallow Graphiti health check cannot be mistaken for a working memory
backend. Settings and Product API runtime
context expose the derived memory namespace. Product API health, diagnostics,
explicit probe audit records, and other audit records include the runtime
workspace/tenant context from `PSKA_WORKSPACE_ID` and `PSKA_TENANT_ID`; the
review store uses that same context to scope workflows, reviews, memory apply
records, and audit reads, while memory adapters use it to scope durable memory
backend search and writes.
