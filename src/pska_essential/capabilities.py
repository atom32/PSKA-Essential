from __future__ import annotations

from typing import Any


MEMORY_OPERATIONS = ("search", "apply", "update", "delete")


def memory_capabilities(adapter: Any) -> dict[str, Any]:
    """Return PSKA-level memory operation capabilities for an adapter."""

    raw = getattr(adapter, "memory_capabilities", {}) or {}
    operations = {
        operation: _operation_capability(adapter, raw, operation)
        for operation in MEMORY_OPERATIONS
    }
    return {
        "backend": str(getattr(adapter, "backend_name", "custom")),
        "operations": operations,
    }


def memory_operation_capability(adapter: Any, operation: str) -> dict[str, Any]:
    return memory_capabilities(adapter)["operations"].get(operation, {"supported": False})


def memory_operation_supported(adapter: Any, operation: str) -> bool:
    return bool(memory_operation_capability(adapter, operation).get("supported", False))


def _operation_capability(adapter: Any, raw: dict[str, Any], operation: str) -> dict[str, Any]:
    entry = raw.get(operation)
    if isinstance(entry, dict):
        supported = bool(entry.get("supported", False))
        reason = str(entry.get("reason") or "")
    elif isinstance(entry, bool):
        supported = entry
        reason = ""
    else:
        supported = callable(getattr(adapter, operation, None))
        reason = "" if supported else f"adapter does not expose {operation}"
    payload: dict[str, Any] = {"supported": supported}
    if reason:
        payload["reason"] = reason
    return payload
