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
        html_path = Path(temp_dir) / "note.html"
        html_path.write_text(
            "<html><body><h1>PSKA</h1><p>Docling extraction works.</p></body></html>",
            encoding="utf-8",
        )
        html_result = extract_source_file(html_path, max_bytes=10_000, extractor="docling")
        pdf_path = Path(temp_dir) / "note.pdf"
        _write_minimal_pdf(pdf_path, "Docling PDF extraction works.")
        pdf_result = extract_source_file(pdf_path, max_bytes=20_000, extractor="docling")

    if html_result is None or html_result.status != "indexed" or "Docling extraction works" not in html_result.text:
        raise SystemExit("docling HTML extraction smoke failed")
    if pdf_result is None or pdf_result.status != "indexed" or "Docling PDF extraction works" not in pdf_result.text:
        raise SystemExit("docling PDF extraction smoke failed")

    extraction_summary = adapter_slots_contract()["summary"]["extraction"]
    if "docling" not in extraction_summary["available"]:
        raise SystemExit("adapter slot summary did not report docling as available")

    print(
        json.dumps(
            {
                "status": "ok",
                "extractor": html_result.extractor,
                "html_section_count": len(html_result.sections),
                "pdf_section_count": len(pdf_result.sections),
                "available_extractors": extraction_summary["available"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _write_minimal_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 18 Tf 72 720 Td ({escaped}) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream".encode("latin-1"),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref_at = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(output))


if __name__ == "__main__":
    raise SystemExit(main())
