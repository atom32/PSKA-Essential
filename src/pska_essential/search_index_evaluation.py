from __future__ import annotations

import importlib.metadata
import importlib.util
from typing import Any

from pska_essential.capabilities import adapter_slots_contract


SEARCH_INDEX_EVALUATION_SCHEMA = "pska.search_index_evaluation.v1"
DEFAULT_SEARCH_PROVIDER = "sqlite_fts5"
PRIMARY_CANDIDATE = "tantivy"
TANTIVY_EXTRA = "search-tantivy"


def build_search_index_evaluation(service: Any | None = None) -> dict[str, Any]:
    """Return a read-only adapter evaluation for local source search.

    This intentionally does not create a Tantivy index or benchmark user files.
    It keeps SQLite FTS5 as the deterministic default and exposes the activation
    gates required before a stronger index can become more than a candidate.
    """

    slots = adapter_slots_contract()["slots"]["search_index"]
    providers = {provider["name"]: dict(provider) for provider in slots.get("providers", [])}
    registry_stats = _source_registry_stats(getattr(service, "source_registry", None))
    tantivy_runtime = _python_package_status("tantivy")
    tantivy_provider = dict(providers.get(PRIMARY_CANDIDATE) or {})
    tantivy_provider["runtime"] = tantivy_runtime
    size_gate = _size_gate(registry_stats)
    reason_codes = _reason_codes(tantivy_runtime, size_gate)

    return {
        "schema": SEARCH_INDEX_EVALUATION_SCHEMA,
        "status": "evaluated_candidate",
        "contract": "SearchIndexPort",
        "current_default": DEFAULT_SEARCH_PROVIDER,
        "candidate": PRIMARY_CANDIDATE,
        "provider_matrix": [
            _provider_summary(providers.get("sqlite_fts5") or {}),
            _provider_summary(tantivy_provider),
            _provider_summary(providers.get("meilisearch") or {}),
            _provider_summary(providers.get("recoll") or {}),
        ],
        "runtime": {
            "python_packages": {
                "tantivy": tantivy_runtime,
            },
            "optional_extra": TANTIVY_EXTRA,
        },
        "source_index_stats": registry_stats,
        "activation_gates": [
            {
                "id": "scale_pressure",
                "status": "met" if size_gate["met"] else "not_met",
                "message": size_gate["message"],
                "thresholds": {
                    "active_object_count": 50_000,
                    "indexed_section_count": 100_000,
                },
            },
            {
                "id": "latency_or_quality_bottleneck",
                "status": "unmeasured",
                "message": "Record p95 search latency or judged recall issues before changing the default provider.",
            },
            {
                "id": "contract_parity",
                "status": "required",
                "message": "Candidate must return ContextPacket and SourceRef with scope, filters, snippets, and match reasons intact.",
            },
            {
                "id": "rebuild_and_rollback",
                "status": "required",
                "message": "Candidate index must be rebuildable from source_registry and reversible to sqlite_fts5 without touching source files.",
            },
        ],
        "recommendation": {
            "selected_default": DEFAULT_SEARCH_PROVIDER,
            "recommended_action": "keep_sqlite_fts5_default",
            "decision": "defer_adapter_activation",
            "reason_codes": reason_codes,
            "next_step": "Install the optional extra and run a parity benchmark only after scale or search-quality pressure appears.",
        },
        "data_flow": {
            "read_only": True,
            "writes_source_files": False,
            "writes_source_registry": False,
            "writes_memory_directly": False,
            "creates_index": False,
            "runs_external_service": False,
            "embedding_required": False,
            "agent_can_override_default": False,
        },
    }


