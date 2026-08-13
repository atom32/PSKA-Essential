from __future__ import annotations

import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pska_essential.extraction import extract_builtin_text, extract_source_file


class ExtractionTests(unittest.TestCase):
    def test_builtin_text_returns_normalized_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "note.md"
            path.write_text("# Note\n\nPSKA should extract text through a port.\n", encoding="utf-8")

            result = extract_builtin_text(path, max_bytes=1000)

        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.extractor, "builtin_text")
        self.assertEqual(result.sections[0].section_type, "file")
        self.assertIn("PSKA should extract text", result.text)

    def test_auto_non_text_without_markitdown_stays_unsupported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paper.pdf"
            path.write_bytes(b"%PDF fake")

            with patch("importlib.util.find_spec", return_value=None):
                result = extract_source_file(path, max_bytes=1000, extractor="auto")

        self.assertIsNone(result)

    def test_auto_unknown_binary_stays_unsupported_even_if_markitdown_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blob.bin"
            path.write_bytes(b"\x00\x01\x02")

            with patch("importlib.util.find_spec", return_value=Mock()):
                result = extract_source_file(path, max_bytes=1000, extractor="auto")

        self.assertIsNone(result)

    def test_markitdown_adapter_normalizes_conversion_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paper.pdf"
            path.write_bytes(b"%PDF fake")
            module = Mock()
            module.MarkItDown.return_value.convert.return_value = Mock(text_content="# Paper\n\nConverted body")

            with patch.dict("sys.modules", {"markitdown": module}):
                result = extract_source_file(path, max_bytes=1000, extractor="markitdown")

        self.assertIsNotNone(result)
        self.assertEqual(result.extractor, "markitdown")
        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.sections[0].section_type, "converted_file")
        self.assertIn("Converted body", result.text)

    def test_docling_adapter_normalizes_document_conversion_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "paper.pdf"
            path.write_bytes(b"%PDF fake")

            class FakeDocument:
                title = "Paper"

                def export_to_markdown(self):
                    return "# Paper\n\nDocling converted body"

            class FakeConverter:
                def convert(self, path_value):
                    return Mock(document=FakeDocument())

            docling_pkg = types.ModuleType("docling")
            converter_module = types.ModuleType("docling.document_converter")
            converter_module.DocumentConverter = FakeConverter

            with patch.dict(
                "sys.modules",
                {
                    "docling": docling_pkg,
                    "docling.document_converter": converter_module,
                },
            ):
                result = extract_source_file(path, max_bytes=1000, extractor="docling")

        self.assertIsNotNone(result)
        self.assertEqual(result.extractor, "docling")
        self.assertEqual(result.status, "indexed")
        self.assertEqual(result.sections[0].section_type, "converted_file")
        self.assertIn("Docling converted body", result.text)
        self.assertEqual(result.metadata["provider"], "docling")
