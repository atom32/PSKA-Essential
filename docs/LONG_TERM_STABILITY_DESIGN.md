# Long-Term Stability Design

This document turns the current PSKA product direction into operational design
rules. It focuses on temporal knowledge, review triage, RAGFlow/Graphiti
division of labor, context budgeting, background jobs, permissions, and
migration.

## Design Invariants

PSKA should preserve these invariants:

- Retrieval, answering, ingestion, and export must not write durable memory as
  a side effect.
- Durable memory, graph writes, updates, and deletes must pass through review or
  an explicit workspace governance policy.
- Source evidence stays in a KB provider such as RAGFlow.
- Reviewed temporal memory stays in a memory/graph provider such as Graphiti.
- PSKA owns canonical contract schemas, review records, audit records, workflow
  control state, workspace boundaries, and provenance validation rules.
- Provider data owns its own durable lineage metadata. PSKA must not become the
  authoritative store for raw documents, chunks, embeddings, extracted facts,
  graph nodes, graph edges, or provider-native mapping tables.
- Provider failure must be visible and actionable. No silent fake data, cached
  guesses, or hidden fallback providers.

For the cross-component data ownership model, see
[Metadata-First Bridge Design](METADATA_FIRST_BRIDGE_DESIGN.md).
For the daily memory user experience, see
[Conversation-Native Memory Design](CONVERSATION_NATIVE_MEMORY_DESIGN.md).

## Temporal Knowledge

PSKA already has the first layer of a temporal model:

- `WorkflowRun.created_at` and `WorkflowRun.updated_at`
- `Proposal.created_at`
- `ReviewBatch.created_at`
- `ReviewDecision.decided_at`
- `AuditEvent.created_at`
- `MemoryFact.valid_at` and `MemoryFact.invalid_at`
- `SourceRef.metadata`
- `MemoryPatch.confidence`

The next stable contract should make temporal semantics explicit instead of
hiding them inside provider payloads.

Recommended fields:

- `observed_at`: when the claim was observed in the source or conversation.
- `created_at`: when PSKA created the record.
- `updated_at`: when PSKA last changed the record.
- `valid_at`: when the fact became true, if known.
- `invalid_at`: when the fact stopped being true, if known.
- `source_published_at`: when the source document was published, if known.
- `source_ingested_at`: when the source entered PSKA/RAGFlow.
- `reviewed_at`: when a human or policy accepted/rejected the candidate.
- `applied_at`: when the accepted change reached the memory backend.

For conflict resolution, newer knowledge should receive a higher default
ranking, but recency must not blindly override evidence. Ranking should combine:

- source relevance;
- source reliability;
- review status;
- confidence;
- temporal freshness;
- whether the older fact has been explicitly invalidated;
- workspace policy;
- user override.

A practical first formula can be:

```text
rank = relevance
     + reviewed_bonus
     + confidence_bonus
     + recency_bonus
     + source_reliability_bonus
     - conflict_penalty
     - stale_penalty
```

The important point is policy shape, not the exact coefficients. A newer
unreviewed claim can outrank an older unreviewed claim, but it should not
silently replace an older reviewed fact. It should normally create a conflict
review.

Implemented v1 behavior: non-conversation memory candidates run a lightweight
memory conflict probe during proposal creation. The probe searches scoped
durable memory, records related fact excerpts and a conflict score in proposal
metadata, and writes a `memory.conflict_probe` audit event. PSKA does not store
these related facts as an authoritative index; they are review evidence for the
candidate.

Implemented v1 search behavior: conversation correction episodes can supersede
older facts at query time. When `pska_memory_search` sees a returned memory fact
with `target_fact_id` and an explicit update/correction strategy, it filters the
targeted older fact from the default result set and records the filtered IDs in
the `memory.search` audit event. This is a temporary view over provider-owned
data, not a PSKA-side supersession ledger; diagnostics can request
`include_superseded_memory=true`.

The same query-time memory view is used by conversation target resolution and
non-conversation conflict probes. This prevents an old fact that has already
been superseded by a returned correction episode from making later chat
corrections ambiguous or forcing batch/document-derived candidates into manual
Review as false conflicts.

## Review Triage

The review queue should contain candidates that are uncertain enough to need
judgment and important enough to be worth keeping.

Use these inputs:

- `importance`: will this change future behavior or decisions?
- `uncertainty`: is the extraction ambiguous, low-confidence, or indirect?
- `durability`: should this survive beyond the current session?
- `risk`: could the fact expose private, security, legal, or business-sensitive
  information?
