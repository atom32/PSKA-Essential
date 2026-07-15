# PSKA Frontend Redesign

This document defines the intended PSKA frontend model after the first working
closed loop exposed a product mismatch: the current frontend behaves too much
like an engineering console. PSKA should be a conversation-first knowledge
workspace that wraps mature components instead of replacing them.

## Core Principle

PSKA does not reimplement mature frontend or backend components when an existing
component already owns the job well.

PSKA builds native frontend only for product responsibilities that existing
components do not provide:

- PSKA-controlled agentic question workflows
- scoped source-aware work products
- transient-to-durable knowledge governance
- review and approval
- audit and traceability across components
- workspace policy and provider-neutral status
- MCP/Hermes workflow handoff

Everything else should be linked, embedded, or surfaced through the component
that already owns it.

## Definition: "PSKA Wraps Components"

"PSKA wraps components" means PSKA provides a unified product shell around
specialized systems.

The shell owns:

- global navigation
- workspace identity
- visual theme and layout frame
- component health/status
- selected workspace/dataset/document context
- links or embeds to external component UIs
- PSKA-native workflow pages
- audit, review, and product policy

The shell does not own:

- the internal UI state of RAGFlow
- the internal UI state of Hermes
- the internal UI state of Graphiti or future memory systems
- provider-native forms, dashboards, and configuration screens
- direct calls from PSKA frontend to provider APIs

If a component is embedded by iframe, the embedded app may call its own backend
inside the iframe. The PSKA shell must not depend on provider DOM structure,
scrape provider state, or call provider APIs directly. PSKA synchronizes through
its own Product API and adapter contracts.

If a component blocks iframe embedding through browser security policy, PSKA
opens it in a new tab or separate window and keeps a visible "refresh status"
action in the shell.

## Conversation-First Product Model

The primary PSKA experience should be a conversation workspace, not a form
dashboard.

The main screen should center on:

- a conversation thread
- selected knowledge scope
- current workflow state
- retrieved sources
- generated work product
- proposed durable knowledge changes
- review actions when persistence is requested

The user should be able to say or type:

- "Use this knowledge base."
- "Ask over the selected annual reports."
- "Compare 2024 and 2025."
- "Create a brief."
- "Turn this into governed memory."
- "Show why this answer is supported."
- "Resume when ingestion is ready."

Advanced controls such as embedding model, chunk method, wait flags, and parse
flags should not be first-class user decisions in the normal conversation flow.
They belong in component-native configuration or advanced settings.

## Component Reuse Matrix

| Product Area | Primary Owner | PSKA Treatment |
| --- | --- | --- |
| KB creation | RAGFlow | Embed/link RAGFlow page |
| PDF/document upload | RAGFlow | Embed/link RAGFlow page; PSKA syncs status |
| OCR/parsing/chunking/embedding/indexing | RAGFlow | RAGFlow owns execution; PSKA shows readiness |
| Chunk inspection | RAGFlow | Embed/link for full inspection |
| Dataset/document readiness | PSKA | Native thin status from Product API |
| Agentic question loop | PSKA | Native conversation workflow |
| Source-aware answer/work product | PSKA | Native conversation + writing surface |
| Export Markdown/JSON | PSKA | Native |
| Durable memory proposal | PSKA | Native |
| Review/approval | PSKA | Native |
| Durable memory apply/update/delete | PSKA | Native workflow through adapters |
| Audit trail | PSKA | Native |
| Hermes run UI | Hermes or borrowed OSS patterns | Embed/link if available; PSKA shows workflow summary |
| Graphiti memory internals | Graphiti | Do not expose directly to agents; optional admin link only |
| Provider diagnostics | PSKA | Native normalized status |

## Revised Navigation

Recommended top-level navigation:

1. **对话**
   - Primary PSKA screen.
   - Conversation-first Ask loop.
   - Scope chips, readiness, retrieved sources, work product, review prompts.

2. **工作产物**
   - Briefs, exports, source manifests, workflow artifacts.
   - Can be opened from conversation.

3. **审核**
   - Durable knowledge review queue.
   - Accept, request changes, reject, apply.

4. **活动**
   - Cross-component audit trail.
   - Workflow, retrieval, export, review, memory events.

