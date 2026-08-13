# Adapter Contracts

Adapters are the only place where external backend shapes are allowed.

Adapters must fail explicitly. They must not silently switch providers, return
fake data, answer from model memory, or hide backend failures.

## Metadata-First Bridge Rule

The detailed design is in
[Metadata-First Bridge Design](METADATA_FIRST_BRIDGE_DESIGN.md).

PSKA owns public contracts and workflow control records, not provider data.
Durable documents, chunks, embeddings, episodes, facts, entities, and graph
edges must live in their owning provider. Cross-component lineage must travel
with the provider object that was created, using PSKA provenance metadata.
Derived PSKA caches or diagnostic indexes are allowed only as rebuildable,
non-authoritative optimizations.

## RetrievalPort

```python
retrieve(query, scope, limit, options) -> list[ContextPacket]
read_source(source_ref) -> SourceContext
```

Rules:

- Return PSKA `ContextPacket`, never backend-native chunk objects.
- Every `ContextPacket` must have a `SourceRef`.
- Preserve enough backend coordinates in `SourceRef` to read or debug the source.
- Preserve upstream lineage metadata, including stable provider coordinates and
  content hashes when available, so downstream memory episodes can point back to
  source evidence without a PSKA-side provider mapping table.
- Store short excerpts in metadata only when useful for citation inspection.
- Retrieval adapters must not broaden dataset/document scope unless the caller
  explicitly passes that broader scope.

## PersonalSourcePort

The personal source layer is for user-authorized local folders and Obsidian
vaults. It is not a replacement for RAGFlow, a durable memory provider, or a
general full-disk search daemon.

The implemented M1-M29 source-safe and memory-governed contract uses SQLite
metadata plus FTS5:

```python
list_roots(scope) -> list[SourceRoot]
register_root(path, kind, permission_mode, label=None) -> SourceRoot
scan(root_id, options) -> SourceScanResult
search(query, scope, limit, filters=None, options=None) -> list[ContextPacket]
read_source(source_ref) -> SourceContext
neighbors(source_ref, strategy, limit) -> list[SourceNeighbor]
duplicate_report(scope, mode, limit) -> DuplicateReport
duplicate_review_list(scope, status, limit) -> SourceDuplicateReview
duplicate_group_mark(group_id, status, note) -> SourceDuplicateGroupReview
duplicate_cleanup_propose(group_id, strategy, keep_object_id, reason) -> SourceActionProposal
source_audit_run(scope, limit) -> SourceAuditReport
saved_search_create(label, query, filters, scope) -> SavedSearch
source_collection_create(label, description, selector, source_refs) -> SourceCollection
source_collection_list() -> list[SourceCollection]
source_collection_resolve(collection_id, limit) -> list[ContextPacket]
propose_tag(target_ref, tag, reason, write_target="sidecar") -> SourceActionProposal
apply_tag(proposal_id) -> SourceActionResult
propose_comment(target_ref, body, reason, write_target="sidecar") -> SourceActionProposal
apply_comment(proposal_id) -> SourceActionResult
propose_obsidian_moc(root_id, source_refs, moc_path, title, reason, group_by="none") -> SourceActionProposal
apply_obsidian_moc(proposal_id) -> SourceActionResult
source_memory_review_create(source_refs, text, memory_type, behavior_delta, memory_scope) -> ReviewRecord
```

The fuller vNext source-management contract adds native organizer operations
and richer duplicate heuristics.

Rules:

- Source roots must be explicitly registered by the user or workspace config.
  PSKA must not scan the user's whole home directory by default.
- The canonical file content remains in the local folder or Obsidian vault.
  PSKA indexes and sidecars are rebuildable source-management metadata, not
  canonical documents.
- Every search hit must return a normal PSKA `ContextPacket` with a `SourceRef`
  that can be passed to `read_source`.
- `pska_source_search` is lexical and embedding-free. The default SQLite FTS5
  path exposes a ranking envelope (`lexical_rank`, `rank_boost`, `match_reason`)
  plus plain/highlighted snippet metadata, and can fall back to LIKE matches for
  path/title/body route queries.
