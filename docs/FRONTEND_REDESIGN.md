# Hermes WebUI Frontend Integration

Status: historical design note. The current v1 decision is that PSKA does not
own a separate daily conversation frontend. Hermes WebUI is the user workspace;
PSKA contributes Product API, MCP tools, proxy-backed panels, review/audit
contracts, and optional local diagnostics.

This document records the frontend model after the first working closed loop
exposed a product mismatch: the old local UI behaved too much like an
engineering console. The product should be a conversation-first knowledge
workspace through a Hermes WebUI-derived shell instead of replacing mature
components.

## V1 Implementation Choice

The preferred v1 implementation is to use a Hermes WebUI-derived frontend as the
Agent Workspace substrate, then add PSKA-specific panels and proxy routes inside
that shell. PSKA should not maintain a second full conversation frontend in
parallel with Hermes WebUI.

The detailed integration plan is in `docs/HERMES_WEBUI_INTEGRATION.md`.

## Core Principle

PSKA does not reimplement mature frontend or backend components when an existing
component already owns the job well.

PSKA builds native UI only inside the Hermes WebUI shell, or as local operator
diagnostics, for product responsibilities that existing components do not
provide:

- PSKA-controlled agentic question workflows
- scoped source-aware work products
- transient-to-durable knowledge governance
- review and approval
- audit and traceability across components
- workspace policy and provider-neutral status
- MCP/Hermes workflow handoff

Everything else should be linked, embedded, or surfaced through the component
that already owns it.

## Definition: "Hermes WebUI Wraps Components Through PSKA"

"Hermes WebUI wraps components through PSKA" means the user sees one workspace,
while PSKA provides the governed API/tool boundary around specialized systems.

The Hermes shell owns:

- global navigation
- workspace identity
- visual theme and layout frame
- component health/status
- selected workspace/dataset/document context
- links or embeds to external component UIs
- PSKA-backed workflow panels
- audit, review, and product policy

The shell does not own:

- the internal UI state of RAGFlow
- the internal UI state of Hermes
- the internal UI state of Graphiti or future memory systems
- provider-native forms, dashboards, and configuration screens
- direct calls from Hermes WebUI PSKA panels to provider APIs

If a component is embedded by iframe, the embedded app may call its own backend
inside the iframe. The PSKA shell must not depend on provider DOM structure,
scrape provider state, or call provider APIs directly. PSKA synchronizes through
its own Product API and adapter contracts.

If a component blocks iframe embedding through browser security policy, PSKA
opens it in a new tab or separate window and keeps a visible "refresh status"
action in the shell.

## Hermes-First Product Model

The primary PSKA experience appears inside a Hermes WebUI conversation
workspace, not inside a second PSKA-owned chat frontend.

The daily user-facing screen should center on Hermes chat and sessions, with
PSKA-backed panels or tool cards for:

- selected knowledge scope;
- ingestion/readiness state;
- retrieved sources;
- generated work products;
- proposed durable knowledge changes;
- conversation-native memory changes;
- review actions when persistence is uncertain, risky, conflicting, or
  batch-derived.

The user should be able to say or type in Hermes:

- "Use this knowledge base."
- "Ask over the selected annual reports."
- "Compare 2024 and 2025."
- "Create a brief."
- "Remember this."
- "That is wrong, change it to X."
- "Show why this answer is supported."
- "Resume when ingestion is ready."

Advanced controls such as embedding model, chunk method, wait flags, and parse
flags should not be first-class user decisions in the normal conversation flow.
They belong in component-native configuration, advanced PSKA settings, or
operator diagnostics.

## Component Reuse Matrix

