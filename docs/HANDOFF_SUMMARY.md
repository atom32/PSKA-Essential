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
- Keep audit trails for retrieval, proposals, review decisions, memory changes,
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
  retrieve them, so local upload-to-Ask checks do not require RAGFlow. Fake KB
  is intentionally text-only; PDF-like or binary uploads are marked as failed
  ingestion with an explicit RAGFlow/real-KB guidance message instead of being
  treated as ready context.
- RAGFlow KB gateway glue for dataset creation, document upload, parsing,
  status polling, and optional structure graph read.
- RAGFlow retrieval adapter.
- Graphiti memory adapter with reviewed add and reviewed entity-edge delete.
  Reviewed update remains explicitly unsupported for Graphiti until a
  transactional fact update contract exists.
- Company GraphRAG stub.
- SQLite review store.
- Audit events.
- MCP tool registry.
- Product API over the PSKA workflow and KB gateway.
- Frontend Alpha served by the Product API, including Home, Knowledge Bases,
  Ask, Reader, Writing, Review, and Settings.
- PSKA-controlled agentic Ask loop with explicit loop diagnostics.
- Canonical KB readiness checks for Product API and MCP Ask entry points.
- Normalized KB ingestion status for Product API, MCP, and frontend flows,
  including uploaded/parsing/embedding/indexing/ready/failed/cancelled phases,
  progress, counts, next actions, and failure reasons.
- MCP ingest and parse tools return normalized readiness and ingestion status
  alongside their operation result, so Hermes can decide whether to wait, parse,
  inspect failure, or Ask without provider direct calls.
- Frontend Ask scope picker for dataset/document selection through Product API.
- Frontend Ask controls for loop max iterations, required context count, and
  optional graph retrieval within selected scope.
- Agentic Ask supports explicit additional retrieval queries from the user or
  agent; PSKA records the query plan and each scoped retrieval step without
  adding runtime case-specific query expansion.
- Agentic Ask inspects a bounded number of unique retrieved sources through the
  retrieval adapter, stores source inspection snippets on the workflow artifact,
  and writes normal `source.read` audit records.
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
- The frontend Ask result can refresh a readiness-blocked workflow in place and
  enable Resume Ask or Resume Loop once the selected KB scope becomes ready.
- The frontend Ask result also supports user-started `Track & Resume`, polling
  readiness and automatically resuming the stored Ask when the scope becomes
  ready.
- Successful Ask prepares a transient sourced brief/artifact without creating
  workflow export audit records.
- Ask persists the agentic loop summary on workflow metadata, including
  governance action, durable/transient status, review requirement, and steps.
- MCP exposes `pska_workflow_list` so Hermes can recover recent workflow runs
  before opening state, artifacts, briefs, or exports.
- Writing shows matched durable memory facts alongside source context when a run
  is reopened, including each memory fact's supporting source trace.
- Writing shows applied durable knowledge results and links to their lifecycle.
- Frontend Ask result actions for Writing, Review, and accepted memory changes.
- Frontend review/apply state synchronization across Ask, Review, and Writing,
  backed by Review API memory-apply records.
- Existing sourced transient workflows can be turned into pending durable memory
  reviews through Product API, MCP, and the frontend Writing/Ask Memory Review
  action without re-retrieval or direct memory changes; the frontend opens the
  resulting Review record and focuses Activity on the actual governance event.
- Existing durable MemoryFacts can create governed deletion reviews through
  Product API, MCP, and frontend Writing actions; deletion applies only after
  accepted review and writes `memory.delete` audit records.
- Existing durable MemoryFacts can create governed update reviews through
  Product API, MCP, and frontend Writing actions; update applies only after
  accepted review and records version metadata plus `memory.update` audit
  records.
- Product API, MCP, and frontend Writing can inspect a durable MemoryFact
  lifecycle from PSKA audit records, showing reviewed apply/update/delete
  history without direct memory-backend history access.