- Source collections are PSKA-owned selectors, not copied files. A collection
  may hold explicit personal `SourceRef`s or a reusable search selector, and
  resolve back into normal `ContextPacket` payloads without embeddings.
- Source refs for local files must include provider role
  `local_folder` or `obsidian_vault`, `root_id`, path relative to the root,
  absolute-path debug metadata only when policy allows it, content hash, and
  section coordinates when the hit is below file level.
- Markdown and Obsidian headings should become section refs. PDF page numbers,
  text line ranges, and extracted attachment refs should be preserved when the
  extractor can provide them.
- `read_only` roots may be scanned and searched only. Tags, comments, MOC
  edits, file moves, and deletes are forbidden.
- `sidecar_write` roots may store PSKA-owned tags/comments under a sidecar
  location such as `.pska/` without modifying the original file.
- `native_write` roots may write explicit Obsidian native targets only after a
  PSKA proposal/policy decision allows the action. Current targets are YAML
  frontmatter `tags` through `write_target="obsidian_frontmatter"`, PSKA
  Markdown comment blocks through `write_target="obsidian_markdown_comment"`,
  and governed MOC marker blocks.
- Obsidian frontmatter tag writeback is implemented through
  `pska_source_tag_propose`/`pska_source_tag_apply`. Proposal stores metadata
  only; apply requires an `obsidian_vault` root with `native_write` or `managed`
  permission, appends a unique value to YAML `tags`, preserves note body text,
  and no-ops when the tag already exists.
- Obsidian markdown comment writeback is implemented through
  `pska_source_comment_propose`/`pska_source_comment_apply`. Proposal stores
  metadata only; apply requires an `obsidian_vault` root with `native_write` or
  `managed` permission and appends a visible PSKA Comment marker block. It is not
  arbitrary in-place note editing.
- Obsidian MOC writeback is implemented as a governed proposal/apply path:
  proposal stores a preview in PSKA source-action metadata, and apply requires
  an `obsidian_vault` root with `native_write` or `managed` permission. Apply
  may create or update only the PSKA-managed MOC block delimited by explicit
  markers inside the target Markdown note; existing user-authored note content
  outside that block must be preserved.
- Duplicate detection must be a report/proposal path. Public tools must not
  delete, move, or merge user files as a side effect of duplicate search.
- Obsidian is a source provider. It may provide markdown files, tags,
  frontmatter, links, backlinks, attachments, and note coordinates, but it does
  not own PSKA durable memory, Review, or agentic loop state.
- Text extraction and OCR failures must be surfaced as source-object status and
  action hints. They must not silently produce empty searchable content as if
  indexing succeeded.
- Embeddings are optional later caches. The source layer must work with
  metadata, lexical search, exact duplicate reports, saved searches, and source
  reads alone.
- Neighbor expansion must be source-safe and deterministic. M4 uses indexed
  Markdown/Obsidian outgoing links, backlinks, and same-folder neighbors before
  any embedding or graph cache is introduced.
- Source-to-memory promotion must create a governed Review item with explicit
  Memory Card type and behavior delta. It must not directly write the memory
  provider.

The first implementation should prefer SQLite metadata plus FTS5/BM25 for the
index. Tools such as MarkItDown, Docling, OCRmyPDF, Czkawka, dupeGuru, or
rmlint may be adapters or workers, but their native output must be normalized
before reaching Product API, MCP, Hermes, or frontend code.

## Upgrade Adapter Slots

The agentic system upgrade plan adds provider slots without making optional
components part of the default runtime. `/api/capabilities` and
`pska_capabilities_get` expose these slots under `adapter_slots` with schema
`pska.adapter_slots.v1`.

Rules:

- Slot availability is discovery, not permission. A discovered CLI or Python
  package still cannot bypass PSKA scope, Review, or Audit.
- `status=available` means the core or optional provider can be called by a
  future adapter. It does not mean public Product API/MCP tools already expose
  that provider.
- `status=unavailable` means the optional package or CLI is absent. PSKA must
  not silently degrade to fake output.
- `status=planned` means the slot is reserved but no adapter exists yet.
- External provider names such as MarkItDown, Docling, fclones, Graphiti, Zep,
  Mem0, Temporal, or OpenTelemetry must not leak native schemas to callers.

### ExtractionPort

