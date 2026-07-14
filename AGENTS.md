# PSKA-Essential Agent Rules

This repository builds PSKA as a universal product, not a domain-specific demo.
Codex and other coding agents must follow these rules.

## Product Boundary

- PSKA-Essential is the glue and control layer for knowledge workflows.
- Hermes is the first supported agent host for v1. Other agents may be added
  later through adapter contracts, but do not make FastReAct-specific jobs,
  prompts, or assumptions part of the core product.
- RAGFlow, Graphiti, embedding services, LLM providers, and future company
  GraphRAG systems stay behind adapters.
- A mature frontend and the PSKA glue layer are both required product surfaces:
  the frontend owns user workflows, and the glue layer owns backend orchestration,
  review gates, normalized contracts, audit, and MCP/tool access.

## Universal Product Rule

- Do not add case-specific logic, hardcoded companies, hardcoded industries,
  hardcoded document names, or demo-only shortcuts to runtime code.
- Domain examples are allowed only in docs, fixtures, or manual demos, never as
  product behavior.
- Product features must be driven by user-provided workspace, dataset, document,
  schema, taxonomy, or prompt inputs.

## No Fallback Rule

- Do not add silent fallback behavior.
- Missing backend configuration must fail explicitly.
- Backend failures must be surfaced as actionable errors, not hidden by fake
  data, cached guesses, generic answers, or another provider.
- `fake` adapters are allowed only for explicit local development and tests
  through `PSKA_DEV_FAKE=1`.

## Agentic Loop Rule

- Agentic loops are first-class, but must run inside PSKA boundaries:
  plan, retrieve, inspect sources, decide whether more retrieval is needed,
  propose, create review, apply accepted memory, and export.
- Agents must use PSKA MCP tools only. They must not call RAGFlow, Graphiti,
  memory, or graph tools directly for PSKA workflows.
- Agent output must remain scoped to selected datasets/documents/memory. If
  context is insufficient, the workflow must ask for more context or report that
  it cannot answer.

## Embedding And Ingestion Rule

- Document upload, parsing, chunking, embedding, and indexing are long-running
  asynchronous jobs.
- Frontend and MCP flows must expose job status, progress, readiness, and
  failure reasons instead of pretending ingestion is instant.
- Question flows must distinguish "dataset exists" from "dataset is ready for
  retrieval."

## Review Rule

- Long-term memory and graph writes require accepted review.
- Do not expose direct add/delete/clear backend memory tools to agents.
- Candidate facts, memories, entities, and relations are workflow-local until
  reviewed.
