# PSKA Mini Hermes-WebUI Extension

Thin local extension for selecting PSKA-mini turn context from Hermes-WebUI.

It intentionally does not provide:

- PSKA chat
- Ask panel
- upload UI
- RAGFlow or Graphiti direct browser calls

It provides:

- a composer chip
- local scope settings
- `/api/pska/turn-context` preview
- `HermesChatStartHooks` registration with a `context_provider` body extension

Development launch:

Start PSKA-Essential Product API with retrieval and memory providers. RAGFlow
credentials belong here, not in Hermes-WebUI browser code:

```bash
cd /Users/xudawei/PSKA-Essential
PSKA_RETRIEVAL_PROVIDER=ragflow \
PSKA_KB_PROVIDER=ragflow \
PSKA_MEMORY_PROVIDER=fake \
PSKA_DEV_FAKE=1 \
RAGFLOW_BASE_URL=http://127.0.0.1:9380 \
RAGFLOW_API_KEY=... \
PSKA_API_HOST=127.0.0.1 \
PSKA_API_PORT=8765 \
python3 -m pska_essential.product_api
```

Then start Hermes-WebUI with the extension and same-origin PSKA proxy enabled:

```bash
cd /Users/xudawei/Documents/Codex/2026-07-27/yi/work/hermes-webui-pska-merge
HERMES_WEBUI_EXTENSION_DIR=/Users/xudawei/PSKA-Essential/integrations/hermes-webui-extension \
HERMES_WEBUI_EXTENSION_MANIFEST=pska-mini/manifest.json \
PSKA_API_BASE_URL=http://127.0.0.1:8765 \
./start.sh
```

Use a Hermes-WebUI checkout that contains the PSKA bridge commit
`3abc31e4` or equivalent.

The browser extension calls only `/api/pska/turn-context`. Hermes-WebUI maps
that to the PSKA Product API `/api/turn-context`, and PSKA-Essential performs
retrieval through its configured RetrievalPort, such as RAGFlow.
