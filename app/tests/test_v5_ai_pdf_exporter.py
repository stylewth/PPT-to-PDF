import json
import sys
import tempfile
import unittest
from pathlib import Path

import fitz


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai_pdf_exporter import _font_for_text, export_ai_guide_pdf


class V5AIPdfExporterTest(unittest.TestCase):
    def test_export_ai_guide_inserts_explanation_page_after_source_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guide_path = root / "guide.pdf"
            doc = fitz.open()
            page = doc.new_page(width=720, height=405)
            page.insert_text((72, 72), "guide source page")
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
                self.assertEqual(exported.page_count, 2)
                text = exported[1].get_text()
                self.assertIn("AI Explanation", text)
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
            self.assertEqual(manifest["version"], "v5a")
            self.assertEqual(manifest["pages"][0]["source_page"], 1)
            self.assertEqual(manifest["pages"][0]["explanation_page"], 2)

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
                text = exported[1].get_text()
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
                text = exported[1].get_text().replace("\xa0", " ")
                self.assertIn("操作步骤", text)
                self.assertIn("Step one", text)
                self.assertIn("风险提醒", text)
                self.assertIn("Risk one", text)
            finally:
                exported.close()

    def test_font_selection_keeps_latin_text_compact(self):
        self.assertEqual(_font_for_text("AI Explanation"), "helv")
        self.assertEqual(_font_for_text("电势能 explanation"), "china-s")
