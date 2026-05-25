import unittest
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from knowledge_blocks import (
    build_whole_page_block,
    merge_animation_duplicates,
    should_use_whole_page_fallback,
)


class KnowledgeBlockDedupeTest(unittest.TestCase):
    def test_same_text_with_multiple_animation_effects_becomes_one_block(self):
        blocks = [
            {
                "id": "s1_a1",
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "display_bbox": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.1},
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "shape3", "effect": "appear"}],
            },
            {
                "id": "s1_a2",
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "display_bbox": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.1},
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "shape3", "effect": "fade"}],
            },
        ]

        merged = merge_animation_duplicates(blocks)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["type"], "text_concept")
        self.assertEqual(len(merged[0]["animation_refs"]), 2)
        self.assertEqual(merged[0]["texts"], ["Like the gravitational force"])

    def test_same_animation_text_with_different_visual_targets_merges_and_expands_bbox(self):
        blocks = [
            {
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "object_ids": ["text18", "pic3"],
                "source_bbox": {"x": 100, "y": 100, "w": 500, "h": 120},
                "display_bbox": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.2},
                "source_refs": [
                    {"kind": "slide_text", "slide": 1, "object_id": "text18"},
                    {"kind": "visual", "slide": 1, "object_id": "pic3"},
                    {"kind": "animation", "slide": 1, "object_id": "pic3"},
                ],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "pic3"}],
            },
            {
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "object_ids": ["text18", "formula11"],
                "source_bbox": {"x": 120, "y": 180, "w": 360, "h": 180},
                "display_bbox": {"x": 0.12, "y": 0.3, "w": 0.36, "h": 0.3},
                "source_refs": [
                    {"kind": "slide_text", "slide": 1, "object_id": "text18"},
                    {"kind": "visual", "slide": 1, "object_id": "formula11"},
                    {"kind": "animation", "slide": 1, "object_id": "formula11"},
                ],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "formula11"}],
            },
        ]

        merged = merge_animation_duplicates(blocks)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["object_ids"], ["text18", "pic3", "formula11"])
        self.assertEqual(merged[0]["display_bbox"], {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5})
        self.assertIn({"kind": "visual", "slide": 1, "object_id": "pic3"}, merged[0]["source_refs"])
        self.assertIn({"kind": "visual", "slide": 1, "object_id": "formula11"}, merged[0]["source_refs"])

    def test_duplicate_heavy_page_uses_whole_page_fallback(self):
        page_blocks = [{"texts": ["same text"], "content_hash": "a"} for _ in range(6)]

        self.assertTrue(should_use_whole_page_fallback(page_blocks))

    def test_whole_page_block_dedupes_text_and_refs(self):
        page = {
            "number": 3,
            "title": "Page title",
            "blocks": [
                {
                    "texts": ["same text"],
                    "source_refs": [{"kind": "slide_text", "slide": 3, "object_id": "a"}],
                },
                {
                    "texts": ["same text", "next text"],
                    "source_refs": [{"kind": "slide_text", "slide": 3, "object_id": "b"}],
                },
            ],
        }

        block = build_whole_page_block(page, "duplicate_animation_text")

        self.assertEqual(block["id"], "s3_page")
        self.assertEqual(block["type"], "whole_page")
        self.assertEqual(block["texts"], ["same text", "next text"])
        self.assertEqual(block["display_bbox"], {"x": 0, "y": 0, "w": 1, "h": 1})
        self.assertEqual(len(block["source_refs"]), 2)