5. **知识库**
   - PSKA status summary plus embedded/linked RAGFlow KB console.
   - Not a reimplementation of RAGFlow upload/config screens.

6. **组件**
   - RAGFlow, Hermes, Graphiti, embedding provider, LLM provider status.
   - Links to native component consoles.
   - Product diagnostics and capability contract.

7. **设置**
   - Workspace policy, tenant/workspace context, provider configuration hints.
   - Not provider-native configuration when the provider already has UI.

## Native PSKA Pages

PSKA should implement these pages because they express PSKA-only product
semantics.

### Conversation

Native page.

Required behavior:

- select or inherit knowledge scope
- show readiness before retrieval
- start and resume agentic question workflows
- show loop state without exposing provider internals
- show retrieved sources and insufficient-context states
- generate transient sourced work products
- offer review creation only when user wants durable knowledge
- keep conversation history tied to workflow runs

### Work Products

Native page.

Required behavior:

- show generated brief/artifact
- show source manifest
- export Markdown/JSON
- show matched durable memory facts
- create durable memory review from selected transient result

### Review

Native page.

Required behavior:

- show pending durable semantic objects
- show supporting sources
- accept, request changes, reject
- apply accepted memory/graph/profile changes when supported
- show lifecycle history

### Activity

Native page.

Required behavior:

- show normalized audit across PSKA workflows
- include retrieval, source read, export, review, memory apply/update/delete,
  and component probe events
- filter by action/workflow/review when needed

### Component Status

Native thin page.

Required behavior:

- show configured providers
- show RAGFlow KB readiness summary
- show memory capability contract
- show diagnostics and probes
- provide links/embeds to component-native consoles

## Embedded Or Linked Component Pages

PSKA should prefer component-native UI for these areas.

### RAGFlow Console

Use RAGFlow for:

- creating datasets
- uploading PDFs and documents
- configuring embedding model
- parsing and chunking controls
- inspecting document progress
- inspecting chunks
- debugging RAGFlow-native retrieval

PSKA shell should provide:

- "Open RAGFlow" or embedded RAGFlow frame
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

PSKA-native pages still own the product result: conversation state, work
product, review, audit, and durable knowledge governance.

## Upload Flow After Redesign

The normal user flow should not ask for provider-specific fields first.

Preferred flow:

```text
Knowledge page
  -> open/embedded RAGFlow console
  -> user creates dataset or uploads files in RAGFlow
  -> return to PSKA shell
  -> click refresh/sync
  -> PSKA shows dataset readiness
  -> Conversation page uses ready dataset scope
```

Optional PSKA quick-upload can exist, but it must be simplified:

- select existing knowledge base
- choose files
- upload

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

- PSKA shell calls Product API
- PSKA shell embeds or links component-native UIs
- Embedded component UI calls its own backend inside its own app context
- PSKA Product API reads provider state through adapters

Not allowed:

- PSKA frontend directly calling RAGFlow APIs
- PSKA frontend directly calling Graphiti APIs
- PSKA frontend scraping iframe DOM
- hardcoding RAGFlow response shapes into PSKA UI
- implementing provider configuration UI before checking whether provider UI
  already owns it

## Redesign Phases

### Phase 1: Product Shell

- Replace current engineering-console navigation with a unified shell.
- Add component links/embeds page.
- Move RAGFlow-heavy KB operations out of the primary PSKA form.
- Keep PSKA readiness status visible.

### Phase 2: Conversation-First Ask

- Make conversation the default landing page.
- Convert current Ask form into contextual controls around a thread.
- Show scope, readiness, loop state, sources, and work product in one flow.

### Phase 3: Review And Work Product Polish

- Keep Review and Work Products native.
- Make durable knowledge governance clear but not obstructive.
- Make source traceability visible without making every transient output feel
  like a compliance form.

### Phase 4: Component Console Integration

- Add RAGFlow iframe/link with fallback to new tab.
- Add Hermes console link/embed when available.
- Add component health and sync status.

## Product Test

A redesigned frontend is successful when a user can understand PSKA as:

> A conversation-first knowledge workspace that uses RAGFlow for knowledge base
> operations, Hermes for agent execution, and PSKA for workflow closure,
> governance, review, audit, and sourced work products.

It should not feel like a replacement RAGFlow UI.
