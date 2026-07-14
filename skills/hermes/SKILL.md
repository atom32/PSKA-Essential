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
- Export briefs from workflow context, not model-only memory.

## Workflow

For an existing KB:

1. Call `pska_workflow_start`.
2. Call `pska_context_retrieve`.
3. Call `pska_propose` with `kind` set to `digest`, `memory_patch`, or
   `writing_brief`.
4. Call `pska_review_create`.
5. Ask the human for review.
6. After acceptance, call `pska_review_decide`.
7. For memory patches only, call `pska_memory_apply`.
8. Call `pska_export_brief` for Markdown or JSON handoff.

For a new document:

1. Call `pska_kb_ingest_files` with absolute file paths, a dataset name, and
   `parse=true`.
2. If ingestion did not wait, call `pska_kb_document_status` until parsing is
   complete.
3. Call `pska_agentic_question_start` with the returned `dataset_id`.
4. If context is insufficient, retrieve again within the same explicit scope or
   report that the question cannot be answered from the selected materials.
5. Answer from the returned context and brief.
6. If a memory patch was proposed, wait for human acceptance before applying it.
7. Export a Markdown or JSON brief.

## Good Prompt

```text
Use PSKA-Essential to retrieve context for this question, propose a reviewed
memory patch, and export a brief. Stop before applying memory until review is
accepted.
```

```text
Use PSKA-Essential to ingest this local document into a RAGFlow-backed
knowledge base, ask a scoped question over that KB, propose any long-term
memory as a review item, and export a brief.
```
