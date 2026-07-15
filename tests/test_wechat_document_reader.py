from __future__ import annotations

from io import BytesIO
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_reader():
    path = ROOT / "agentic_tools" / "wechat_gui_agent" / "scripts" / "wechat_document_reader.py"
    spec = importlib.util.spec_from_file_location("wechat_document_reader_for_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def docx_bytes() -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>',
        )
        archive.writestr(
            "word/document.xml",
            """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
              <w:p><w:r><w:t>Hybrid imaging combines event and frame sensing.</w:t></w:r></w:p>
              <w:tbl><w:tr>
                <w:tc><w:p><w:r><w:t>Mode</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>Dynamic range</w:t></w:r></w:p></w:tc>
              </w:tr></w:tbl>
            </w:body></w:document>""",
        )
        archive.writestr(
            "docProps/core.xml",
            """<cp:coreProperties
            xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
            xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Hybrid Imager Notes</dc:title></cp:coreProperties>""",
        )
    return buffer.getvalue()


class WeChatDocumentReaderTests(unittest.TestCase):
    def test_docx_extracts_paragraphs_tables_and_metadata(self) -> None:
        reader = load_reader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "notes.docx"
            source.write_bytes(docx_bytes())

            result = reader.analyze_document(source, root / "read")
            content = Path(result["text_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["status"], "readable")
        self.assertEqual(result["kind"], "docx")
        self.assertEqual(result["method"], "docx-xml")
        self.assertEqual(result["metadata"]["title"], "Hybrid Imager Notes")
        self.assertIn("event and frame sensing", content)
        self.assertIn("Dynamic range", content)
        self.assertFalse(result["executed_content"])

    def test_docx_rejects_utf16_entity_declarations(self) -> None:
        reader = load_reader()
        malicious_xml = """<?xml version="1.0" encoding="UTF-16"?>
        <!DOCTYPE document [<!ENTITY injected "not trusted">]>
        <document><p>&injected;</p></document>""".encode("utf-16")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "unsafe.docx"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", "<Types/>")
                archive.writestr("word/document.xml", malicious_xml)

            result = reader.analyze_document(source, root / "read")

        self.assertEqual(result["status"], "failed")
        self.assertIn("DTD/entity declarations", result["error"])

    def test_extensionless_pdf_is_a_document_candidate(self) -> None:
        reader = load_reader()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wechat-attachment"
            source.write_bytes(b"%PDF-1.7\nplaceholder")

            self.assertTrue(reader.is_document_candidate(source))
            self.assertEqual(reader.detect_document_kind(source), "pdf")

    def test_zip_reads_supported_members_and_blocks_path_traversal(self) -> None:
        reader = load_reader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bundle.zip"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("../escape.txt", "must not escape")
                archive.writestr("..\\escape-windows.txt", "must not escape on Windows")
                archive.writestr("notes/readme.txt", "A concise experiment note.")
                archive.writestr("papers/hybrid.docx", docx_bytes())

            result = reader.analyze_document(source, root / "read")
            content = Path(result["text_path"]).read_text(encoding="utf-8")

            self.assertFalse((root / "escape.txt").exists())

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["kind"], "zip")
        self.assertEqual(result["readable_member_count"], 2)
        self.assertEqual(sum(item.get("reason") == "unsafe-path" for item in result["members"]), 2)
        self.assertIn("notes/readme.txt", content)
        self.assertIn("hybrid.docx", content)

    def test_zip_rejects_extreme_compression_ratio(self) -> None:
        reader = load_reader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "compressed.zip"
            with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("huge.txt", b"0" * 2_000_000)
            limits = reader.default_limits()
            limits["max_archive_ratio"] = 10.0

            result = reader.analyze_document(source, root / "read", limits=limits)

        self.assertEqual(result["status"], "unreadable")
        self.assertEqual(result["members"][0]["reason"], "compression-ratio-too-high")

    def test_pdf_uses_pdftotext_evidence_when_available(self) -> None:
        reader = load_reader()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "paper.pdf"
            source.write_bytes(b"%PDF-1.7\nplaceholder")

            def fake_external(command, **_kwargs):
                Path(command[-1]).write_text("A substantive paper finding. " * 20, encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(reader, "pdf_info", return_value={"pages": "2", "encrypted": "no"}), mock.patch.object(
                reader.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}" if name == "pdftotext" else None
            ), mock.patch.object(reader, "run_external", side_effect=fake_external):
                result = reader.analyze_document(source, root / "read")

        self.assertEqual(result["status"], "readable")
        self.assertEqual(result["method"], "pdftotext")
        self.assertIn("substantive paper finding", result["text_preview"].lower())


if __name__ == "__main__":
    unittest.main()
