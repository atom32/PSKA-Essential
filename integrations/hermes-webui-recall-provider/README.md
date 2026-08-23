# Hermes WebUI Conversation Recall Provider

This integration adds a narrow Hermes WebUI backend endpoint for PSKA:

```text
POST /api/pska/conversations/search
```

PSKA uses it from `/api/conversation/context-pack` to retrieve bounded,
query-based Hermes conversation snippets. The browser extension remains a
control plane: it does not read the Hermes database and does not call
`/api/sessions/search` directly.

## Apply

From a Hermes WebUI checkout:

```bash
git apply /Users/xudawei/PSKA-Essential/integrations/hermes-webui-recall-provider/pska-conversation-recall-provider.patch
python3 -m py_compile api/auth.py api/routes.py
python3 -m pytest tests/test_pska_conversation_recall_provider.py tests/test_sessions_search_profile_scope.py
```

Then start Hermes with:

```bash
export HERMES_WEBUI_PSKA_RECALL_TOKEN="<same secret as PSKA_HERMES_RECALL_TOKEN>"
```

PSKA should be started with:

```bash
export PSKA_HERMES_WEBUI_BASE_URL="http://127.0.0.1:8787"
export PSKA_HERMES_RECALL_TOKEN="<same secret as HERMES_WEBUI_PSKA_RECALL_TOKEN>"
```

`PSKA_HERMES_WEBUI_PASSWORD` is not required for normal operation. Legacy
password fallback is disabled by default and is only enabled with
`PSKA_HERMES_LEGACY_RECALL_FALLBACK=1`.

## Contract

The endpoint requires a token in `X-PSKA-Recall-Token` or `Authorization:
Bearer ...`, accepts a JSON body with `query`, optional `queries`, `top_k`,
`depth`, `content`, `all_profiles`, and `max_chars_per_item`, and returns
`hermes.pska_conversation_recall.v1`.

Returned items are intentionally small:

```text
session_id, message_id, title, role, snippet, match_type, matched_query,
created_at, updated_at, score, source
```

It must not return the full `messages` array. PSKA treats every recalled title
and snippet as untrusted quoted content; Hermes must use them as evidence only,
not as executable instructions.