```python
extract(source_object, options) -> ExtractionResult
```

Provider slots:

- `builtin_text`: implemented default for Markdown, plain text, and code.
- `markitdown`: implemented optional extra for broad file-to-Markdown
  conversion. The adapter loads only when the Python module is installed.
- `docling`: implemented optional extra for PDF/layout/table/OCR-sensitive
  parsing. It is exposed through `extractor="docling"` and remains
  `unavailable` until the optional extra is installed.
- `tika`: planned optional extra or service adapter for broad enterprise file
  type extraction.

Rules:

- Extractors return PSKA sections and warnings, not provider-native documents.
- Extraction failures must set source-object parse status and expose a clear
  action hint.
- Extracted sections must preserve `SourceRef` coordinates such as path,
  heading, page, line range, content hash, and extractor metadata.

### SearchIndexPort

```python
index(source_object, sections, options) -> IndexResult
search(query, scope, filters, limit) -> list[ContextPacket]
```

Provider slots:

- `sqlite_fts5`: implemented default local-first BM25 index.
- `tantivy`: planned local high-performance full-text adapter.
- `meilisearch`: planned service adapter for typo tolerant/server search.
- `recoll`: planned desktop-search adapter/reference.

Rules:

- Search results must return PSKA `ContextPacket` and `SourceRef`.
- Search adapters must honor source scope and permission filters.
- Embedding indexes remain optional caches, not a prerequisite for local source
  retrieval.

### DedupPort

```python
report(scope, mode, options) -> DuplicateReport
```

Provider slots:

- `exact_hash`: implemented default.
- `size_name_version`: implemented core heuristic for same normalized filename,
  copy/version/date/numeric suffixes, and similar-size candidate groups. It is a
  lower-confidence report signal only; it does not delete, move, merge, or edit
  source files.
- `text_similarity`: implemented core heuristic over already indexed source text
  using token Jaccard and optional `scope.similarity_threshold`. It does not use
  embeddings and remains a dry-run report signal only.
- `media_metadata`: implemented core heuristic for image, video, and audio
  candidates using media family, normalized filename, and similar size. It does
  not use embeddings or perceptual hashes and remains a review signal only.
- `imagehash`: implemented optional extra for image perceptual hash candidates
  through ImageHash/Pillow. `mode="image_phash"` groups images by pHash Hamming
  distance, returns `status=unavailable` when the optional package is absent,
  and remains a non-destructive review signal.
- `fclones`: implemented CLI adapter for hash duplicate groups and JSON
  reports. It uses `PSKA_FCLONES_BIN` when it points to an executable binary,
  otherwise `PATH`, and returns `status=unavailable` when no command can be
  found.
- `czkawka`: implemented CLI adapter for hash duplicate groups and JSON reports.
  It uses `PSKA_CZKAWKA_BIN` when it points to an executable binary, otherwise
  `PATH`, and returns `status=unavailable` when no command can be found. Video
  similarity remains a planned extension behind the same provider family.
- `dupeguru`: planned fuzzy duplicate reference.
- `rmlint`: planned advanced duplicate lint report adapter.

Rules:

- Dedup adapters produce reports and proposals only.
- Delete, move, merge, hardlink, or symlink actions must be separate
  destructive-review flows and are not part of `DedupPort.report`.

### ThoughtArtifactPort

```python
read_context(refs, options) -> list[ThoughtArtifactContext]
propose_memory(refs, intent) -> ReviewRecord
```

Provider slots:

- `eidolia_project_files`: planned file adapter for thought/artifact nodes and
  agentic traces.
- `eidolia_product_api`: planned live canvas adapter.

Rules:

- Eidolia remains `thought` / `artifact` at the user-visible node level.
- Belief, decision, source route, and memory are metadata/trace projections,
  not new mandatory node types.
- PSKA stores references and trace, not a canonical copy of the Eidolia canvas.

### ObservabilityPort

```python
emit_trace(event) -> None
emit_metric(metric) -> None
```

Provider slots:

- `sqlite_audit`: implemented governance audit baseline.
- `opentelemetry`: planned optional trace/metric exporter.
- `phoenix`: planned LLM/RAG tracing target.
- `ragas`: planned RAG evaluation target.
- `deepeval`: planned LLM workflow evaluation target.

