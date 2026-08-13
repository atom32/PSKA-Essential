from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import SourceRef, to_jsonable, utc_now_iso


EIDOLIA_PROJECT_TRACE_IMPORT_SCHEMA = "pska.eidolia_project_trace_import.v1"
EIDOLIA_NODE_REF_SCHEMA = "pska.eidolia_node_ref.v1"
EIDOLIA_TRACE_REF_SCHEMA = "pska.eidolia_agentic_trace_ref.v1"
_MAX_JSON_BYTES = 20_000_000


class EidoliaImportError(ValueError):
    pass


def import_eidolia_project_traces(
    service: Any,
    *,
    project_path: str = "",
    workspace_path: str = "",
    trace_paths: list[str] | None = None,
    node_limit: int = 100,
    trace_limit: int = 50,
    audit: bool = True,
) -> dict[str, Any]:
    paths = _resolve_import_paths(
        project_path=project_path,
        workspace_path=workspace_path,
        trace_paths=trace_paths or [],
        trace_limit=trace_limit,
    )
    workspace = _read_json_file(paths["workspace_path"]) if paths.get("workspace_path") else {}
    if not isinstance(workspace, dict):
        raise EidoliaImportError("Eidolia workspace JSON must be an object")
    raw_project_id = str(workspace.get("projectId") or workspace.get("project_id") or paths["project_id"] or "").strip()
    project_id = raw_project_id or _project_id_from_paths(paths)
    if not project_id:
        raise EidoliaImportError("Eidolia project import requires project_id, project_path, or workspace_path")

    raw_nodes = workspace.get("nodes") if isinstance(workspace.get("nodes"), list) else []
    raw_edges = workspace.get("edges") if isinstance(workspace.get("edges"), list) else []
    imported_nodes = _import_nodes(
        raw_nodes,
        project_id=project_id,
        workspace_path=str(paths.get("workspace_path") or ""),
        limit=max(0, int(node_limit)),
    )
    node_refs_by_id = {node["node_id"]: node["source_ref"] for node in imported_nodes}
    imported_edges = _import_edges(raw_edges, node_refs_by_id)
    imported_traces = _import_traces(
        paths.get("trace_paths") or [],
        project_id=project_id,
        project_path=str(paths.get("project_path") or ""),
        node_refs_by_id=node_refs_by_id,
        limit=max(0, int(trace_limit)),
    )
    source_refs = _unique_source_refs(
        [
            *(node["source_ref"] for node in imported_nodes),
            *(trace["source_ref"] for trace in imported_traces),
        ]
    )
    import_id = f"eidimp_{uuid4().hex}"
    result = {
        "schema": EIDOLIA_PROJECT_TRACE_IMPORT_SCHEMA,
        "import_id": import_id,
        "created_at": utc_now_iso(),
        "status": "imported" if imported_nodes or imported_traces else "empty",
        "project": {
            "project_id": project_id,
            "project_path": str(paths.get("project_path") or ""),
            "workspace_path": str(paths.get("workspace_path") or ""),
            "trace_paths": [str(path) for path in paths.get("trace_paths") or []],
            "read_mode": "project_files",
            "canonical_owner": "eidolia_project",
        },
        "summary": {
            "workspace_node_count": len(raw_nodes),
            "imported_node_count": len(imported_nodes),
            "edge_count": len(raw_edges),
            "imported_edge_count": len(imported_edges),
            "trace_file_count": len(paths.get("trace_paths") or []),
            "imported_trace_count": len(imported_traces),
            "source_ref_count": len(source_refs),
        },
        "nodes": imported_nodes,
        "edges": imported_edges,
        "traces": imported_traces,
        "source_refs": source_refs,
        "data_flow": {
            "reads_project_files": True,
            "writes_source_files": False,
            "writes_memory_directly": False,
            "writes_audit": bool(audit),
            "embedding_required": False,
            "creates_review": False,
        },
        "limitations": [
            "This import reads explicit Eidolia project JSON files only.",
            "It records PSKA audit trace references; it does not copy the canvas into a PSKA canonical store.",
            "It does not mutate Eidolia project files or create durable memory reviews.",
        ],
    }
    if audit:
        _write_import_audit(service, result)
    return to_jsonable(result)


