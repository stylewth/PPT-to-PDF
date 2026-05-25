import unittest
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai_context import build_single_block_context, build_whole_page_context


class AiContextV5Test(unittest.TestCase):
    def test_single_block_context_contains_only_selected_block_text(self):
        block = {
            "id": "s1_b1",
            "texts": ["selected concept"],
            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
            "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "shape1", "effect": "appear"}],
        }

        context = build_single_block_context(block, page_title="Title")

        self.assertEqual(context["mode"], "explain")
        self.assertIn("selected concept", context["evidence_text"])
        self.assertNotIn("unselected concept", context["evidence_text"])
        self.assertEqual(context["source_refs"], block["source_refs"])
        self.assertEqual(context["animation_refs"], block["animation_refs"])

    def test_whole_page_context_uses_deduped_text(self):
        page = {
            "number": 1,
            "title": "Title",
            "blocks": [
                {"texts": ["A"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "a"}]},
                {"texts": ["A"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "b"}]},
                {"texts": ["B"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "c"}]},
            ],
        }

        context = build_whole_page_context(page)

        self.assertEqual(context["mode"], "whole_page")
        self.assertEqual(context["evidence_text"].count("A"), 1)
        self.assertIn("B", context["evidence_text"])
        self.assertEqual(len(context["source_refs"]), 3)
