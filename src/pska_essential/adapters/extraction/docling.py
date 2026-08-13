from __future__ import annotations

from pathlib import Path
from typing import Any

from pska_essential.extraction import ExtractedSection, ExtractionError, ExtractionResult, ExtractionWarning


def extract_docling(path: Path, *, max_bytes: int) -> ExtractionResult:
    if path.stat().st_size > max_bytes:
        return ExtractionResult(
            text="",
            sections=[],
            extractor="docling",
            status="too_large",
            warnings=[
                ExtractionWarning(
                    code="file_too_large",
                    message="File exceeds the configured extraction byte limit.",
                    metadata={"max_bytes": max_bytes},
                )
            ],
        )
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise ExtractionError("Python module `docling` is not installed.") from exc

    try:
        converted = DocumentConverter().convert(str(path))
    except Exception as exc:  # noqa: BLE001 - adapter must surface provider failures.
        raise ExtractionError(f"Docling extraction failed: {exc}") from exc

    text = _docling_text(converted)
    if not text.strip():
        return ExtractionResult(
            text="",
            sections=[],
            extractor="docling",
            status="error",
            warnings=[
                ExtractionWarning(
                    code="empty_conversion",
                    message="Docling returned no text for this source file.",
                )
            ],
            metadata=_docling_metadata(converted),
        )
    line_count = max(len(text.splitlines()), 1)
    return ExtractionResult(
        text=text,
        sections=[
            ExtractedSection(
                section_type="converted_file",
                title=path.stem or path.name,
                text=text,
                line_start=1,
                line_end=line_count,
                metadata={"source_extractor": "docling"},
            )
        ],
        extractor="docling",
        status="indexed",
        metadata=_docling_metadata(converted),
    )


def _docling_text(converted: Any) -> str:
    document = getattr(converted, "document", None)
    for candidate in (document, converted):
        if candidate is None:
            continue
        for method in ("export_to_markdown", "export_to_text"):
            value = getattr(candidate, method, None)
            if callable(value):
                rendered = value()
                if isinstance(rendered, str):
                    return rendered
        for attr in ("markdown", "text", "text_content"):
            value = getattr(candidate, attr, None)
            if isinstance(value, str):
                return value
    if isinstance(converted, dict):
        for key in ("markdown", "text", "text_content"):
            value = converted.get(key)
            if isinstance(value, str):
                return value
    return str(converted or "")


def _docling_metadata(converted: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"provider": "docling"}
    document = getattr(converted, "document", None)
    for attr in ("title", "name"):
        value = getattr(document, attr, None) if document is not None else getattr(converted, attr, None)
        if isinstance(value, str) and value.strip():
            metadata[attr] = value.strip()
    return metadata
