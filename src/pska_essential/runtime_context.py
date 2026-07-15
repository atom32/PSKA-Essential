from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RuntimeWorkspaceContext:
    workspace_id: str
    tenant_id: str
    workspace_configured: bool
    tenant_configured: bool
    memory_namespace: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "tenant_id": self.tenant_id,
            "workspace_configured": self.workspace_configured,
            "tenant_configured": self.tenant_configured,
            "memory_namespace": self.memory_namespace,
        }


def build_runtime_workspace_context() -> RuntimeWorkspaceContext:
    workspace_id = os.getenv("PSKA_WORKSPACE_ID", "").strip()
    tenant_id = os.getenv("PSKA_TENANT_ID", "").strip()
    resolved_workspace_id = workspace_id or "default"
    memory_namespace = build_memory_namespace(
        workspace_id=resolved_workspace_id,
        tenant_id=tenant_id,
        workspace_configured=bool(workspace_id),
        tenant_configured=bool(tenant_id),
    )
    return RuntimeWorkspaceContext(
        workspace_id=resolved_workspace_id,
        tenant_id=tenant_id,
        workspace_configured=bool(workspace_id),
        tenant_configured=bool(tenant_id),
        memory_namespace=memory_namespace,
    )


def build_runtime_memory_scope(scope: dict[str, Any] | None = None) -> dict[str, Any]:
    context = build_runtime_workspace_context()
    payload = dict(scope or {})
    payload.setdefault("workspace_id", context.workspace_id)
    payload.setdefault("tenant_id", context.tenant_id)
    payload.setdefault("workspace_configured", context.workspace_configured)
    payload.setdefault("tenant_configured", context.tenant_configured)
    if context.memory_namespace:
        payload.setdefault("memory_namespace", context.memory_namespace)
    return payload


def build_memory_namespace(
    *,
    workspace_id: str,
    tenant_id: str = "",
    workspace_configured: bool = False,
    tenant_configured: bool = False,
) -> str:
    if not workspace_configured and not tenant_configured:
        return ""
    parts = [f"workspace:{workspace_id or 'default'}"]
    if tenant_id:
        parts.append(f"tenant:{tenant_id}")
    return ":".join(parts)