- Review queues can be resumed through Product API single-review reads and MCP
  `pska_review_list` / `pska_review_get`; frontend Review actions now open exact
  single-review Product API records by ID.
- Reviews marked `needs_edit` can create revised pending reviews from the same
  workflow/source trace through Product API, MCP, and frontend Review actions.
  Review records expose revision lineage so original and revised candidates can
  be traced in both directions.
- Review records expose `source_refs` / `source_count`, and the frontend Review
  queue shows cited sources with Product API Reader actions and can open the
  originating Writing workflow context.
- Review cards show status-specific actions: pending decisions, accepted memory
  apply, applied memory lifecycle history, `needs_edit` revision, and closed
  rejected reviews.
- After a review decision, the frontend keeps the decided review visible so the
  next action is available.
- Durable memory review creation, acceptance, and apply all refuse source-less
  durable proposals; reject/edit decisions can still close or revise bad queued
  reviews without writing long-term knowledge.
- Frontend Review queue supports status filtering while Home keeps an
  independent pending-review summary.
- Frontend ingestion tracking: upload refreshes document status, readiness, and
  normalized ingestion job status until terminal processing state, and exposes
  status actions for parse, tracking, failure reload, and ready-to-Ask states.
- Frontend parse action for loaded unready documents through Product API.
- Frontend/Product API optional document structure graph read.
- Product API runtime diagnostics and Settings diagnostics view for provider
  connectivity without frontend provider direct calls.
- Runtime diagnostics include a read-only memory search contract check, so a
  healthy Graphiti `/healthcheck` does not mask missing LLM/embedding provider
  configuration.
- MCP exposes `pska_runtime_diagnostics`, so Hermes can inspect the same
  read-only Product API diagnostics without direct provider calls.
- Frontend Settings exposes component check plus retrieval, memory, and live
  closed-loop probes through Product API routes; probe audit records remain
  scoped to PSKA workspace/tenant context.
- Product API `/api/capabilities`, MCP `pska_capabilities_get`, health, runtime
  diagnostics, workspace status, and frontend Writing/Settings expose memory
  operation capabilities. Unsupported durable memory operations are blocked
  before creating dead-end review items, and historical accepted unsupported
  reviews surface as inspect actions instead of apply actions.
- The frontend explicitly loads `/api/capabilities` as the authoritative
  product capability contract; Review and Writing durable-memory controls stay
  disabled until the selected operation is reported as supported.
- Product API, MCP, and frontend Home expose workspace operational status with
  next actions for ready Ask scopes, ingestion waits, resumable Ask workflows,
  pending reviews, and accepted durable memory awaiting apply. Next actions
  include PSKA tool/API/view hints and safe parameters for Hermes/frontend
  navigation without provider direct access, and the frontend refreshes this
  status after mutating KB, Ask, review, and memory actions. Workspace status
  preserves per-dataset readiness so a processing upload does not hide other
  ready datasets from Ask, and it translates ingestion job actions such as
  `start_parse` into product actions such as `parse_documents`. Home
  next-action buttons can prefill Ask scope and check readiness, start parsing,
  open/track waiting blocked Ask workflows, resume ready blocked Ask workflows,
  open pending reviews, and apply accepted durable memory through Product API
  routes.
- Product API and MCP normalize required list inputs for Ask, readiness,
  ingestion, and parse operations. Blank dataset, document, and file path lists
  fail at the PSKA boundary with explicit errors before provider calls.
- Knowledge Bases polling now preselects a ready dataset in the Ask scope when
  ingestion completes, without automatically running Ask or writing durable
  knowledge.
- Dataset cards expose Ask, Upload, and Status actions, so frontend users do
  not need to copy dataset IDs between workflow forms.
- Newly created knowledge bases are selected as upload targets automatically,
  upload keeps the resolved target selected for additional files, and the upload
  form has a dataset picker backed by Product API dataset state.
