# PSKA User Guide

This guide explains how PSKA should be used as a product today. It is written
from the intended v1 shape: Hermes WebUI is the daily user entry point, while
PSKA is the knowledge workflow and governance layer behind it.

For the current local runnable demo, read
[`DEMO_BASELINE_2026-08-03.zh.md`](DEMO_BASELINE_2026-08-03.zh.md) first. That
baseline uses Hermes WebUI, Eidolia, RAGFlow, SQLite memory, and SQLite review;
Graphiti is optional, not required for the demo.

## Product Shape

PSKA is not the main chat application. It is the control plane that makes
RAGFlow, the selected memory provider, review, audit, and agent tools behave
like one governed knowledge workflow.

The normal user path is:

```text
User
  -> Hermes WebUI
    -> Hermes runtime
      -> PSKA MCP tools and Product API
        -> RAGFlow for source evidence and retrieval
        -> selected memory provider for reviewed long-term memory
        -> PSKA review store and audit log
```

Use Hermes WebUI for daily work. Use RAGFlow and memory-provider native UIs only
when you are administering those providers directly. PSKA should not ship a
separate daily workspace frontend. Its Product API and MCP tools are consumed
by Hermes WebUI; any PSKA-local page is only for development diagnostics or
operator status, not for normal user workflows.

## Frontend Boundary

The product frontend is Hermes WebUI, with PSKA-specific panels and proxy
routes added inside that shell.

PSKA owns:

- Product API contracts;
- MCP tools;
- adapters;
- review, audit, readiness, and policy;
- optional local diagnostics for operators.

Hermes WebUI owns:

- chat;
- sessions;
- streaming;
- tool-call display;
- the Knowledge panel that calls PSKA through `/api/pska/*`;
- user-facing review and apply controls.

Do not build or rely on a second PSKA conversation frontend. The legacy local
page served by PSKA Product API can remain useful for smoke tests and debugging,
but it is not the v1 workspace.

## First-Run Checklist

Use the bundled startup wrapper when running on this local PSKA machine:

```bash
make start-workspace
```

It checks RAGFlow, the selected memory provider, PSKA Product API, and Hermes
WebUI; starts missing local services when a known startup path exists; then
opens Hermes WebUI.

1. Start the configured provider backends.
2. Start PSKA Product API with an explicit env file.
3. Start Hermes WebUI with PSKA proxy configuration.
4. Configure Hermes MCP to expose only the PSKA MCP server.
5. Open Hermes WebUI and verify the Knowledge panel shows provider health,
   workspace status, and PSKA MCP tool inventory.

The key rule is that Hermes must call PSKA, not RAGFlow or the memory provider directly.
Direct provider tools bypass PSKA's review gate, source trace, readiness, and
audit model.

## Daily Workflow

The common loop is:

```text
Create or select a workspace
  -> upload a document through the PSKA/Hermes Knowledge panel
  -> wait for provider readiness
  -> ask a scoped question
  -> inspect sources
  -> create a transient artifact or durable memory candidate
  -> review durable candidates
  -> apply accepted memory to the selected memory provider
  -> ask again with both RAG and reviewed memory available
```

This is intentionally not "upload once to every backend". A file should enter
the product through PSKA once. PSKA sends source documents to RAGFlow for
chunking, embedding, indexing, and source-grounded retrieval. The memory
provider receives only reviewed fact, event, entity, or relation projections
that are worth keeping as durable memory.

## Ingestion

Use the Knowledge panel or PSKA KB tools to create datasets and upload files.
Ingestion is asynchronous. A dataset can exist while its documents are still
parsing, chunking, embedding, or indexing.

Ask flows must treat these states differently:

- Dataset missing: create or select a dataset.
- Dataset exists but not ready: wait, inspect provider status, or resume later.
- Dataset ready: Ask can retrieve from the selected scope.
- Dataset blocked: surface the failing document or provider reason.

RAGFlow remains the source-evidence system. It owns raw documents, chunks,
embeddings, parser state, and retrieval over the document corpus. PSKA owns the
normalized readiness/status view and decides whether an agent is allowed to ask
over a scope.

Use `pska_provider_jobs` or `GET /api/provider/jobs` for a workspace-level job
view. It reports KB dataset/document ingestion, PSKA digest jobs, recent
provider-level events, phases, progress, failure reasons, and next actions. It
does not replace RAGFlow's or a memory provider's native job queues.

## From Documents To Memory Provider

Uploading a file does not write durable memory.

The upload path is:

```text
Hermes Knowledge panel or PSKA API
  -> PSKA KB adapter
  -> RAGFlow dataset/document ingest
  -> RAGFlow parsing, chunking, embedding, indexing
```

