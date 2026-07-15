from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.contracts import MemoryApplyResult, MemoryDelete, MemoryFact, MemoryPatch, MemoryUpdate


class GraphitiAdapterError(RuntimeError):
    pass


class GraphitiMemoryAdapter:
    """Graphiti memory adapter with a review-gated write surface.

    This class intentionally exposes only search and reviewed apply. It does
    not forward Graphiti MCP delete/clear/direct add tools to agents.
    """

    backend_name = "graphiti"
    memory_capabilities = {
        "search": True,
        "apply": True,
        "update": {
            "supported": False,
            "reason": "Graphiti reviewed update requires a transactional fact update endpoint.",
        },
        "delete": True,
    }

    def __init__(
        self,
        *,
        client: Any | None = None,
        base_url: str | None = None,
        group_id: str = "pska-essential",
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/") if base_url else None
        self.group_id = group_id

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        group_ids = _group_ids(scope, self.group_id)
        if self.client is not None and hasattr(self.client, "search"):
            result = _run_maybe_async(
                self.client.search(query=query, group_ids=group_ids, num_results=limit)
            )
            return [_edge_to_fact(edge) for edge in list(result or [])[:limit]]
        if self.base_url:
            payload = {"query": query, "group_ids": group_ids, "max_facts": limit}
            data = self._post_json("/search", payload)
            return [_fact_dict_to_fact(item) for item in data.get("facts", [])[:limit]]
        raise GraphitiAdapterError("Graphiti adapter requires a graphiti client or base_url")

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        if not reviewed_patch.source_refs:
            raise GraphitiAdapterError("reviewed memory patch requires source refs")
        episode_uuid = f"pska_{uuid4().hex}"
        group_id = _group_id_from_metadata(reviewed_patch.metadata, self.group_id)
        if self.client is not None and hasattr(self.client, "add_episode"):
            kwargs = {
                "uuid": episode_uuid,
                "name": "PSKA reviewed memory patch",
                "episode_body": reviewed_patch.text,
                "source_description": "PSKA-Essential reviewed memory patch",
                "reference_time": datetime.now(timezone.utc),
                "group_id": group_id,
            }
            try:
                from graphiti_core.nodes import EpisodeType  # type: ignore

                kwargs["source"] = EpisodeType.text
            except Exception:
                pass
            _run_maybe_async(self.client.add_episode(**kwargs))
            return MemoryApplyResult(
                applied=True,
                target_id=episode_uuid,
                backend=self.backend_name,
                message="Reviewed memory patch queued in Graphiti",
                metadata={"group_id": group_id},
            )
        if self.base_url:
            payload = {
                "group_id": group_id,
                "messages": [
                    {
                        "uuid": episode_uuid,
                        "name": "PSKA reviewed memory patch",
                        "role": "system",
                        "role_type": "memory",
                        "content": reviewed_patch.text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source_description": "PSKA-Essential reviewed memory patch",
                    }
                ],
            }
            self._post_json("/messages", payload, accept_empty=True)
            return MemoryApplyResult(
                applied=True,
                target_id=episode_uuid,
                backend=self.backend_name,
                message="Reviewed memory patch queued in Graphiti HTTP service",
                metadata={"group_id": group_id},
            )
        raise GraphitiAdapterError("Graphiti adapter requires a graphiti client or base_url")

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        if not reviewed_delete.target_id:
            raise GraphitiAdapterError("reviewed memory delete requires target_id")
        if not reviewed_delete.source_refs:
            raise GraphitiAdapterError("reviewed memory delete requires source refs")
        if self.client is not None:
            group_id = _group_id_from_metadata(reviewed_delete.metadata, self.group_id)
            if hasattr(self.client, "delete_entity_edge"):
                _run_maybe_async(self.client.delete_entity_edge(reviewed_delete.target_id))
                return MemoryApplyResult(
                    applied=True,
                    target_id=reviewed_delete.target_id,
                    backend=self.backend_name,
                    message="Reviewed memory fact deleted in Graphiti",
                    metadata={"operation": "delete", "group_id": group_id},
                )
            if hasattr(self.client, "get_entity_edge") and hasattr(self.client, "driver"):
                edge = _run_maybe_async(self.client.get_entity_edge(reviewed_delete.target_id))
                _run_maybe_async(edge.delete(self.client.driver))
                return MemoryApplyResult(
                    applied=True,
                    target_id=reviewed_delete.target_id,
                    backend=self.backend_name,
                    message="Reviewed memory fact deleted in Graphiti",
                    metadata={"operation": "delete", "group_id": group_id},
                )
            raise GraphitiAdapterError("Graphiti client does not expose reviewed memory delete")
        if self.base_url:
            group_id = _group_id_from_metadata(reviewed_delete.metadata, self.group_id)
            data = self._delete_json(f"/entity-edge/{quote(reviewed_delete.target_id, safe='')}")
            return MemoryApplyResult(
                applied=True,
                target_id=reviewed_delete.target_id,
                backend=self.backend_name,
                message=str(data.get("message") or "Reviewed memory fact deleted in Graphiti HTTP service"),
                metadata={"operation": "delete", "group_id": group_id},
            )
        raise GraphitiAdapterError("Graphiti adapter requires a graphiti client or base_url")

    def update(self, reviewed_update: MemoryUpdate) -> MemoryApplyResult:
        raise GraphitiAdapterError(
            "Graphiti reviewed memory update requires a transactional fact update endpoint; "
            "the current Graphiti HTTP surface supports reviewed add and delete only"
        )

    def _post_json(self, path: str, payload: dict[str, Any], *, accept_empty: bool = False) -> dict[str, Any]:
        req = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GraphitiAdapterError(_http_error_message("POST", path, exc)) from exc
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        if not raw and accept_empty:
            return {}
        return json.loads(raw or "{}")

    def _delete_json(self, path: str) -> dict[str, Any]:
        req = Request(f"{self.base_url}{path}", method="DELETE")
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GraphitiAdapterError(_http_error_message("DELETE", path, exc)) from exc
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        return json.loads(raw or "{}")


def _run_maybe_async(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)
    raise GraphitiAdapterError("Graphiti async client cannot be used from an active event loop in sync adapter mode")


def _group_ids(scope: dict[str, Any], default: str) -> list[str]:
    raw = (
        scope.get("memory_group_ids")
        or scope.get("memory_group_id")
        or _group_id_from_metadata(scope, default)
    )
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return [str(raw)]


def _group_id_from_metadata(metadata: dict[str, Any], default: str) -> str:
    namespace = str(metadata.get("memory_namespace") or "")
    return f"{default}:{namespace}" if namespace else default


def _edge_to_fact(edge: Any) -> MemoryFact:
    fact_id = str(getattr(edge, "uuid", None) or getattr(edge, "id", None) or uuid4().hex)
    text = str(getattr(edge, "fact", None) or getattr(edge, "name", None) or edge)
    return MemoryFact(
        fact_id=fact_id,
        text=text,
        valid_at=_iso(getattr(edge, "valid_at", None)),
        invalid_at=_iso(getattr(edge, "invalid_at", None)),
        metadata={
            "name": getattr(edge, "name", None),
            "group_id": getattr(edge, "group_id", None),
            "episodes": list(getattr(edge, "episodes", []) or []),
        },
    )


def _fact_dict_to_fact(data: dict[str, Any]) -> MemoryFact:
    return MemoryFact(
        fact_id=str(data.get("uuid") or data.get("fact_id") or uuid4().hex),
        text=str(data.get("fact") or data.get("text") or data.get("name") or ""),
        valid_at=data.get("valid_at"),
        invalid_at=data.get("invalid_at"),
        metadata={key: value for key, value in data.items() if key not in {"uuid", "fact_id", "fact", "text"}},
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _http_error_message(method: str, path: str, exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    status = f"{exc.code} {exc.reason}".strip()
    message = f"Graphiti HTTP {method} {path} failed: {status}"
    if body:
        message = f"{message}: {body[:500]}"
    if path in {"/search", "/messages"} and exc.code >= 500:
        message = (
            f"{message}. Check Graphiti LLM/embedding provider configuration "
            "(OPENAI_API_KEY, OPENAI_BASE_URL, model, and embedding model)."
        )
    return message