- Ready document cards can set a single-document Ask scope directly.
- Ask exposes a selected-scope readiness check using the same Product API
  readiness gate that protects retrieval, with explicit Run Ask, Parse Scope,
  Track Status, and Open Status actions for the checked scope. Blocked Ask
  result actions reuse the same scope bridge while Resume Ask or Resume Loop
  preserves the original request.
- Product API, MCP, and frontend Settings expose an explicit retrieval probe
  for selected ready scopes; it writes `retrieval.probe` audit records and
  reports provider/model errors without falling back.
- Product API, MCP, and frontend Settings expose an explicit memory probe that
  verifies configured memory search through the PSKA adapter contract, rejects
  fake memory by default for live component verification, writes `memory.probe`
  audit records, and reports provider errors without fallback.
- Product API runtime diagnostics verify the same memory search contract through
  a read-only check without writing `memory.search` or `memory.probe` audit
  records.
- Product API and MCP expose a live closed-loop probe that rejects fake KB and
  fake retrieval providers, then runs readiness, retrieval, agentic Ask, source
  inspection, and explicit export for a transient work product against the
  configured live providers. It writes `closed_loop.probe` audit records and
  reports the exact failing stage without fallback; successful probes now
  surface top-level source and source-inspection counts. Durable memory/graph
  writes still use the normal review/apply workflow.
- `make live-component-check`, `pska-essential-component-check`, MCP
  `pska_component_check`, and `POST /api/runtime/component-check` aggregate
  runtime diagnostics, explicit memory probe, retrieval probe, and live
  closed-loop probe into one structured component acceptance result. They
  surface missing dataset scope, skipped core checks, fake live proofs, memory
  search failures, or retrieval/Ask/export failures without fallback. Skipping
  memory or closed-loop checks now returns `incomplete` so partial probes are
  not mistaken for full component proof. The component-check CLI also reports
  startup configuration failures as structured JSON with a nonzero exit.
  `not_ready` KB scope is also `incomplete`, so processing ingestion is treated
  as a readiness wait instead of a backend failure or fallback path.
- Product API startup validates both workflow providers and the configured KB
  gateway before serving the frontend. Missing provider env and unauthorized
  fake mode fail explicitly instead of starting a partially wired Product API.
- Product API, MCP, component-check, live closed-loop, and ingest-loop CLI
  entries can load an explicit runtime env file via `--env-file`; Make live
  targets accept `ENV_FILE=.env.pska`. Env files are not auto-loaded, and the
  normal provider validation/no-fallback rules still apply.
- `pska-essential-workspace-status` and `make workspace-status` expose the same
  PSKA next-action summary as Product API Home and MCP `pska_workspace_status`,
  so terminal users can see whether to upload, parse, wait, resume, review,
  apply memory, or ask without starting the frontend or reading provider state.
- `POST /api/ingest-loop`, MCP `pska_ingest_loop`, `make live-ingest-loop`,
  and `pska-essential-ingest-loop` run the file-first operational loop through
  configured PSKA adapters: ingest local files, poll KB readiness, run the
  PSKA-controlled agentic Ask loop, and export a sourced transient work
  product. Processing ingestion records a resumable blocked Ask before stopping
  short of retrieval/export; `POST /api/workflows/{run_id}/resume-ingest-loop`,
  MCP `pska_ingest_loop_resume`, `pska-essential-ingest-loop-resume <run_id>`,
  and `PSKA_LOOP_RUN_ID=<run_id> make live-ingest-loop-resume` resume that same
  upload -> Ask -> export intent after readiness is achieved. Failed or
  cancelled ingestion stops without creating a resumable Ask.
- Frontend Knowledge Bases upload can call the same Product API ingest loop, so
  users can go from selected files to sourced Writing output without the
  frontend calling RAGFlow, Graphiti, embedding services, or fake providers
  directly. The upload loop exposes PSKA loop controls for limit, iterations,
  minimum context, additional retrieval queries, source inspection, proposal
  kind, optional review, graph-aware retrieval, and a Wait checkbox. When Wait
  is unchecked, Run Loop returns a resumable not-ready workflow instead of
  holding the browser request open through long parsing/embedding/indexing jobs.
