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
- Use `pska_kb_*` tools when the user needs a document uploaded or parsed into
  an external knowledge base.
- Treat upload, parsing, embedding, and indexing as asynchronous. Check document
  readiness before asking over a dataset.
- Do not use case-specific shortcuts or hardcoded domains.
- Do not invent fallback answers when retrieval or backend calls fail.
- Treat retrieved context as workflow-local until review accepts it.
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

For an existing KB:

1. Call `pska_workflow_start`.
2. Call `pska_context_retrieve`.
3. Call `pska_propose` with `kind` set to `digest`, `memory_patch`, or
   `writing_brief`.
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

1. Call `pska_kb_ingest_files` with absolute file paths, a dataset name, and
   `parse=true`.
2. If ingestion did not wait, call `pska_kb_document_status` until parsing is
   complete.
3. Call `pska_agentic_question_start` with the returned `dataset_id`.
4. If context is insufficient, retrieve again within the same explicit scope or
   report that the question cannot be answered from the selected materials.
5. Answer from the returned context, artifact, and brief.
6. If a memory patch or deletion was proposed, wait for human acceptance before
   applying it.
7. Use `pska_export_brief` only when the user asks for an explicit export.

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
