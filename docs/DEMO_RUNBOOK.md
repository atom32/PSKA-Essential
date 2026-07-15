# Demo Runbook

Product demos assume a fresh workspace: no useful datasets, no preloaded demo
knowledge, and no cleanup step in the user path. The user starts by uploading
source material through PSKA. Bad local datasets may be deleted only as
development maintenance before rerunning the fresh upload loop.

## Hermes Demo

1. Start PSKA-Essential MCP with the `mcp` optional dependency installed.
2. Add only this MCP server to Hermes.
3. Ask Hermes to run this workflow:

```text
Use PSKA-Essential to inspect workspace status. If no knowledge base exists,
follow the returned next action to ingest a local document first. When the
selected scope is ready, ask about the uploaded document, propose a memory
patch, create a review item, stop for review, then explicitly export a brief.
```

4. Manually call `pska_review_decide(..., decision="accept")`.
5. Call `pska_workspace_status` again; it should surface accepted durable memory
   awaiting apply.
6. Call `pska_memory_apply`.

The point of the demo is that RAGFlow/Graphiti can be swapped without changing
the agent-facing workflow.

## RAGFlow Upload-To-Ask Demo

This is the first operational loop: the user brings a document, RAGFlow owns
the KB and parsing work, and PSKA-Essential owns the agent-facing workflow gate.
Assume a fresh workspace with no useful datasets; the demo starts by uploading
source material through PSKA, not by relying on pre-existing KB data.

Prerequisites:

```bash
export PSKA_RETRIEVAL_PROVIDER=ragflow
export PSKA_KB_PROVIDER=ragflow
export RAGFLOW_BASE_URL=http://127.0.0.1:9380
export RAGFLOW_API_KEY=...
```

MCP tool sequence:

```text
pska_workspace_status()

pska_ingest_loop(
  file_paths=["/absolute/path/to/document.pdf"],
  dataset_name="pska-demo",
  question="What should we remember from this document?",
  proposal_kind="memory_patch",
  parse=true,
  wait_ready=false,
  export_format="markdown"
)
```

If the result is `status=not_ready`, wait for parsing/chunking/embedding to
finish and resume the same upload -> Ask -> export intent:

```text
pska_agentic_question_resumable(limit=5)
pska_ingest_loop_resume("<blocked_run_id>")
```

```text
pska_review_list("pending")
pska_review_get("<review_id>")
pska_review_decide("<review_id>", "accept", "approved for demo")
pska_workspace_status()
pska_memory_apply("<review_id>")
pska_workspace_status()
pska_workflow_list(limit=5)
pska_workflow_artifact("<run_id>")
pska_workflow_brief("<run_id>", "markdown")
pska_export_brief("<run_id>", "markdown")
pska_audit_list(limit=20)
```

Use the lower-level `pska_kb_ingest_files -> pska_kb_ingestion_status ->
pska_agentic_question_start` sequence only when the demo needs manual dataset
control or separate ingestion/status inspection.

If RAGFlow structure compilation was configured before parsing, inspect the
optional graph layer:

```text
pska_kb_graph_read("<dataset_id>", "<document_id>")
```

## Local Contract Smoke (Fake Only)

This is not the product demo path. It is a local development/test smoke for the
review gate contract when live RAGFlow/Graphiti components are unavailable.

```bash
cd /Users/xudawei/PSKA-Essential
PSKA_DEV_FAKE=1 PYTHONPATH=src python3 -m unittest discover -s tests
PSKA_DEV_FAKE=1 PYTHONPATH=src python3 - <<'PY'
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

## Development Maintenance

Bad development datasets may be deleted through PSKA maintenance paths such as
`pska_kb_delete`, `DELETE /api/kb/datasets/{dataset_id}`, or Knowledge Bases
Delete All. Cleanup is not part of the product demo path; it is only for
resetting a development environment before rerunning the fresh upload loop.
