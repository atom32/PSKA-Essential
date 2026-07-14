# PSKA-Essential Doctrine

PSKA-Essential exists to make agent knowledge workflows finish cleanly.

It is not sold as an evidence product. Evidence is a mechanism used to make
workflow state inspectable and memory writes safe.

The product is universal. Runtime behavior must not contain vertical-specific
or demo-specific logic. Domain workflows must be expressed through user-provided
workspaces, datasets, schemas, prompts, and templates, not hardcoded branches.

## Principles

- Workflow first: collect, retrieve, propose, review, apply, export.
- Hermes first: v1 validates one mature agent host before generalizing to many.
- Adapter first: RAGFlow, Graphiti, Hermes, and company GraphRAG stay outside.
- Agentic loop first-class: questions may plan, retrieve, inspect sources,
  retrieve again, synthesize, propose, and review inside PSKA boundaries.
- Review before memory: candidate knowledge cannot write long-term memory until
  a review decision accepts it.
- Explicit readiness: upload, parsing, embedding, indexing, and graph extraction
  are asynchronous states, not instant side effects.
- No silent fallback: missing or failing providers must produce explicit errors.
- Audit everything important: workflow starts, retrievals, proposals, reviews,
  and memory writes are recorded.
- Replace platforms, keep contracts: changing GraphRAG backend must not change
  the MCP tools.

## Non-Goals

- No custom knowledge base.
- No custom GraphRAG.
- No first-party editor in v1.
- No FastReAct coupling until a later agent adapter proves it should exist.
- No domain-specific shortcuts.
- No case-specific code, prompts, fixtures, or fallback behavior in runtime
  paths.
