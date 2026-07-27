# PSKA Product Design

PSKA is a universal AI knowledge workspace. It is not limited to investment,
research, product, consulting, or any other specific domain.

Product promise:

> PSKA turns user materials into trusted work products and governed durable
> knowledge.

## V1 Position

PSKA v1 should ship as two coordinated product surfaces:

- A mature Hermes-based frontend for human workflows: conversation, selected
  knowledge scope, ingestion/readiness status, source reading, work products,
  conversation-native memory changes, exception review, activity, and settings.
- A glue/control layer for backend orchestration: normalized contracts,
  adapters, governance policy, audit, and MCP tools.

RAGFlow, Graphiti, local embedding services, LLM providers, and future company
GraphRAG systems are not the product surface. They are replaceable substrates.
RAGFlow may still provide its own native operator console for detailed knowledge
base, parser, chunk, and embedding management. PSKA should not reimplement that
surface unless it is simplifying a cross-component workflow.

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
  -> make the work product available for explicit export
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
possible governance mechanisms. Review is an exception inbox, not the normal
daily memory-management experience. Governance is the broader product model.

Agents may freely produce transient results during normal workflows. Governance
applies when an agent or user attempts to create or modify durable workspace
knowledge. The object may be a memory, graph relationship, profile preference,
durable summary, or another persistent semantic object intended to shape future
reasoning.

Governance may be implemented through explicit human review, conversation
policy, or workspace policy. The product should support different policies for
different origins and workspaces, such as:

- auto-approve entity or graph extraction
- auto-apply clear user-driven remember/correct/forget requests from
  conversation while preserving audit records
- manual approval for uncertain, risky, broad destructive, ambiguous
  destructive, conflicting, or batch-derived memory/profile changes
- enterprise approval workflows
- fully automatic personal workspaces

The point is to protect future knowledge quality without blocking normal
question answering, writing, retrieval, or ingestion workflows.

Conversation-native memory is the primary user path. If the user says "remember
this", "that is wrong", or "forget that", Hermes should call PSKA conversation
memory through MCP/Product API. PSKA may auto-accept and auto-apply clear,
low-risk user instructions under workspace policy, but it still records the
proposal, decision, apply result, and audit trail. Pending Review items should
be created only when the change is uncertain, important, risky, conflicting,
broad destructive, ambiguous destructive, batch-derived, or explicitly forced
by policy or user intent. A clear user-requested correction or forget action
stays in the conversation memory path by default.

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

The frontend should be redesigned as a conversation-first product shell, not as
an engineering console or a replacement RAGFlow UI.

PSKA should not reimplement mature component frontends when those components
already own the workflow well. RAGFlow should remain the primary UI for
knowledge-base creation, document upload, parsing, chunking, embedding,
indexing, and chunk inspection when deep operator control is needed. Hermes
WebUI is the daily conversation workspace and first user entry. PSKA may link or
embed component pages inside that shell, but normal user workflows should not
depend on provider-native screens.

"PSKA wraps components" means PSKA owns the product contract: workspace
identity, selected context, component status, PSKA-native workflow APIs,
conversation memory, exception review, audit, and policy. It does not mean PSKA
rewrites or scrapes provider-native screens. Browser code in the integrated
workspace calls Hermes WebUI routes and PSKA proxy/Product APIs; provider-native
details stay behind adapters or inside embedded provider consoles.

V1 frontend should focus on:

- Conversation: the default surface for scoped agentic questions, readiness,
  sources, work products, conversation memory, and resumable workflows.
- Work Products: sourced briefs, source manifests, exports, and durable-review
  creation from selected transient results.
- Review: exception inbox for uncertain, risky, conflicting, broad destructive,
  ambiguous destructive, or batch-derived durable knowledge changes.
- Activity: audit trail across workflow, review, memory, and export events.
- Knowledge: a PSKA readiness/status summary plus embedded or linked RAGFlow
  knowledge-base console.
- Components: RAGFlow, Hermes, Graphiti, embedding, LLM, capability, and
  diagnostic status with links to native consoles where appropriate.
- Settings: workspace policy, tenant/workspace context, and provider
  configuration guidance.

Provider-specific controls such as embedding model, chunk method, parse flags,
and wait flags should be hidden from the normal user flow unless they are
explicitly advanced settings. The ordinary upload path should prefer the
component-native UI or a simplified PSKA quick-upload.

The detailed frontend redesign is specified in `docs/FRONTEND_REDESIGN.md`.

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
