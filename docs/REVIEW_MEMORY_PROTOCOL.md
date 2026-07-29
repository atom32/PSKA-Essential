# PSKA Review And Memory Protocol

PSKA owns the review and memory lifecycle. External products may host a UI,
queue, database, or workflow runner, but they do not define the canonical PSKA
schema.

## Rules

- PSKA does not provide chat. Agent hosts call PSKA APIs, MCP tools, or skills.
- Retrieval and Ask flows are read-only unless an explicit memory flow is
  invoked.
- Durable memory create, update, and delete flows must pass through a review
  candidate and an auditable decision before provider write.
- Review UI is replaceable. SQLite, Busabase, GitHub, Label Studio, Argilla, or
  Hermes extensions are adapters, not the protocol source.
- Memory is optional for evidence retrieval. A failed memory provider must not
  block RAGFlow-backed evidence retrieval.

## Lifecycle

```text
EvidenceRef / ConversationRef
  -> ReviewCandidate
  -> ReviewDecision
  -> accepted ReviewBatch
  -> MemoryProvider.apply/update/delete
  -> AuditEvent
```

## Canonical Candidate

Current PSKA code represents candidates as `Proposal` plus optional durable
payload:

- `kind`: `memory_patch`, `memory_update`, `memory_delete`, `digest`,
  `writing_brief`
- `body`: human-readable candidate text or diff summary
- `source_refs`: evidence references required for durable memory writes
- `memory_patch`: create/upsert payload
- `memory_update`: replace payload with previous text and target id
- `memory_delete`: deactivation payload with target id and reason
- `metadata`: origin, triage, workspace, tenant, namespace, confidence, risk,
  conflict, review hints, and provider-neutral provenance

Provider adapters should preserve these PSKA fields even when their native
schema names differ.

## Review Status

The local PSKA status values are:

- `pending`: waiting for human or policy decision
- `accepted`: approved and eligible for durable memory apply
- `rejected`: closed without provider write
- `needs_edit`: requires a revised proposal

Adapters may map these to their own terms, for example `approve`,
`needs_revision`, issue labels, or pull request review states.

## Provider Contract

A ReviewProvider must support:

```text
create(proposal_id) -> ReviewBatch
list(status?, limit) -> ReviewCandidate[]
get(review_id) -> ReviewCandidate
decide(review_id, decision, reason) -> ReviewDecision
audit_events(target_id?) -> AuditEvent[]
```

A MemoryProvider must support:

```text
search(query, scope, limit) -> MemoryFact[]
apply(reviewed MemoryPatch) -> MemoryApplyResult
update(reviewed MemoryUpdate) -> MemoryApplyResult
delete(reviewed MemoryDelete) -> MemoryApplyResult
```

The default lightweight provider is SQLite. It stores reviewed memory facts,
versions, source refs, and metadata. It is deliberately not a graph engine,
document repository, vector index, or review UI.

## Adapter Positions

- `sqlite`: local durable baseline and tests.
- `graphiti`: optional graph memory provider when healthy.
- `busabase`: possible approval-first ReviewProvider adapter, not a core
  dependency.
- `github`: possible public/open-source ReviewProvider adapter for issue or PR
  based reviews. Avoid for private personal memory by default.
- `label_studio` and `argilla`: useful export targets for annotation, feedback,
  and eval datasets rather than daily memory governance.
