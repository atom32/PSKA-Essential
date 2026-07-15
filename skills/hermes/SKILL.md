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
- Use `pska_runtime_diagnostics` when provider configuration, backend health,
  or adapter contract readiness needs troubleshooting. Do not call provider
  health endpoints directly.
- Use `pska_component_check` when the user wants to verify that configured
  providers can support the PSKA product loop. Treat `incomplete`, `error`, or
  skipped required checks as not proven.
- Use `pska_capabilities_get` as the stable PSKA operation capability contract
  before durable memory apply, update, or delete work. If an operation is not
  supported, report that PSKA cannot perform it with the current memory adapter.
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
- Treat upload, parsing, embedding, and indexing as asynchronous. Check document
  readiness and `pska_kb_ingestion_status` before asking over a dataset.
- Do not use case-specific shortcuts or hardcoded domains.
- Do not invent fallback answers when retrieval or backend calls fail.
- Treat retrieved context as workflow-local until review accepts it.
- Use `pska_policy_get` when you need to understand the current workspace
  governance policy; do not infer policy from provider capabilities.
- Do not call `pska_memory_apply` until a review has status `accepted`.
- Use `pska_workflow_artifact` or `pska_workflow_brief` to inspect transient
  work products without export side effects.
- If a user wants an existing transient workflow to become durable memory, call
  `pska_memory_review_from_workflow`; do not write memory directly.
- If a user wants an existing durable memory changed, start from a
  `pska_memory_search` result and call `pska_memory_update_review`; do not call
  backend update tools directly.
- If a user wants an existing durable memory removed, start from a
  `pska_memory_search` result and call `pska_memory_delete_review`; do not call
  backend delete tools directly.
- If a review is marked `needs_edit`, use `pska_review_revise` to create a new
  candidate review instead of mutating the old review.
- Use `pska_memory_lifecycle` to inspect a durable memory's reviewed
  apply/update/delete history; do not query backend memory history directly.
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

- `create_or_upload_knowledge_base`: ask for files or dataset details, then use
  `pska_kb_ingest_files`.
- `wait_for_ingestion`: use `pska_kb_ingestion_status` or wait before asking.
- `run_agentic_question`: ask for the question if needed, then call
  `pska_agentic_question_start` with the provided scope params.
- `resume_blocked_ask`: call `pska_agentic_question_resume` with the provided
  `run_id`.
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
   `pska_review_revise`.
7. For accepted memory patch, memory update, or memory delete reviews, call
   `pska_memory_apply`.
8. Call `pska_workflow_artifact` or `pska_workflow_brief` to inspect the
   transient work product.
9. Call `pska_export_brief` only for explicit Markdown or JSON handoff.

For a new document:

1. Prefer `pska_ingest_loop` with absolute file paths, a dataset name, and the
   user's question when the user wants the normal upload -> Ask -> export loop.
2. If `pska_ingest_loop` returns `status=ok`, answer from its exported sourced
   work product and artifact. If it returns `status=not_ready`, report the
   readiness or ingestion failure and stop before answering.
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