def _resolve_import_paths(
    *,
    project_path: str,
    workspace_path: str,
    trace_paths: list[str],
    trace_limit: int,
) -> dict[str, Any]:
    normalized_project = _optional_path(project_path)
    normalized_workspace = _optional_path(workspace_path)
    if normalized_project is None and normalized_workspace is None and not trace_paths:
        raise EidoliaImportError("Eidolia project import requires project_path, workspace_path, or trace_paths")
    if normalized_project is not None and (not normalized_project.exists() or not normalized_project.is_dir()):
        raise EidoliaImportError(f"project_path not found: {normalized_project}")
    if normalized_project is None and normalized_workspace is not None:
        normalized_project = normalized_workspace.parent
    if normalized_workspace is None and normalized_project is not None:
        candidate = normalized_project / "canvas-workspace.json"
        normalized_workspace = candidate if candidate.exists() else None
    normalized_traces = [_required_json_path(path) for path in trace_paths]
    if not normalized_traces and normalized_project is not None:
        trace_dir = normalized_project / "agentic-traces"
        if trace_dir.exists():
            normalized_traces = sorted(trace_dir.glob("*.json"))[: max(0, int(trace_limit))]
    if normalized_workspace is not None:
        _ensure_file(normalized_workspace, "workspace_path")
    for trace_path in normalized_traces:
        _ensure_file(trace_path, "trace_paths")
    return {
        "project_path": normalized_project,
        "workspace_path": normalized_workspace,
        "trace_paths": normalized_traces[: max(0, int(trace_limit))],
        "project_id": normalized_project.name if normalized_project is not None else "",
    }


def _import_nodes(
    raw_nodes: list[Any],
    *,
    project_id: str,
    workspace_path: str,
    limit: int,
) -> list[dict[str, Any]]:
    imported = []
    for node in raw_nodes:
        if len(imported) >= limit:
            break
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        if not node_id:
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        semantic_type = _semantic_node_type(node, data)
        if semantic_type not in {"thought", "artifact"}:
            continue
        title = _node_title(node_id, data)
        artifact_kind = _artifact_kind(node, data, semantic_type)
        role = str(data.get("role") or data.get("category") or "").strip()
        source_ref = _eidolia_source_ref(
            project_id=project_id,
            node_id=node_id,
            node_type=semantic_type,
            title=title,
            canvas_path=f"{workspace_path}#{node_id}" if workspace_path else f"{project_id}/canvas-workspace.json#{node_id}",
            role=role,
            artifact_kind=artifact_kind,
            metadata={
                "display_type": str(node.get("type") or ""),
                "subtype": str(data.get("subtype") or ""),
                "read_mode": "project_files",
            },
        )
        text = _node_text(data)
        imported.append(
            {
                "schema": EIDOLIA_NODE_REF_SCHEMA,
                "node_id": node_id,
                "node_type": semantic_type,
                "display_type": str(node.get("type") or ""),
                "title": title,
                "role": role,
                "artifact_kind": artifact_kind,
                "text_preview": _preview(text),
                "char_count": len(text),
                "source_ref": to_jsonable(source_ref),
            }
        )
    return imported


