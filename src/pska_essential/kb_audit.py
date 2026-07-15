from __future__ import annotations

from typing import Any

from pska_essential.audit import audit_event


def add_kb_dataset_create_audit(store: Any, dataset: dict[str, Any]) -> None:
    dataset_id = str(dataset.get("dataset_id") or dataset.get("id") or "")
    dataset_name = str(dataset.get("name") or "")
    store.add_audit_event(
        audit_event(
            "kb.dataset.create",
            "dataset",
            dataset_id or dataset_name or "unknown",
            backend=str(dataset.get("backend") or ""),
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            chunk_method=str(dataset.get("chunk_method") or ""),
            permission=str(dataset.get("permission") or ""),
        )
    )


def add_kb_dataset_delete_audit(store: Any, result: dict[str, Any]) -> None:
    dataset_ids = [str(dataset_id) for dataset_id in result.get("dataset_ids") or []]
    dataset_names = [str(dataset_name) for dataset_name in result.get("dataset_names") or []]
    deleted_dataset_ids = [str(dataset_id) for dataset_id in result.get("deleted_dataset_ids") or []]
    target_id = ",".join(dataset_ids or deleted_dataset_ids or dataset_names) or ("all" if result.get("delete_all") else "unknown")
    store.add_audit_event(
        audit_event(
            "kb.dataset.delete",
            "dataset",
            target_id,
            backend=str(result.get("backend") or ""),
            dataset_ids=dataset_ids,
            dataset_names=dataset_names,
            deleted_dataset_ids=deleted_dataset_ids,
            delete_all=bool(result.get("delete_all")),
            deleted=bool(result.get("deleted")),
        )
    )


def add_kb_ingest_audit(store: Any, result: dict[str, Any]) -> None:
    dataset = result.get("dataset") or {}
    documents = result.get("documents") or []
    parse = result.get("parse") or {}
    dataset_id = str(dataset.get("dataset_id") or "")
    document_ids = [str(document.get("document_id") or "") for document in documents if document.get("document_id")]
    document_names = [str(document.get("name") or "") for document in documents if document.get("name")]
    store.add_audit_event(
        audit_event(
            "kb.ingest",
            "dataset",
            dataset_id or str(dataset.get("name") or "unknown"),
            backend=str(result.get("backend") or dataset.get("backend") or ""),
            dataset_id=dataset_id,
            dataset_name=str(dataset.get("name") or ""),
            dataset_created=bool(result.get("dataset_created")),
            document_count=len(documents),
            document_ids=document_ids,
            document_names=document_names,
            parse_started=bool(parse.get("parse_started")) if isinstance(parse, dict) else False,
        )
    )


def add_kb_parse_audit(store: Any, result: dict[str, Any]) -> None:
    dataset_id = str(result.get("dataset_id") or "")
    document_ids = [str(document_id) for document_id in result.get("document_ids") or []]
    store.add_audit_event(
        audit_event(
            "kb.parse",
            "dataset",
            dataset_id or "unknown",
            backend=str(result.get("backend") or ""),
            dataset_id=dataset_id,
            document_ids=document_ids,
            parse_started=bool(result.get("parse_started")),
        )
    )


def add_kb_graph_read_audit(store: Any, graph: dict[str, Any], *, dataset_id: str, document_id: str) -> None:
    store.add_audit_event(
        audit_event(
            "kb.graph.read",
            "document",
            document_id,
            dataset_id=dataset_id,
            document_id=document_id,
            backend=str(graph.get("backend") or ""),
        )
    )
