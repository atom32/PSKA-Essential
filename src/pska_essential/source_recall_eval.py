from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from pska_essential.audit import audit_event
from pska_essential.contracts import to_jsonable, utc_now_iso
from pska_essential.workflow import build_fake_service


SOURCE_RECALL_EVAL_SCHEMA = "pska.source_recall_eval.v1"
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
MAX_CASES = 50


def build_source_recall_eval(
    service: Any,
    *,
    cases: list[dict[str, Any]] | None = None,
    scope: dict[str, Any] | None = None,
    mode: str = "fixture",
    limit: int = DEFAULT_LIMIT,
    audit: bool = True,
) -> dict[str, Any]:
    """Run source recall cases without embeddings or source/memory writes."""

    selected_mode = str(mode or "fixture").strip().lower()
    selected_limit = min(MAX_LIMIT, max(1, int(limit)))
    run_id = f"sreval_{uuid4().hex}"
    if cases:
        report = _run_cases(
            service,
            _normalize_cases(cases, default_scope=scope or {}, default_limit=selected_limit),
            mode="provided",
            run_id=run_id,
        )
    elif selected_mode == "fixture":
        report = _run_fixture_cases(run_id=run_id, limit=selected_limit)
    else:
        report = _empty_report(run_id=run_id, mode=selected_mode, limit=selected_limit)

    if audit:
        _add_eval_audit(service, report)
    return report


def _run_fixture_cases(*, run_id: str, limit: int) -> dict[str, Any]:
    fixture_service = build_fake_service()
    with tempfile.TemporaryDirectory(prefix="pska-source-recall-eval-") as tmp:
        root_path = Path(tmp) / "RecallFixture"
        (root_path / "finance").mkdir(parents=True)
        (root_path / "creative").mkdir(parents=True)
        (root_path / "architecture").mkdir(parents=True)
        (root_path / "decoys").mkdir(parents=True)
        (root_path / "finance" / "annual-report-2026.md").write_text(
            "# Annual Report 2026\n\n"
            "The finance report describes revenue growth, cashflow pressure, audit risks, "
            "and board-level operating comments for a quarterly review.\n",
            encoding="utf-8",
        )
        (root_path / "creative" / "eidolia-novel-continuation.md").write_text(
            "# Eidolia Novel Continuation\n\n"
            "The Eidolia canvas keeps a novel continuation scene with a red scarf protagonist, "
            "artifact notes, character stakes, and a follow-on chapter draft.\n",
            encoding="utf-8",
        )
        (root_path / "architecture" / "pska-memory-gbrain.md").write_text(
            "# PSKA Memory And GBrain\n\n"
            "PSKA uses GBrain over HTTP MCP as a governed memory component. Memory Cards, "
            "source routes, reviews, and trace records keep durable memory separate from source files.\n",
            encoding="utf-8",
        )
        (root_path / "decoys" / "lunch-notes.md").write_text(
            "# Lunch Notes\n\n"
            "This note mentions coffee, noodles, and ordinary errands. It should not answer "
            "finance, Eidolia, or PSKA memory recall cases.\n",
            encoding="utf-8",
        )
        root = fixture_service.source_root_register(
            str(root_path),
            permission_mode="read_only",
            label="Source Recall Eval Fixture",
        )
        scan = fixture_service.source_scan(root["root_id"], max_files=20)
        cases = _normalize_cases(
            [
                {
                    "case_id": "fixture.finance_report",
                    "query": "annual report revenue cashflow audit risk",
                    "expected_paths": ["finance/annual-report-2026.md"],
                },
                {
                    "case_id": "fixture.eidolia_creation",
                    "query": "Eidolia canvas novel continuation red scarf protagonist",
                    "expected_paths": ["creative/eidolia-novel-continuation.md"],
                },
                {
                    "case_id": "fixture.pska_gbrain_memory",
                    "query": "PSKA GBrain HTTP MCP memory cards source routes reviews",
                    "expected_paths": ["architecture/pska-memory-gbrain.md"],
                },
                {
                    "case_id": "fixture.expected_zero",
                    "query": "quantum orchard satellite weather almanac",
                    "expect_zero_results": True,
                },
            ],
            default_scope={"root_ids": [root["root_id"]]},
            default_limit=limit,
        )
        report = _run_cases(fixture_service, cases, mode="fixture", run_id=run_id)
        report["fixture"] = {
            "root_label": root["label"],
            "source_object_count": int(scan.get("active_object_count") or 0),
            "indexed_count": int((scan.get("counts") or {}).get("indexed") or 0),
            "writes_live_source_registry": False,
            "writes_live_source_files": False,
        }
        return report


