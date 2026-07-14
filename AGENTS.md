# PSKA-Essential Agent Rules

This repository builds PSKA as a universal product, not a domain-specific demo.
Codex and other coding agents must follow these rules.

## Product Philosophy

PSKA is not another RAG system, another memory engine, or another agent
framework. PSKA provides a stable, governance-driven orchestration layer that
connects independent AI systems into a coherent, auditable knowledge workspace.

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

## Layer Rule

- Frontend code must communicate only with PSKA services, product APIs, and MCP
  tools.
- Frontend code must never call RAGFlow, Graphiti, embedding services, LLM
  providers, databases, queues, or other backend systems directly.
- Backend integrations belong exclusively to adapters.

## API Boundary

- All external access must go through stable PSKA APIs, MCP tools, CLI/SDK
  surfaces, or adapter contracts.
- Do not expose internal databases, queues, or provider APIs directly to
  clients.
- Do not let temporary integration convenience become a public contract.

## Canonical Model Rule

- PSKA owns the canonical domain model.
- External systems may use different schemas, IDs, and payloads internally, but
  adapters must translate them into PSKA contracts.
- Do not leak provider-specific data structures outside adapters.
- Frontend, MCP, SDK, CLI, audit, review, and export flows should speak PSKA
  contract language, not provider-native language.

## Provider Independence Rule

- Do not encode provider-specific prompts, response formats, tool names, API
  shapes, or runtime assumptions into core modules.
- Provider-specific behavior belongs inside adapters, skills, or configuration.
- Hermes is the first supported agent host, not a permanent coupling point.

## Universal Product Rule

- Do not add case-specific logic, hardcoded companies, hardcoded industries,
  hardcoded document names, or demo-only shortcuts to runtime code.
- Domain examples are allowed only in docs, fixtures, or manual demos, never as
  product behavior.
- Product features must be driven by user-provided workspace, dataset, document,
  schema, taxonomy, or prompt inputs.
- Product behavior is determined by workspace configuration, selected datasets,
  schemas, prompts, and policies, never by runtime special cases.

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

## Deterministic Workflow Rule

- Workflow state transitions must be explicit and auditable.
- Every review, memory application, graph write, durable knowledge update, and
  export must produce traceable records.
- Avoid hidden state changes.
- Never write durable memory, graph, profile, or summary state as a side effect
  of retrieval, answering, ingestion, or export.

## Embedding And Ingestion Rule

- Document upload, parsing, chunking, embedding, and indexing are long-running
  asynchronous jobs.
- Frontend and MCP flows must expose job status, progress, readiness, and
  failure reasons instead of pretending ingestion is instant.
- Question flows must distinguish "dataset exists" from "dataset is ready for
  retrieval."

## Review Rule

- Long-term memory and graph writes, updates, and deletions require accepted
  review.
- Do not expose direct add/delete/clear backend memory tools to agents.
- Candidate facts, memories, entities, and relations are workflow-local until
  reviewed.
