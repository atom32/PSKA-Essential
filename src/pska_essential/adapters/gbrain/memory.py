from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.contracts import (
    MemoryApplyResult,
    MemoryDelete,
    MemoryFact,
    MemoryPatch,
    MemoryUpdate,
    SourceRef,
)


class GBrainAdapterError(RuntimeError):
    pass


class GBrainCaller(Protocol):
    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class GBrainHttpMemoryAdapter:
    """PSKA MemoryPort adapter for GBrain over HTTP MCP.

    The adapter is deliberately not a Hermes MCP registration. Hermes talks to
    PSKA; PSKA then calls the GBrain HTTP MCP endpoint after PSKA policy,
    review, provenance, and audit boundaries have already run.
    """

    backend_name = "gbrain"
    memory_capabilities = {
        "search": True,
        "list": True,
        "get": {
            "supported": False,
            "reason": "GBrain MEMORY_VERBS v1 exposes recall rather than a provider-neutral direct fact lookup.",
        },
        "apply": True,
        "update": {
            "supported": False,
            "reason": "GBrain MEMORY_VERBS v1 has remember/forget; PSKA target-specific update needs a later adapter policy.",
        },
        "delete": True,
        "conversation_update_strategies": ["append_correction_episode"],
    }

    def __init__(
        self,
        *,
        mcp_url: str,
        token: str,
        timeout: float = 30.0,
        caller: GBrainCaller | None = None,
    ) -> None:
        self.mcp_url = mcp_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._caller = caller or _HttpMcpCaller(mcp_url=self.mcp_url, token=token, timeout=timeout)

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        payload = _recall_args(scope, limit=limit, query=query, include_inactive=False)
        data = self._call("recall", payload)
        return _recall_to_facts(data, limit=max(1, int(limit or 1)))

    def list_facts(self, scope: dict[str, Any], limit: int, *, include_inactive: bool = False) -> list[MemoryFact]:
        payload = _recall_args(scope, limit=limit, query="", include_inactive=include_inactive)
        data = self._call("recall", payload)
        return _recall_to_facts(data, limit=max(1, int(limit or 1)))

    def get_fact(self, fact_id: str, scope: dict[str, Any]) -> MemoryFact | None:
        # Best-effort only; advertised as unsupported in memory_capabilities.
        target = str(fact_id or "").strip()
        if not target:
            return None
        try:
            facts = self.list_facts({**scope, "include_expired": True}, 100, include_inactive=True)
        except GBrainAdapterError:
            return None
        return next((fact for fact in facts if fact.fact_id == target), None)

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        if not reviewed_patch.source_refs:
            raise GBrainAdapterError("reviewed memory patch requires source refs")
        provenance = _provenance_text(reviewed_patch.metadata, reviewed_patch.source_refs)
        payload: dict[str, Any] = {
            "fact": reviewed_patch.text,
            "provenance": provenance,
            "visibility": str(reviewed_patch.metadata.get("gbrain_visibility") or "world"),
        }
        entity = _entity_from_metadata(reviewed_patch.metadata)
        if entity:
            payload["entity"] = entity
        kind = _gbrain_kind(reviewed_patch.metadata)
        if kind:
            payload["kind"] = kind
        ttl = str(reviewed_patch.metadata.get("ttl") or reviewed_patch.metadata.get("gbrain_ttl") or "").strip()
        if ttl:
            payload["ttl"] = ttl
        data = self._call("remember", payload)
        target_id = str(data.get("id") or data.get("fact_id") or "")
        return MemoryApplyResult(
            applied=True,
            target_id=target_id or None,
            backend=self.backend_name,
            message=str(data.get("status_text") or data.get("status") or "Reviewed memory patch remembered by GBrain"),
            metadata={
                "operation": "remember",
                "gbrain": data,
                "provenance": provenance,
                "source_count": len(reviewed_patch.source_refs),
            },
        )

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        if not reviewed_delete.target_id:
            raise GBrainAdapterError("reviewed memory delete requires target_id")
        if not reviewed_delete.source_refs:
            raise GBrainAdapterError("reviewed memory delete requires source refs")
        target_id = str(reviewed_delete.target_id)
        reason = reviewed_delete.reason or _provenance_text(reviewed_delete.metadata, reviewed_delete.source_refs)
        try:
            data = self._call("forget", {"id": target_id, "reason": reason})
            fallback = False
        except GBrainAdapterError as exc:
            if "unknown_tool" not in str(exc) and "Unknown tool" not in str(exc):
                raise
            data = self._call("forget_fact", {"id": _numeric_fact_id(target_id), "reason": reason})
            fallback = True
        return MemoryApplyResult(
            applied=True,
            target_id=target_id,
            backend=self.backend_name,
            message=str(data.get("reason") or "Reviewed memory fact forgotten by GBrain"),
            metadata={"operation": "forget", "gbrain": data, "used_forget_fact_fallback": fallback},
        )

    def update(self, reviewed_update: MemoryUpdate) -> MemoryApplyResult:
        raise GBrainAdapterError(
            "GBrain reviewed update is not enabled; create a new reviewed memory patch or a reviewed delete instead"
        )

    def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._caller.call(tool_name, arguments)


