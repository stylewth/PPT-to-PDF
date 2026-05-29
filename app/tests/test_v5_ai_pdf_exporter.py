import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai_pdf_exporter import _display_width_units, _font_for_text, _wrap_text, export_ai_guide_pdf


class V5AIPdfExporterTest(unittest.TestCase):
    def test_export_ai_guide_keeps_selected_block_note_on_same_logical_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            page = doc.new_page(width=720, height=405)
            page.insert_text((72, 72), "guide source page")
            page.insert_text((500, 40), "protected source text")
            doc.save(guide_path)
            doc.close()

            knowledge = {
                "slides": [
                    {
                        "number": 1,
                        "title": "Electric potential energy",
                        "blocks": [
                            {
                                "id": "s1_b1",
                                "title": "Conservative force",
                                "type": "text_concept",
                                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                            }
                        ],
                    }
                ]
            }
            explanations = [
                {
                    "block_id": "s1_b1",
                    "explanation": {
                        "short_explanation": "Electrostatic force is conservative.",
                        "detail": "The slide connects work done by the electrostatic force with potential energy.",
                        "key_points": ["Potential energy belongs to the system.", "Only selected evidence is used."],
                        "review_questions": ["Why is the force called conservative?"],
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                    },
                }
            ]

            output_path = export_ai_guide_pdf(guide_path, knowledge, explanations, root)

            exported = fitz.open(output_path)
            try:
                self.assertEqual(exported.page_count, 1)
                text = exported[0].get_text()
                self.assertNotIn("AI Explanation", text)
                self.assertIn("Conservative force", text)
                self.assertIn("Electrostatic force is conservative.", text)
                self.assertNotIn("Sources:", text)
                self.assertNotIn("slide_text", text)
            finally:
                exported.close()

            original = fitz.open(guide_path)
            try:
                self.assertEqual(original.page_count, 1)
            finally:
                original.close()

            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["pages"][0]["explanation_page"])
            self.assertEqual(manifest["pages"][0]["block_ids"], ["s1_b1"])
            self.assertEqual(manifest["pages"][0]["placements"][0]["note_type"], "margin_note")
            self.assertIn("placement_rect", manifest["pages"][0]["placements"][0])

    def test_export_writes_manifest_with_source_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Block",
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
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
                root,
            )

            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(Path(output_path).name, "ai_guide.pdf")
            self.assertEqual(manifest["version"], "v5b")
            self.assertEqual(manifest["pages"][0]["source_page"], 1)
            self.assertIsNone(manifest["pages"][0]["explanation_page"])
            self.assertIn("anchor_bbox", manifest["pages"][0]["placements"][0])

    def test_export_preserves_shared_pdf_resources_when_copying_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            image = Image.frombytes("RGB", (720, 720), bytes((index * 37) % 256 for index in range(720 * 720 * 3)))
            stream = io.BytesIO()
            image.save(stream, format="JPEG", quality=92)
            image_bytes = stream.getvalue()

            doc = fitz.open()
            shared_xref = 0
            for index in range(6):
                page = doc.new_page(width=720, height=405)
                if index == 0:
                    shared_xref = page.insert_image(fitz.Rect(0, 0, 720, 405), stream=image_bytes)
                else:
                    page.insert_image(fitz.Rect(0, 0, 720, 405), xref=shared_xref)
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Block",
                                    "display_bbox": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
                [
                    {
                        "block_id": "s1_b1",
                        "explanation": {
                            "pdf_snippet": "Short note.",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
                root,
            )

            guide_size = guide_path.stat().st_size
            ai_size = Path(output_path).stat().st_size
            self.assertLess(ai_size, guide_size * 2)

    def test_export_uses_study_note_visual_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            page = doc.new_page(width=720, height=405)
            page.insert_text((40, 48), "Dense page")
            page.draw_rect(fitz.Rect(36, 70, 690, 360), color=(0.2, 0.4, 0.7))
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "电势能",
                                    "display_bbox": {"x": 0.05, "y": 0.18, "w": 0.86, "h": 0.68},
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
                [
                    {
                        "block_id": "s1_b1",
                        "explanation": {
                            "pdf_snippet": "这是贴在原页旁边的学习笔记。",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
                root,
            )

            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            placement = manifest["pages"][0]["placements"][0]
            self.assertEqual(placement["style_version"], "study_note_v2")

            exported = fitz.open(output_path)
            try:
                drawings = exported[0].get_drawings()
                note_shapes = [
                    drawing
                    for drawing in drawings
                    if drawing.get("fill") and drawing.get("rect") and drawing["rect"].x0 > 700
                ]
                self.assertGreaterEqual(len(note_shapes), 3)
            finally:
                exported.close()

    def test_export_places_blank_note_on_source_page_when_safe_space_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            page = doc.new_page(width=720, height=405)
            page.insert_text((72, 72), "guide source page")
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Block",
                                    "display_bbox": {"x": 0.05, "y": 0.08, "w": 0.42, "h": 0.72},
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
                [
                    {
                        "block_id": "s1_b1",
                        "layout_intent": "blank_note",
                        "explanation": {
                            "pdf_snippet": "Inline note should use the empty side area.",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
                root,
            )

            exported = fitz.open(output_path)
            try:
                self.assertEqual(exported.page_count, 1)
                text = exported[0].get_text()
                self.assertIn("guide source page", text)
                self.assertIn("Inline note should use the empty side area.", text)
            finally:
                exported.close()

            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            self.assertIsNone(manifest["pages"][0]["explanation_page"])
            self.assertEqual(manifest["pages"][0]["layout_modes"], ["blank_note"])
            self.assertEqual(manifest["pages"][0]["placements"][0]["block_id"], "s1_b1")
            placement_rect = fitz.Rect(*manifest["pages"][0]["placements"][0]["rect"])
            self.assertFalse(placement_rect.intersects(fitz.Rect(492, 24, 700, 58)))

    def test_export_accepts_whole_page_explanation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "title": "Page title",
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Block",
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
                [
                    {
                        "page_number": 1,
                        "explanation": {
                            "short_explanation": "Whole page summary",
                            "detail": "This explanation covers the complete page.",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
                root,
            )

            exported = fitz.open(output_path)
            try:
                self.assertEqual(exported.page_count, 1)
                text = exported[0].get_text()
                self.assertIn("Whole page", text)
                self.assertIn("Whole page summary", text)
            finally:
                exported.close()
            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["pages"][0]["block_ids"], ["page_1"])

    def test_export_renders_role_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Training block",
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                }
                            ],
                        }
                    ]
                },
                [
                    {
                        "block_id": "s1_b1",
                        "explanation": {
                            "short_explanation": "Training summary",
                            "detail": "Training detail",
                            "sections": [
                                {"label": "操作步骤", "items": ["Step one"]},
                                {"label": "风险提醒", "items": ["Risk one"]},
                            ],
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    }
                ],
                root,
            )

            exported = fitz.open(output_path)
            try:
                self.assertEqual(exported.page_count, 1)
                text = exported[0].get_text().replace("\xa0", " ")
                self.assertIn("Training summary", text)
                self.assertNotIn("Training detail", text)
                self.assertNotIn("Step one", text)
                self.assertNotIn("Risk one", text)
            finally:
                exported.close()

    def test_font_selection_keeps_latin_text_compact(self):
        self.assertEqual(_font_for_text("AI Explanation"), "helv")
        self.assertEqual(_font_for_text("电势能 explanation"), "china-s")

    def test_wrap_text_treats_chinese_as_wide_text(self):
        lines = _wrap_text("电势能是单位正电荷的电势能。English", 12)

        self.assertGreater(len(lines), 1)
        self.assertTrue(all(_display_width_units(line) <= 12 for line in lines))

    def test_export_uses_pdf_snippet_and_records_dropped_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(guide_path)
            doc.close()

            output_path = export_ai_guide_pdf(
                guide_path,
                {
                    "slides": [
                        {
                            "number": 1,
                            "blocks": [
                                {
                                    "id": "s1_b1",
                                    "title": "Block 1",
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                                },
                                {
                                    "id": "s1_b2",
                                    "title": "Block 2",
                                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape2"}],
                                },
                            ],
                        }
                    ]
                },
                [
                    {
                        "block_id": "s1_b1",
                        "include_in_pdf": True,
                        "layout_intent": "extension_panel",
                        "explanation": {
                            "short_explanation": "完整讲解不应进入 PDF。",
                            "detail": "这是一段很长的完整讲解。",
                            "pdf_title": "短补充",
                            "pdf_snippet": "这是真正进入 PDF 的短补充。",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                    },
                    {
                        "block_id": "s1_b2",
                        "include_in_pdf": False,
                        "drop_reason": "重复原文",
                        "explanation": {
                            "short_explanation": "不应出现",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape2"}],
                        },
                    },
                ],
                root,
            )

            exported = fitz.open(output_path)
            try:
                self.assertEqual(exported.page_count, 1)
                text = exported[0].get_text().replace("\xa0", " ")
                self.assertIn("这是真正进入 PDF 的短补充。", text)
                self.assertNotIn("完整讲解不应进入 PDF。", text)
                self.assertNotIn("不应出现", text)
                image_blocks = [block for block in exported[0].get_text("dict")["blocks"] if block.get("type") == 1]
                self.assertGreaterEqual(len(image_blocks), 1)
            finally:
                exported.close()
            manifest = json.loads((root / "ai_guide_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["dropped"][0]["block_id"], "s1_b2")
            self.assertEqual(manifest["dropped"][0]["drop_reason"], "重复原文")