| Product Area | Primary Owner | PSKA Treatment |
| --- | --- | --- |
| Chat, sessions, streaming | Hermes WebUI | Keep as daily entry |
| Tool-call display | Hermes WebUI | Reuse; expose PSKA MCP tools only |
| KB creation | PSKA Product API -> RAGFlow adapter | Hermes PSKA panel; RAGFlow UI remains admin fallback |
| PDF/document upload | PSKA Product API -> RAGFlow adapter | Upload once through Hermes/PSKA; RAGFlow owns parsing/indexing |
| OCR/parsing/chunking/embedding/indexing | RAGFlow | RAGFlow owns execution; PSKA shows readiness |
| Chunk inspection | RAGFlow | Link/admin view for deep inspection |
| Dataset/document readiness | PSKA | Native thin status from Product API |
| Agentic question loop | Hermes + PSKA | Hermes conversation drives PSKA ask/resume tools |
| Source-aware answer/work product | PSKA | Hermes artifact/panel backed by Product API |
| Export Markdown/JSON | PSKA | Hermes action/panel |
| Conversation memory correction | Hermes + PSKA | `pska_memory_change_from_conversation` |
| Durable memory proposal | PSKA | Product API/MCP; Review only for exception queue |
| Review/approval | PSKA | Hermes panel for pending exception items |
| Durable memory apply/update/delete | PSKA | Native workflow through adapters |
| Audit trail | PSKA | Hermes panel or local diagnostics |
| Hermes run UI | Hermes WebUI | Keep |
| Graphiti memory internals | Graphiti | Do not expose directly to agents; optional admin link only |
| Provider diagnostics | PSKA | Native normalized status |

## Hermes WebUI Navigation

Recommended PSKA additions inside Hermes WebUI:

1. **Chat**
   - Remains Hermes-native.
   - Shows PSKA tool calls, selected scope, readiness, retrieved sources, work
     product, and memory changes in the transcript.

2. **Knowledge**
   - Hermes/PSKA panel for datasets, upload, ingestion status, readiness, and
     ready-to-ask scopes.
   - Calls PSKA Product API only; PSKA routes to RAGFlow through adapters.

3. **Work Products**
   - Briefs, exports, source manifests, workflow artifacts.
   - Opened from conversation or workflow history.

4. **Review**
   - Exception inbox for uncertain, risky, conflicting, or batch-derived
     durable knowledge.
   - Ordinary user corrections stay in chat.

5. **Activity**
   - Cross-component PSKA audit trail.
   - Workflow, retrieval, source read, export, review, memory
     apply/update/delete, and component probe events.

6. **Components**
   - RAGFlow, Hermes, Graphiti, embedding provider, LLM provider status.
   - Links to native component consoles.
   - Product diagnostics, provider jobs, migration manifest, and capability
     contract.

7. **Settings**
   - Workspace policy, tenant/workspace context, provider configuration hints.
   - Not provider-native configuration when the provider already has UI.

## PSKA Panels And Diagnostics

PSKA should implement product panels inside Hermes WebUI, plus local diagnostics
for development and operators. These are not a second daily conversation
frontend.

### Knowledge Panel

Required behavior:

- create/list datasets through PSKA;
- upload files once through PSKA;
- show asynchronous ingestion, parsing, embedding, indexing, readiness, and
  failure reasons;
- start or resume Ask only when the selected scope is ready, or preserve the
  blocked workflow for later resume.

### Work Product Panel

Required behavior:

- show generated brief/artifact;
- show source manifest;
- export Markdown/JSON;
- show matched durable memory facts using PSKA `memory.search_view`;
- create durable memory review from selected transient result only when the user
  requests durable knowledge.

### Review Panel

Required behavior:

- show pending exception items;
- show supporting sources and traceability;
- accept, request changes, reject;
- apply accepted memory/graph/profile changes when supported;
- show lifecycle history.

### Activity And Component Panels

Required behavior:

- show normalized audit across PSKA workflows;
- show configured providers;
- show RAGFlow KB readiness summary;
- show provider jobs;
- show memory capability and search-view contract;
- show diagnostics and probes;
- provide links to component-native consoles.

## Embedded Or Linked Component Pages

PSKA should prefer component-native UI for these areas.