class _HttpMcpCaller:
    def __init__(self, *, mcp_url: str, token: str, timeout: float) -> None:
        self.mcp_url = mcp_url
        self.token = token
        self.timeout = timeout

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }
        ).encode("utf-8")
        request = Request(
            self.mcp_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise GBrainAdapterError(_http_error_message(exc)) from exc
        except TimeoutError as exc:
            raise GBrainAdapterError(f"GBrain HTTP MCP call timed out after {self.timeout:g}s") from exc
        except URLError as exc:
            raise GBrainAdapterError(str(exc)) from exc
        return _parse_mcp_response(raw, tool_name)


def _recall_args(
    scope: dict[str, Any],
    *,
    limit: int,
    query: str = "",
    include_inactive: bool = False,
) -> dict[str, Any]:
    args: dict[str, Any] = {"limit": max(1, int(limit or 1))}
    normalized_query = str(query or "").strip()
    if normalized_query:
        args["query"] = normalized_query
    entity = _entity_from_metadata(scope)
    if entity:
        args["entity"] = entity
    for scope_key, gbrain_key in (
        ("since", "since"),
        ("session_id", "session_id"),
        ("gbrain_session_id", "session_id"),
        ("budget_tokens", "budget_tokens"),
        ("memory_budget_tokens", "budget_tokens"),
    ):
        value = scope.get(scope_key)
        if value not in (None, ""):
            args[gbrain_key] = value
    if include_inactive or bool(scope.get("include_expired")):
        args["include_expired"] = True
    return args


def _recall_to_facts(data: dict[str, Any], *, limit: int) -> list[MemoryFact]:
    facts: list[MemoryFact] = []
    for item in data.get("facts") or []:
        if isinstance(item, dict):
            facts.append(_gbrain_fact_to_memory_fact(item, recall=data))
    for item in data.get("results") or []:
        if isinstance(item, dict):
            facts.append(_gbrain_result_to_memory_fact(item, recall=data))
    return facts[:limit]


def _gbrain_fact_to_memory_fact(data: dict[str, Any], *, recall: dict[str, Any]) -> MemoryFact:
    fact_id = str(data.get("fact_id") or data.get("id") or uuid4().hex)
    text = str(data.get("fact") or data.get("text") or data.get("name") or "")
    provenance = str(data.get("provenance") or data.get("source") or "")
    metadata = {
        key: value
        for key, value in data.items()
        if key not in {"fact_id", "id", "fact", "text", "name"}
    }
    metadata.update(_recall_metadata(recall))
    return MemoryFact(
        fact_id=fact_id,
        text=text,
        valid_at=data.get("valid_from") or data.get("created_at"),
        invalid_at=data.get("expired_at"),
        source_refs=_gbrain_source_refs(provenance, fact_id=fact_id, title="GBrain fact"),
        metadata=metadata,
    )


def _gbrain_result_to_memory_fact(data: dict[str, Any], *, recall: dict[str, Any]) -> MemoryFact:
    slug = str(data.get("slug") or data.get("provenance") or uuid4().hex)
    title = str(data.get("title") or slug)
    text = str(data.get("chunk") or data.get("text") or "")
    metadata = {
        "gbrain_result": True,
        "slug": slug,
        "title": title,
        "evidence": data.get("evidence"),
        "create_safety": data.get("create_safety"),
        "provenance": data.get("provenance"),
    }
    metadata.update(_recall_metadata(recall))
    return MemoryFact(
        fact_id=f"gbrain_result:{slug}",
        text=text,
        source_refs=[
            SourceRef(
                adapter="gbrain",
                source_id=slug,
                title=title,
                metadata={"kind": "recall_result", "evidence": data.get("evidence")},
            )
        ],
        metadata=metadata,
    )


def _recall_metadata(recall: dict[str, Any]) -> dict[str, Any]:
    return {
        key: recall[key]
        for key in ("protocol_version", "search_degraded", "budget_tokens", "budget_used", "dropped_count")
        if key in recall
    }


def _gbrain_source_refs(provenance: str, *, fact_id: str, title: str) -> list[SourceRef]:
    return [
        SourceRef(
            adapter="gbrain",
            source_id=provenance or fact_id,
            external_id=fact_id,
            title=title,
            metadata={"provenance": provenance, "kind": "memory_fact"},
        )
    ]


def _parse_mcp_response(raw: str, tool_name: str) -> dict[str, Any]:
    payload = _json_or_sse_json(raw)
    if not isinstance(payload, dict):
        raise GBrainAdapterError(f"GBrain MCP {tool_name} returned non-object response")
    if payload.get("error"):
        raise GBrainAdapterError(f"GBrain MCP {tool_name} failed: {payload['error']}")
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        raise GBrainAdapterError(f"GBrain MCP {tool_name} returned non-object result")
    is_error = bool(result.get("isError"))
    content = result.get("content")
    if isinstance(content, list) and content:
        texts = [str(item.get("text") or "") for item in content if isinstance(item, dict)]
        parsed = _first_json_text(texts)
        if is_error:
            raise GBrainAdapterError(_tool_error_message(tool_name, parsed, texts))
        if isinstance(parsed, dict):
            return parsed
        return {"text": "\n".join(text for text in texts if text)}
    if is_error:
        raise GBrainAdapterError(f"GBrain MCP {tool_name} failed")
    return result


def _json_or_sse_json(raw: str) -> Any:
    text = raw.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    data_lines = [
        line[5:].strip()
        for line in text.splitlines()
        if line.startswith("data:") and line[5:].strip() and line[5:].strip() != "[DONE]"
    ]
    for item in reversed(data_lines):
        try:
            return json.loads(item)
        except json.JSONDecodeError:
            continue
    raise GBrainAdapterError("GBrain MCP response was not JSON or parseable SSE JSON")


def _first_json_text(texts: list[str]) -> Any:
    for text in texts:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    return None


def _tool_error_message(tool_name: str, parsed: Any, texts: list[str]) -> str:
    if isinstance(parsed, dict):
        code = parsed.get("error") or parsed.get("code") or "tool_error"
        message = parsed.get("message") or parsed.get("detail") or json.dumps(parsed, ensure_ascii=False)
        return f"GBrain MCP {tool_name} failed: {code}: {message}"
    text = "\n".join(item for item in texts if item)
    return f"GBrain MCP {tool_name} failed: {text or 'tool error'}"


def _http_error_message(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    status = f"{exc.code} {exc.reason}".strip()
    return f"GBrain HTTP MCP failed: {status}" + (f": {body[:500]}" if body else "")


def _provenance_text(metadata: dict[str, Any], source_refs: list[SourceRef]) -> str:
    parts = []
    for key, label in (("review_id", "pska_review"), ("proposal_id", "proposal"), ("run_id", "workflow")):
        value = str(metadata.get(key) or "").strip()
        if value:
            parts.append(f"{label}:{value}")
    if not parts:
        parts.append("pska_review:unknown")
    source_labels = []
    for ref in source_refs[:4]:
        source_labels.append(ref.title or ref.source_id or ref.document_id or ref.path or ref.adapter)
    if source_labels:
        parts.append("sources:" + ";".join(str(item) for item in source_labels if item))
    text = " ".join(parts)
    return text[:500]


def _entity_from_metadata(metadata: dict[str, Any]) -> str:
    for key in ("gbrain_entity", "entity", "entity_slug", "memory_entity"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return ""


def _gbrain_kind(metadata: dict[str, Any]) -> str:
    value = str(metadata.get("gbrain_kind") or metadata.get("memory_type") or metadata.get("kind") or "").strip()
    return value if value in {"event", "preference", "commitment", "belief", "fact"} else ""


def _numeric_fact_id(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise GBrainAdapterError(f"GBrain forget_fact fallback requires a numeric fact id, got {value!r}") from exc
