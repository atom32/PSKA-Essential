from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar


T = TypeVar("T")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


@dataclass(slots=True)
class SourceRef:
    adapter: str
    dataset_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    source_id: str | None = None
    title: str | None = None
    url: str | None = None
    path: str | None = None
    external_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceRef":
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: data.get(key) for key in allowed if key in data})


PROVENANCE_SCHEMA = "pska.provenance.v1"


@dataclass(slots=True)
class ProvenanceEnvelope:
    schema: str = PROVENANCE_SCHEMA
    tenant_id: str = ""
    workspace_id: str = "default"
    namespace: str = ""
    object_role: str = "derived_memory"
    created_by: dict[str, Any] = field(default_factory=dict)
    process: dict[str, Any] = field(default_factory=dict)
    upstreams: list[dict[str, Any]] = field(default_factory=list)
    timestamps: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_source_refs(
        cls,
        source_refs: list[SourceRef],
        *,
        metadata: dict[str, Any] | None = None,
        object_role: str = "derived_memory",
    ) -> "ProvenanceEnvelope":
        values = dict(metadata or {})
        now = utc_now_iso()
        return cls(
            tenant_id=str(values.get("tenant_id") or ""),
            workspace_id=str(values.get("workspace_id") or "default"),
            namespace=str(values.get("memory_namespace") or values.get("namespace") or ""),
            object_role=object_role,
            created_by={
                "component": "pska",
                "agent_host": values.get("agent_host") or _agent_host_from_sources(source_refs),
                "agent_id": values.get("agent_id") or "",
            },
            process={
                "workflow_id": values.get("run_id") or values.get("workflow_id") or "",
                "proposal_id": values.get("proposal_id") or "",
                "review_id": values.get("review_id") or "",
                "policy_version": values.get("policy_version") or values.get("governance_action") or "",
            },
            upstreams=[_source_ref_to_upstream(ref) for ref in source_refs],
            timestamps={
                "observed_at": values.get("observed_at") or "",
                "created_at": values.get("created_at") or now,
                "reviewed_at": values.get("reviewed_at") or "",
                "applied_at": values.get("applied_at") or now,
            },
            metadata={
                key: value
                for key, value in values.items()
                if key
                not in {
                    "agent_host",
                    "agent_id",
                    "tenant_id",
                    "workspace_id",
                    "memory_namespace",
                    "namespace",
                    "run_id",
                    "workflow_id",
                    "proposal_id",
                    "review_id",
                    "policy_version",
                    "governance_action",
                    "observed_at",
                    "created_at",
                    "reviewed_at",
                    "applied_at",
                }
            },
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceEnvelope":
        payload = dict(data.get("pska") or data)
        allowed = set(cls.__dataclass_fields__)
        return cls(**{key: payload.get(key) for key in allowed if key in payload})

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def wrapped(self) -> dict[str, Any]:
        return {"pska": self.to_dict()}

    def source_refs(self) -> list[SourceRef]:
        refs: list[SourceRef] = []
        for upstream in self.upstreams:
            source_ref = upstream.get("source_ref")
            if isinstance(source_ref, dict):
                refs.append(SourceRef.from_dict(source_ref))
                continue
            adapter = str(upstream.get("component") or upstream.get("adapter") or "")
            if not adapter:
                continue
            refs.append(
                SourceRef(
                    adapter=adapter,
                    dataset_id=_optional_text(upstream.get("dataset_id")),
                    document_id=_optional_text(upstream.get("document_id")),
                    chunk_id=_optional_text(upstream.get("chunk_id")),
                    source_id=_optional_text(upstream.get("source_id")),
                    title=_optional_text(upstream.get("title")),
                    url=_optional_text(upstream.get("url")),
                    path=_optional_text(upstream.get("path")),
                    external_id=_optional_text(upstream.get("external_id")),
                    metadata=dict(upstream.get("metadata") or {}),
                )
            )
        return refs


def _source_ref_to_upstream(ref: SourceRef) -> dict[str, Any]:
    if ref.chunk_id:
        object_type = "chunk"
    elif ref.document_id:
        object_type = "document"
    elif ref.adapter in {"conversation", "hermes"}:
        object_type = "message"
    else:
        object_type = "source"
    metadata = dict(ref.metadata or {})
    content_hash = metadata.get("content_hash") or metadata.get("excerpt_hash") or ""
    return {
        "component": ref.adapter,
        "object_type": object_type,
        "dataset_id": ref.dataset_id or "",
        "document_id": ref.document_id or "",
        "chunk_id": ref.chunk_id or "",
        "source_id": ref.source_id or "",
        "external_id": ref.external_id or "",
        "title": ref.title or "",
        "url": ref.url or "",
        "path": ref.path or "",
        "content_hash": content_hash,
        "metadata": metadata,
        "source_ref": to_jsonable(ref),
    }


def _agent_host_from_sources(source_refs: list[SourceRef]) -> str:
    if any(ref.adapter == "hermes" for ref in source_refs):
        return "hermes"
    if any(ref.adapter == "conversation" for ref in source_refs):
        return "conversation"
    return ""


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


@dataclass(slots=True)
class ContextPacket:
    context_id: str
    text: str
    source_ref: SourceRef
    score: float = 0.0
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPacket":
        payload = dict(data)
        payload["source_ref"] = SourceRef.from_dict(payload["source_ref"])
        return cls(**payload)


@dataclass(slots=True)
class SourceContext:
    source_ref: SourceRef
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowRun:
    run_id: str
    intent: str
    scope: dict[str, Any]
    status: str = "active"
    context_packets: list[ContextPacket] = field(default_factory=list)
    proposal_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowRun":
        payload = dict(data)
        payload["context_packets"] = [
            ContextPacket.from_dict(item) for item in payload.get("context_packets", [])
        ]
        return cls(**payload)


@dataclass(slots=True)
class MemoryPatch:
    text: str
    source_refs: list[SourceRef]
    layer: str = "semantic"
    confidence: float = 0.8
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryPatch":
        payload = dict(data)
        payload["source_refs"] = [SourceRef.from_dict(item) for item in payload.get("source_refs", [])]
        return cls(**payload)


@dataclass(slots=True)
class MemoryDelete:
    target_id: str
    source_refs: list[SourceRef]
    reason: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryDelete":
        allowed = set(cls.__dataclass_fields__)
        payload = {key: data.get(key) for key in allowed if key in data}
        payload["source_refs"] = [SourceRef.from_dict(item) for item in payload.get("source_refs", [])]
        return cls(**payload)


@dataclass(slots=True)
class MemoryUpdate:
    target_id: str
    text: str
    source_refs: list[SourceRef]
    previous_text: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryUpdate":
        allowed = set(cls.__dataclass_fields__)
        payload = {key: data.get(key) for key in allowed if key in data}
        payload["source_refs"] = [SourceRef.from_dict(item) for item in payload.get("source_refs", [])]
        return cls(**payload)


@dataclass(slots=True)
class Proposal:
    proposal_id: str
    run_id: str
    kind: str
    intent: str
    title: str
    body: str
    source_refs: list[SourceRef]
    memory_patch: MemoryPatch | None = None
    memory_delete: MemoryDelete | None = None
    memory_update: MemoryUpdate | None = None
    status: str = "proposed"
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Proposal":
        payload = dict(data)
        payload["source_refs"] = [SourceRef.from_dict(item) for item in payload.get("source_refs", [])]
        if payload.get("memory_patch"):
            payload["memory_patch"] = MemoryPatch.from_dict(payload["memory_patch"])
        if payload.get("memory_delete"):
            payload["memory_delete"] = MemoryDelete.from_dict(payload["memory_delete"])
        if payload.get("memory_update"):
            payload["memory_update"] = MemoryUpdate.from_dict(payload["memory_update"])
        return cls(**payload)


@dataclass(slots=True)
class ReviewBatch:
    review_id: str
    proposal_id: str
    status: str = "pending"
    created_at: str = field(default_factory=utc_now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReviewDecision:
    review_id: str
    proposal_id: str
    decision: str
    reason: str
    status: str
    decided_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class MemoryFact:
    fact_id: str
    text: str
    source_refs: list[SourceRef] = field(default_factory=list)
    valid_at: str | None = None
    invalid_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryFact":
        allowed = set(cls.__dataclass_fields__)
        payload = {key: data.get(key) for key in allowed if key in data}
        payload["source_refs"] = [SourceRef.from_dict(item) for item in payload.get("source_refs", [])]
        return cls(**payload)


@dataclass(slots=True)
class MemoryApplyResult:
    applied: bool
    target_id: str | None = None
    backend: str | None = None
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditEvent:
    audit_event_id: str
    action: str
    target_type: str
    target_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
