import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from guide_preview import build_guide_preview


class GuidePreviewTest(unittest.TestCase):
    def test_build_guide_preview_writes_manifest_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(pdf_path)
            doc.close()

            manifest_path = build_guide_preview(pdf_path, root)

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "guide_preview")
            self.assertEqual(data["version"], "v5a")
            self.assertEqual(data["pdf"], "guide.pdf")
            self.assertEqual(len(data["pages"]), 1)
            self.assertTrue((root / data["pages"][0]["image"]).exists())
            self.assertEqual(data["pages"][0]["width_pt"], 720)
            self.assertEqual(data["pages"][0]["height_pt"], 405)
            self.assertEqual(data["pages"][0]["image_width"], 1440)
            self.assertEqual(data["pages"][0]["image_height"], 810)