- Frontend Run Loop opens the blocked Ask result with Track & Resume actions
  when uploaded documents are still processing. Home and Resumable Ask cards can
  open that blocked Ask view and start Track & Resume, and ready ingest-loop
  runs resume as Resume Loop so the eventual Ask/export path remains intact.
  Failed/cancelled ingestion remains a KB status/cleanup path.
- The file-first ingest loop returns proposal, review, review-decision,
  memory-apply, memory context, loop, and export payloads as a single PSKA
  contract. Frontend Run Loop syncs Review and Activity from that contract, so
  durable governance can continue after upload without provider or store access.
- KB readiness normalizes repeated RAGFlow embedding provider failures into a
  stable PSKA `failure_code=embedding_provider_missing` and
  `configure_embedding_provider` next action instead of leaking page-by-page
  provider logs through Product API, MCP, or CLI output.
- KB creation/ingest accepts optional `embedding_model`. KB deletion remains a
  development maintenance path for selected bad datasets or full local resets,
  including deletion by ID/name/all through PSKA adapters with audit records.
  The product/demo path still assumes a fresh workspace starts by uploading
  source material, not by cleaning existing data.
- Runtime workspace/tenant context, including derived PSKA `memory_namespace`,
  surfaced in health, diagnostics, Settings, and audit metadata.
- The SQLite review store indexes workflows, proposals, reviews, memory apply
  records, and audit events by workspace/tenant; default list/read APIs only
  return records for the current `PSKA_WORKSPACE_ID` / `PSKA_TENANT_ID`.
  Existing unscoped SQLite rows are migrated into the `default` workspace.
- Workflow memory search and reviewed memory writes attach the same
  workspace/tenant context as a PSKA `memory_namespace`. Fake, company-stub, and
  Graphiti memory adapters honor that namespace; Graphiti maps it to a derived
  group ID under the configured `GRAPHITI_GROUP_ID`.
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
  (`kb.ingest`, `source.read`, `workflow.export`, `memory.apply`,
  `memory.update`, `memory.delete`, and related actions) after records are
  written.
- Review and memory apply/update/delete audit records carry proposal, run, and
  source trace metadata for durable knowledge writes.
- Durable memory lifecycle history is derived from those PSKA audit records and
  exposed as a product contract.
- Reviews become immutable after durable memory has been applied; further
  durable changes require a new proposal/review.
- Writing opens workflow state, work product, source manifest, and context
  without export side effects; Markdown and JSON buttons perform explicit
  exports.
- Ready Ask results can trigger explicit Markdown/JSON exports and open the
  generated work product in Writing.
- Exports are traceable work products: Markdown and JSON include proposal/work
  product content, source manifests, inspected source snippets, supporting
  context, and traceability metadata, including durable-memory source manifests,
  source inspection counts, and the workflow export audit event for explicit
  exports. Explicit export requires both a proposal/work product and source
  trace; empty diagnostic workflows can be inspected but not exported as briefs.
- Workspace governance policy for durable memory: manual review, auto accept,
  or auto apply.
- Product API, MCP, and frontend Settings expose the workspace governance
  policy as a product contract, including durable proposal kinds and the
  transient-results skip rule.
- Product API and MCP expose operation capabilities as a stable product
  contract, so Hermes/frontends can check durable-operation support without
  probing provider-native APIs or depending on workspace status shape.
- Operational upload-to-agentic-question MCP loop.
- Smoke eval.
- Hermes skill/config examples. Hermes now starts from `pska_workspace_status`
  and follows PSKA `next_actions` instead of inferring workflow steps from
  provider state. It also exposes `pska_runtime_diagnostics` and
  `pska_capabilities_get`, and treats `workspace.memory_namespace` as PSKA
  runtime context instead of passing provider-native memory group IDs. Hermes
  now treats fresh empty workspaces as `run_file_to_work_product_loop`, using
  `pska_ingest_loop` as the preferred upload -> Ask/export path. Home handles
  the same action by opening the Knowledge Bases Run Loop form with safe
  defaults. Hermes and OpenClaw skill docs prefer `pska_ingest_loop` /
  `pska_ingest_loop_resume` for file-first workflows, with lower-level KB tools
  reserved for manual dataset control. The Hermes config example starts
  PSKA-Essential MCP with `--env-file .env.pska` and no longer embeds fake
  provider env directly.