Rules:

- Audit remains the user-facing governance ledger.
- Observability adapters may export traces and metrics, but cannot become the
  authoritative memory/source/review store.

### WorkflowPort

```python
enqueue(job) -> JobRecord
tick(now, limit) -> TickResult
run(job_id) -> JobResult
```

Provider slots:

- `sqlite_jobs`: implemented job ledger and explicit tick.
- `watchdog_tick`: implemented bounded authorized-root filesystem event trigger.
- `system_cron_launchd`: planned external scheduler trigger.
- `temporal`: future durable execution backend for long-running jobs.

Rules:

- Background triggers must only operate on authorized source roots.
- Tick may enqueue work; it must not silently scan full disk or write memory.
- The current watchdog implementation is `watch_once`: it listens for a short
  explicit interval and then queues source extraction and/or audit jobs.
- Temporal is a backend for job durability, not the PSKA workflow contract.

### CloudSourcePort

```python
list_roots(scope) -> list[CloudSourceRoot]
search(query, scope, filters, limit) -> list[ContextPacket]
read_source(source_ref) -> SourceContext
```

Provider slots:

- `google_drive`
- `box`
- `sharepoint`
- `notion`
- `zotero`

Rules:

- Cloud sources must normalize to the same `SourceRef`, permission, Review, and
  Audit model as local folders and Obsidian vaults.
- Connector/plugin availability must not imply broad account-wide scanning.
- Cloud writes, if ever supported, must use explicit proposal/apply flows.

## MemoryPort

```python
search(query, scope, limit) -> list[MemoryFact]
apply(reviewed_patch) -> MemoryApplyResult
update(reviewed_update) -> MemoryApplyResult
delete(reviewed_delete) -> MemoryApplyResult
```

Rules:

- `apply` receives only reviewed `MemoryPatch` objects.
- `update` receives only reviewed `MemoryUpdate` objects from PSKA review flow.
- `delete` receives only reviewed `MemoryDelete` objects from PSKA review flow.
- Direct clear, unreviewed add, or provider-native delete operations are
  intentionally absent from public tools.
- Graphiti `add_episode` is allowed only inside reviewed `apply`; Graphiti
  entity-edge delete is allowed only inside reviewed `delete`.
- If a backend cannot provide a transactional reviewed update, its adapter must
  fail explicitly instead of approximating update with hidden delete/add side
  effects.
- Conversation-native corrections may use an explicit core workflow strategy
  when the backend is temporal rather than transactional. For example, with
  Graphiti, PSKA may keep the user semantic operation as `memory_update` while
  creating a reviewed `memory_patch` correction episode carrying
  `memory_update_strategy="append_correction_episode"`, `target_fact_id`, and
  provenance. The episode body should include current text, previous text, and
  target coordinates so provider search can retrieve the correction via old or
  new terms. The metadata should also carry `current_text`/`display_text` for
  agent-facing views. This strategy belongs in PSKA workflow metadata and
  tests, not as hidden adapter-side fallback behavior. Adapters must advertise
  this through `memory_capabilities["conversation_update_strategies"]`; PSKA
  must not infer it merely because `update` is unsupported and `apply` is
  supported.
- Memory adapters should expose PSKA memory capabilities. The Product API
  capabilities contract, diagnostics, workspace status, MCP tools, and
  frontend controls use those capabilities to avoid creating durable review
  items that the selected backend cannot apply.
- `capabilities.memory.inflow` is the public flow contract for memory-provider
  ingestion. It must say that source uploads target the KB provider only and
  that Graphiti or another memory provider receives only governed projections
  from conversation memory, digest job review/application, or workflow memory
  promotion.
- Memory adapters must honor PSKA `memory_namespace` / workspace metadata on
  search and reviewed writes. Provider-specific isolation, such as Graphiti
  group IDs, belongs inside adapters and must not leak into core workflow code
  or public tool contracts.
- Reviewed memory writes must carry provenance into the memory provider. For
  Graphiti, the durable linkage should be `fact -> episode -> PSKA provenance
  envelope -> upstream SourceRef`, not a PSKA-owned fact/source ledger.
