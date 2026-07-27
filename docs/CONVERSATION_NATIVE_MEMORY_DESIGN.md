# Conversation-Native Memory Design

This document defines how PSKA should move knowledge from daily Hermes
conversation into Graphiti without making the Review queue a normal user
workflow.

## Decision

Review remains a governance mechanism, but not the ordinary user experience.

The normal user action is conversation:

```text
User: remember this
User: that is wrong
User: forget that
User: only use that in this project
```

Hermes decides whether the user is asking to add, clarify, update, or delete a
memory. Hermes then calls PSKA. PSKA governs the change, writes audit records,
and calls the memory adapter only through accepted policy.

This creates two separate meanings of "review":

- visible Review UI: an exception inbox for uncertain, risky, conflicting,
  broad destructive, ambiguous destructive, or batch-derived changes;
- internal governance records: proposal, decision, memory apply, and audit
  entries that PSKA may create even when a clear conversation correction is
  auto-accepted and auto-applied.

The first should not be a common user workflow. The second is the ledger that
keeps conversation-native memory changes traceable.

## Upload-To-Graphiti Data Flow

Uploading a document does not immediately write to Graphiti.

```text
Hermes WebUI upload
  -> PSKA ingest API
    -> RAGFlow document, chunks, embeddings, index jobs
      -> RAGFlow scope becomes ready
        -> optional PSKA digest job
          -> candidate facts/events/entities/relations
            -> review only for uncertain, important, risky, or conflicting items
              -> Graphiti episode with upstream RAGFlow provenance
```

RAGFlow is the evidence system. Graphiti is the compact temporal memory system.
Graphiti should not mirror every chunk.

## Graphiti Inflow Sources

Graphiti can receive data from three places:

1. Conversation-native memory operations.
   The user explicitly corrects, remembers, or forgets something in chat.

2. Question-answer memory extraction.
   A sourced Ask result can produce candidate facts based on what the user
   actually asked and what PSKA inspected.

3. Background digest jobs.
   After RAGFlow marks a document ready, PSKA may run low-priority digest over
   selected source ranges. Digest produces candidates, not direct graph writes.

The v1 implementation exposes this as an explicit `pska_digest_scope` tool and
`POST /api/digest` route. It is intentionally not a hidden ingestion side
effect. The caller selects a ready dataset/document scope; PSKA creates a
sourced digest workflow, and only `create_memory_review=true` turns that digest
into a governed memory candidate.

For scheduled or deferred digest work, v1 also exposes explicit digest job
tools/routes. They enqueue workflow metadata, check provider readiness at run
time, and mark jobs as `waiting` instead of creating fake digest output when
RAGFlow is still parsing, chunking, embedding, or indexing.

Conversation-native operations are the default daily path. Digest is batch
processing and should be conservative.

PSKA exposes this as a machine-readable contract at
`/api/capabilities -> capabilities.memory.inflow` and through
`pska_capabilities_get`. The contract schema is `pska.memory_inflow.v1`.
It says explicitly:

- upload enters the KB provider once and does not write the memory provider;
- conversation memory is the primary user path;
- digest jobs require a ready KB scope and create artifacts or exception
  Reviews, not direct memory writes;
- sourced workflow promotion uses `/api/workflows/{run_id}/memory-review` and
  writes only after governance.

Lineage is exposed separately as
`/api/capabilities -> capabilities.memory.lineage` with schema
`pska.memory_lineage.v1`. It declares that Graphiti or another memory provider
must carry authoritative fact-to-source provenance on provider-owned objects,
while PSKA only resolves that provenance into `SourceRef` values at query time.

## Review Queue Role

Review queue is an exception inbox, not a daily dashboard.

Create pending review for:

- batch digest candidates with high value but uncertain extraction;
- conflicts between existing memory and new evidence;
- broad destructive operations, or destructive operations where the target or
  user intent is ambiguous;
- high-risk privacy, security, legal, or enterprise-governed memory;
- low-confidence important claims extracted from documents, digests, or other
  non-conversation workflows;
- operations explicitly marked `force_review`.

Do not require pending review for:

- a user saying "remember this" in the active conversation;
- a user correcting an existing memory with clear replacement text;
- a user saying "forget this" for a specific memory fact;
- a low-confidence conversational inference that can be corrected by the user
  in a later turn;