- Docs and runbook.

Validated commands:

```bash
cd /Users/xudawei/PSKA-Essential
make test
make list-tools
make smoke
```

Expected result:

- `make test`: 178 tests pass.
- Product API tests cover health, static frontend serving, frontend ingest-loop
  startup provider gates, controls, governance payloads, and resumable
  processing uploads, scoped Ask, Review, memory apply/update/delete, audit
  records, KB readiness blocking,
  diagnostics, document graph read, dataset creation, parsing audit, multipart
  document upload, fake upload-to-Ask source reads, fake PDF-like upload failure
  before Ask, and export refusal for unsourced/empty workflows.
- Config/KB gateway tests cover explicit provider selection, fake dev gating,
  RAGFlow delete-by-name maintenance cleanup, and live RAGFlow/Graphiti startup
  failure when required connection env is missing.
- Env-file tests cover explicit runtime config loading for MCP/component-check
  startup, non-overriding behavior for already exported variables, and invalid
  env-file failures.
- Ingest-loop tests cover CLI/MCP/Product API file upload -> readiness -> Ask
  -> governance payload -> export, resumable blocked Ask creation for
  processing uploads, and the failed-ingestion stop condition before Ask/export.
- Product API/static frontend tests cover Review status filtering, pending
  review summaries, review source trace display, component check UI, focused
  probe UI, and Knowledge Bases maintenance cleanup by ID/name/all.
- Product API tests cover Ask loop controls reaching the PSKA-controlled loop.
- Agentic loop/Product API/MCP tests cover explicit retrieval query plans and
  source-coordinate de-duplication across query rounds.
- Agentic loop/Product API/MCP tests cover bounded source inspection and
  persisted source inspection limits.
- Adapter/Workflow/Product API tests cover graph retrieval hint propagation to
  RAGFlow retrieval and audit/loop metadata.
- Agentic loop/Product API tests cover reviewed memory influencing later Ask
  runs without replacing external retrieval requirements.
- Product API and agentic loop tests cover partial-context insufficiency gating.
- Product API tests cover audit action filtering.
- Workflow/Product API/MCP tests cover source-read audit records.
- Product API/MCP tests cover turning transient sourced workflows into durable
  memory reviews, including workspace-policy auto apply.
- Workflow/Product API/MCP tests cover reviewed memory deletion and verify later
  Ask runs no longer see deleted fake/stub memory facts.
- Graphiti adapter/gate tests cover reviewed entity-edge delete routing and
  confirm Graphiti delete is blocked until review acceptance.
- Workspace status/Product API/frontend tests cover memory operation capability
  reporting, unsupported Graphiti update gating, and accepted unsupported
  review inspect actions. Workspace status tests also lock the fresh empty
  workspace next action to upload/create knowledge, not cleanup or Ask.
- Workspace status CLI tests cover explicit env-file startup, terminal
  next-action output, and nonzero exit for explicit KB status errors.
- Workflow/Product API/MCP tests cover reviewed memory update/versioning and
  verify later Ask runs see updated fake/stub memory facts.
- Workflow/Product API/MCP tests cover durable memory lifecycle history derived
  from PSKA audit records.
- Product API/MCP tests cover revising `needs_edit` reviews into new pending
  review candidates.
- Product API/MCP/frontend tests cover workspace policy visibility.
- Product API/MCP tests cover explicit retrieval probes and their audit records.
- Product API/MCP/frontend/diagnostics tests cover explicit memory probes,
  read-only runtime memory search checks, and their audit boundaries, including
  fake-memory rejection for live verification and actionable Graphiti provider
  errors.
