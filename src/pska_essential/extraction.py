from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".log",
    ".md",
    ".mdown",
    ".markdown",
    ".mjs",
    ".py",
    ".rst",
    ".text",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
MARKITDOWN_EXTENSIONS = {
    ".doc",
    ".docx",
    ".epub",
    ".msg",
    ".odp",
    ".ods",
    ".odt",
    ".pdf",
    ".ppt",
    ".pptx",
    ".rtf",
    ".xls",
    ".xlsx",
}
DOCLING_EXTENSIONS = {
    ".docx",
    ".html",
    ".md",
    ".pdf",
    ".pptx",
    ".xlsx",
}


class ExtractionError(RuntimeError):
    """Raised when an extractor fails in a way callers should surface."""


@dataclass(frozen=True)
class ExtractionWarning:
    code: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class ExtractedSection:
    section_type: str
    title: str
    text: str
    heading_path: str = ""
    line_start: int = 1
    line_end: int = 1
    page: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section_type": self.section_type,
            "title": self.title,
            "text": self.text,
            "heading_path": self.heading_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }
        if self.page is not None:
            payload["page"] = self.page
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    sections: list[ExtractedSection]
    extractor: str
    status: str = "indexed"
    warnings: list[ExtractionWarning] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "sections": [section.to_dict() for section in self.sections],
            "extractor": self.extractor,
            "status": self.status,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "metadata": dict(self.metadata),
        }


def read_text_file(path: Path, *, max_bytes: int) -> str | None:
    data = path.read_bytes()
    if len(data) > max_bytes:
        return None
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def extract_builtin_text(path: Path, *, max_bytes: int) -> ExtractionResult:
    if path.stat().st_size > max_bytes:
        return ExtractionResult(
            text="",
            sections=[],
            extractor="builtin_text",
            status="too_large",
            warnings=[
                ExtractionWarning(
                    code="file_too_large",
                    message="File exceeds the configured extraction byte limit.",
                    metadata={"max_bytes": max_bytes},
                )
            ],
        )
    text = read_text_file(path, max_bytes=max_bytes)
    if text is None:
        return ExtractionResult(
            text="",
            sections=[],
            extractor="builtin_text",
            status="error",
            warnings=[
                ExtractionWarning(
                    code="text_decode_failed",
                    message="File could not be decoded by the built-in text extractor.",
                )
            ],
        )
    line_count = max(len(text.splitlines()), 1)
    return ExtractionResult(
        text=text,
        sections=[
            ExtractedSection(
                section_type="file",
                title=path.stem or path.name,
                text=text,
                line_start=1,
                line_end=line_count,
            )
        ],
        extractor="builtin_text",
        status="indexed",
        metadata={"extension": path.suffix.lower()},
    )


def extract_source_file(
    path: Path,
    *,
    max_bytes: int,
    extractor: str = "auto",
) -> ExtractionResult | None:
    selected = (extractor or "auto").strip().lower()
    suffix = path.suffix.lower()
    if selected in {"", "auto"}:
        if suffix in TEXT_EXTENSIONS:
            selected = "builtin_text"
        elif suffix not in MARKITDOWN_EXTENSIONS or importlib.util.find_spec("markitdown") is None:
            return None
        else:
            selected = "markitdown"
    if selected == "builtin_text":
        if suffix not in TEXT_EXTENSIONS:
            return None
        return extract_builtin_text(path, max_bytes=max_bytes)
    if selected == "markitdown":
        from pska_essential.adapters.extraction.markitdown import extract_markitdown

        return extract_markitdown(path, max_bytes=max_bytes)
    if selected == "docling":
        if suffix not in DOCLING_EXTENSIONS:
            return None
        from pska_essential.adapters.extraction.docling import extract_docling

        return extract_docling(path, max_bytes=max_bytes)
    raise ExtractionError(f"unsupported extractor: {extractor}")
