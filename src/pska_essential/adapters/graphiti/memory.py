from __future__ import annotations

import asyncio
import inspect
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from pska_essential.contracts import (
    MemoryApplyResult,
    MemoryDelete,
    MemoryFact,
    MemoryPatch,
    MemoryUpdate,
    ProvenanceEnvelope,
    SourceRef,
)


class GraphitiAdapterError(RuntimeError):
    pass


_PROVENANCE_PREFIX = "PSKA_PROVENANCE_JSON:"


class GraphitiMemoryAdapter:
    """Graphiti memory adapter with a review-gated write surface.

    This class intentionally exposes only search and reviewed apply. It does
    not forward Graphiti MCP delete/clear/direct add tools to agents.
    """

    backend_name = "graphiti"
    memory_capabilities = {
        "search": True,
        "list": {
            "supported": False,
            "reason": "Graphiti search is supported, but the current adapter does not expose a provider-neutral full memory enumeration endpoint.",
        },
        "get": {
            "supported": False,
            "reason": "Graphiti fact lookup needs a provider fact endpoint plus PSKA provenance mapping.",
        },
        "apply": True,
        "update": {
            "supported": False,
            "reason": "Graphiti reviewed update requires a transactional fact update endpoint.",
        },
        "delete": True,
        "conversation_update_strategies": ["append_correction_episode"],
    }

    def __init__(
        self,
        *,
        client: Any | None = None,
        base_url: str | None = None,
        group_id: str = "pska-essential",
        timeout: float = 120.0,
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/") if base_url else None
        self.group_id = group_id
        self.timeout = timeout

    def search(self, query: str, scope: dict[str, Any], limit: int) -> list[MemoryFact]:
        group_ids = _group_ids(scope, self.group_id)
        if self.client is not None and hasattr(self.client, "search"):
            result = _run_maybe_async(
                self.client.search(query=query, group_ids=group_ids, num_results=limit)
            )
            edges = list(result or [])[:limit]
            episode_provenance = _client_episode_provenance(self.client, group_ids, edges)
            return [_edge_to_fact(edge, episode_provenance) for edge in edges]
        if self.base_url:
            payload = {"query": query, "group_ids": group_ids, "max_facts": limit}
            data = self._post_json("/search", payload)
            facts = list(data.get("facts", [])[:limit])
            episode_ids = _fact_episode_ids(facts)
            episode_provenance = self._http_episode_provenance(group_ids, episode_ids)
            return [_fact_dict_to_fact(item, episode_provenance) for item in facts]
        raise GraphitiAdapterError("Graphiti adapter requires a graphiti client or base_url")

    def list_facts(self, scope: dict[str, Any], limit: int, *, include_inactive: bool = False) -> list[MemoryFact]:
        raise GraphitiAdapterError(
            "Graphiti search is supported, but full provider-neutral memory enumeration is not available"
        )

    def get_fact(self, fact_id: str, scope: dict[str, Any]) -> MemoryFact | None:
        raise GraphitiAdapterError("Graphiti provider-neutral memory fact lookup is not available")

    def apply(self, reviewed_patch: MemoryPatch) -> MemoryApplyResult:
        if not reviewed_patch.source_refs:
            raise GraphitiAdapterError("reviewed memory patch requires source refs")
        episode_uuid = f"pska_{uuid4().hex}"
        group_id = _group_id_from_metadata(reviewed_patch.metadata, self.group_id)
        provenance = ProvenanceEnvelope.from_source_refs(
            reviewed_patch.source_refs,
            metadata={**reviewed_patch.metadata, "graphiti_group_id": group_id, "graphiti_episode_uuid": episode_uuid},
            object_role="derived_memory",
        )
        source_description = _source_description_with_provenance(provenance)
        if self.client is not None and hasattr(self.client, "add_episode"):
            kwargs = {
                "uuid": episode_uuid,
                "name": "PSKA reviewed memory patch",
                "episode_body": reviewed_patch.text,
                "source_description": source_description,
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
                metadata={
                    "group_id": group_id,
                    "provenance": provenance.to_dict(),
                    "source_count": len(reviewed_patch.source_refs),
                },
            )
        if self.base_url:
            payload = {
                "group_id": group_id,
                "messages": [
                    {
                        "uuid": episode_uuid,
                        "name": "PSKA reviewed memory patch",
                        "role": "memory",
                        "role_type": "system",
                        "content": reviewed_patch.text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source_description": source_description,
                    }
                ],
            }
            self._post_json("/messages", payload, accept_empty=True)
            return MemoryApplyResult(
                applied=True,
                target_id=episode_uuid,
                backend=self.backend_name,
                message="Reviewed memory patch queued in Graphiti HTTP service",
                metadata={
                    "group_id": group_id,
                    "provenance": provenance.to_dict(),
                    "source_count": len(reviewed_patch.source_refs),
                },
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
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GraphitiAdapterError(_http_error_message("POST", path, exc)) from exc
        except TimeoutError as exc:
            raise GraphitiAdapterError(f"Graphiti HTTP POST {path} timed out after {self.timeout:g}s") from exc
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        if not raw and accept_empty:
            return {}
        return json.loads(raw or "{}")

    def _delete_json(self, path: str) -> dict[str, Any]:
        req = Request(f"{self.base_url}{path}", method="DELETE")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GraphitiAdapterError(_http_error_message("DELETE", path, exc)) from exc
        except TimeoutError as exc:
            raise GraphitiAdapterError(f"Graphiti HTTP DELETE {path} timed out after {self.timeout:g}s") from exc
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        return json.loads(raw or "{}")

    def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = f"?{urlencode({key: value for key, value in (params or {}).items() if value is not None})}" if params else ""
        req = Request(f"{self.base_url}{path}{query}", method="GET")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise GraphitiAdapterError(_http_error_message("GET", path, exc)) from exc
        except TimeoutError as exc:
            raise GraphitiAdapterError(f"Graphiti HTTP GET {path} timed out after {self.timeout:g}s") from exc
        except URLError as exc:
            raise GraphitiAdapterError(str(exc)) from exc
        return json.loads(raw or "{}")

    def _http_episode_provenance(
        self,
        group_ids: list[str],
        episode_ids: set[str],
    ) -> dict[str, ProvenanceEnvelope]:
        if not episode_ids:
            return {}
        provenance: dict[str, ProvenanceEnvelope] = {}
        last_n = max(10, len(episode_ids))
        for group_id in group_ids:
            try:
                episodes = self._get_json(f"/episodes/{quote(group_id, safe='')}", {"last_n": last_n})
            except GraphitiAdapterError:
                continue
            for episode in _episode_rows(episodes):
                episode_uuid = _episode_uuid(episode)
                if episode_uuid not in episode_ids:
                    continue
                envelope = _extract_episode_provenance(episode)
                if envelope is not None:
                    provenance[episode_uuid] = envelope
        return provenance


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
        return [_graphiti_group_id(str(item), default) for item in raw if item]
    return [_graphiti_group_id(str(raw), default)]


def _group_id_from_metadata(metadata: dict[str, Any], default: str) -> str:
    namespace = str(metadata.get("memory_namespace") or "")
    return _graphiti_group_id(f"{default}:{namespace}" if namespace else default, default)


def _graphiti_group_id(value: str, default: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    if normalized:
        return normalized
    return re.sub(r"[^A-Za-z0-9_-]+", "_", default).strip("_") or "pska"


def _edge_to_fact(
    edge: Any,
    episode_provenance: dict[str, ProvenanceEnvelope] | None = None,
) -> MemoryFact:
    provenance = episode_provenance or {}
    episode_ids = _episode_ids_from_edge(edge)
    direct_provenance = _extract_episode_provenance(edge)
    source_refs = _unique_source_refs(
        [
            *(direct_provenance.source_refs() if direct_provenance is not None else []),
            *_source_refs_from_episode_ids(episode_ids, provenance),
        ]
    )
    fact_id = str(_object_value(edge, "uuid") or _object_value(edge, "id") or uuid4().hex)
    text = str(_object_value(edge, "fact") or _object_value(edge, "name") or edge)
    metadata = {
        "name": _object_value(edge, "name"),
        "group_id": _object_value(edge, "group_id"),
        "episodes": sorted(episode_ids),
    }
    metadata.update(_provenance_metadata_from_direct_envelope(direct_provenance, carrier="edge"))
    metadata.update(_provenance_metadata_from_episode_ids(episode_ids, provenance))
    metadata["lineage_status"] = _lineage_status(episode_ids, source_refs)
    return MemoryFact(
        fact_id=fact_id,
        text=text,
        valid_at=_iso(_object_value(edge, "valid_at")),
        invalid_at=_iso(_object_value(edge, "invalid_at")),
        source_refs=source_refs,
        metadata=metadata,
    )


def _fact_dict_to_fact(
    data: dict[str, Any],
    episode_provenance: dict[str, ProvenanceEnvelope] | None = None,
) -> MemoryFact:
    provenance = episode_provenance or {}
    episode_ids = _episode_ids_from_fact(data)
    direct_provenance = _extract_episode_provenance(data)
    source_refs = _unique_source_refs(
        [
            *(direct_provenance.source_refs() if direct_provenance is not None else []),
            *_source_refs_from_episode_ids(episode_ids, provenance),
        ]
    )
    metadata = {key: value for key, value in data.items() if key not in {"uuid", "fact_id", "fact", "text"}}
    if episode_ids:
        metadata["episodes"] = sorted(episode_ids)
    metadata.update(_provenance_metadata_from_direct_envelope(direct_provenance, carrier="fact"))
    metadata.update(_provenance_metadata_from_episode_ids(episode_ids, provenance))
    metadata["lineage_status"] = _lineage_status(episode_ids, source_refs)
    return MemoryFact(
        fact_id=str(data.get("uuid") or data.get("fact_id") or uuid4().hex),
        text=str(data.get("fact") or data.get("text") or data.get("name") or ""),
        valid_at=data.get("valid_at"),
        invalid_at=data.get("invalid_at"),
        source_refs=source_refs,
        metadata=metadata,
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


def _source_description_with_provenance(envelope: ProvenanceEnvelope) -> str:
    payload = json.dumps(
        envelope.wrapped(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"PSKA-Essential reviewed memory patch\n{_PROVENANCE_PREFIX} {payload}"


def _client_episode_provenance(
    client: Any,
    group_ids: list[str],
    edges: list[Any],
) -> dict[str, ProvenanceEnvelope]:
    episode_ids: set[str] = set()
    for edge in edges:
        episode_ids.update(_episode_ids_from_edge(edge))
    if not episode_ids:
        return {}

    episodes = _fetch_client_episodes(client, group_ids, max(10, len(episode_ids)))
    provenance: dict[str, ProvenanceEnvelope] = {}
    for episode in _episode_rows(episodes):
        episode_uuid = _episode_uuid(episode)
        if episode_uuid not in episode_ids:
            continue
        envelope = _extract_episode_provenance(episode)
        if envelope is not None:
            provenance[episode_uuid] = envelope
    return provenance


def _fetch_client_episodes(client: Any, group_ids: list[str], last_n: int) -> Any:
    now = datetime.now(timezone.utc)
    for method_name in ("retrieve_episodes", "get_episodes"):
        method = getattr(client, method_name, None)
        if not callable(method):
            continue
        attempts = [
            {"group_ids": group_ids, "last_n": last_n, "reference_time": now},
            {"group_ids": group_ids, "last_n": last_n},
            {"group_id": group_ids[0] if group_ids else None, "last_n": last_n},
            {"last_n": last_n},
        ]
        for kwargs in attempts:
            try:
                return _run_maybe_async(method(**kwargs))
            except TypeError:
                continue
            except Exception:
                break
    return getattr(client, "episodes", [])


def _extract_episode_provenance(episode: Any) -> ProvenanceEnvelope | None:
    for value in _episode_provenance_values(episode):
        if isinstance(value, dict):
            try:
                return ProvenanceEnvelope.from_dict(value)
            except Exception:
                continue
        if isinstance(value, str):
            envelope = _parse_provenance_text(value)
            if envelope is not None:
                return envelope
    return None


def _episode_provenance_values(episode: Any) -> list[Any]:
    values: list[Any] = []
    for container in (episode, _object_value(episode, "metadata")):
        if not isinstance(container, dict):
            continue
        for key in ("pska", "provenance", "pska_provenance", "pska_provenance_v1"):
            if key in container:
                values.append(container[key])
    for key in ("source_description", "content", "episode_body", "body", "text"):
        value = _object_value(episode, key)
        if value:
            values.append(value)
    return values


def _parse_provenance_text(text: str) -> ProvenanceEnvelope | None:
    marker = text.find(_PROVENANCE_PREFIX)
    if marker < 0:
        return None
    payload = text[marker + len(_PROVENANCE_PREFIX) :].strip().splitlines()[0].strip()
    if not payload:
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    try:
        return ProvenanceEnvelope.from_dict(parsed)
    except Exception:
        return None


def _episode_rows(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("episodes", "data", "results", "items"):
            nested = value.get(key)
            if isinstance(nested, dict):
                return _episode_rows(nested)
            if isinstance(nested, list):
                return list(nested)
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _episode_uuid(episode: Any) -> str:
    for key in ("uuid", "id", "episode_uuid", "episode_id"):
        value = _object_value(episode, key)
        if value:
            return str(value)
    return ""


def _fact_episode_ids(facts: list[dict[str, Any]]) -> set[str]:
    episode_ids: set[str] = set()
    for fact in facts:
        episode_ids.update(_episode_ids_from_fact(fact))
    return episode_ids


def _episode_ids_from_fact(data: dict[str, Any]) -> set[str]:
    episode_ids: set[str] = set()
    for key in ("episodes", "episode_uuids", "episode_ids", "episode_uuid", "episode_id"):
        episode_ids.update(_episode_ids_from_value(data.get(key)))
    return episode_ids


def _episode_ids_from_edge(edge: Any) -> set[str]:
    episode_ids: set[str] = set()
    for key in ("episodes", "episode_uuids", "episode_ids", "episode_uuid", "episode_id"):
        episode_ids.update(_episode_ids_from_value(_object_value(edge, key)))
    return episode_ids


def _episode_ids_from_value(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, dict):
        episode_uuid = _episode_uuid(value)
        return {episode_uuid} if episode_uuid else set()
    if isinstance(value, (list, tuple, set)):
        episode_ids: set[str] = set()
        for item in value:
            episode_ids.update(_episode_ids_from_value(item))
        return episode_ids
    return {str(value)}


def _source_refs_from_episode_ids(
    episode_ids: set[str],
    episode_provenance: dict[str, ProvenanceEnvelope],
) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for episode_id in sorted(episode_ids):
        envelope = episode_provenance.get(episode_id)
        if envelope is not None:
            refs.extend(envelope.source_refs())
    return _unique_source_refs(refs)


def _provenance_metadata_from_episode_ids(
    episode_ids: set[str],
    episode_provenance: dict[str, ProvenanceEnvelope],
) -> dict[str, Any]:
    envelopes: list[tuple[str, ProvenanceEnvelope]] = [
        (episode_id, episode_provenance[episode_id])
        for episode_id in sorted(episode_ids)
        if episode_id in episode_provenance
    ]
    if not envelopes:
        return {}

    merged: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    for episode_id, envelope in envelopes:
        for key, value in envelope.metadata.items():
            if value not in ("", None, [], {}):
                merged[key] = value
        records.append(
            {
                "episode_id": episode_id,
                "schema": envelope.schema,
                "tenant_id": envelope.tenant_id,
                "workspace_id": envelope.workspace_id,
                "namespace": envelope.namespace,
                "object_role": envelope.object_role,
                "created_by": envelope.created_by,
                "process": envelope.process,
                "timestamps": envelope.timestamps,
                "metadata": envelope.metadata,
                "upstream_count": len(envelope.upstreams),
            }
        )
    merged["pska_provenance"] = {
        "schema": "pska.graphiti_episode_provenance.v1",
        "episode_count": len(records),
        "episodes": records,
    }
    return merged


def _provenance_metadata_from_direct_envelope(
    envelope: ProvenanceEnvelope | None,
    *,
    carrier: str,
) -> dict[str, Any]:
    if envelope is None:
        return {}
    merged = {
        key: value
        for key, value in envelope.metadata.items()
        if value not in ("", None, [], {})
    }
    merged["pska_direct_provenance"] = {
        "schema": "pska.graphiti_direct_provenance.v1",
        "carrier": carrier,
        "provenance_schema": envelope.schema,
        "tenant_id": envelope.tenant_id,
        "workspace_id": envelope.workspace_id,
        "namespace": envelope.namespace,
        "object_role": envelope.object_role,
        "created_by": envelope.created_by,
        "process": envelope.process,
        "timestamps": envelope.timestamps,
        "metadata": envelope.metadata,
        "upstream_count": len(envelope.upstreams),
    }
    return merged


def _unique_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    unique: list[SourceRef] = []
    for ref in source_refs:
        key = _source_ref_key(ref)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique


def _source_ref_key(ref: SourceRef) -> str:
    return json.dumps(
        {
            "adapter": ref.adapter,
            "dataset_id": ref.dataset_id,
            "document_id": ref.document_id,
            "chunk_id": ref.chunk_id,
            "source_id": ref.source_id,
            "external_id": ref.external_id,
            "url": ref.url,
            "path": ref.path,
            "metadata": ref.metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _lineage_status(episode_ids: set[str], source_refs: list[SourceRef]) -> str:
    if source_refs:
        return "resolved"
    return "unresolved"


def _object_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
