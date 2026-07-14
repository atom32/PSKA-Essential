# PSKA Product Design

PSKA is a universal AI knowledge workspace. It is not limited to investment,
research, product, consulting, or any other specific domain.

Product promise:

> PSKA turns user materials into trusted work products and governed durable
> knowledge.

## V1 Position

PSKA v1 should ship as two product surfaces:

- A mature frontend for human workflows: knowledge bases, ingestion progress,
  scoped questions, source reading, writing briefs, review, and settings.
- A glue/control layer for backend orchestration: normalized contracts,
  adapters, governance policy, audit, and MCP tools.

RAGFlow, Graphiti, local embedding services, LLM providers, and future company
GraphRAG systems are not the product surface. They are replaceable substrates.

## Agent Strategy

Hermes is the first supported agent host for v1.

FastReAct has not yet proved that it is more mature than Hermes for this
product, so PSKA must not depend on FastReAct-specific jobs, prompts, or runtime
contracts. Multiple agents can be supported later through an agent adapter
boundary, but the first closed product loop should be Hermes-first.

Agents execute workflows. PSKA exclusively owns persistence, workspace state,
governance, and product policy. Agents must work through PSKA MCP tools and stay
inside selected dataset, document, memory, governance, and audit boundaries.

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
  -> produce transient answer / brief
  -> optionally propose durable knowledge changes
  -> apply workspace governance when persistence is requested
  -> export
```

The loop can call retrieval multiple times, but it must never expand scope
silently. If the selected context is insufficient, it should ask for a broader
scope or return an explicit insufficient-context result without creating a
proposal, review, durable knowledge change, or export.

Transient answers, draft briefs, citations, source notes, and intermediate
reasoning do not require review merely because AI produced them. Governance is
triggered when a result is intended to persist as workspace knowledge.

## Source First Principle

Every durable statement should be traceable to its supporting source materials.
When evidence is insufficient, PSKA reports insufficient context instead of
fabricating certainty.

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

Parsing, OCR, chunking, embedding, indexing, retrieval, citation generation,
source normalization, and ingestion pipelines may proceed automatically. These
are mechanical transformations of source materials and should not create review
items just because AI or an automated pipeline executed them.

## Knowledge Lifecycle

PSKA distinguishes knowledge by permanence. Knowledge flows from source
knowledge to transient working knowledge to durable workspace knowledge.
Durable persistence never happens as an ungoverned side effect; it must be an
explicit outcome of workspace governance.

Source knowledge is user-provided material: uploaded files, PDFs, markdown, web
pages, source code, meeting notes, emails, and other external data. These are
source materials. Uploading and transforming them for retrieval does not require
human approval.

Transient working knowledge is disposable workflow state: retrieval results,
temporary summaries, citations, source notes, draft answers, draft briefs, and
intermediate reasoning. Agents may create these freely inside the selected
scope. They help users think and work, but they do not automatically become
future workspace memory.

Durable workspace knowledge is made of persistent semantic objects maintained
by PSKA across future sessions. Representative examples include memory, graph
relationships, profile preferences, and durable summaries. Because these can
influence future reasoning, creating or modifying them requires governance.

## Durable Knowledge Governance

Governance is the overall mechanism that controls how transient results become
durable workspace knowledge. Review, approval, workspace policy, and audit are
possible governance mechanisms. Review is the primary user-facing action;
governance is the broader product model.

Agents may freely produce transient results during normal workflows. Governance
applies when an agent or user attempts to create or modify durable workspace
knowledge. The object may be a memory, graph relationship, profile preference,
durable summary, or another persistent semantic object intended to shape future
reasoning.

Governance may be implemented through explicit human review or through
workspace policy. The product should support different policies for different
workspaces, such as:

- auto-approve entity or graph extraction
- manual approval for memory or profile changes
- enterprise approval workflows
- fully automatic personal workspaces

The point is to protect future knowledge quality without blocking normal
question answering, writing, retrieval, or ingestion workflows.

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

Product behavior is determined by workspace configuration, selected datasets,
schemas, prompts, and policies, never by runtime special cases.

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
- Ask: select scope, tune the agentic loop, show sourced answers and source
  gaps.
- Reader: inspect source chunks/documents, optional source-derived structure
  graphs, and trace where evidence was used.
- Writing: inspect workflow state and turn sourced answers into explicit
  exports.
- Review: inspect and decide durable knowledge changes according to workspace
  policy.
- Activity: inspect the audit trail for workflow, review, memory, and export
  events.
- Settings: configure providers, keys, embedding service, workspace/tenant scope.

The frontend should be a real application surface, not a demo page. It must make
slow ingestion, scoped retrieval, durable knowledge governance, and backend
configuration visible to the user.

## Glue Layer Responsibilities

The PSKA glue layer owns:

- adapter contracts
- provider configuration validation
- workspace/tenant runtime context
- dataset/document status normalization
- retrieval packet normalization
- source references
- agentic loop state
- durable knowledge governance
- durable knowledge lifecycle: persistence, updates, deletion, review, and
  versioning
- audit events
- MCP/tool surface
- product API surface

External systems own their specialized internals. PSKA owns the product
workflow, policy, and contract boundary.

## Product Philosophy

PSKA does not replace specialized AI systems. Hermes, RAGFlow, Graphiti,
embedding providers, LLMs, and future company systems can each do specialized
work well. PSKA provides the stable workspace, governance model, and product
contract that orchestrate specialized AI infrastructure into a coherent
knowledge workflow.
