---
name: pska-essential-workflow-gate
description: Use PSKA-Essential MCP to run reviewed agent knowledge workflows.
---

# PSKA-Essential Workflow Gate

Use this skill when a task requires document ingestion, knowledge retrieval,
candidate memory, review, and durable export.

## Rules

- Use PSKA-Essential MCP tools only.
- Do not call RAGFlow or Graphiti MCP servers directly.
- Start by calling `pska_workspace_status` unless the user explicitly asks for
  a specific low-level tool. Follow its `next_actions` tool/API/view hints and
  safe parameters instead of inspecting provider state directly.
- When the user asks what is stuck, what to inspect next, or wants a broad
  workspace/source briefing, call `pska_jarvis_briefing`. Treat it as the
  Hermes/Jarvis dashboard contract: it ranks source, memory, review, and
  workspace priorities without generating final answer text or writing source
  files.
- Use `pska_runtime_diagnostics` when provider configuration, backend health,
  or adapter contract readiness needs troubleshooting. Do not call provider
  health endpoints directly.
- Use `pska_component_check` when the user wants to verify that configured
  providers can support the PSKA product loop. Treat `incomplete`, `error`, or
  skipped required checks as not proven.
- Use `pska_alpha_readiness` when the user asks whether PSKA is mature enough
  for self-use, technical alpha, or broader user trial. Treat `not_ready` as
  demo/development only, and treat `technical_alpha` as guided trial rather than
  ordinary To C readiness.
- Use `pska_alpha_trial_guide` when the user asks how to start dogfooding or
  run a guided alpha. Treat it as a read-only first-run checklist: it can name
  phases, guardrails, tools, views, and exit criteria, but it does not execute
  registration, scans, source writeback, or durable memory apply.
- Use `pska_capabilities_get` as the stable PSKA operation capability contract
  before durable memory apply, update, or delete work. If an operation is not
  supported, report that PSKA cannot perform it with the current memory adapter.
- Use `pska_capabilities_get.memory.search_view` to understand memory search
  display and filtering semantics. Prefer the declared agent-facing metadata
  keys, such as `display_text` or `current_text`, over raw correction episode
  text when explaining memory to the user.
- Use `pska_memory_card_list` and `pska_memory_card_get` when the user asks to
  inspect or manage durable memories as Memory Cards. Treat these tools as the
  PSKA envelope view over provider facts: use `display_text`, `memory_type`,
  `memory_scope`, `behavior_delta`, `quality`, source refs, and lifecycle rather
  than raw provider text alone.
- Use `pska_memory_health_scan` when the user asks whether memories are stale,
  conflicting, incomplete, or need cleanup. Treat it as a conservative
  provider-neutral health scan; do not auto-resolve or overwrite memory without
  a review-gated update/delete flow.
- Use `pska_memory_candidate_dedup` when the user asks to clean up candidate
  reviews or avoid duplicate memories. Treat it as an embedding-free review hint
  based on lexical fingerprints and SourceRefs. Its `related_groups` may flag
  cross-scope scope collisions, such as a preference appearing as both global
  and project memory. Do not merge, reject, revise, approve, or apply memory
  from this result alone; if the human approves a merged candidate text, call
  `pska_review_merge_candidates` with the source review ids and explicit
  `memory_candidate` fields.
- Use `pska_memory_use_trace` and `pska_memory_why_used` when the user asks why a
  durable memory appeared, whether a memory has been used recently, or which
  query/tool surfaced it. Treat the result as audit-backed candidate retrieval
  or card inspection evidence, not proof that the final model response depended
  on that memory.
- Use `pska_workflow_memory_attribution` for answer-level memory attribution
  after a PSKA Ask/workflow run. Report `used_memory_ids` as explicit
  answer-context trace, and keep the limitation clear: it records what PSKA
  supplied to the work product, not hidden model causality.
- Use `pska_workflow_memory_suggestions` when deciding whether an answer should
  become durable memory. Treat suggestions as review candidates only; follow
  `pska_memory_review_from_workflow` instead of writing memory directly.
- Use `pska_migration_manifest` when the user asks how to migrate, back up, or
  inspect component ownership. Treat it as an inventory, not a raw provider data
  export.
- Use `pska_provider_jobs` when the user asks what is still processing, queued,
  failed, or ready across KB ingestion and PSKA digest jobs.
- Refresh `pska_workspace_status` after KB, Ask, review, or memory actions that
  change workspace state.
- Treat `workspace.memory_namespace` from `pska_workspace_status` as PSKA
  runtime context for diagnostics and audit only. Do not pass provider-native
  memory group IDs, Graphiti group IDs, or backend namespace parameters.
- Use `pska_kb_*` tools when the user needs a document uploaded or parsed into
  an external knowledge base.