- Product API/MCP/diagnostics tests cover live closed-loop probes, including
  explicit fake-provider rejection and non-fake sourced Ask/export success.
- Component-check tests cover the combined diagnostics/probe/closed-loop
  acceptance path, the missing-dataset-scope failure, and skipped core checks
  returning `incomplete` instead of full success. They also cover processing
  KB scopes returning `incomplete` instead of `error`.
- Env-file/component-check CLI tests cover structured startup configuration
  errors for missing live provider env.
- RAGFlow adapter tests cover actionable model-provider retrieval errors.
- Governance/runtime context tests cover explicit default workspace, derived
  memory namespace, and audit workspace/tenant metadata.
- Governance/store tests cover workspace/tenant isolation for workflow, review,
  and audit reads in a shared SQLite review store.
- Governance/adapter tests cover durable memory backend scoping through the
  PSKA `memory_namespace`, including fake memory search and Graphiti group ID
  mapping.
- `make list-tools`: lists 44 PSKA MCP tools, including `pska_ingest_loop`
  and `pska_ingest_loop_resume`.
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
pska_ingest_loop
pska_ingest_loop_resume
pska_kb_delete
pska_kb_document_status
pska_kb_readiness
pska_kb_ingestion_status
pska_component_check
pska_retrieval_probe
pska_memory_probe
pska_live_closed_loop_probe
pska_agentic_question_start
pska_agentic_question_resumable
pska_agentic_question_resume
pska_policy_get
pska_capabilities_get
pska_workspace_status
pska_runtime_diagnostics
pska_workflow_list
pska_workflow_artifact
pska_workflow_brief
pska_memory_review_from_workflow
pska_memory_update_review
pska_memory_delete_review
pska_memory_lifecycle
pska_review_list
pska_review_get
pska_review_decide
pska_review_revise
pska_memory_apply
pska_export_brief
pska_audit_list
```

This loop lets Hermes upload local documents into a RAGFlow-backed dataset,
wait for parsing/readiness, resume the same upload loop after asynchronous
embedding finishes, run a KB-scoped PSKA workflow, propose reviewed memory or
writing artifacts, inspect the transient artifact/brief without export side
effects, and explicitly export a brief. PSKA-Essential still does not own the
KB/index; RAGFlow remains the KB backend.

`fake` adapters are now explicit development/test adapters only. Product runtime
must set providers intentionally. Use `PSKA_DEV_FAKE=1` only for local tests or
tool discovery.

Selected live providers now fail at startup when required connection env is
missing. RAGFlow retrieval/KB requires `RAGFLOW_BASE_URL` and
`RAGFLOW_API_KEY`; Graphiti memory requires `GRAPHITI_BASE_URL`. PSKA does not
substitute implicit localhost, empty API keys, fake providers, or alternate
providers.

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
explicit additional retrieval queries, bounded source inspection, and optional
graph retrieval inside selected scope, opens sources through
Product API Reader, loads workspace policy from `/api/policy`, opens workflow
state, work product, source manifest, and context in Writing without export side
effects, restores persisted loop
governance/status details, opens related review items, creates Memory Reviews
that open the resulting Review record, and can apply accepted
memory patches, reviewed memory updates, or reviewed memory deletions, then
inspect the reviewed lifecycle for a durable MemoryFact. Explicit
exports can also be launched from ready Ask results and produce traceable
Markdown/JSON work products with source manifests, inspected source snippets,
supporting context, and traceability metadata, include the workflow export audit
event, and create workflow export audit records. Review
decisions and memory apply/update/delete actions refresh the current Ask/Writing
state, and applied memory state is served back through Review API records. Writing
shows the applied durable knowledge result and links to its lifecycle. Review supports
status filtering without changing the Home pending-review summary. Activity
shows the recent audit trail with action filtering, including workflow export
records, review/memory apply/update/delete records with proposal, run, and
source trace metadata, and KB/source operation records for dataset creation, ingestion,
parsing, source reads, and graph reads. Knowledge Base create, upload, parse,
source read, and graph read actions refresh Activity and focus the matching
audit action after their source-operation audit records are written. Review,
memory apply/update/delete, export, and Ask actions also focus Activity on their
matching workflow/governance audit action. Settings shows runtime provider
configuration, Product API diagnostics for review store, KB gateway, retrieval,
and memory connectivity, and the explicit `/api/capabilities` operation
contract.
Product API health, diagnostics, Settings, and audit records include the
runtime workspace/tenant context from `PSKA_WORKSPACE_ID` and
`PSKA_TENANT_ID`, including the derived PSKA `memory_namespace`. The review
store scopes workflow, review, memory-apply, and audit reads by that same
context. Durable memory adapters receive `memory_namespace` for backend
search/write scoping. If
the selected dataset or document scope is not ready, Ask returns `not_ready` and
does not start retrieval. If retrieved context remains below the required
context count, Ask returns `insufficient_context`, shows any retrieved partial
context, and does not create a proposal, review, or export. The Knowledge Bases
view shows dataset/document
readiness and normalized ingestion status, can start parsing for loaded unready
documents, selects newly created knowledge bases as upload targets, keeps the
resolved upload target selected after ingest, can set ready documents as
single-document Ask scopes, can open
optional document structure graph data through Product API,
and automatically refreshes ingestion status.

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
- Graphiti `/healthcheck` can pass while LLM or embedding provider
  configuration is still missing. Runtime diagnostics now perform a read-only
  memory search contract check, and `pska_memory_probe` /
  `POST /api/runtime/memory-probe` records an explicit audited probe.
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
cp .env.example .env.pska
# Fill in real RAGFlow/Graphiti keys for live use, then:
uv run pska-essential-mcp --env-file .env.pska
```

