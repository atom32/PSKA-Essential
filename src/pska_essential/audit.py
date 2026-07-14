from __future__ import annotations

from uuid import uuid4

from pska_essential.contracts import AuditEvent
from pska_essential.runtime_context import build_runtime_workspace_context


def audit_event(action: str, target_type: str, target_id: str, **metadata) -> AuditEvent:
    context = build_runtime_workspace_context().to_dict()
    event_metadata = dict(metadata)
    event_metadata.setdefault("workspace_id", context["workspace_id"])
    event_metadata.setdefault("tenant_id", context["tenant_id"])
    event_metadata.setdefault("workspace_configured", context["workspace_configured"])
    event_metadata.setdefault("tenant_configured", context["tenant_configured"])
    return AuditEvent(
        audit_event_id=f"aud_{uuid4().hex}",
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=event_metadata,
    )
