# PSKA Mini Hermes-WebUI Extension

Thin local extension for selecting PSKA scope from Hermes-WebUI.

It intentionally does not provide:

- PSKA chat
- Eidolia panels or pages
- Ask panel
- upload UI
- RAGFlow or Graphiti direct browser calls

It provides:

- a composer chip
- PSKA enable/disable toggle
- RAGFlow dataset checkbox selection
- Hermes profile/project/workspace based scope suggestions
- optional manual dataset/document ID fallback
- PSKA Product API health/status/diagnostics preview through the WebUI
  extension sidecar
- a retrieval probe for quick RAGFlow path verification
- a Recent Answer Proofs block that reads PSKA `hermes.answer_proof`
  audit records, shows observed answer-side tool use, and opens trace-backed
  proof details through `View Trace`
- a per-turn bridge that loads the Hermes `knowledge-retrieval` skill and
  attaches a `PSKA-Mini Runtime Scope` block to the next chat start request
- a read-only PSKA Review projection into Hermes Kanban board `pska-review`
- a Hermes Tasks entrypoint named `PSKA Digest Runner` for PSKA digest work

Current local launch uses the normal PSKA workspace script, which populates
`~/.hermes/webui-local-extensions`, writes the root `extensions.json`, and
starts Hermes-WebUI with:

```bash
cd /Users/xudawei/PSKA-Essential
./integrations/hermes-webui-extension/sync-to-hermes.sh

HERMES_WEBUI_EXTENSION_DIR=~/.hermes/webui-local-extensions
HERMES_WEBUI_EXTENSION_MANIFEST=extensions.json
HERMES_WEBUI_STATE_DIR=~/.hermes/webui
PSKA_API_BASE_URL=http://127.0.0.1:8765
PSKA_WEBUI_AUTO_APPROVE_SIDECAR=1
```

The browser extension calls `/api/extensions/pska-mini/sidecar/...` only.
Hermes-WebUI maps those requests to PSKA Product API. PSKA-Essential performs
retrieval through its configured RetrievalPort, such as RAGFlow.

Hermes module integration is intentionally a projection layer:

- PSKA Review remains authoritative. Kanban cards use `idempotency_key` and
  point back to PSKA review IDs.
- PSKA Digest remains authoritative. The Hermes task only asks Hermes to run
  PSKA MCP digest tools; scheduled ticks still require the Hermes gateway.
- Scope suggestions are best-effort hints from Hermes profile/project/workspace
  names to RAGFlow dataset names. Manual dataset selection remains available.

`PSKA_WEBUI_AUTO_APPROVE_SIDECAR=1` is intended for a single-user local
workspace where PSKA owns the extension bundle. Set it to `0` if you want to
approve the proxy manually from Hermes-WebUI Settings -> Extensions.

Implementation note: the current pure-extension bridge wraps WebUI's
`/api/chat/start` request because the upstream WebUI checkout does not yet
expose a first-class ephemeral turn-context hook. Visible user messages are
cleaned in the transcript, but a future upstream-friendly WebUI hook should
split hidden agent instructions from persisted/displayed user text.