def _import_edges(raw_edges: list[Any], node_refs_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    imported = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        source_id = str(edge.get("source") or edge.get("sourceId") or edge.get("source_id") or "").strip()
        target_id = str(edge.get("target") or edge.get("targetId") or edge.get("target_id") or "").strip()
        if not source_id or not target_id:
            continue
        if source_id not in node_refs_by_id or target_id not in node_refs_by_id:
            continue
        data = edge.get("data") if isinstance(edge.get("data"), dict) else {}
        imported.append(
            {
                "edge_id": str(edge.get("id") or f"{source_id}->{target_id}"),
                "source_node_id": source_id,
                "target_node_id": target_id,
                "relation": str(data.get("relation") or data.get("semantic") or edge.get("label") or edge.get("type") or ""),
                "source_ref": node_refs_by_id[source_id],
                "target_ref": node_refs_by_id[target_id],
            }
        )
    return imported


def _import_traces(
    trace_paths: list[Path],
    *,
    project_id: str,
    project_path: str,
    node_refs_by_id: dict[str, dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    imported = []
    for trace_path in trace_paths[:limit]:
        payload = _read_json_file(trace_path)
        if not isinstance(payload, dict):
            continue
        trace_project_id = str(payload.get("project_id") or payload.get("projectId") or project_id).strip() or project_id
        trace_id = str(payload.get("run_id") or payload.get("trace_id") or trace_path.stem).strip()
        trace_kind = str(payload.get("kind") or payload.get("trace_kind") or "agentic_trace").strip()
        linked_node_ids = _trace_node_ids(payload)
        linked_refs = [node_refs_by_id[node_id] for node_id in linked_node_ids if node_id in node_refs_by_id]
        trace_ref = _trace_source_ref(
            project_id=trace_project_id,
            trace_id=trace_id,
            trace_path=trace_path,
            project_path=project_path,
            trace_kind=trace_kind,
            linked_node_ids=linked_node_ids,
            title=str(payload.get("title") or trace_path.stem),
        )
        text = str(payload.get("content") or payload.get("final_content") or payload.get("final_answer") or payload.get("notes") or "")
        imported.append(
            {
                "schema": EIDOLIA_TRACE_REF_SCHEMA,
                "trace_id": trace_id,
                "trace_kind": trace_kind,
                "run_id": str(payload.get("run_id") or ""),
                "title": str(payload.get("title") or trace_path.stem),
                "created_at": str(payload.get("created_at") or payload.get("createdAt") or ""),
                "start_node_id": str(payload.get("start_node_id") or payload.get("startNodeId") or ""),
                "linked_node_ids": linked_node_ids,
                "linked_node_refs": linked_refs,
                "text_preview": _preview(text),
                "source_ref": to_jsonable(trace_ref),
            }
        )
    return imported


def _write_import_audit(service: Any, result: dict[str, Any]) -> None:
    project = result["project"]
    summary = result["summary"]
    service.store.add_audit_event(
        audit_event(
            "eidolia.project_trace.import",
            "eidolia_project",
            project["project_id"],
            import_id=result["import_id"],
            project_id=project["project_id"],
            project_path=project["project_path"],
            workspace_path=project["workspace_path"],
            node_count=summary["imported_node_count"],
            trace_count=summary["imported_trace_count"],
            source_refs=result["source_refs"],
            writes_source_files=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
    for node in result["nodes"]:
        service.store.add_audit_event(
            audit_event(
                "eidolia.node.import",
                "eidolia_node",
                node["node_id"],
                import_id=result["import_id"],
                project_id=project["project_id"],
                node_id=node["node_id"],
                node_type=node["node_type"],
                display_type=node["display_type"],
                title=node["title"],
                source_ref=node["source_ref"],
                writes_source_files=False,
                writes_memory_directly=False,
                embedding_required=False,
            )
        )
    for trace in result["traces"]:
        refs = _unique_source_refs([trace["source_ref"], *(trace.get("linked_node_refs") or [])])
        service.store.add_audit_event(
            audit_event(
                "eidolia.agentic_trace.import",
                "eidolia_trace",
                trace["trace_id"],
                import_id=result["import_id"],
                project_id=project["project_id"],
                trace_id=trace["trace_id"],
                trace_kind=trace["trace_kind"],
                run_id=trace["run_id"],
                start_node_id=trace["start_node_id"],
                linked_node_ids=trace["linked_node_ids"],
                source_refs=refs,
                writes_source_files=False,
                writes_memory_directly=False,
                embedding_required=False,
            )
        )


def _eidolia_source_ref(
    *,
    project_id: str,
    node_id: str,
    node_type: str,
    title: str,
    canvas_path: str,
    role: str,
    artifact_kind: str,
    metadata: dict[str, Any],
) -> SourceRef:
    values = {
        "source_layer": "thought_artifact",
        "project_id": project_id,
        "node_id": node_id,
        "node_type": node_type,
        "role": role,
        "artifact_kind": artifact_kind,
        "canvas_path": canvas_path,
        "canonical_owner": "eidolia_project",
        "writes_source_files": False,
    }
    values.update({str(key): value for key, value in metadata.items()})
    return SourceRef(
        adapter="eidolia",
        source_id=project_id,
        external_id=node_id,
        title=title or node_id,
        path=canvas_path,
        metadata=values,
    )


def _trace_source_ref(
    *,
    project_id: str,
    trace_id: str,
    trace_path: Path,
    project_path: str,
    trace_kind: str,
    linked_node_ids: list[str],
    title: str,
) -> SourceRef:
    path = str(trace_path)
    if project_path:
        try:
            path = str(trace_path.relative_to(project_path))
        except ValueError:
            path = str(trace_path)
    return SourceRef(
        adapter="eidolia",
        source_id=project_id,
        external_id=trace_id,
        title=title or trace_id,
        path=path,
        metadata={
            "source_layer": "thought_artifact",
            "project_id": project_id,
            "trace_id": trace_id,
            "trace_kind": trace_kind,
            "linked_node_ids": linked_node_ids,
            "canonical_owner": "eidolia_project",
            "writes_source_files": False,
        },
    )


def _semantic_node_type(node: dict[str, Any], data: dict[str, Any]) -> str:
    kind = str(data.get("kind") or "").strip().lower()
    if kind in {"thought", "artifact"}:
        return kind
    display_type = str(node.get("type") or "").strip().lower()
    if display_type == "thought":
        return "thought"
    if display_type in {"note", "chapter", "draft"}:
        return "artifact"
    return ""


def _artifact_kind(node: dict[str, Any], data: dict[str, Any], semantic_type: str) -> str:
    if semantic_type != "artifact":
        return ""
    return str(data.get("subtype") or data.get("artifact_kind") or node.get("type") or "").strip()


def _node_title(node_id: str, data: dict[str, Any]) -> str:
    return str(data.get("title") or data.get("label") or data.get("name") or node_id).strip()


def _node_text(data: dict[str, Any]) -> str:
    for key in ("content", "text", "body", "summary", "description"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _trace_node_ids(payload: dict[str, Any]) -> list[str]:
    values = []
    for key in (
        "start_node_id",
        "startNodeId",
        "derived_from_node_ids",
        "derivedFromNodeIds",
        "supporting_node_ids",
        "supportingNodeIds",
        "challenge_node_ids",
        "challengeNodeIds",
        "requested_canvas_node_ids",
        "requestedCanvasNodeIds",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
        elif value:
            values.append(str(value).strip())
    return _unique_strings(values)


def _read_json_file(path: Path) -> Any:
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise EidoliaImportError(f"JSON file too large: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EidoliaImportError(f"invalid JSON file: {path}") from exc


def _optional_path(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _required_json_path(value: str) -> Path:
    path = _optional_path(value)
    if path is None:
        raise EidoliaImportError("trace path cannot be empty")
    if path.suffix.lower() != ".json":
        raise EidoliaImportError(f"trace path must be a JSON file: {path}")
    return path


def _ensure_file(path: Path, label: str) -> None:
    if not path.exists() or not path.is_file():
        raise EidoliaImportError(f"{label} not found: {path}")


def _project_id_from_paths(paths: dict[str, Any]) -> str:
    project_path = paths.get("project_path")
    if isinstance(project_path, Path):
        return project_path.name
    workspace_path = paths.get("workspace_path")
    if isinstance(workspace_path, Path):
        return workspace_path.parent.name
    trace_paths = paths.get("trace_paths") or []
    if trace_paths:
        return trace_paths[0].parent.parent.name
    return ""


def _preview(text: str, limit: int = 280) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _unique_source_refs(values: list[Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for value in values:
        if not isinstance(value, dict):
            value = to_jsonable(value)
        key = json.dumps(
            [
                value.get("adapter") or "",
                value.get("source_id") or "",
                value.get("external_id") or "",
                value.get("path") or "",
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