def _run_cases(service: Any, cases: list[dict[str, Any]], *, mode: str, run_id: str) -> dict[str, Any]:
    selected_cases = cases[:MAX_CASES]
    results = [_run_case(service, case) for case in selected_cases]
    passed = [case for case in results if case["status"] == "ok"]
    failed = [case for case in results if case["status"] != "ok"]
    return {
        "schema": SOURCE_RECALL_EVAL_SCHEMA,
        "kind": "source_recall_eval",
        "run_id": run_id,
        "mode": mode,
        "status": "ok" if results and not failed else "needs_attention" if results else "no_cases",
        "generated_at": utc_now_iso(),
        "summary": {
            "case_count": len(results),
            "passed_case_count": len(passed),
            "failed_case_count": len(failed),
            "expected_hit_count": sum(1 for case in results if case["metrics"]["expected_hit"]),
            "zero_result_case_count": sum(1 for case in results if case["expect_zero_results"]),
            "zero_result_pass_count": sum(
                1 for case in results if case["expect_zero_results"] and case["status"] == "ok"
            ),
            "top1_hit_count": sum(1 for case in results if case["metrics"]["expected_rank"] == 1),
            "forbidden_hit_count": sum(1 for case in results if case["metrics"]["forbidden_hit"]),
        },
        "cases": results,
        "data_flow": _data_flow(mode),
        "next_actions": _next_actions(results),
    }


def _run_case(service: Any, case: dict[str, Any]) -> dict[str, Any]:
    query = str(case.get("query") or "").strip()
    if not query:
        return _case_error(case, "case query is required")
    try:
        packets = service.source_search(
            query,
            scope=dict(case.get("scope") or {}),
            limit=int(case.get("limit") or DEFAULT_LIMIT),
            filters=dict(case.get("filters") or {}),
        )
    except Exception as exc:  # noqa: BLE001 - eval case must be structured.
        return _case_error(case, str(exc), error_type=exc.__class__.__name__)

    results = [_packet_result(index, packet) for index, packet in enumerate(packets, start=1)]
    expected_rank = _first_expected_rank(results, case)
    forbidden_hits = [result for result in results if _matches_any_path(result["path"], case.get("forbidden_paths") or [])]
    expect_zero = bool(case.get("expect_zero_results", False))
    min_results = int(case.get("min_result_count") or (0 if expect_zero else 1))
    expected_hit = expected_rank > 0
    has_explicit_expectation = bool(case.get("expected_paths") or case.get("expected_source_ids") or case.get("expected_titles"))
    if expect_zero:
        passed = len(results) == 0
        message = "Expected zero results and got none." if passed else "Expected zero results but search returned matches."
    elif has_explicit_expectation:
        passed = expected_hit and not forbidden_hits
        message = "Expected source was recalled." if passed else "Expected source was not recalled cleanly."
    else:
        passed = len(results) >= min_results and not forbidden_hits
        message = "Search returned enough results." if passed else "Search did not return enough results."
    return {
        "case_id": str(case.get("case_id") or ""),
        "query": query,
        "status": "ok" if passed else "error",
        "message": message,
        "expect_zero_results": expect_zero,
        "expected_paths": list(case.get("expected_paths") or []),
        "forbidden_paths": list(case.get("forbidden_paths") or []),
        "metrics": {
            "result_count": len(results),
            "min_result_count": min_results,
            "expected_hit": expected_hit,
            "expected_rank": expected_rank,
            "top_path": results[0]["path"] if results else "",
            "forbidden_hit": bool(forbidden_hits),
            "embedding_required": any(bool(result["embedding_required"]) for result in results),
        },
        "results": results,
    }


