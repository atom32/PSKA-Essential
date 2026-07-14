from __future__ import annotations

import asyncio
import inspect
import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.contracts import MemoryApplyResult, MemoryDelete, MemoryFact, MemoryPatch


class GraphitiAdapterError(RuntimeError):
    pass


class GraphitiMemoryAdapter:
    """Graphiti memory adapter with a review-gated write surface.

    This class intentionally exposes only search and reviewed apply. It does
    not forward Graphiti MCP delete/clear/direct add tools to agents.
    """

    backend_name = "graphiti"

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
        if self.client is not None and hasattr(self.client, "add_episode"):
            kwargs = {
                "uuid": episode_uuid,
                "name": "PSKA reviewed memory patch",
                "episode_body": reviewed_patch.text,
                "source_description": "PSKA-Essential reviewed memory patch",
                "reference_time": datetime.now(timezone.utc),
                "group_id": self.group_id,
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
            )
        if self.base_url:
            payload = {
                "group_id": self.group_id,
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
            )
        raise GraphitiAdapterError("Graphiti adapter requires a graphiti client or base_url")

    def delete(self, reviewed_delete: MemoryDelete) -> MemoryApplyResult:
        raise GraphitiAdapterError(
            "Graphiti reviewed memory delete is not configured in the PSKA adapter"
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
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        if not raw and accept_empty:
            return {}
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
    raw = scope.get("group_ids") or scope.get("graphiti_group_ids") or scope.get("group_id") or default
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return [str(raw)]


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