- Memory search must preserve provider-carried provenance on the returned
  `MemoryFact`. Graphiti search should resolve episode provenance back into
  `source_refs` and expose useful envelope metadata, such as
  `target_fact_id`, `previous_text`, `memory_update_strategy`, process, and
  timestamps, in `MemoryFact.metadata`.
- PSKA may interpret returned memory metadata at query time. If a returned fact
  carries `semantic_operation="memory_update"` or
  `memory_update_strategy="append_correction_episode"` and points to
  `target_fact_id`, default `pska_memory_search` filters the targeted older fact
  from that result set. This is a non-authoritative view over provider-owned
  data; callers can request `include_superseded_memory=true` for diagnostics.

## Public MCP Contract

The current public tool surface is:

- `pska_workflow_start`
- `pska_workflow_list`
- `pska_workflow_state`
- `pska_workflow_artifact`
- `pska_workflow_brief`
- `pska_context_retrieve`
- `pska_source_read`
- `pska_source_root_list`
- `pska_source_root_register`
- `pska_source_scan`
- `pska_source_search`
- `pska_source_neighbors`
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
- `pska_policy_get`
- `pska_capabilities_get`
- `pska_workspace_status`
- `pska_jarvis_briefing`
- `pska_alpha_readiness`
- `pska_alpha_trial_guide`
- `pska_alpha_recovery_plan`
- `pska_alpha_first_run_session`
- `pska_alpha_first_run_item_update`
- `pska_runtime_diagnostics`
- `pska_propose`
- `pska_review_create`
- `pska_review_list`
- `pska_review_get`
- `pska_review_decide`
- `pska_review_revise`
- `pska_memory_search`
- `pska_memory_card_list`
- `pska_memory_card_get`
- `pska_memory_health_scan`
- `pska_memory_use_trace`
- `pska_memory_why_used`
- `pska_workflow_memory_attribution`
- `pska_workflow_memory_suggestions`
- `pska_memory_apply`
- `pska_memory_change_from_conversation`
- `pska_memory_review_from_workflow`
- `pska_memory_refresh_review`
- `pska_memory_update_review`
- `pska_memory_delete_review`
- `pska_memory_lifecycle`
- `pska_export_brief`
- `pska_audit_list`
- `pska_component_check`
- `pska_retrieval_probe`
- `pska_memory_probe`
- `pska_live_closed_loop_probe`
- `pska_eval_run`
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
- `pska_agentic_question_start`
- `pska_agentic_question_resumable`
- `pska_agentic_question_resume`

Backends must be replaceable without changing these tools.
`pska_policy_get` returns PSKA workspace governance policy; agents must use it
for product policy awareness instead of inferring review behavior from backend
capabilities.
`pska_capabilities_get` returns PSKA-level operation capabilities; agents must
use it to check durable-operation support instead of probing provider-native
APIs or creating known-dead review items. The memory capability payload also
contains `search_view`, which declares default superseded-fact filtering,
diagnostic scope keys such as `include_superseded_memory`, and agent-facing text
metadata keys such as `display_text` and `current_text`.
It also contains `lineage` (`pska.memory_lineage.v1`), which declares that
authoritative fact-to-source lineage belongs in memory-provider object metadata,
not in a PSKA authoritative mapping table. Adapters should resolve provenance
from episode metadata, fact/edge metadata, or compatible `source_description`
fields.
`pska_workspace_status` returns PSKA-level operational status and next actions;
agents must use it for workflow navigation instead of inspecting provider state
directly. Next actions may include PSKA tool/API/view hints and safe parameters,
but must not expose provider-native schemas.
Workspace status must keep per-dataset readiness visible, so a processing or
failed dataset does not hide a separate ready dataset from Ask. Workspace status
must translate ingestion-job action names into stable PSKA product actions, for
example `start_parse` becomes `parse_documents`.
`pska_runtime_diagnostics` returns the same read-only provider, contract, and
workspace diagnostics as the Product API diagnostics route. Agents should use it
for troubleshooting component configuration instead of probing provider-native
health endpoints.
`pska_component_check` runs the structured component acceptance path through
PSKA: runtime diagnostics, memory probe, retrieval probe, and live closed-loop
probe. It returns `incomplete` for missing dataset scope, skipped core checks,
or `not_ready` KB scope instead of silently treating partial probes as full
component proof or reporting long-running ingestion as a backend failure.
Component, retrieval, and live closed-loop probes may accept user-facing
dataset names, but PSKA resolves them through the KB gateway into canonical
dataset IDs before retrieval, Ask, or export. Unresolved or ambiguous names are
reported as incomplete scope rather than replaced with another dataset.
`pska_eval_run("product_acceptance")` runs a local product-loop acceptance suite
through PSKA contracts: file ingest, ready Ask/export, not-ready upload resume,
governed durable memory transition, and audit traceability. It may use fake
adapters only when explicit local development/test fake mode is configured, and
it records an `eval.run` audit event for the acceptance result. Outside explicit
all-fake development mode, manual-review durable memory checks stop at the
review gate and leave persistence to user review or workspace policy.
`pska_ingest_loop` runs the file-first operational loop through PSKA adapters:
local file ingest, readiness polling, agentic Ask, and sourced export. It
returns `not_ready` and stops before Ask/export when ingestion is still
processing or has failed. `pska_ingest_loop_resume` resumes a processing-blocked
upload loop after the selected scope becomes ready, preserving the original Ask
and export intent. Not-ready upload-loop results expose PSKA-level
`next_actions`; resumable processing states also expose a `resume` contract for
the PSKA resume tool/API instead of requiring provider-specific inspection.
`pska_memory_probe` is an explicit diagnostic operation for the configured
memory adapter. It verifies memory search through the PSKA contract, rejects
fake memory by default for live component verification, and writes
`memory.probe` audit records.