- `conflict`: does it contradict existing memory?
- `source_quality`: is the source authoritative, recent, and traceable?
- `operation`: create, update, delete, or invalidate.

Initial routing policy:

```text
low importance + low uncertainty
  -> skip durable memory; keep source evidence in RAGFlow

low importance + high uncertainty
  -> discard or keep as transient workflow note

high importance + low uncertainty + low risk + no conflict
  -> allow auto_accept or auto_apply only if workspace policy permits

high importance + high uncertainty
  -> review

any non-conversation conflict, ambiguous delete/update, broad destructive
operation, policy-sensitive, or high-risk candidate
  -> review
```

This keeps the review queue small and meaningful. The user should not have to
approve every sentence in a document.

When conflict triage recommends review, PSKA may downgrade an `auto_accept` or
`auto_apply` workspace policy to `manual_review` for non-conversation durable
memory. Conversation-native user corrections keep their normal chat path unless
the caller explicitly sets `force_review`. A clear user instruction such as
"forget this specific memory" is governed and audited through conversation
memory; it is not routed to visible Review just because the operation is a
delete.

## RAGFlow And Graphiti Ownership

RAGFlow and Graphiti are intentionally not duplicates.

RAGFlow owns:

- raw document ingestion;
- OCR/parser/chunk pipeline;
- embeddings and indexes;
- source-grounded retrieval;
- document readiness and parse/index errors.

Graphiti owns:

- reviewed facts;
- temporal events;
- entities and relations;
- invalidations;
- compact memory useful across future sessions.

PSKA owns:

- the canonical source reference and provenance schemas;
- the workflow that turns source evidence into candidate knowledge;
- review gates;
- audit records;
- provider adapter translation;
- the decision about what should be projected from RAGFlow into Graphiti.

Not every document should create Graphiti knowledge. A document can be useful
only as retrievable evidence. Graphiti should receive facts first: concise,
evidence-linked, time-aware statements that matter later.

The source link for Graphiti knowledge should live with Graphiti episode data.
The intended chain is `Graphiti fact -> episode -> PSKA provenance envelope ->
upstream SourceRef -> RAGFlow source evidence`. PSKA may cache this resolution
for performance, but the cache is not authoritative.

## Context Budget And Top-N

Top-N should be computed from the model context budget, not hardcoded as a
single global number.

A typical budget should reserve tokens for:

- system and agent instructions;
- conversation history;
- task/question text;
- RAGFlow context packets;
- Graphiti memory facts;
- source citations;
- tool outputs;
- final answer margin.

Within the retrieval budget, PSKA should select by:

- relevance score;
- source diversity;
- recency;
- review status;
- confidence;
- conflict state;
- token size;
- dataset/document scope.

The result is a dynamic Top-N. A long-context model can carry more evidence,
while a smaller model should receive fewer, denser packets. PSKA should prefer
high-signal packets over simply increasing count.

Implemented v1 behavior: Ask, Digest, MCP, Product API, and upload-to-Ask loops
accept optional `model_context_tokens` and `model_profile`. When
`model_context_tokens` is present, PSKA computes a `pska.context_budget.v1`
record with effective retrieval, memory, source-inspection, and minimum-context
limits. The requested `limit` remains the caller's maximum; the model budget can
reduce effective Top-N for small-context models. The computed budget is persisted
in `ask_request`, returned in `loop.context_budget`, and added as a
`context.budget` loop step.

## Retrieval Loop And Subagents

RAG and graph retrieval do not have to run inside an independent subagent every
time. The default PSKA workflow should be a bounded, auditable retrieval loop:

```text
plan retrieval
  -> retrieve from scoped KB
  -> retrieve reviewed memory
  -> read missing KB evidence referenced by memory provenance
  -> inspect sources when needed
  -> decide whether context is sufficient
  -> produce transient output or durable candidate
```

The memory-provenance read is a query-time federation step. It does not write
new durable memory, graph facts, or PSKA mapping rows. It only turns Graphiti
fact `source_refs` into additional scoped context packets when the configured
retrieval adapter can read those upstream sources. The workflow records this as
`memory.source_federate` so operators can see when memory pulled source
evidence back into an Ask.

Use a separate retrieval subagent only for complex cases, such as:

- multi-hop investigation;
- large search spaces;
- cross-dataset comparison;
- source contradiction analysis;
- long-running research tasks.

Even then, the subagent must use PSKA tools only. It should return inspected
context, source refs, and a reasoning summary to the main workflow. It must not
write durable memory directly.

## Background Jobs

Provider-native queues remain the source of truth for provider work.

