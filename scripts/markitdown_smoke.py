from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

from pska_essential.capabilities import adapter_slots_contract
from pska_essential.extraction import extract_source_file


def main() -> None:
    if importlib.util.find_spec("markitdown") is None:
        raise SystemExit("markitdown is not installed in this Python environment")

    with tempfile.TemporaryDirectory(prefix="pska-markitdown-smoke-") as temp_dir:
        path = Path(temp_dir) / "note.html"
        path.write_text(
            "<html><body><h1>PSKA</h1><p>MarkItDown extraction works.</p></body></html>",
            encoding="utf-8",
        )
        result = extract_source_file(path, max_bytes=10_000, extractor="markitdown")

    if result is None or result.status != "indexed" or "MarkItDown extraction works" not in result.text:
        raise SystemExit("markitdown extraction smoke failed")

    extraction_summary = adapter_slots_contract()["summary"]["extraction"]
    if "markitdown" not in extraction_summary["available"]:
        raise SystemExit("adapter slot summary did not report markitdown as available")

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


if __name__ == "__main__":
    main()
