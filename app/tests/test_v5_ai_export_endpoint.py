import sys
import tempfile
import unittest
from pathlib import Path

import fitz


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from server import export_ai_guide_for_job


class V5AIExportEndpointTest(unittest.TestCase):
    def test_export_ai_guide_for_job_returns_download_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            guide_path = output_dir / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(guide_path)
            doc.close()
            (output_dir / "knowledge_blocks.json").write_text(
                """
                {
                  "slides": [
                    {
                      "number": 1,
                      "blocks": [
                        {
                          "id": "s1_b1",
                          "title": "Block",
                          "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}]
                        }
                      ]
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            response = export_ai_guide_for_job(
                "jobx",
                output_dir,
                [
                    {
                        "block_id": "s1_b1",
                        "explanation": {
                            "short_explanation": "Short",
                            "detail": "Detail",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
            )

            self.assertEqual(response["status"], "ok")
            self.assertEqual(response["ai_guide_pdf_url"], "/outputs/jobx/ai_guide.pdf")
            self.assertEqual(response["ai_guide_manifest_url"], "/outputs/jobx/ai_guide_manifest.json")
            self.assertTrue((output_dir / "ai_guide.pdf").exists())