RAGFlow should remain responsible for:

- parse jobs;
- chunking;
- embedding;
- indexing;
- per-document readiness;
- provider-specific failure reasons.

Graphiti should remain responsible for:

- memory episode ingestion;
- entity and relation extraction;
- temporal graph maintenance;
- graph write failures.

PSKA should normalize and expose:

- job IDs when providers expose them;
- dataset and document readiness;
- provider component health;
- blocked reasons and next actions;
- resumable workflow IDs;
- audit events for PSKA-level transitions.
- a provider job status view for KB ingestion, document processing, digest
  jobs, and recent provider-level audit events.

The user-facing rule is simple: PSKA should never pretend ingestion or graph
write completion is instant. It should show "queued", "processing", "ready",
"blocked", or "failed" states with a next action.

Implemented v1 behavior: `pska_provider_jobs` and `GET /api/provider/jobs`
return `pska.provider_jobs.v1`, a normalized job inventory across KB
readiness/ingestion status, PSKA digest jobs, and recent KB provider audit
events. Workspace status includes a compact `jobs` summary and recent active
jobs. PSKA reports provider state but does not own provider-native queues.

## Agent Permissions

Start with soft constraints, but design them as stepping stones toward hard
permissions.

Soft constraints for v1:

- Hermes receives only PSKA MCP tools for PSKA workflows.
- Tool descriptions tell agents which actions are read-only, transient, or
  durable.
- `/api/capabilities` and `pska_capabilities_get` expose a soft tool-policy
  manifest with read/write, readiness, review, durable, and provider-write
  labels.
- Durable writes require review/apply tools.
- PSKA policy decides whether durable memory is manual review, auto accept, or
  auto apply.
- Product API and MCP responses expose readiness and capability limits.
- Audit records capture workflow, proposal, review, memory, and export actions.

Soft constraints are product controls, not a security boundary. They help the
agent behave correctly but do not replace authorization.

Harder future controls:

- API authentication;
- workspace and tenant ACLs;
- scoped tokens per agent;
- per-tool capability checks;
- read/write separation;
- human confirmation for sensitive actions;
- provider credentials isolated behind PSKA adapters;
- deny direct provider tools in managed Hermes configurations.

## Distributed Data And Migration

Distributed data is expected. PSKA should migrate by component case, with PSKA
contracts and provider-carried provenance as the bridge.

Migration cases:

- PSKA review/audit store: export workflows, proposals, reviews, memory apply
  records, audit events, workspace IDs, tenant IDs, and policy decisions.
- RAGFlow dataset migration: export dataset metadata and source files when
  possible, re-ingest into the target KB provider, and preserve or regenerate
  source refs and content hashes.
- Graphiti memory migration: export reviewed facts, entity/edge IDs, temporal
  fields, invalidation state, episodes, and embedded PSKA provenance, then
  import through the target memory adapter.
- Hermes migration: export session/config artifacts and MCP server config, then
  point Hermes at the target PSKA API/MCP server.
- Provider replacement: prefer provider-native export plus embedded provenance;
  replay accepted PSKA reviews only when the target provider cannot preserve the
  original graph episodes.

The durable migration unit should be the provider-owned object plus its PSKA
provenance envelope, not a PSKA-owned shadow row.

Implemented v1 behavior: `pska_migration_manifest` and
`GET /api/migration/manifest` return a scoped provider-owned migration manifest.
It lists PSKA control record counts/IDs, provider source refs, memory target
IDs, agent-host refs, exclusions, and the component-by-component migration
plan. It does not export raw documents, chunks, embeddings, graph nodes, graph
edges, Hermes messages, or artifact binaries.

## Near-Term Implementation Steps

1. Done for v1: memory candidates carry temporal metadata (`created_at`,
   `observed_at`, `applied_at` after apply), confidence, source count, and
   triage metadata.
2. Done for v1: proposal creation adds review triage as metadata. Conversation
   memory remains conversation-native by default; triage does not make Review a
   daily memory editor.
3. Done for v1: non-conversation memory candidates probe existing scoped memory
   and conflict triage can downgrade automatic durable writes to manual review.
4. Done for v1: model context tokens can tune effective Top-N for retrieval,
   memory search, source inspection, and minimum context count.
5. Done for v1: expose normalized provider job state through MCP, Product API,
   and workspace status.
6. Done for v1: expose a provider-owned migration manifest through MCP and
   Product API.
7. Done for v1: expose soft tool-policy constraints through capabilities; next
   add auth and scoped capability enforcement after the workflow contract
   stabilizes.
