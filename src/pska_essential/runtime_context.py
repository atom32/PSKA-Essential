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

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "tenant_id": self.tenant_id,
            "workspace_configured": self.workspace_configured,
            "tenant_configured": self.tenant_configured,
        }


def build_runtime_workspace_context() -> RuntimeWorkspaceContext:
    workspace_id = os.getenv("PSKA_WORKSPACE_ID", "").strip()
    tenant_id = os.getenv("PSKA_TENANT_ID", "").strip()
    return RuntimeWorkspaceContext(
        workspace_id=workspace_id or "default",
        tenant_id=tenant_id,
        workspace_configured=bool(workspace_id),
        tenant_configured=bool(tenant_id),
    )
