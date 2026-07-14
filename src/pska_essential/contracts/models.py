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
