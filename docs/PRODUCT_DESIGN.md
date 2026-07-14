# PSKA Product Design

PSKA is a universal AI knowledge workspace. It is not limited to investment,
research, product, consulting, or any other specific domain.

The product promise:

```text
User materials -> external knowledge base -> scoped agentic question loop
  -> sourced answer / brief -> reviewed memory or graph candidates
  -> durable workspace knowledge
```

## V1 Position

PSKA v1 should ship as two product surfaces:

- A mature frontend for human workflows: knowledge bases, ingestion progress,
  scoped questions, source reading, writing briefs, review, and settings.
- A glue/control layer for backend orchestration: normalized contracts,
  adapters, review gates, audit, and MCP tools.

RAGFlow, Graphiti, local embedding services, LLM providers, and future company
GraphRAG systems are not the product surface. They are replaceable substrates.

## Agent Strategy

Hermes is the first supported agent host for v1.

FastReAct has not yet proved that it is more mature than Hermes for this
product, so PSKA must not depend on FastReAct-specific jobs, prompts, or runtime
contracts. Multiple agents can be supported later through an agent adapter
boundary, but the first closed product loop should be Hermes-first.

Agents may be powerful, but they are not allowed to own PSKA policy. They must
work through PSKA MCP tools and stay inside selected dataset, document, memory,
review, and audit boundaries.

## Agentic Question Loop

The Ask experience should not be a single one-shot retrieval call. It should be
an agentic loop controlled by PSKA:

```text
start question
  -> inspect selected scope and readiness
  -> retrieve context
  -> inspect sources
  -> decide whether more retrieval is needed
  -> synthesize answer or report insufficient context
  -> propose writing brief / memory candidates / graph candidates
  -> create review items
  -> export
```

The loop can call retrieval multiple times, but it must never expand scope
silently. If the selected context is insufficient, it should ask for a broader
scope or return an explicit insufficient-context result.

## Embedding And Ingestion

Embedding is a real product bottleneck, not an implementation detail. Upload,
parsing, chunking, embedding, indexing, and optional graph extraction must be
modeled as asynchronous jobs.

Required product states:

- uploaded
- parsing
- embedding
- indexing
- ready
- failed
- cancelled

The frontend must show progress, per-document readiness, failure reasons, and
what actions are currently available. A dataset that exists is not necessarily
ready for agentic questions.

## Universal Product Rule

Runtime code must not contain case-specific behavior:

- no hardcoded companies
- no hardcoded industries
- no hardcoded document names
- no demo-specific prompts
- no special handling for a sample annual report or a sample vertical

Domain-specific templates may exist only as optional user-facing templates,
fixtures, or demos. Product behavior must be driven by user-selected workspace,
datasets, documents, schemas, taxonomies, and prompts.

## No Fallback Rule

PSKA must fail explicitly when required backends are not configured or when a
backend operation fails.

Not allowed:

- silently switching to fake adapters
- answering from model memory when retrieval fails
- hiding embedding/indexing failures
- replacing one configured backend with another without user/admin intent
- writing placeholder results into review, memory, graph, or export flows

Fake adapters remain valid only for explicit local development and tests with
`PSKA_DEV_FAKE=1`.

## Frontend Modules

V1 frontend should include:

- Home: recent work, pending jobs, pending reviews, recent briefs.
- Knowledge Bases: create datasets, upload files, track ingestion and readiness.
- Ask: select scope, run the agentic loop, show sourced answers and source gaps.
- Reader: inspect source chunks/documents and trace where evidence was used.
- Writing: turn sourced answers into briefs and exports.
- Review: accept, reject, or edit candidate memory/graph/fact items.
- Settings: configure providers, keys, embedding service, workspace/tenant scope.

The frontend should be a real application surface, not a demo page. It must make
slow ingestion, scoped retrieval, review status, and backend configuration
visible to the user.

## Glue Layer Responsibilities

The PSKA glue layer owns:

- adapter contracts
- provider configuration validation
- dataset/document status normalization
- retrieval packet normalization
- source references
- agentic loop state
- review gate
- memory and graph write policy
- audit events
- MCP/tool surface
- frontend API surface

External systems own their specialized internals. PSKA owns the product
workflow, policy, and contract boundary.