The selected memory provider receives data only through explicit durable-memory
paths:

- conversation memory: the user says remember/correct/forget in chat, Hermes
  decides whether this is an add, correction/update, delete/forget, or
  clarification, calls `pska_memory_change_from_conversation`, and PSKA applies
  a clear user-driven change under conversation policy;
- digest review: PSKA runs `pska_digest_scope` or a queued digest job over a
  ready RAGFlow scope, creates a compact sourced digest artifact, optionally
  creates an exception Review, and writes memory only after the Review is
  accepted and applied when policy requires review.

Review is not the normal memory editor. If a memory is wrong, correct it in the
Hermes conversation; PSKA keeps the internal proposal/decision/apply/audit trail
without making you approve routine corrections in a separate screen.

Digest jobs are lightweight PSKA workflow metadata, not a shadow copy of
RAGFlow chunks. `pska_provider_jobs` reports them as `pska_digest_job` entries
with `dataset_ids`, `document_ids`, `priority`, `attempt_count`, readiness, and
`data_flow.writes_memory_directly=false`. Running a digest job may create a
candidate Review; it does not write memory as a side effect of ingestion.
In Hermes WebUI, use the PSKA Knowledge panel's Digest card to queue this job
explicitly. The Jobs card then shows the queued job and can run it.

Hermes WebUI also shows a Memory inflow card from
`/api/pska/capabilities -> memory.inflow`. Use it as the runtime answer to
"when will durable memory receive data?": upload alone will not do it; only
conversation memory, digest job review/application, or workflow memory promotion
can move governed projections into the memory provider.

This keeps the ownership rule intact: RAGFlow stores source evidence and
chunks; the memory provider stores compact reviewed temporal memory; PSKA stores
contracts, workflow state, audit, and provider-carried provenance metadata.

For lineage, check `/api/pska/capabilities -> memory.lineage`. The expected
contract is `pska.memory_lineage.v1`: Graphiti or another memory provider owns
the durable fact-to-source metadata, while PSKA resolves it at query time and
returns `source_refs`. If the provider cannot expose that lineage, PSKA reports
`lineage_status=unresolved` instead of inventing a shadow mapping.

## Asking

Ask from Hermes WebUI through PSKA tools or the Hermes `/api/pska/*` proxy to
PSKA Product API. The selected dataset scope should be explicit. PSKA should
return:

- retrieved context packets;
- reviewed memory facts;
- KB source context federated from memory provenance when available;
- source references;
- source inspection details when requested;
- a proposal or transient artifact when context is sufficient;
- an insufficient-context response when the selected scope cannot answer.

An answer must stay scoped to the selected datasets and reviewed memory. If the
context is insufficient, the workflow should say so instead of producing a
generic answer.

Memory provenance federation is read-only. It lets a Graphiti fact point PSKA
back to RAGFlow evidence during Ask, but it does not write new memory or create
a PSKA-side fact mapping table.

Ask can accept `model_context_tokens` and `model_profile`. When
`model_context_tokens` is set, PSKA computes effective Top-N limits for
retrieval, memory search, and source inspection, then returns the decision in
`loop.context_budget`. The original `limit` remains the caller's requested
maximum.

## Proposal Kinds

Use transient proposals for work products and durable proposals for long-term
knowledge.

- `writing_brief`: a sourced work product. It does not become long-term memory
  by default and has no memory apply action.
- `digest`: a sourced summary or synthesis. It is normally transient unless a
  later explicit memory review is created from it.
- `memory_patch`: a candidate new fact, preference, event, entity, or relation
  that may enter long-term memory after review.
- `memory_update`: a reviewed correction to an existing memory fact.
- `memory_delete`: a reviewed invalidation or removal of an existing memory
  fact or edge.

Use durable proposal kinds only when the candidate knowledge is meant to
influence future agent behavior.

## Conversation Memory

Daily memory management happens in chat, not in the Review queue.

When the user says "remember this", "that is wrong", or "forget that", Hermes
should call `pska_memory_change_from_conversation`. PSKA can auto-apply clear
conversation changes under workspace policy while still preserving proposal,
review-decision, apply, and audit records internally.

If Hermes asks PSKA to correct or forget something but does not pass an existing
`memory_fact`, PSKA tries to resolve the target from the selected memory scope.
If it cannot find one clear target, the response is `status="needs_target"` with
a suggested `pska_memory_search` next action. Hermes should search or ask the
user a clarifying question, then retry with the selected `memory_fact`. PSKA
must not turn "forget X" into a newly stored memory just because the target was
missing.

