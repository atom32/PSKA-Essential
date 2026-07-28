# PSKA Graphiti Failure Recovery

> Reference document for when PSKA's Graphiti memory backend is down.
> Captured from session 2026-07-28.

## Error Signatures

### Graphiti 502 (most common)
```
pska_agentic_question_start -> "Graphiti HTTP POST /search failed: 502 Bad Gateway. Check Graphiti LLM/embedding provider configuration (OPENAI_API_KEY, OPENAI_BASE_URL, model, and embedding model)."
pska_memory_search -> Same 502 error
```

### Cascading MCP server retry window
After repeated Graphiti-heavy tool failures, Hermes may park the PSKA MCP
transport temporarily:
```
MCP server 'pska-essential' is unreachable after 4 consecutive failures. Auto-retry available in ~Xs.
```

This is a client-side retry/backoff posture, not proof that RAGFlow retrieval is
broken. Wait for the backoff window or use the PSKA Product API retrieval probe.

## Architecture (from `.env.pska`)

| Component | Role | Endpoint |
|-----------|------|----------|
| RAGFlow | KB provider (documents, chunks, retrieval) | `http://127.0.0.1:9380` |
| Graphiti | Memory backend (durable facts) | `http://127.0.0.1:8000` |
| infinity-emb | Embedding service (bge-m3) | `http://127.0.0.1:6380` |
| PSKA API | Orchestration + governance | `http://127.0.0.1:8765` |
| PSKA Review DB | Local SQLite for governance | `~/.pska-essential/review.sqlite3` |

## Recovery Strategy

### Tier 1: Wait + Retry
The MCP watchdog auto-retries (backoff window ~40-60s per failure). If Graphiti comes back, tools resume working.

### Tier 2: Retrieval-first fallback
Prefer PSKA Product API retrieval before raw RAGFlow:

```bash
curl -s -X POST http://127.0.0.1:8765/api/runtime/retrieval-probe \
  -H "Content-Type: application/json" \
  -d '{"question":"probe","dataset_ids":["<dataset-id>"],"limit":3,"use_kg":false}'
```

If the Product API is unavailable, see the `knowledge-retrieval` skill's raw
RAGFlow fallback path. Use the RAGFlow API key from `.env.pska`, but never echo
or reveal it.

### Tier 3: Check Graphiti process
```bash
ps aux | grep graphiti
curl -s http://localhost:8000/health
```
Graphiti is NOT bundled with PSKA-Essential — it's a separate service. If it's not running, it needs to be started independently.

### Tier 4: Check embedding service
```bash
curl -s http://localhost:6380/health
```
The infinity-emb server (bge-m3) runs independently on port 6380. RAGFlow queries need it for vector search.
