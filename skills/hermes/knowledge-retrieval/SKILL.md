---
name: knowledge-retrieval
description: "Use when answering with PSKA-Essential, RAGFlow, personal knowledge bases, or memory evidence. Retrieval-first workflow for PSKA MCP: honor WebUI PSKA-mini chip scope, avoid Graphiti-dependent tools when memory is down, cite evidence, and propose durable memory updates after the answer."
version: 1.1.0
author: hermes-agent
license: MIT
platforms: [macos, linux]
prerequisites:
  mcp_servers: ["pska-essential"]
  commands: [curl, python3]
metadata:
  hermes:
    tags: [pska, ragflow, retrieval, memory, evidence]
    related_skills: [system-introspection]
---

# PSKA-Essential Knowledge Retrieval

## Overview

PSKA-Essential is the glue layer for evidence, memory, and governance. It is not
a chat surface. Hermes-WebUI is the daily chat entry, RAGFlow stores documents
and chunks, and PSKA-Essential exposes MCP tools that let Hermes retrieve,
assemble, cite, and govern knowledge.

Treat Graphiti as an optional memory backend. RAGFlow evidence retrieval must
remain useful when Graphiti is down. Do not let a failed memory service block a
document-grounded answer.

## When to Use

- The user asks to use PSKA, RAGFlow, a knowledge base, document evidence, or
  the PSKA-mini chip.
- The user asks a factual question where local KB evidence is expected.
- The user asks about prior project decisions, architecture, runbooks, or
  durable preferences that might live in PSKA/Hermes memory.
- The WebUI PSKA-mini chip forced this skill into the next turn.

Do not use this skill for ordinary conversation, pure coding tasks with no
knowledge-base requirement, or creative writing unless the user asks to ground
the writing in stored evidence.

## Runtime Scope

If the WebUI PSKA-mini chip is enabled, the user message may contain a
`PSKA-Mini Runtime Scope` block injected before the visible user text. Read it
first. It normally includes:

```json
{
  "enabled": true,
  "mode": "auto",
  "dataset_ids": ["..."],
  "document_ids": [],
  "max_tokens": 3000,
  "source": "hermes-webui.pska-mini-chip"
}
```

Rules:

- Honor `dataset_ids` and `document_ids` exactly. Do not invent IDs.
- If the scope has no dataset IDs, call `pska_workspace_status` and choose from
  ready datasets by name/description. If several plausible datasets remain,
  ask the user to choose instead of forcing them to hand-type IDs.
- `mode: evidence-only` or `project` means retrieve document evidence first and
  skip memory unless the user explicitly asks for memory.
- `mode: memory-only` means avoid KB retrieval and only use memory tools if the
  memory backend is healthy.
- `mode: auto` means prefer selected KB evidence, then memory if useful and
  healthy.

## Tool Order

1. **Status and scope.** Call `pska_workspace_status` when you need dataset
   inventory or backend status. Call `pska_capabilities_get` if you need to know
   whether memory operations are supported.

2. **Retrieval first.** For normal KB questions, call:

   ```python
   pska_retrieval_probe(
       question="<user question>",
       dataset_ids=["<selected-ready-dataset-id>"],
       document_ids=[],
       limit=5,
       use_kg=False,
   )
   ```

   Use `pska_context_retrieve(query, scope, limit)` when you need PSKA's
   assembled context packets instead of a diagnostic-style probe. Keep `scope`
   aligned with the chip-selected dataset/document IDs.

3. **Agentic workflows sparingly.** Use `pska_agentic_question_start` only for
   longer synthesis workflows when Graphiti/memory is healthy or the user
   explicitly asks for a PSKA workflow artifact. Do not use it as the default
   for simple factual questions; it is more likely to fail when memory is down.

4. **Memory search only when helpful.** Call `pska_memory_search` only when the
   answer depends on durable prior facts or preferences. If Graphiti or memory
   diagnostics fail, continue with KB retrieval and mention memory unavailability
   only if it affects the answer.

5. **Fallback.** If MCP retrieval is unavailable but the PSKA Product API is
   running, use the local Product API retrieval endpoints before falling back to
   raw RAGFlow REST. If raw RAGFlow needs an API key, read it from the configured
   env file but never print or reveal it.

## Answer Contract

- Answer from retrieved evidence, not from chat-context guesses.
- Cite sources compactly: source title/document plus chunk or context index when
  available.
- If evidence is thin, say what was found and what remains uncertain.
- Never quote large copyrighted passages. Summarize and use short excerpts only
  when they clarify the evidence.
- If retrieval fails, report the failure and the fallback attempted.

## Memory Candidate Pass

After forming the answer, do a short memory-candidate pass before finishing.
Save or propose only durable facts:

- User preferences about how Hermes/PSKA should behave.
- Stable architecture decisions, component responsibilities, ports, or runbooks.
- Corrections from the user that should change future behavior.
- Reusable troubleshooting lessons after the fix is confirmed.

Do not save:

- Secrets, API keys, tokens, passwords, or private credentials.
- One-off document facts from a KB answer.
- Transient failures that may disappear after restart or redeploy.
- Uncertain inferences, speculation, or bulky source text.

When a candidate is clearly durable and PSKA memory is healthy, use:

```python
pska_memory_change_from_conversation(
    user_message="<concise memory-worthy fact or correction>",
    operation="auto",
    text="<normalized durable fact>",
    source_refs=[],
    scope={"namespace": "workspace:default"},
    reason="<why this should persist>",
    confidence=0.9,
)
```

If Graphiti or memory apply is down, do not block the answer. For an important
new add-style candidate, prefer queueing it for review instead of losing it:

```python
pska_memory_change_from_conversation(
    user_message="<concise memory-worthy fact or correction>",
    operation="auto",
    text="<normalized durable fact>",
    source_refs=[],
    scope={"namespace": "workspace:default"},
    reason="<why this should persist>",
    confidence=0.9,
    force_review=True,
)
```

`force_review=True` stores the candidate in PSKA's local SQLite review store
and avoids immediate backend apply. Use it only for compact, high-confidence
workspace/user-behavior facts. For updates or deletes, memory search/target
resolution still needs a healthy memory backend or an explicit `memory_fact`.
If PSKA MCP itself is unavailable, mention the unsaved candidate briefly.

Use Hermes built-in memory only for user preferences and operational rules that
should affect Hermes itself.

## Common Pitfalls

1. **Starting with Graphiti-heavy workflows.** Do not default to
   `pska_agentic_question_start`; use retrieval/context first.
2. **Forcing users to type IDs.** Use the chip dataset selector or
   `pska_workspace_status`; ask for selection only when the available names are
   genuinely ambiguous.
3. **Treating memory failure as PSKA failure.** Graphiti down means memory is
   down; it does not mean RAGFlow retrieval is unusable.
4. **Saving answers as memory.** KB answers are evidence outputs, not memory.
   Save the user's stable decisions and preferences, not the source document.
5. **Leaking secrets.** Env files may contain API keys. Use them only for
   requests and never echo them.

## Verification Checklist

- [ ] Dataset scope came from the chip or from `pska_workspace_status`.
- [ ] Retrieval used selected ready datasets and returned evidence, or a fallback
      was attempted.
- [ ] Final answer distinguishes evidence, uncertainty, and memory availability.
- [ ] Durable memory candidates were considered without saving transient or
      secret content.