If the selected memory backend cannot update facts transactionally, a clear
conversation correction may still be applied as an explicit correction episode.
For Graphiti this appears as `operation="memory_update"` with
`proposal_operation="memory_patch"` and
`memory_update_strategy="append_correction_episode"`. The old fact is not
rewritten in place; the new temporal episode tells future retrieval that the
user corrected it. This path is available only when the memory backend advertises
`append_correction_episode` in `conversation_update_strategies`; otherwise PSKA
fails the unsupported update explicitly.
The correction episode text includes the current fact, previous fact, and
superseded target ID, so searches using either old or new terms can retrieve the
correction without PSKA maintaining a separate index. Agent-facing proposals,
briefs, and exports use `metadata.display_text` or `metadata.current_text` so
the user sees the clean current fact rather than the internal correction episode
format.

Default memory search hides older facts that are superseded by a returned
correction episode. This happens only within the current search result using
provider-carried metadata such as `target_fact_id`; PSKA does not keep a central
supersession ledger. Diagnostics can include older facts by passing
`include_superseded_memory=true` in the memory scope.

## Review

The review queue should contain knowledge that is both important and not
certain enough to write automatically. Review is an exception inbox, not a
daily memory editor, and it is not a dumping ground for every retrieved
sentence.

Good review candidates include:

- user preferences, identity facts, commitments, or policies;
- facts that would materially change future answers;
- facts that conflict with existing memory;
- facts extracted from weak, indirect, or ambiguous evidence;
- facts whose source is trusted but whose interpretation is uncertain;
- broad destructive operations, ambiguous delete/update operations, or
  high-risk durable memory changes.

Poor review candidates include:

- low-importance trivia;
- one-off document details that are already retrievable from RAGFlow;
- unsourced claims;
- generic summaries that do not change future behavior;
- highly confident transient work products;
- clear user-driven corrections such as "that is wrong, change it to X".

Accepted durable reviews can be applied to the configured memory backend.
Rejected reviews close the candidate. `needs_edit` reviews should produce a new
revised candidate while preserving lineage to the original.

For non-conversation memory candidates, PSKA probes existing scoped memory
before durable write. If a candidate may conflict with an existing fact, PSKA
records the probe in proposal metadata and can require pending Review even when
the workspace durable-memory policy is `auto_apply`. This prevents batch or
document-derived knowledge from silently replacing older memory.

## Graphiti Memory

Graphiti is for reviewed temporal memory, not for mirroring every document.

Store these kinds of projections in Graphiti:

- durable facts;
- user preferences;
- entity relations;
- events with time meaning;
- corrected or invalidated facts;
- high-value patterns learned across multiple interactions.

Do not store every chunk, paragraph, or extracted note. RAGFlow already handles
document retrieval. Graphiti should hold a compact, governed graph that helps
future agents reason across time.

Graphiti reviewed update reviews are disabled until Graphiti exposes a
transactional fact update endpoint compatible with PSKA. Conversation-native
corrections are different: PSKA can append a correction episode with target
metadata and provenance, preserving Graphiti's temporal model without hiding an
unsupported backend operation.
Lifecycle lookup follows that target metadata. Inspecting the old fact ID can
show a later correction episode that superseded it, even though the provider
write target is the new Graphiti episode.

## Migration Manifest

Use `pska_migration_manifest` or `GET /api/migration/manifest` to inspect how a
workspace should migrate by component. The manifest lists PSKA control records,
provider source refs, memory target IDs, agent-host refs, exclusions, and a
migration plan. It is not a data export: raw documents, chunks, embeddings,
graph nodes, graph edges, Hermes messages, and artifact binaries stay with
their owning providers.

## Admin And Troubleshooting

If Hermes WebUI does not show PSKA tools, reload MCP in Hermes and verify the
PSKA MCP server starts with the correct env file.

If Ask returns no useful answer, check:

- selected dataset IDs and names;
- dataset readiness;
- embedding provider configuration in RAGFlow;
- RAGFlow document parse/index status;
- Graphiti memory probe status;
- PSKA workspace and tenant IDs;
- pending reviews and accepted reviews waiting for apply.

If memory does not influence later answers, verify that the review was accepted
and applied, not merely created. Durable memory changes are intentionally not
side effects of retrieval, answering, ingestion, or export.

For daily corrections, use conversation. Tell Hermes "remember this", "that was
wrong", or "forget that"; Hermes should call PSKA's conversation-native memory
tool/API. Pending Review is for batch-derived, non-conversation, policy-governed,
or explicitly requested memory checks, not for every normal correction.
