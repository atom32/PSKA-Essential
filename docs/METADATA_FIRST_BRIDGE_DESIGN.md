# Metadata-First Bridge Design

This document freezes the PSKA design decision for cross-component data
ownership and provenance. It exists because PSKA should connect RAGFlow,
Graphiti, Hermes, and future systems without becoming a second data warehouse or
an authoritative cross-component index.

## Decision

PSKA is a metadata-first bridge and control layer.

PSKA owns:

- stable public contracts;
- provider adapter translation;
- workflow, review, policy, and audit control records;
- query-time orchestration across providers;
- validation rules for cross-component provenance metadata.

PSKA does not own:

- raw documents;
- chunks;
- embeddings;
- extracted facts;
- graph nodes or edges;
- provider-native durable data.

The durable knowledge objects live in their natural component. RAGFlow owns
source evidence. Graphiti owns temporal memory and graph facts. Hermes owns
sessions and agent turns. PSKA defines the metadata envelope that lets those
objects refer to each other.

## Core Principle

Cross-component lineage travels with the data object that was created.

This means:

- RAGFlow documents and chunks should expose stable source coordinates.
- Graphiti episodes created from reviewed PSKA memory must carry upstream
  source references.
- Hermes messages used as memory sources must be referenced by session and
  message IDs.
- Ingest worker outputs must reference the job and upstream objects that
  produced them.
- PSKA may keep review and audit traces for governance, but those traces are not
  the authoritative place where provider data lineage lives.

If a PSKA derived cache is deleted, RAGFlow source evidence and Graphiti memory
should still be able to describe how a graph fact was produced.

## Component Ownership

| Component | Owns durable data | Must carry PSKA-facing metadata |
| --- | --- | --- |
| RAGFlow | documents, chunks, embeddings, indexes, retrieval coordinates | dataset, document, chunk, content hash, title, published/ingested time where available |
| Graphiti | episodes, entities, facts, relations, valid/invalid time | tenant/workspace/group, episode ID, upstream source refs, review/apply context |
| Hermes | sessions, messages, tool calls, artifacts | session ID, message ID, selected PSKA scope, tool run IDs |
| Local folders / Obsidian | user-owned files, Markdown notes, attachments, tags, links, comments | root ID, path, content hash, section coordinates, source permission mode |
| PSKA | workflows, proposals, reviews, audit, policy decisions | normalized contracts and transient orchestration state |

PSKA control records are allowed because they describe PSKA decisions. They must
not be treated as the canonical storage location for provider data.

For the personal knowledge architecture, local folders and Obsidian vaults are
source providers, not memory providers. PSKA may keep a metadata ledger, FTS
index, tags, comments, duplicate reports, and saved searches for those sources,
but the canonical file content remains in the user-owned folder or vault.
Sidecar annotations under `.pska/` and governed Obsidian MOC marker blocks are
source-management metadata owned by PSKA's proposal/apply policy; they are not a
license for PSKA or Hermes to rewrite arbitrary user content. See
`PERSONAL_KNOWLEDGE_ARCHITECTURE.zh.md` for the To C source-management design.

## Provenance Envelope

All cross-component references should use a small provider-neutral envelope
inside provider metadata where the provider supports it.

```json
{
  "pska": {
    "schema": "pska.provenance.v1",
    "tenant_id": "tenant_default",
    "workspace_id": "default",
    "namespace": "pska-essential_workspace_default",
    "object_role": "derived_memory",
    "created_by": {
      "component": "pska",
      "agent_host": "hermes",
      "agent_id": "optional"
    },
    "process": {
      "workflow_id": "run_...",
      "proposal_id": "proposal_...",
      "review_id": "review_...",
      "policy_version": "manual_review"
    },
    "upstreams": [
      {
        "component": "ragflow",
        "object_type": "chunk",
        "dataset_id": "dataset_id",
        "document_id": "document_id",
        "chunk_id": "chunk_id",
        "title": "source title",
        "content_hash": "sha256:..."
      }
    ],
    "timestamps": {
      "observed_at": "2026-07-20T00:00:00Z",
      "created_at": "2026-07-20T00:00:00Z",
      "reviewed_at": "2026-07-20T00:00:00Z",
      "applied_at": "2026-07-20T00:00:00Z"
    }
  }
}
```

The exact provider field name may differ. The contract is the content and
semantics of the `pska` envelope.

## Graphiti Data Source Problem

The Graphiti source problem is this:

Graphiti search returns facts, but a fact is not useful to PSKA unless PSKA can
explain where that fact came from. The source cannot be inferred from dataset
names or from a PSKA-side ledger. It must be recoverable from Graphiti's own
episode lineage.

The target chain is:

```text
Graphiti fact
  -> Graphiti episode UUIDs
    -> episode PSKA provenance envelope
      -> upstream SourceRef
        -> RAGFlow read_source / retrieve-by-source
```

The implementation should follow these rules:

1. PSKA creates memory candidates from retrieved `ContextPacket.source_ref`
   values, Hermes message refs, or worker artifact refs.
2. Review accepts, rejects, or revises the candidate. Durable graph writes are
   still impossible before review or explicit workspace policy approval.
3. `MemoryPort.apply` sends the reviewed memory patch to Graphiti as an episode.
4. The Graphiti episode carries the PSKA provenance envelope.
5. Later `MemoryPort.search` returns `MemoryFact` values with either resolved
   `source_refs` or explicit metadata saying that provenance resolution was not
   available from the provider.
6. Query-time federation can use Graphiti source refs to fetch missing RAGFlow
   evidence, dedupe source packets, and give Hermes a merged context.

## Graphiti Write Compatibility

Ideal path:

- Graphiti exposes structured episode metadata.
- PSKA writes the provenance envelope into that metadata field.
- Graphiti fact search can expose fact episode UUIDs.
- PSKA adapter resolves those episode UUIDs and reads episode metadata.

Compatibility path for the current local Graphiti HTTP service:

- The current message API visibly accepts `source_description` and episode body,
  but not a dedicated metadata payload in the inspected route.
- PSKA should first try to encode a compact machine-readable provenance block in
  the episode source description.
- If the provider only preserves episode body, PSKA may put the provenance block
  in the body with clear delimiters.
- The graph extraction prompt should be instructed to treat the provenance block
  as metadata, not as factual domain content.
- The adapter should parse the block when reading episodes.

Example compatibility block:

```text
PSKA_PROVENANCE_JSON: {"schema":"pska.provenance.v1","upstreams":[...]}
```

This is less elegant than provider-native metadata, but it still keeps the
lineage inside Graphiti-owned episode data instead of PSKA maintaining a shadow
fact table.

Current implementation status:

- The local Graphiti adapter writes the PSKA provenance envelope into applied
  Graphiti episode `source_description` values.
- `/api/capabilities` and `pska_capabilities_get` expose
  `capabilities.memory.lineage` (`pska.memory_lineage.v1`), declaring that
  memory-provider object metadata is the authoritative lineage store and PSKA
  does not own an authoritative provider mapping table.
- RAGFlow retrieval source refs include stable provider coordinates and a
  `content_hash`.
- Graphiti client search can resolve fact episode UUIDs back into upstream
  `MemoryFact.source_refs` when the provider exposes episode links and episode
  metadata.
- Graphiti HTTP/client search can also resolve provenance carried directly on
  returned fact or edge metadata/source descriptions. This covers providers that
  surface the PSKA provenance envelope with the fact rather than through a
  separate episode lookup.
- Graphiti HTTP search may return facts without episode UUIDs. In that case
  PSKA returns an empty `source_refs` list and `lineage_status: unresolved`
  instead of inventing a source mapping.
- Ask now performs first-pass query-time federation: when memory facts contain
  readable upstream source refs, PSKA reads missing KB evidence through the
  configured retrieval adapter, appends it as federated context, and records a
  `memory.source_federate` audit event.
- Remaining federation improvements are ranking, token-budget-aware selection,
  multi-hop graph expansion, and provider-specific targeted retrieval beyond
  `read_source`.

## RAGFlow Source Coordinates

RAGFlow remains the upstream evidence system for document-derived memory.

The RAGFlow adapter must expose enough `SourceRef` data for downstream Graphiti
episodes:

- dataset ID;
- document ID;
- chunk ID when the result is chunk-level;
- source title or file name;
- content hash or excerpt hash when available;
- source timestamps where available.

Where RAGFlow supports document metadata, such as document `meta_fields`, PSKA
may write ingestion metadata there. Chunk-level source identity still comes from
retrieval results and provider coordinates. If RAGFlow cannot store downstream
Graphiti pointers, that is acceptable: the required durable direction is
Graphiti episode -> upstream RAGFlow SourceRef. Reverse pointers from RAGFlow to
Graphiti are useful for admin views, but not required for query correctness.

## Query-Time Federation

When Hermes asks a scoped question through PSKA:

```text
question + selected scope
  -> source retrieval over selected RAGFlow datasets/documents,
     local folders, and Obsidian vaults
  -> Graphiti search over selected tenant/workspace namespace
  -> optional graph expansion from returned facts/entities
  -> provenance resolution from Graphiti episodes or memory metadata
  -> fetch missing source evidence by SourceRef
  -> dedupe by provider coordinates and content hash
  -> return bounded context to Hermes
```

Graphiti should not replace source retrieval. Graphiti can suggest what related
evidence may matter. RAGFlow, local folders, and Obsidian remain the places PSKA
reads source evidence from.

Deduplication should prefer:

- exact provider coordinates: adapter, dataset ID, document ID, chunk ID;
- content hash when coordinates differ after migration;
- title plus document ID as a weaker fallback;
- timestamp and review status for ranking, not identity.

## Multi-Tenant Alignment

Names are display labels, not isolation keys.

Required scope keys:

- `tenant_id`
- `workspace_id`
- provider namespace or group ID derived by the adapter
- selected `dataset_ids` and optional `document_ids`

Graphiti `group_id` should be derived from tenant/workspace scope, not from a
RAGFlow dataset name. A Graphiti fact may point to one or many RAGFlow source
refs across datasets, so dataset names cannot be the graph alignment model.

## What Goes Into Graphiti

Graphiti stores compact reviewed memory, not a mirror of every document.

Good Graphiti candidates:

- durable facts likely to matter later;
- user or organization preferences;
- entities and relationships that recur across sessions;
- events with useful temporal meaning;
- contradictions or invalidations of older reviewed facts.

Poor Graphiti candidates:

- every chunk in a document;
- one-off passages already retrievable from RAGFlow;
- low-importance uncertain extraction;
- summaries whose only purpose is to answer the current question.

## Optional Caches

PSKA may later keep derived caches for performance or operator diagnostics, such
as recent provenance resolution results. These caches must be:

- rebuildable from provider-owned metadata;
- clearly marked non-authoritative;
- excluded from migration as the source of truth;
- safe to delete without corrupting RAGFlow or Graphiti lineage.

## Migration

Migration is component-by-component.

- RAGFlow migration exports documents, dataset metadata, and chunk coordinates
  where possible.
- Graphiti migration exports episodes, graph facts, temporal fields, and
  embedded PSKA provenance.
- Hermes migration exports sessions, messages, artifacts, and MCP config.
- PSKA migration exports workflow, review, audit, and policy control records.

PSKA exposes a migration manifest through `pska_migration_manifest` and
`GET /api/migration/manifest`. The manifest inventories PSKA control records,
provider source refs, memory target IDs, component ownership, exclusions, and a
component-by-component migration plan. It intentionally excludes raw documents,
chunks, embeddings, provider-native indexes, graph nodes, graph edges, Hermes
messages, and artifact binaries.

PSKA may assist migration, but it should not become the only place that knows
how Graphiti facts connect back to source evidence. The manifest is a map for
provider-owned exports, not a PSKA-owned data warehouse.

## Acceptance Criteria

The design is satisfied when:

- a reviewed memory apply writes Graphiti episode provenance;
- Graphiti search facts can be resolved back to episode provenance or report
  `lineage_status: unresolved`;
- a Graphiti-derived source ref can drive a RAGFlow source read or targeted
  retrieval;
- deleting PSKA derived caches does not erase durable data lineage;
- Hermes and the browser still call only PSKA Product API or PSKA MCP tools.

## Near-Term Implementation Order

1. Done: add a `ProvenanceEnvelope` helper in the PSKA contracts layer.
2. Done: include `content_hash` and relevant RAGFlow coordinates in
   `SourceRef` metadata during retrieval.
3. Done: extend reviewed memory metadata with workflow, proposal, review,
   tenant, workspace, and upstream references where available.
4. Done: extend the Graphiti adapter to write provenance to each applied
   episode.
5. Done where supported by the provider: resolve Graphiti fact episode UUIDs or
   direct fact/edge provenance into `source_refs`; otherwise return
   `lineage_status: unresolved`.
6. Done: add tests proving PSKA does not need a central provider mapping table
   for fact-to-source lineage.
7. Done: add first-pass query-time federation that uses memory provenance to
   fetch missing KB evidence and dedupe the final context packet set.
8. Done: add explicit conservative digest over selected ready scopes through
   `pska_digest_scope` / `POST /api/digest`.
9. Done: add optional queued digest jobs with priority and readiness-aware
   `waiting` state, without making ingestion write Graphiti as a side effect.
10. Next: attach an external scheduler or cron to call the explicit job runner
    when desired.