The personal source layer has an M1-M21 source-management MCP surface:

- `pska_source_root_list`
- `pska_source_root_register`
- `pska_source_scan`
- `pska_source_search`
- `pska_source_read`
- `pska_source_neighbors`
- `pska_duplicate_report`
- `pska_duplicate_review_list`
- `pska_duplicate_group_mark`
- `pska_duplicate_cleanup_propose`
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
- `pska_source_collection_create`
- `pska_source_collection_list`
- `pska_source_collection_resolve`
- `pska_source_tag_propose`
- `pska_source_tag_apply`
- `pska_source_comment_propose`
- `pska_source_comment_apply`
- `pska_obsidian_moc_propose`
- `pska_obsidian_moc_apply`
- `pska_source_memory_review_create`

`pska_source_audit_run` is the read-only agentic routine entry point for local
folders and Obsidian vaults. It returns root summaries, exact duplicate previews,
unresolved links, unlinked Markdown notes, route candidates, and structured
`next_actions`; it writes no source files, no memory, and no embeddings.
`pska_source_audit_job_enqueue`, `pska_source_audit_schedule_create`,
`pska_source_audit_job_list`, `pska_source_audit_job_tick`, and
`pska_source_audit_job_run` provide a PSKA-owned proactive audit queue for the
same routine. Jobs are stored as workflow metadata, surfaced through
`pska_provider_jobs` and workspace status, can wait on wall-clock `due_at`, and
keep the same no source-file write, no direct memory write, no embedding
guarantee. `pska_source_audit_job_tick` only promotes due waiting jobs to queued
jobs; scanning still requires running the explicit audit job.
`pska_source_extract_job_enqueue`, `pska_source_extract_job_list`, and
`pska_source_extract_job_run` provide the PSKA-owned source extraction queue.
Jobs run a selected extractor through `pska_source_scan`, update rebuildable
source index metadata and FTS sections, and keep the no source-file write, no
direct memory write, and no embedding requirement guarantees.
`pska_source_watch_once` provides the optional watchdog bridge. It only listens
to a registered source root for a bounded interval, summarizes filesystem
events, and queues extraction and/or audit jobs. It is not a hidden daemon,
does not scan full disk, does not write source files, and does not write durable
memory.
`pska_obsidian_moc_propose` and `pska_obsidian_moc_apply` provide the current
native Obsidian writeback path. They collect explicit source refs into a MOC
preview, then apply only the PSKA-managed Markdown block after native/managed
vault permission is present. They do not edit arbitrary note text, write durable
memory, or require embeddings. MOC proposals support `group_by="none"`,
`"folder"`, `"tag"`, `"topic"`, or `"project"` and expose both grouped payloads
and the rendered Markdown preview before apply.
`pska_source_tag_propose`/`pska_source_tag_apply` also support
`write_target="obsidian_frontmatter"` for Obsidian Markdown notes. Sidecar
remains the default tag path.
`pska_source_comment_propose`/`pska_source_comment_apply` also support
`write_target="obsidian_markdown_comment"` for Obsidian Markdown notes. Sidecar
remains the default comment path, and native comment apply appends only a PSKA
Comment marker block.
`pska_source_collection_create`, `pska_source_collection_list`, and
`pska_source_collection_resolve` provide the first source-collection surface:
named reusable bundles over explicit SourceRefs or search selectors. They write
only source-registry metadata and resolve into normal context packets for
Hermes/RAG workflows.
`pska_source_search` returns ranked local lexical context packets with
`match_reason`, `rank_boost`, `lexical_rank`, `snippet_plain`, and
`snippet_highlighted` metadata. It still does not require embeddings.