- low-risk, scoped clarification where workspace policy allows auto apply.

Even when no pending review remains, PSKA still creates proposal, review
decision, memory apply, and audit records. The difference is that conversation
policy can auto-accept and auto-apply them.

## Policy Defaults

Default v1 policy:

```text
PSKA_GOVERNANCE_DURABLE_MEMORY=manual_review
PSKA_GOVERNANCE_DIGEST_MEMORY=manual_review
PSKA_GOVERNANCE_CONVERSATION_MEMORY=auto_apply
```

This preserves the old explicit durable-memory review flow while making daily
conversation corrections lightweight.

## Conversation Tool Contract

Hermes should call:

```text
pska_memory_change_from_conversation(...)
```

The tool accepts:

- `user_message`: the user's natural-language instruction;
- `operation`: `auto`, `remember`, `clarify`, `correct`, `update`, `forget`, or
  `delete`;
- `text`: normalized durable memory text when the agent can extract it;
- `memory_fact`: existing fact when correcting or deleting;
- `source_refs`: optional supporting RAGFlow or artifact sources;
- `session_id` and `message_id`: Hermes source coordinates;
- `force_review`: true only when the user, workspace policy, or agent host
  explicitly wants a visible review item.

PSKA turns this into a governed durable proposal. A conversation source ref is
always attached, so even a correction of a fact with missing provider lineage
has an auditable source.

When `operation` is `auto` and the user clearly says "forget/delete/remove",
PSKA treats the request as `memory_delete` even if Hermes did not pass a
`memory_fact`. When `operation` is `correct/update/delete/forget` and
`memory_fact` is missing, PSKA searches the selected memory scope and returns a
target resolution result:

- `resolved`: PSKA found one clear existing memory and can update/delete it.
- `provided`: Hermes passed the target memory explicitly.
- `not_found`: PSKA found no plausible target.
- `ambiguous`: PSKA found multiple equally plausible targets.

`not_found` and `ambiguous` return `status="needs_target"` with a suggested
`pska_memory_search` next action. They do not create a Review item and they do
not convert the instruction into a new memory. Hermes should search, ask a
clarifying question if needed, then retry with `memory_fact`.
Target resolution uses PSKA's default memory search view, so already-superseded
older facts do not create false ambiguity when a newer correction episode points
to them.

Some memory providers are temporal rather than transactional. Graphiti can add
new reviewed episodes and delete reviewed entity edges, but does not currently
provide a PSKA-compatible transactional fact update endpoint. For conversation
corrections against Graphiti, PSKA keeps the semantic operation as
`memory_update` but writes a `memory_patch` correction episode with
`memory_update_strategy="append_correction_episode"`, `target_fact_id`, and
`previous_text` metadata. It also stores `current_text` and `display_text` so
agent-facing proposals, briefs, and exports can show the clean current fact
while the raw episode remains searchable. The correction episode body includes
the current fact, the previous fact, and the superseded target ID so searches
for either old or new terms can retrieve the correction relationship from
Graphiti itself. This is an explicit provider strategy, not a silent fallback:
ordinary durable update reviews still fail before creating dead Review items
when the selected memory backend reports no update support.

## Agent Behavior

Hermes should not ask the user to open Review for ordinary corrections.

Good interaction:

```text
User: 不对，我的主力机不是 ThinkPad，是 Framework。
Agent:
  -> search relevant memory
  -> call pska_memory_change_from_conversation(operation="correct", ...)
  -> answer: 已更新。
```

When the target or intent is unclear, Hermes should search memory or ask a
clarifying question. It should not create a Review item just because it failed
to identify the target memory.

When the agent is unsure:

```text
User: 这条可能以后有用，你看着办。
Agent:
  -> call pska_memory_change_from_conversation(force_review=true, ...)
  -> answer: 我先放到待确认里。
```

## Non-Goals

- Do not expose direct Graphiti add/update/delete tools to Hermes.
- Do not make Graphiti ingest every RAGFlow chunk.
- Do not treat Review queue as the primary memory management UI.
- Do not silently convert unsupported update/delete into a new add. If the
  backend cannot perform the selected operation, PSKA must fail explicitly
  unless the conversation-memory contract reports an explicit provider strategy
  such as `append_correction_episode`.
