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
  readiness before asking over a dataset.
- Do not use case-specific shortcuts, hardcoded domains, or fallback answers.
- Memory writes require accepted review.
- Use workflow artifacts or transient briefs for inspection; explicit exports
  must come from workflow context.

## Steps

1. If needed, upload documents with `pska_kb_ingest_files`.
2. Confirm readiness with `pska_kb_document_status`.
3. Start a scoped PSKA workflow or call `pska_agentic_question_start`.
4. Retrieve context and answer only from returned context.
5. Propose digest, writing brief, or memory patch.
6. Create a review.
7. Wait for review acceptance; use review list/get tools to resume pending
   review work.
8. Apply memory only after acceptance.
9. Inspect `pska_workflow_artifact` or `pska_workflow_brief`.
10. Export a Markdown or JSON brief only for explicit handoff.