The remaining personal source-management capabilities are planned vNext surface
and are not part of the current Alpha MCP registry until implemented: native
Obsidian richer frontmatter fields, executable move/delete proposals, background
wakeup integration, stronger ranking adapters, and richer media duplicate
heuristics.

`pska_source_read` is the common read tool for both RAGFlow source refs and
personal source refs.

## Assistant Layer

Hermes is the primary agentic layer. PSKA does not own generation, but it exposes
the dashboard-grade facts Hermes needs through `pska_workspace_status` and
`pska_jarvis_briefing`.

`pska_jarvis_briefing(scope, source_scope, audit_limit)` returns:

- workspace status and provider/review/job summaries;
- personal source roots plus an optional source audit snapshot;
- prioritized source, memory, review, and workspace signals;
- deduplicated PSKA `next_actions` with tool/API/view hints;
- data-flow flags proving it does not write source files, write memory directly,
  require embeddings, or generate final answer text.

This is the M7 Hermes/Jarvis contract. It is intentionally an orchestration
briefing, not a chat answer and not a direct provider interface.

## KB Gateway

The KB gateway is a thin operational layer over an external KB provider. In v1
that provider is RAGFlow.

Rules:

- PSKA-Essential may create datasets, upload files, start parsing, poll document
  status, and read optional structure graph data through provider APIs.
- RAGFlow dataset/document lookup used for reuse, maintenance, readiness, and
  resume flows must scan visible pages through the provider API instead of
  assuming the target appears on the first page.
- KB gateways may expose `get_dataset(dataset_id)` so readiness gates can
  resolve explicitly selected scopes by ID instead of depending on a list page.
- RAGFlow uploads request raw document rows through the provider's
  `return_raw_files=true` query option, then normalize those rows into PSKA
  document contracts before returning them to Product API or MCP callers.
- RAGFlow parsing uses the current public document parse contract
  `/datasets/{dataset_id}/documents/parse`.
- PSKA-Essential may delete selected datasets by ID, by name, or all datasets
  through adapter APIs for explicit cleanup and development reset flows.
- Fresh workspaces, including the explicit fake KB gateway, start without
  preloaded source knowledge. The product path starts with upload/ingest;
  cleanup is only maintenance for bad development data.
- PSKA-Essential must not persist raw documents or build its own index.
- Public tools return normalized dataset/document IDs and status fields, not
  raw provider responses.
- Dataset creation and ingest may carry optional `embedding_model`; adapters
  translate it to provider-native configuration while PSKA keeps the public
  contract provider-independent.
- Readiness checks return PSKA status language and must not leak provider-native
  task or document payloads outside the gateway.
- Ingestion status is the product-facing job summary for upload, parse,
  embedding, and indexing readiness. It must expose phase, progress, counts,
  next actions, and failure reasons in PSKA language.
- Provider job status is the workspace-facing inventory across current KB
  ingestion/readiness, digest jobs, and recent provider-level audit events. It
  is exposed through `pska_provider_jobs` and `GET /api/provider/jobs`, but
  provider-native queues remain authoritative.
