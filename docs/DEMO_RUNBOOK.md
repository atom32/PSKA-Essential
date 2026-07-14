# Demo Runbook

## Local Fake Demo

```bash
cd /Users/xudawei/PSKA-Essential
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 - <<'PY'
from pska_essential.workflow import build_fake_service

svc = build_fake_service()
run = svc.start("Show the workflow gate", {"dataset_ids": ["demo"]})
ctx = svc.context_retrieve(run.run_id, "adapter review memory", 2)
proposal = svc.propose(run.run_id, "memory_patch", "remember reviewed knowledge")
review = svc.review_create(proposal.proposal_id)

try:
    svc.memory_apply(review.review_id)
except Exception as exc:
    print("Blocked before review:", exc)

svc.review_decide(review.review_id, "accept", "demo approval")
print(svc.memory_apply(review.review_id))
print(svc.export_brief(run.run_id, "markdown"))
PY
```

## Hermes Demo

1. Start PSKA-Essential MCP with the `mcp` optional dependency installed.
2. Add only this MCP server to Hermes.
3. Ask Hermes to run this workflow:

```text
Use PSKA-Essential to start a workflow about adapter replaceability, retrieve
context, propose a memory patch, create a review item, stop for review, then
explicitly export a brief.
```

4. Manually call `pska_review_decide(..., decision="accept")`.
5. Call `pska_memory_apply`.

The point of the demo is that RAGFlow/Graphiti can be swapped without changing
the agent-facing workflow.

## RAGFlow Upload-To-Ask Demo

This is the first operational loop: the user brings a document, RAGFlow owns
the KB and parsing work, and PSKA-Essential owns the agent-facing workflow gate.

Prerequisites:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export RAGFLOW_BASE_URL=http://127.0.0.1:9380
export RAGFLOW_API_KEY=...
```

MCP tool sequence:

```text
pska_kb_ingest_files(
  file_paths=["/absolute/path/to/document.pdf"],
  dataset_name="pska-demo",
  parse=true,
  wait=true
)

pska_agentic_question_start(
  question="What should we remember from this document?",
  dataset_ids=["<dataset_id from ingest>"],
  proposal_kind="memory_patch",
  use_kg=false
)

pska_review_list("pending")
pska_review_get("<review_id>")
pska_review_decide("<review_id>", "accept", "approved for demo")
pska_memory_apply("<review_id>")
pska_workflow_artifact("<run_id>")
pska_workflow_brief("<run_id>", "markdown")
pska_export_brief("<run_id>", "markdown")
```

If RAGFlow structure compilation was configured before parsing, inspect the
optional graph layer:

```text
pska_kb_graph_read("<dataset_id>", "<document_id>")
```
