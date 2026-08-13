from __future__ import annotations

from pathlib import Path
from typing import Any

from pska_essential.extraction import ExtractedSection, ExtractionError, ExtractionResult, ExtractionWarning


def extract_markitdown(path: Path, *, max_bytes: int) -> ExtractionResult:
    if path.stat().st_size > max_bytes:
        return ExtractionResult(
            text="",
            sections=[],
            extractor="markitdown",
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
        from markitdown import MarkItDown
    except ImportError as exc:
        raise ExtractionError("Python module `markitdown` is not installed.") from exc

    try:
        converted = MarkItDown().convert(str(path))
    except Exception as exc:  # noqa: BLE001 - adapter must surface provider failures.
        raise ExtractionError(f"MarkItDown extraction failed: {exc}") from exc

    text = _converted_text(converted)
    if not text.strip():
        return ExtractionResult(
            text="",
            sections=[],
            extractor="markitdown",
            status="error",
            warnings=[
                ExtractionWarning(
                    code="empty_conversion",
                    message="MarkItDown returned no text for this source file.",
                )
            ],
            metadata=_converted_metadata(converted),
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
                metadata={"source_extractor": "markitdown"},
            )
        ],
        extractor="markitdown",
        status="indexed",
        metadata=_converted_metadata(converted),
    )


def _converted_text(converted: Any) -> str:
    for attr in ("text_content", "markdown", "text"):
        value = getattr(converted, attr, None)
        if isinstance(value, str):
            return value
    if isinstance(converted, dict):
        for key in ("text_content", "markdown", "text"):
            value = converted.get(key)
            if isinstance(value, str):
                return value
    return str(converted or "")


def _converted_metadata(converted: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {"provider": "markitdown"}
    title = getattr(converted, "title", None)
    if isinstance(title, str) and title.strip():
        metadata["title"] = title.strip()
    return metadata