- Agentic questions should carry explicit `dataset_ids` and optional
  `document_ids` into the normal retrieval workflow.
- Upload, parsing, embedding, indexing, and optional graph extraction are
  asynchronous. Gateway APIs must expose status/readiness instead of implying
  immediate retrieval availability.

## Agentic Loop

The public `pska_agentic_question_start` tool is the first step toward a richer
agentic Ask loop. That loop should remain PSKA-controlled:

```text
start -> check scope/readiness -> retrieve -> inspect sources
  -> optionally retrieve again -> synthesize/propose -> review
  -> make available for explicit export
```

The loop may iterate, but it must not silently change user-selected scope or
write memory/graph state before review. Additional retrieval rounds may use
explicit `retrieval_queries` supplied by the user or agent; PSKA records the
query plan and each scoped retrieval step, but must not add domain-specific
query expansion in runtime code.
After retrieval, PSKA may inspect a bounded number of unique retrieved
`SourceRef`s through the retrieval adapter. Source inspection is transient
workflow evidence, records `source.inspect` loop metadata, and uses normal
`source.read` audit records.
If readiness blocks the selected scope, PSKA must persist the blocked workflow,
surface it through a resumable Ask list with a fresh readiness check, and allow
a later resume to create a new audited Ask workflow from the stored request.
The resumable list must expose PSKA-level `resume` and `next_actions` contracts
so agents and clients do not infer resume behavior from provider or workflow
metadata.

## Review Gate

Memory write flow:

```text
retrieve -> propose(memory_patch) -> review_create -> review_decide(accept) -> memory_apply
```

Memory delete flow:

```text
memory_search -> pska_memory_delete_review(MemoryFact) -> review_decide(accept) -> memory_apply
```

Memory update flow:

```text
memory_search -> pska_memory_update_review(MemoryFact, text) -> review_decide(accept) -> memory_apply
```

Memory Card refresh-review flow:

```text
pska_memory_card_get -> pska_memory_refresh_review(memory_id, text?, reason?) -> review_decide(accept) -> memory_apply
```

Memory refresh-review queue surface:

```text
pska_memory_review_queue -> refresh_reviews group -> review_memory_refresh -> pska_review_get -> review_decide(accept) -> memory_apply
```

Memory Card inventory and inspection:

```text
pska_memory_card_list(scope, limit, query, status, memory_type) -> Memory Card inventory/envelope view
pska_memory_card_get(memory_id, scope) -> single Memory Card envelope
pska_memory_refresh_review(memory_id, text, reason, scope) -> pending Memory Card refresh review, no direct memory write
pska_memory_review_queue(scope, limit) -> grouped memory maintenance queue including refresh_reviews
```

Memory use trace and why-used:

```text
pska_memory_health_scan(scope, issue_type, limit) -> provider-neutral health issues for quality/stale/conflict
pska_memory_use_trace(memory_id, query, action, limit) -> audit-backed candidate retrieval / card inspection trace
pska_memory_why_used(memory_id, scope, limit) -> Memory Card plus recent trace explanation
pska_workflow_memory_attribution(run_id) -> answer-level used_memory_ids for a PSKA workflow
pska_workflow_memory_suggestions(run_id) -> governed memory review suggestions for a PSKA workflow
```

Durable memory lifecycle inspection:

```text
pska_memory_lifecycle(memory_target_id) -> PSKA audit-derived apply/update/delete history
```

`memory_apply` must fail when the review is pending, rejected, or needs edit.
Durable memory review creation, review acceptance, and memory apply must fail
when the durable proposal has no PSKA `SourceRef` trace.
Once reviewed memory has been applied, the review decision is immutable; later
changes require a new governed proposal rather than rewriting the old decision.
Lifecycle history here means the PSKA decision lifecycle: review, apply, update,
delete, and audit events. It is not the authoritative fact-to-source lineage.
Provider fact lineage must be resolved from provider-carried provenance, such as
Graphiti episode metadata pointing back to upstream `SourceRef`s.
For temporal correction episodes, lifecycle inspection also follows
provider-carried semantic target metadata such as `target_fact_id`; this lets
`pska_memory_lifecycle(old_fact_id)` show a later correction episode without
requiring a PSKA fact/source ledger.