def _normalize_cases(
    cases: list[dict[str, Any]],
    *,
    default_scope: dict[str, Any],
    default_limit: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(cases[:MAX_CASES], start=1):
        if not isinstance(raw, dict):
            normalized.append(
                {
                    "case_id": f"case_{index}",
                    "query": "",
                    "scope": dict(default_scope or {}),
                    "filters": {},
                    "limit": default_limit,
                    "expected_paths": [],
                    "expected_source_ids": [],
                    "expected_titles": [],
                    "forbidden_paths": [],
                }
            )
            continue
        item = dict(raw or {})
        item["case_id"] = str(item.get("case_id") or f"case_{index}")
        item["query"] = str(item.get("query") or "")
        item["scope"] = dict(item.get("scope") or default_scope or {})
        item["filters"] = dict(item.get("filters") or {})
        item["limit"] = min(MAX_LIMIT, max(1, int(item.get("limit") or default_limit)))
        for key in ("expected_paths", "expected_source_ids", "expected_titles", "forbidden_paths"):
            item[key] = [str(value) for value in item.get(key) or [] if str(value)]
        normalized.append(item)
    return normalized


def _packet_result(index: int, packet: Any) -> dict[str, Any]:
    ref = packet.source_ref
    metadata = dict(getattr(packet, "metadata", {}) or {})
    return {
        "rank": index,
        "context_id": str(packet.context_id or ""),
        "title": str(packet.title or ref.title or ""),
        "path": str(ref.path or ""),
        "source_id": str(ref.source_id or ""),
        "document_id": str(ref.document_id or ""),
        "score": float(packet.score or 0.0),
        "snippet": str(metadata.get("snippet") or metadata.get("highlighted_snippet") or "")[:240],
        "match_reasons": list(metadata.get("match_reasons") or []),
        "embedding_required": bool(metadata.get("embedding_required", False)),
        "source_ref": to_jsonable(ref),
    }


def _first_expected_rank(results: list[dict[str, Any]], case: dict[str, Any]) -> int:
    expected_paths = list(case.get("expected_paths") or [])
    expected_source_ids = set(str(value) for value in case.get("expected_source_ids") or [])
    expected_titles = set(str(value).casefold() for value in case.get("expected_titles") or [])
    for result in results:
        if _matches_any_path(result["path"], expected_paths):
            return int(result["rank"])
        if expected_source_ids and result["source_id"] in expected_source_ids:
            return int(result["rank"])
        if expected_titles and result["title"].casefold() in expected_titles:
            return int(result["rank"])
    return 0


def _matches_any_path(path: str, expected_paths: list[Any]) -> bool:
    normalized = str(path or "").strip()
    for expected in expected_paths:
        candidate = str(expected or "").strip()
        if not candidate:
            continue
        if normalized == candidate or normalized.endswith(f"/{candidate}"):
            return True
    return False


def _case_error(case: dict[str, Any], message: str, *, error_type: str = "") -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id") or ""),
        "query": str(case.get("query") or ""),
        "status": "error",
        "message": message,
        "expect_zero_results": bool(case.get("expect_zero_results", False)),
        "expected_paths": list(case.get("expected_paths") or []),
        "forbidden_paths": list(case.get("forbidden_paths") or []),
        "metrics": {
            "result_count": 0,
            "min_result_count": 0,
            "expected_hit": False,
            "expected_rank": 0,
            "top_path": "",
            "forbidden_hit": False,
            "embedding_required": False,
        },
        "results": [],
        "error": {"type": error_type, "message": message},
    }


def _empty_report(*, run_id: str, mode: str, limit: int) -> dict[str, Any]:
    return {
        "schema": SOURCE_RECALL_EVAL_SCHEMA,
        "kind": "source_recall_eval",
        "run_id": run_id,
        "mode": mode,
        "status": "no_cases",
        "generated_at": utc_now_iso(),
        "summary": {
            "case_count": 0,
            "passed_case_count": 0,
            "failed_case_count": 0,
            "expected_hit_count": 0,
            "zero_result_case_count": 0,
            "zero_result_pass_count": 0,
            "top1_hit_count": 0,
            "forbidden_hit_count": 0,
        },
        "cases": [],
        "data_flow": _data_flow(mode),
        "next_actions": [
            {
                "action": "provide_source_recall_cases",
                "label": "Provide query and expected source path cases",
                "api": "POST /api/sources/recall-eval",
                "mcp": "pska_source_recall_eval",
            }
        ],
    }


def _data_flow(mode: str) -> dict[str, Any]:
    return {
        "read_only": True,
        "mode": mode,
        "uses_isolated_fixture": mode == "fixture",
        "writes_audit_events": True,
        "writes_source_files": False,
        "writes_source_registry": False,
        "writes_memory_directly": False,
        "creates_review": False,
        "runs_jobs": False,
        "activates_due_jobs": False,
        "exports_external_trace": False,
        "embedding_required": False,
        "agent_can_override_search_flow": False,
    }


def _next_actions(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    failures = [case for case in results if case.get("status") != "ok"]
    if failures:
        actions.append(
            {
                "action": "inspect_failed_recall_cases",
                "label": "Inspect failed source recall cases",
                "failed_case_ids": [str(case.get("case_id") or "") for case in failures[:8]],
            }
        )
    if any(case["metrics"].get("embedding_required") for case in results):
        actions.append(
            {
                "action": "remove_embedding_dependency",
                "label": "Check source search path for unintended embedding dependency",
            }
        )
    return actions


def _add_eval_audit(service: Any, report: dict[str, Any]) -> None:
    store = getattr(service, "store", None)
    if store is None:
        return
    summary = dict(report.get("summary") or {})
    store.add_audit_event(
        audit_event(
            "source.recall_eval.run",
            "source_eval",
            str(report.get("run_id") or "source_recall_eval"),
            status=str(report.get("status") or ""),
            mode=str(report.get("mode") or ""),
            case_count=int(summary.get("case_count") or 0),
            passed_case_count=int(summary.get("passed_case_count") or 0),
            failed_case_count=int(summary.get("failed_case_count") or 0),
            expected_hit_count=int(summary.get("expected_hit_count") or 0),
            zero_result_case_count=int(summary.get("zero_result_case_count") or 0),
            writes_source_files=False,
            writes_source_registry=False,
            writes_memory_directly=False,
            embedding_required=False,
        )
    )