If using explicit local fake mode:

```bash
cat > .env.fake.pska <<'EOF'
PSKA_DEV_FAKE=1
PSKA_RETRIEVAL_PROVIDER=fake
PSKA_KB_PROVIDER=fake
PSKA_MEMORY_PROVIDER=fake
PSKA_REVIEW_DB=:memory:
EOF
uv run pska-essential-mcp --env-file .env.fake.pska --list-tools
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
make smoke
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
   workflow/review/export gates. PDF annual reports should use RAGFlow-backed
   KB mode; fake KB now reports PDF-like uploads as failed ingestion.

7. Validate that Graphiti writes are still review-gated and that Hermes cannot
   bypass PSKA by calling Graphiti directly.

## Known Gotchas

- RAGFlow source backend needs base services running first.
- RAGFlow live retrieval needs a dataset and API key.
- The earlier bad "海康威视年报测试" dataset that used `bge-m3@xxxx` was deleted
  through `pska_kb_delete`. The current live RAGFlow dataset
  `海康威视年报测试-local-embedding` uses
  `bge-m3@local-infinity@OpenAI-API-Compatible`, has one parsed PDF with 615
  chunks, and completed the PSKA live closed-loop probe with 5 context packets,
  2 source inspections, and explicit JSON export.
- RAGFlow ingestion can be slow because parsing, chunking, embedding, and
  indexing are long-running jobs. Check document status before asking.
- Graphiti needs `OPENAI_API_KEY` in `.env.pska` before real memory extraction.
  A healthy Graphiti container is not enough; use runtime diagnostics or run
  `pska_memory_probe` to verify the configured memory adapter can search
  through its LLM/embedding provider.
- Docker Desktop is currently configured around 8 GB RAM. This is enough for the
  current source-run setup, but heavy RAGFlow ingestion can still be slow.
- The third-party image `0xgkd/ragflow-arm64:v0.20.3` is not ARM64 despite its
  name. Do not use it as the Apple Silicon backend.
- Do not replace the PSKA adapter boundary with direct Graphiti/RAGFlow MCP
  exposure.
