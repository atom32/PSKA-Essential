from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from pska_essential.capabilities import adapter_slots_contract
from pska_essential.extraction import extract_source_file


def main() -> int:
    if importlib.util.find_spec("docling") is None:
        print(
            json.dumps(
                {
                    "status": "unavailable",
                    "provider": "docling",
                    "message": "Python module `docling` is not installed.",
                    "install_hint": "Install PSKA optional extra `extract-docling`.",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 77

    with TemporaryDirectory(prefix="pska-docling-smoke-") as temp_dir:
        path = Path(temp_dir) / "note.html"
        path.write_text(
            "<html><body><h1>PSKA</h1><p>Docling extraction works.</p></body></html>",
            encoding="utf-8",
        )
        result = extract_source_file(path, max_bytes=10_000, extractor="docling")

    if result is None or result.status != "indexed" or "Docling extraction works" not in result.text:
        raise SystemExit("docling extraction smoke failed")

    extraction_summary = adapter_slots_contract()["summary"]["extraction"]
    if "docling" not in extraction_summary["available"]:
        raise SystemExit("adapter slot summary did not report docling as available")

    print(
        json.dumps(
            {
                "status": "ok",
                "extractor": result.extractor,
                "section_count": len(result.sections),
                "available_extractors": extraction_summary["available"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
