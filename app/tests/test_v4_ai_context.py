import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V4AIContextTest(unittest.TestCase):
    def test_context_contains_only_selected_block_evidence_by_default(self):
        from ai_context import build_ai_context

        index = _knowledge_index()

        context = build_ai_context(index, ["s1_b1"], mode="explain", max_chars=500)

        self.assertEqual(context["mode"], "explain")
        self.assertEqual([block["id"] for block in context["blocks"]], ["s1_b1"])
        self.assertIn("r = mv / qB", context["context_text"])
        self.assertNotIn("无关例题", context["context_text"])
        self.assertLessEqual(len(context["context_text"]), 500)
        self.assertEqual(context["source_refs"], [{"kind": "slide_text", "slide": 1, "object_id": "4"}])
        self.assertNotIn("source_refs JSON", context["context_text"])

    def test_compose_context_keeps_selection_order_and_token_budget(self):
        from ai_context import build_ai_context

        index = _knowledge_index()

        context = build_ai_context(index, ["s2_b1", "s1_b1"], mode="compose", max_chars=180)

        self.assertEqual([block["id"] for block in context["blocks"]], ["s2_b1", "s1_b1"])
        self.assertLessEqual(len(context["context_text"]), 180)
        self.assertGreater(context["estimated_token_count"], 0)

    def test_whole_page_context_keeps_source_refs_out_of_evidence_text(self):
        from ai_context import build_whole_page_context

        page = _knowledge_index()["slides"][0]

        context = build_whole_page_context(page, max_chars=500)

        self.assertIn("r = mv / qB", context["context_text"])
        self.assertEqual(
            context["source_refs"],
            [
                {"kind": "slide_text", "slide": 1, "object_id": "4"},
                {"kind": "slide_text", "slide": 1, "object_id": "9"},
            ],
        )
        self.assertNotIn("source_refs JSON", context["context_text"])


def _knowledge_index():
    return {
        "kind": "knowledge_blocks",
        "version": "v4a",
        "slides": [
            {
                "number": 1,
                "title": "洛伦兹力",
                "blocks": [
                    {
                        "id": "s1_b1",
                        "type": "formula_group",
                        "title": "半径公式",
                        "texts": ["r = mv / qB", "半径由速度、质量、电荷量和磁感应强度决定。"],
                        "summary": "解释半径公式。",
                        "object_ids": ["4"],
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                        "token_estimate": 40,
                    },
                    {
                        "id": "s1_b2",
                        "type": "text_concept",
                        "title": "无关例题",
                        "texts": ["无关例题：求周期。"],
                        "summary": "不应进入单块解释。",
                        "object_ids": ["9"],
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "9"}],
                        "token_estimate": 20,
                    },
                ],
            },
            {
                "number": 2,
                "title": "机械运动",
                "blocks": [
                    {
                        "id": "s2_b1",
                        "type": "media_timeline",
                        "title": "滚动过程",
                        "texts": ["关键帧展示小球滚动。"],
                        "summary": "GIF 关键帧。",
                        "object_ids": ["7"],
                        "source_refs": [{"kind": "media", "slide": 2, "object_id": "7"}],
                        "token_estimate": 35,
                    }
                ],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
