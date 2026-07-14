# Feasibility Audit

This audit freezes the implementation assumptions behind PSKA-Essential v1.

## Component Findings

Hermes Agent `e589b73`

- Supports stdio and HTTP MCP servers through `mcp_servers` config.
- Supports tool include/exclude filters.
- Has CLI lifecycle commands such as add, test, configure, and catalog install.
- Conclusion: feasible as the primary agent host. PSKA-Essential should ship an
  MCP server and Hermes config, not a Hermes core plugin.
- Product decision: v1 is Hermes-first. Other agents may be supported later,
  but only through a PSKA agent adapter boundary.

RAGFlow `b0cac0a`

- Python SDK exposes `RAGFlow.retrieve(...)`.
- HTTP examples use `/api/v1/retrieval`.
- Dataset search and graph read APIs exist, but PSKA-Essential v1 only needs
  retrieval and citation/source mapping.
- Document upload, parsing, embedding, and indexing can be slow and must be
  treated as asynchronous job states in the product.
- Conclusion: feasible as the default retrieval backend. Adapter must map
  RAGFlow chunks into `ContextPacket` and `SourceRef`; raw RAGFlow payloads
  must not leak through MCP contracts.

Graphiti `526dcad`

- Core API exposes `add_episode`, `add_episode_bulk`, `search`, and group_id.
- Graphiti MCP exposes useful tools, but also includes direct write/delete/clear
  tools such as add_memory, delete_episode, delete_entity_edge, and clear_graph.
- Conclusion: feasible as the default memory graph backend, but not safe to
  expose directly to Hermes. PSKA-Essential must be the only agent-visible MCP
  surface and must gate writes through review.
- Current PSKA adapter support: reviewed add and reviewed entity-edge delete.
  Reviewed update remains explicitly unsupported for Graphiti until a
  transactional fact update contract exists.

OpenClaw `e43bd3d`

- Skills are installable through local, Git, or ClawHub flows and use `SKILL.md`
  as the root instruction file.
- Conclusion: useful as secondary packaging. v1 primary delivery remains Hermes.

Current PSKA

- Reusable: candidate schemas, source_refs, review statuses, audit idea, MCP
  naming experience.
- Not reusable for this repo: FastReAct job coupling, frontend workspace,
  Postgres-first store, domain-sized product surface.
- Current conclusion: FastReAct has not proved higher maturity than Hermes for
  v1, so it must not shape core PSKA contracts.

## Hard Constraints

- Do not implement a knowledge base.
- Do not implement GraphRAG.
- Do not expose Graphiti MCP directly to the agent.
- Do not expose RAGFlow raw payloads through public MCP tools.
- Do not migrate FastReAct-specific jobs or prompts.
- Do not add case-specific or domain-hardcoded runtime behavior.
- Do not add silent fallback. Missing or failed providers must fail explicitly.
- Do not treat embedding or indexing as instant.

## Implementation Choice

PSKA-Essential is a glue layer with adapter ports:

- `RetrievalPort`
- `MemoryPort`
- workflow/review/audit service
- MCP tools over those services

The fake adapter and company GraphRAG stub are first-class tests of
replaceability, not demos only. Fake adapters must be selected explicitly for
development/tests and are not runtime fallbacks.