- Use `pska_ingest_loop` when the user wants the normal file-to-work-product
  loop in one PSKA-controlled tool call. Treat `status=not_ready` as a stop:
  inspect readiness or ingestion status instead of answering from missing
  context.
- Use `pska_ingest_loop_resume` for a readiness-blocked run that came from
  `pska_ingest_loop`, so the upload -> Ask -> export intent is preserved after
  parsing, embedding, or indexing finishes.
- Use `pska_digest_scope` for an explicit low-frequency digest over a ready
  dataset or document scope. It creates a sourced digest and only creates a
  durable memory review when `create_memory_review=true`; it must not be used
  as an automatic write path into Graphiti.
- Use `pska_digest_job_enqueue`, `pska_digest_job_list`, and
  `pska_digest_job_run` when digest work should be queued or run by a scheduler.
  A waiting job means KB readiness is still controlled by the provider.
- Treat upload, parsing, embedding, and indexing as asynchronous. Check document
  readiness and `pska_kb_ingestion_status` before asking over a dataset.
- For retrieval, component, and live closed-loop probes, prefer canonical
  `dataset_ids` when available. If the user only knows a knowledge-base name,
  pass it as `dataset_names`; PSKA will resolve it through the KB gateway before
  retrieval or Ask.
- Do not use case-specific shortcuts or hardcoded domains.
- Do not invent fallback answers when retrieval or backend calls fail.
- Treat retrieved context as workflow-local until review accepts it.
- Use `pska_policy_get` when you need to understand the current workspace
  governance policy; do not infer policy from provider capabilities.
- Do not call `pska_memory_apply` until a review has status `accepted`.
- Use `pska_workflow_artifact` or `pska_workflow_brief` to inspect transient
  work products without export side effects.
- When personal source-layer capabilities are available, treat Obsidian vaults
  and local folders as PSKA source scopes, not as memory backends. Use PSKA
  source tools to search/read/propose tags/comments; do not use direct
  filesystem, Obsidian, or shell file operations for PSKA personal-knowledge
  workflows.
- For local folder or Obsidian questions, search/read the selected source scope
  before answering. When a note or file is clearly central, use
  `pska_source_neighbors` to inspect linked, backlink, or same-folder sources
  before broadening to the entire vault. Use durable memory for project state,
  preferences, source routes, and corrections; do not substitute memory text for
  source evidence when the user asks what is inside files.
- For file organization work, run `pska_source_audit_run` for an immediate
  read-only check, queue ad-hoc checks with `pska_source_audit_job_enqueue`, or
  create wall-clock recurring checks with `pska_source_audit_schedule_create`.
  Inspect jobs with `pska_source_audit_job_list`; when workspace/Jarvis says a
  scheduled audit is due, call `pska_source_audit_job_tick`, then run the queued
  job with `pska_source_audit_job_run`. Follow audit `next_actions` for
  duplicate review, unresolved links, unlinked notes, and source-route memory
  candidates. Propose tags, comments, saved searches, MOC updates, and duplicate
  reports before any heavier operation. Do not delete, move, merge, or natively
  edit user files unless PSKA policy/tool output explicitly authorizes that
  action.
- For source extraction/index refresh work, queue roots with
  `pska_source_extract_job_enqueue`, inspect queued or completed extraction
  work with `pska_source_extract_job_list`, and run either the next queued job
  or a selected job with `pska_source_extract_job_run`. Extraction jobs may use
  builtin text parsing or optional adapters such as MarkItDown, but they still
  write only PSKA source index metadata/FTS sections. They must not be treated
  as permission to edit source files, write durable memory, or require
  embeddings.
- For short explicit local folder monitoring, call `pska_source_watch_once`
  only on a registered source root. It uses the optional watchdog adapter for a
  bounded interval, then queues extraction and/or audit jobs. It is not a hidden
  daemon, does not scan full disk, does not edit source files, and does not
  write durable memory.
- For Obsidian organization, use `pska_obsidian_moc_propose` to create a
  governed MOC writeback preview from explicit source refs. Only call
  `pska_obsidian_moc_apply` when the selected root is an Obsidian vault with
  `native_write` or `managed` permission and the user/tool action clearly asks
  to apply the MOC. This tool updates only the PSKA-managed MOC block, not the
  rest of the note.
- If the user says to remember, correct, clarify, or forget something in chat,
  call `pska_memory_change_from_conversation`; do not send them to Review for
  ordinary corrections.
