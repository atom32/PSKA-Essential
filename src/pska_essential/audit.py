from __future__ import annotations

from uuid import uuid4

from pska_essential.contracts import AuditEvent


def audit_event(action: str, target_type: str, target_id: str, **metadata) -> AuditEvent:
    return AuditEvent(
        audit_event_id=f"aud_{uuid4().hex}",
        action=action,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata,
    )
