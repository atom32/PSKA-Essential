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

```bash
HERMES_WEBUI_EXTENSION_DIR=/Users/xudawei/PSKA-Essential/integrations/hermes-webui-extension \
HERMES_WEBUI_EXTENSION_MANIFEST=pska-mini/manifest.json \
./start.sh
```

The WebUI backend still needs a PSKA bridge or extension sidecar that maps
`/api/pska/turn-context` to the PSKA-mini Product API.