- If a conversation contains stable preferences, project decisions, working
  habits, source routes, or corrections that may affect future behavior but the
  user did not explicitly ask to remember them, call
  `pska_conversation_memory_candidates_create` with compact candidates. Each
  candidate must include concrete `text`, `memory_type`, `memory_scope`,
  `behavior_delta`, and conversation evidence. Treat the output as pending
  Review work; do not claim memory was saved. Use `pska_memory_review_queue`
  to inspect the `conversation_candidates` group and follow
  `review_conversation_memory_candidate` when the user is ready to accept,
  edit, or reject candidates.
- If `pska_memory_change_from_conversation` returns `status="needs_target"`,
  call `pska_memory_search` with the returned `next_actions` query, ask the user
  to disambiguate when needed, then retry with the selected `memory_fact`.
- If a conversation correction returns
  `memory_update_strategy="append_correction_episode"`, tell the user the
  correction was recorded; do not claim the backend fact was rewritten in place.
- If a user wants an existing transient workflow to become durable memory, call
  `pska_memory_review_from_workflow`; do not write memory directly.
- If source audit reports route-like local-folder or Obsidian entry points,
  call `pska_source_memory_candidates_from_audit` to create deduped governed
  Memory Card review candidates.
- If one inspected source should affect future behavior, call
  `pska_source_memory_review_create` with explicit `memory_type`,
  `behavior_delta`, and source refs. Prefer `source_route` and `project_state`
  for source-derived memory; do not promote generic file summaries.
- If an Eidolia `thought` or `artifact` node is cited as context, call
  `pska_eidolia_context_read` with the project/node metadata so PSKA records a
  source-safe `SourceRef(adapter="eidolia")`.
- If an Eidolia `thought` or `artifact` is explicitly meant to affect future
  behavior, call `pska_eidolia_memory_review_create` to create a governed
  Memory Card candidate. Keep Eidolia's user-facing ontology to `thought` and
  `artifact`; do not invent new canvas node types.
- If the user asks why a memory/review/source/Eidolia node exists, where it
  came from, when it entered review, or how it connects to another PSKA object,
  call `pska_trace_query`. Treat it as a read-only ledger view over audit and
  review records; do not infer hidden model causality from missing trace data.
- If the user explicitly asks to import or trace an Eidolia project export or
  runtime project folder, call `pska_eidolia_project_trace_import` with the
  project path, workspace JSON path, or selected agentic trace JSON paths. This
  is a read-only project-file import into PSKA audit/source refs; it must not
  mutate the canvas, copy the project into PSKA as canonical content, or create
  memory reviews by itself.
- If an existing durable memory must be changed outside the normal conversation
  flow, start from a `pska_memory_search` or `pska_memory_card_list` result and call
  `pska_memory_update_review`; do not call backend update tools directly.
- If a Memory Card health issue says an existing durable memory may be stale,
  incomplete, or conflicting, prefer `pska_memory_refresh_review` from the
  Memory Card id. It creates a pending refresh/update Review and still does not
  write durable memory until the Review is accepted and applied.
- If Memory Review Queue returns `refresh_reviews` or the
  `review_memory_refresh` action, open the referenced Review with
  `pska_review_get` and treat it as existing-card maintenance; do not bury it in
  generic pending review handling.
- If an existing durable memory must be removed outside the normal conversation
  flow, start from a `pska_memory_search` or `pska_memory_card_get` result and call
  `pska_memory_delete_review`; do not call backend delete tools directly.
- If a review is marked `needs_edit`, use `pska_review_revise` to create a new
  candidate review instead of mutating the old review. For memory_patch
  candidates, pass a `memory_candidate` object when the human has edited the
  candidate text, memory type, scope, or behavior_delta.
- If Memory Review Queue returns a group-level accept/reject action and the
  human has explicitly approved that group decision, call
  `pska_review_decide_batch`; this only changes Review states and still does not
  write durable memory.
- Use `pska_memory_lifecycle` to inspect a durable memory's reviewed
  apply/update/delete history; do not query backend memory history directly.
- Use `pska_memory_health_scan` before planning memory cleanup work, then follow
  the returned `next_actions`.
- Use `pska_memory_why_used` before claiming that a Memory Card shaped an
  answer. If the trace confidence is only `candidate_retrieval`, say that the
  memory was surfaced as context rather than asserting final-answer influence.
- Use `pska_workflow_memory_attribution` for final-answer `used_memory_ids`; use
  `pska_workflow_memory_suggestions` before offering to preserve an answer as
  durable memory.
- Export briefs from workflow context only when the user needs an explicit
  Markdown or JSON handoff.

## Workflow

Default loop:

1. Call `pska_workspace_status`.
2. Inspect the first relevant `next_actions` item.
3. Use its PSKA `tool` and `params` fields when they are present.
4. If `requires_input` is present, ask the user for that input before calling
   the tool.
5. If provider configuration or component readiness is unclear, call
   `pska_runtime_diagnostics`.
