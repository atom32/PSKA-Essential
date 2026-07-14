---
name: pska-essential
description: Run PSKA-Essential reviewed knowledge workflows through its MCP server.
---

# PSKA-Essential

Use this skill when a user wants a reviewed agent knowledge workflow backed by
external KB, GraphRAG, or memory systems.

## Contract

- PSKA-Essential is the only safe tool surface.
- Backend MCP servers such as Graphiti must not be exposed directly for this
  workflow.
- Use PSKA `kb` tools for RAGFlow-backed dataset creation, document upload,
  parsing, and readiness checks instead of calling RAGFlow directly.
- Treat upload, parsing, embedding, and indexing as asynchronous and check
  `pska_kb_ingestion_status` readiness before asking over a dataset.
- Do not use case-specific shortcuts, hardcoded domains, or fallback answers.
- Use `pska_policy_get` to inspect the current workspace governance policy
  instead of inferring policy from provider capabilities.
- Memory writes require accepted review.
- Use workflow artifacts or transient briefs for inspection; explicit exports
  must come from workflow context.
- Use `pska_memory_review_from_workflow` when an existing transient workflow
  should become a durable memory candidate.
- Use `pska_memory_update_review` from an explicit `pska_memory_search` result
  when durable memory should be changed; do not call backend update tools.
- Use `pska_memory_delete_review` from an explicit `pska_memory_search` result
  when durable memory should be removed; do not call backend delete tools.
- Use `pska_review_revise` for `needs_edit` reviews instead of mutating the
  original review.
- Use `pska_memory_lifecycle` to inspect PSKA's reviewed apply/update/delete
  history for durable memory; do not call backend memory history directly.

## Steps

1. If needed, upload documents with `pska_kb_ingest_files`.
2. Confirm readiness with `pska_kb_document_status` and
   `pska_kb_ingestion_status`.
3. Start a scoped PSKA workflow or call `pska_agentic_question_start`.
4. Pass explicit `retrieval_queries` when useful follow-up angles are known;
   PSKA will run them inside the selected scope and record the query plan.
5. Use `source_inspection_limit` to bound how many retrieved sources PSKA should
   inspect through adapters during Ask.
6. Retrieve context and answer only from returned context and inspected sources.
7. Propose digest, writing brief, or memory patch.
8. Create a review, or use `pska_memory_review_from_workflow` for an existing
   transient sourced workflow.
9. Wait for review acceptance; use review list/get tools to resume pending
   review work.
10. If review asks for edits, create a revised review; apply memory changes only
   after acceptance.
11. Inspect `pska_workflow_artifact` or `pska_workflow_brief`.
12. Export a Markdown or JSON brief only for explicit handoff.
