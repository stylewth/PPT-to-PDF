import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
TMP_ROOT = Path(__file__).resolve().parent / ".tmp_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

import fitz

from pdf_micro_reflow import apply_micro_reflow_pdf, map_emu_box_to_pdf, require_pymupdf


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class V3PdfMicroReflowTest(unittest.TestCase):
    def test_require_pymupdf_returns_module(self):
        self.assertIs(require_pymupdf(), fitz)

    def test_map_emu_box_to_pdf_scales_coordinates(self):
        rect = map_emu_box_to_pdf(
            {"x": 0, "y": 0, "w": 6096000, "h": 3429000},
            {"width": 12192000, "height": 6858000},
            fitz.Rect(0, 0, 720, 405),
        )

        self.assertEqual(round(rect.x0), 0)
        self.assertEqual(round(rect.y0), 0)
        self.assertEqual(round(rect.width), 360)
        self.assertEqual(round(rect.height), 202)

    def test_apply_micro_reflow_keeps_page_count_and_draws_flow_labels(self):
        with workspace_tmpdir() as tmp:
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_base_pdf(base_pdf)
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "strategy": "pdf_micro_reflow",
                        "title": "遮挡页",
                        "size": {"width": 12192000, "height": 6858000},
                        "object_boxes": [
                            {"id": "content", "bbox": {"x": 0, "y": 0, "w": 7600000, "h": 6858000}},
                        ],
                        "micro_reflow": {
                            "placement_policy": "blank_space_first",
                            "occlusion_flows": [
                                {
                                    "order": 1,
                                    "target_text": "覆盖后",
                                    "target_bbox": {"x": 2600000, "y": 1200000, "w": 1800000, "h": 800000},
                                    "covered": [
                                        {
                                            "id": "3",
                                            "text": "遮挡前",
                                            "bbox": {"x": 900000, "y": 1200000, "w": 1800000, "h": 800000},
                                        }
                                    ],
                                }
                            ],
                        },
                    }
                ],
            }

            apply_micro_reflow_pdf(base_pdf, guide_pdf, plan)

            output = fitz.open(guide_pdf)
            self.assertEqual(output.page_count, 1)
            text = output[0].get_text()
            self.assertIn("遮挡前", text)
            self.assertIn("覆盖后", text)
            self.assertIn("流程", text)
            output.close()


def _write_base_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_textbox(fitz.Rect(40, 70, 240, 120), "遮挡前", fontsize=18)
    page.draw_rect(fitz.Rect(40, 70, 240, 120), color=(0.2, 0.45, 0.35))
    page.insert_textbox(fitz.Rect(180, 90, 380, 150), "覆盖后", fontsize=18)
    page.draw_rect(fitz.Rect(180, 90, 380, 150), color=(0.6, 0.25, 0.15))
    doc.save(path)
    doc.close()


if __name__ == "__main__":
    unittest.main()
