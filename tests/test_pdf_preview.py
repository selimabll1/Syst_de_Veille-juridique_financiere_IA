"""Verify actual rendering and source preservation in temporary storage."""
from pathlib import Path
import tempfile
import unittest
import fitz
from modules.pdf_preview import page_preview


class PdfPreviewTests(unittest.TestCase):
    def test_renders_selected_page_without_changing_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.pdf"
            with fitz.open() as document:
                document.new_page().insert_text((40, 40), "First page")
                document.new_page().insert_text((40, 40), "Second page")
                document.save(path)
            original = path.read_bytes()
            first, second = page_preview(path), page_preview(path, 2)
            self.assertEqual(second["pages"], 2)
            self.assertEqual(second["page"], 2)
            self.assertTrue(second["image"].startswith(b"\x89PNG"))
            self.assertNotEqual(first["image"], second["image"])
            self.assertEqual(original, path.read_bytes())
