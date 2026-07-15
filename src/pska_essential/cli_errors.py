from __future__ import annotations

import os
from typing import Any


def startup_error_payload(kind: str, exc: Exception, *, operation: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": "error",
        "message": f"{operation} startup failed: {exc}",
        "providers": provider_snapshot(),
        "steps": [
            {
                "name": "runtime.startup",
                "status": "error",
                "message": str(exc),
                "required": True,
                "metadata": {"error_type": exc.__class__.__name__},
            }
        ],
        "next_actions": [
            {
                "action": "fix_runtime_config",
                "label": "Fix runtime configuration",
                "reason": str(exc),
                "view": "settings",
            }
        ],
    }


def missing_scope_payload(kind: str, *, message: str, env_var: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "status": "incomplete",
        "message": message,
        "providers": provider_snapshot(),
        "scope": {"dataset_ids": [], "document_ids": []},
        "steps": [
            {
                "name": "scope.check",
                "status": "incomplete",
                "message": message,
                "required": True,
                "metadata": {"env_var": env_var},
            }
        ],
        "next_actions": [
            {
                "action": "select_ready_dataset",
                "label": "Select dataset",
                "reason": message,
                "view": "kb",
                "requires_input": [env_var],
            }
        ],
    }


def provider_snapshot() -> dict[str, Any]:
    return {
        "retrieval": os.getenv("PSKA_RETRIEVAL_PROVIDER", "").strip().lower(),
        "kb": os.getenv("PSKA_KB_PROVIDER", "").strip().lower(),
        "memory": os.getenv("PSKA_MEMORY_PROVIDER", "").strip().lower(),
        "dev_fake": os.getenv("PSKA_DEV_FAKE", "").strip().lower() in {"1", "true", "yes", "on"},
    }
