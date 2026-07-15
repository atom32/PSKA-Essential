from __future__ import annotations

import json
import os

from pska_essential.config import build_service_from_env
from pska_essential.contracts import to_jsonable
from pska_essential.diagnostics import add_live_closed_loop_probe_audit, run_live_closed_loop_probe
from pska_essential.kb_gateway import build_kb_gateway_from_env


def main() -> int:
    dataset_ids = _csv_env("PSKA_LIVE_DATASET_IDS")
    if not dataset_ids:
        raise SystemExit("PSKA_LIVE_DATASET_IDS is required, for example: PSKA_LIVE_DATASET_IDS=dataset_id")

    service = build_service_from_env()
    gateway = build_kb_gateway_from_env()
    probe = run_live_closed_loop_probe(
        service,
        gateway,
        question=os.getenv("PSKA_LIVE_QUESTION", "PSKA live closed-loop probe"),
        dataset_ids=dataset_ids,
        document_ids=_csv_env("PSKA_LIVE_DOCUMENT_IDS"),
        limit=int(os.getenv("PSKA_LIVE_LIMIT", "3")),
        proposal_kind=os.getenv("PSKA_LIVE_PROPOSAL_KIND", "writing_brief"),
        use_kg=_env_enabled("PSKA_LIVE_USE_KG"),
        export_format=os.getenv("PSKA_LIVE_EXPORT_FORMAT", "json"),
        source_inspection_limit=int(os.getenv("PSKA_LIVE_SOURCE_INSPECTION_LIMIT", "1")),
    )
    add_live_closed_loop_probe_audit(service.store, probe)
    print(json.dumps(to_jsonable(probe), ensure_ascii=False, indent=2))
    return 0 if probe.get("status") == "ok" else 2


def _csv_env(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def _env_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