def _provider_summary(provider: dict[str, Any]) -> dict[str, Any]:
    if not provider:
        return {"name": "", "status": "unknown", "maturity": "unknown", "supports": []}
    return {
        "name": str(provider.get("name") or ""),
        "status": str(provider.get("status") or "unknown"),
        "maturity": str(provider.get("maturity") or "unknown"),
        "integration": str(provider.get("integration") or ""),
        "optional_extra": str(provider.get("optional_extra") or provider.get("extra") or ""),
        "python_module": str(provider.get("python_module") or ""),
        "supports": list(provider.get("supports") or []),
        "runtime": dict(provider.get("runtime") or {}),
    }


def _python_package_status(module: str) -> dict[str, Any]:
    installed = importlib.util.find_spec(module) is not None
    version = ""
    if installed:
        try:
            version = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            version = "unknown"
    return {
        "module": module,
        "installed": installed,
        "version": version,
        "status": "available" if installed else "unavailable",
        "install_hint": f"pip install -e '.[{TANTIVY_EXTRA}]'" if module == "tantivy" else "",
    }


def _source_registry_stats(registry: Any | None) -> dict[str, Any]:
    if registry is None:
        return {
            "status": "unavailable",
            "root_count": 0,
            "active_object_count": 0,
            "indexed_section_count": 0,
            "fts_row_count": 0,
            "total_active_bytes": 0,
        }
    try:
        roots = list(registry.list_roots())
    except Exception as exc:  # pragma: no cover - defensive for non-core registries.
        return {
            "status": "error",
            "error": str(exc),
            "root_count": 0,
            "active_object_count": 0,
            "indexed_section_count": 0,
            "fts_row_count": 0,
            "total_active_bytes": 0,
        }

    stats = {
        "status": "ok",
        "root_count": len(roots),
        "active_object_count": sum(int(root.get("active_object_count") or 0) for root in roots),
        "indexed_section_count": 0,
        "fts_row_count": 0,
        "total_active_bytes": 0,
        "root_kinds": sorted({str(root.get("kind") or "") for root in roots if root.get("kind")}),
    }
    conn = getattr(registry, "conn", None)
    lock = getattr(registry, "lock", None)
    if conn is None or lock is None:
        stats["status"] = "partial"
        return stats

    try:
        with lock:
            section_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM source_sections s
                JOIN source_objects o ON o.object_id = s.object_id
                WHERE o.status = 'active'
                """
            ).fetchone()
            fts_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM source_fts f
                JOIN source_objects o ON o.object_id = f.object_id
                WHERE o.status = 'active'
                """
            ).fetchone()
            bytes_row = conn.execute(
                "SELECT COALESCE(SUM(size), 0) AS total FROM source_objects WHERE status = 'active'"
            ).fetchone()
        stats["indexed_section_count"] = int(section_row["count"] or 0)
        stats["fts_row_count"] = int(fts_row["count"] or 0)
        stats["total_active_bytes"] = int(bytes_row["total"] or 0)
    except Exception as exc:  # pragma: no cover - defensive for non-core registries.
        stats["status"] = "partial"
        stats["error"] = str(exc)
    return stats


def _size_gate(stats: dict[str, Any]) -> dict[str, Any]:
    active_objects = int(stats.get("active_object_count") or 0)
    indexed_sections = int(stats.get("indexed_section_count") or 0)
    met = active_objects >= 50_000 or indexed_sections >= 100_000
    if met:
        message = "Current indexed source scale is large enough to justify a Tantivy parity benchmark."
    else:
        message = "Current indexed source scale does not yet require replacing SQLite FTS5."
    return {
        "met": met,
        "active_object_count": active_objects,
        "indexed_section_count": indexed_sections,
        "message": message,
    }


def _reason_codes(runtime: dict[str, Any], size_gate: dict[str, Any]) -> list[str]:
    reasons = ["default_provider_meets_current_contract"]
    if not runtime.get("installed"):
        reasons.append("tantivy_optional_package_not_installed")
    if not size_gate.get("met"):
        reasons.append("current_index_scale_below_activation_threshold")
    reasons.extend(
        [
            "no_latency_benchmark_recorded",
            "contract_parity_not_verified",
            "rollback_plan_required_before_activation",
        ]
    )
    return reasons