### RAGFlow Console

Use RAGFlow for:

- configuring embedding model
- parsing and chunking controls
- inspecting document progress
- inspecting chunks
- debugging RAGFlow-native retrieval

Hermes/PSKA should provide:

- "Open RAGFlow" admin link when needed
- current PSKA-known dataset readiness
- refresh/sync button
- selected dataset/document context
- warning when dataset exists but is not ready for Ask

### Hermes Console

If Hermes provides or later needs a UI, PSKA should not rebuild it from scratch
without product design. PSKA may embed or link it for:

- agent run timeline
- tool call inspection
- logs
- resume/continue controls

Hermes-native pages own chat/session experience. PSKA-backed panels own product
results: work products, review, audit, readiness, and durable knowledge
governance.

## Upload Flow After Redesign

The normal user flow should not ask for provider-specific fields first.

Preferred flow:

```text
Hermes WebUI Knowledge panel
  -> upload once through PSKA Product API
  -> PSKA RAGFlow adapter creates dataset/documents and starts provider jobs
  -> PSKA shows ingestion/readiness status
  -> Hermes chat uses ready dataset scope through PSKA Ask/MCP
```

Advanced fields are hidden by default:

- new knowledge base name
- embedding model
- chunk method
- parse flag
- wait flag

Defaults:

- embedding model empty: use provider/dataset default
- parse enabled
- wait disabled for large PDFs
- run closed loop only after readiness or as an explicit resumable workflow

## Implementation Boundary

Frontend code must still follow PSKA layer rules.

Allowed:

- Hermes WebUI PSKA panels call Hermes backend proxy routes or PSKA Product API
- Hermes WebUI links component-native UIs for admin/debug paths
- Embedded component UI calls its own backend inside its own app context
- PSKA Product API reads provider state through adapters

Not allowed:

- Hermes WebUI PSKA panels directly calling RAGFlow APIs
- Hermes WebUI PSKA panels directly calling Graphiti APIs
- Hermes WebUI PSKA panels scraping iframe DOM
- hardcoding RAGFlow response shapes into PSKA UI
- implementing provider configuration UI before checking whether provider UI
  already owns it

## Redesign Phases

### Phase 1: Hermes Shell Integration

- Keep Hermes chat, sessions, streaming, tool cards, and workspace surfaces.
- Add Hermes backend proxy routes to PSKA Product API.
- Configure Hermes MCP to expose PSKA tools only.
- Show PSKA health, capabilities, workspace status, and provider jobs.

### Phase 2: Knowledge And Ask Panels

- Add PSKA Knowledge panel for dataset creation, upload, ingestion status, and
  readiness.
- Start Ask from a selected ready scope.
- Preserve blocked Ask workflows and resume them after provider readiness.
- Show retrieved sources, inspected sources, memory facts, work products, and
  insufficient-context states without exposing provider-native payloads.

### Phase 3: Conversation Memory And Exception Review

- Route "remember/correct/forget" chat turns through
  `pska_memory_change_from_conversation`.
- Use `memory.search_view` for display text and superseded-fact behavior.
- Keep Review as an exception inbox for uncertain, risky, conflicting,
  ambiguous destructive, broad destructive, or batch-derived durable knowledge.

### Phase 4: Component Links And Operator Diagnostics

- Add RAGFlow and Graphiti admin links with fallback to new tab.
- Add component diagnostics, provider jobs, migration manifest, and audit views.
- Keep local PSKA diagnostic UI available for development smoke tests, not as
  the primary product workspace.

## Product Test

A redesigned frontend is successful when a user can understand PSKA as:

> A Hermes WebUI-based agent workspace that uses PSKA for governed knowledge
> workflows, RAGFlow for source evidence, Graphiti for temporal memory, and
> PSKA contracts for workflow closure, review, audit, and sourced work products.

It should not feel like a replacement RAGFlow UI or a second PSKA-owned chat
application.