6. For durable memory operations, call `pska_capabilities_get` before deciding
   whether PSKA can apply, update, or delete memory with the configured adapter.
7. After any KB, Ask, review, or memory mutation, call `pska_workspace_status`
   again before choosing the next step.

Common next actions:

- `run_file_to_work_product_loop`: ask for files, dataset name, and question,
  then call `pska_ingest_loop` with the provided safe params. This is the
  preferred fresh-workspace path.
- `create_or_upload_knowledge_base`: ask for files or dataset details, then use
  `pska_kb_ingest_files` only when manual KB setup is needed without the full
  upload-to-work-product loop.
- `wait_for_ingestion`: use `pska_kb_ingestion_status` or wait before asking.
- `run_agentic_question`: ask for the question if needed, then call
  `pska_agentic_question_start` with the provided scope params.
- `resume_blocked_ask`: call `pska_agentic_question_resume` with the provided
  `run_id`, unless the action tool is `pska_ingest_loop_resume`.
- `wait_for_resumable_ask`: call `pska_agentic_question_resumable` or wait,
  then resume with the returned PSKA tool once `can_resume=true`.
- `review_pending_durable_knowledge`: open the provided review with
  `pska_review_get`.
- `apply_accepted_memory`: call `pska_memory_apply` only if the review is
  already accepted.
- `inspect_unsupported_memory_operation`: open the provided review and report
  the unsupported PSKA capability; do not call provider-native memory tools.

For an existing KB:

1. Call `pska_workspace_status` and prefer its `run_agentic_question` action
   when a ready scope exists.
2. Call `pska_agentic_question_start` for normal Ask flows.
3. Use lower-level `pska_workflow_start`, `pska_context_retrieve`, and
   `pska_propose` only when the user explicitly asks to inspect or control those
   steps.
4. For durable memory, call `pska_review_create` after `memory_patch`, or call
   `pska_memory_review_from_workflow` for an existing transient workflow.
5. Ask the human for review. Use `pska_review_list` or `pska_review_get` to
   resume pending review work if needed.
6. After acceptance, call `pska_review_decide`; after `needs_edit`, call
   `pska_review_revise`, passing `memory_candidate` edits for memory_patch
   reviews when available.
7. For accepted memory patch, memory update, or memory delete reviews, call
   `pska_memory_apply`.
8. Call `pska_workflow_artifact` or `pska_workflow_brief` to inspect the
   transient work product.
9. Call `pska_export_brief` only for explicit Markdown or JSON handoff.

For a new document:

1. Prefer `pska_ingest_loop` with absolute file paths, a dataset name, and the
   user's question when the user wants the normal upload -> Ask -> export loop.
   For long PDFs or slow embedding, set `wait_ready=false` so PSKA records a
   resumable blocked workflow instead of holding the agent call open.
2. If `pska_ingest_loop` returns `status=ok`, answer from its exported sourced
   work product and artifact. If it returns `status=not_ready`, report the
   readiness or ingestion failure and stop before answering; after the selected
   scope becomes ready, call `pska_ingest_loop_resume` with the blocked
   `run_id`.
3. Use the lower-level path when the user wants step-by-step control or the
   ingestion job needs long polling: call `pska_kb_ingest_files` with absolute
   file paths, a dataset name, and
   `parse=true`; inspect the returned `readiness` and `ingestion_status`.
4. Call `pska_workspace_status` and follow its ingestion-related next action.
5. If ingestion did not wait or the returned status is not ready, call
   `pska_kb_document_status` and `pska_kb_ingestion_status` until the selected
   scope is ready, failed, or requires parsing.
6. If ingestion status returns a failed scope, report the failure reason instead
   of asking.
7. Call `pska_agentic_question_start` with the returned `dataset_id`.
8. If you already know useful follow-up angles, pass them as
   `retrieval_queries`; PSKA will run them inside the same explicit scope and
   record the query plan.
9. Use `source_inspection_limit` to bound how many retrieved sources PSKA should
   inspect through adapters during Ask.
10. If context is insufficient, retrieve again within the same explicit scope or
   report that the question cannot be answered from the selected materials.
11. Answer from the returned context, inspected sources, artifact, and brief.
12. If a memory patch or deletion was proposed, wait for human acceptance before
   applying it.
13. Use `pska_export_brief` only when the user asks for an explicit export.

## Good Prompt

```text
Use PSKA-Essential to retrieve context for this question, propose a reviewed
memory patch, and prepare a sourced brief. Stop before applying memory until
review is accepted, and export only if I ask for a handoff.
```

```text
Use PSKA-Essential to ingest this local document into a RAGFlow-backed
knowledge base, ask a scoped question over that KB, propose any long-term
memory as a review item, and prepare a sourced brief with explicit citations.
```
