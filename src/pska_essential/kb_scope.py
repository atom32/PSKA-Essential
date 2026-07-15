from __future__ import annotations

from typing import Any


def resolve_dataset_scope(
    gateway: Any,
    *,
    dataset_ids: list[str] | None = None,
    dataset_names: list[str] | None = None,
) -> dict[str, Any]:
    """Resolve user-facing dataset names into PSKA canonical dataset IDs."""

    selected_ids = _deduped([str(item).strip() for item in dataset_ids or [] if str(item).strip()])
    selected_names = _deduped([str(item).strip() for item in dataset_names or [] if str(item).strip()])
    resolved_names: list[dict[str, str]] = []
    unresolved_names: list[str] = []
    ambiguous_names: list[dict[str, Any]] = []

    for name in selected_names:
        matches = [
            item
            for item in gateway.list_datasets(name=name, page_size=100)
            if str(item.get("name") or "") == name and str(item.get("dataset_id") or "").strip()
        ]
        if not matches:
            unresolved_names.append(name)
            continue
        if len(matches) > 1:
            ambiguous_names.append(
                {
                    "name": name,
                    "dataset_ids": [str(item.get("dataset_id") or "") for item in matches],
                }
            )
            continue
        dataset_id = str(matches[0].get("dataset_id") or "")
        if dataset_id not in selected_ids:
            selected_ids.append(dataset_id)
        resolved_names.append({"name": name, "dataset_id": dataset_id})

    return {
        "dataset_ids": selected_ids,
        "dataset_names": selected_names,
        "resolved_dataset_names": resolved_names,
        "unresolved_dataset_names": unresolved_names,
        "ambiguous_dataset_names": ambiguous_names,
    }


def dataset_scope_has_resolution_errors(scope: dict[str, Any]) -> bool:
    return bool(scope.get("unresolved_dataset_names") or scope.get("ambiguous_dataset_names"))


def dataset_scope_resolution_message(scope: dict[str, Any]) -> str:
    unresolved = [str(item) for item in scope.get("unresolved_dataset_names") or []]
    ambiguous = [str(item.get("name") or "") for item in scope.get("ambiguous_dataset_names") or []]
    parts: list[str] = []
    if unresolved:
        parts.append(f"unresolved dataset name(s): {', '.join(unresolved)}")
    if ambiguous:
        parts.append(f"ambiguous dataset name(s): {', '.join(ambiguous)}")
    if parts:
        return "Cannot resolve selected dataset scope; " + "; ".join(parts) + "."
    if not scope.get("dataset_ids"):
        return "dataset_ids or dataset_names are required for this operation."
    return "Selected dataset scope resolved."


def _deduped(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
