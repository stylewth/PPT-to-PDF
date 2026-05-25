import unittest
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from server import build_convert_response


class ReaderPayloadContractTest(unittest.TestCase):
    def test_convert_response_exposes_reader_assets(self):
        result = {
            "source": {"name": "deck.pptx", "slide_count": 1},
            "warnings": [],
            "base_pdf_path": "out/base.pdf",
            "guide_pdf_path": "out/guide.pdf",
            "compare_html_path": "out/compare.html",
            "media_manifest_path": "out/media_manifest.json",
            "knowledge_blocks_path": "out/knowledge_blocks.json",
            "guide_preview_manifest_path": "out/guide_preview_manifest.json",
        }

        response = build_convert_response("job123", result)

        self.assertEqual(response["base_pdf_url"], "/outputs/job123/base.pdf")
        self.assertEqual(response["guide_pdf_url"], "/outputs/job123/guide.pdf")
        self.assertEqual(response["guide_preview_manifest_url"], "/outputs/job123/guide_preview_manifest.json")
        self.assertEqual(response["knowledge_blocks_url"], "/outputs/job123/knowledge_blocks.json")
        self.assertIn("ai_guide_pdf_url", response)
        self.assertIsNone(response["ai_guide_pdf_url"])

    def test_convert_response_exposes_ai_guide_when_present(self):
        result = {
            "source": {"name": "deck.pptx", "slide_count": 1},
            "warnings": [],
            "base_pdf_path": "out/base.pdf",
            "guide_pdf_path": "out/guide.pdf",
            "compare_html_path": "out/compare.html",
            "knowledge_blocks_path": "out/knowledge_blocks.json",
            "guide_preview_manifest_path": "out/guide_preview_manifest.json",
            "ai_guide_pdf_path": "out/ai_guide.pdf",
        }

        response = build_convert_response("job123", result)

        self.assertEqual(response["ai_guide_pdf_url"], "/outputs/job123/ai_guide.pdf")
