import json
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V5AIPromptProfilesTest(unittest.TestCase):
    def test_training_profile_changes_system_prompt(self):
        from ai_explainer import explain_blocks

        captured = {}

        def provider(payload, api_key):
            captured["payload"] = payload
            return _ok_response()

        explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test",
            provider=provider,
            prompt_profile="training",
        )

        system = captured["payload"]["messages"][0]["content"]
        self.assertIn("工作培训", system)
        self.assertIn("培训要点", system)

        content = captured["payload"]["messages"][1]["content"]
        self.assertIn("培训目标", content)
        self.assertIn("操作步骤", content)
        self.assertIn("风险提醒", content)
        self.assertIn("执行清单", content)
        self.assertNotIn("易错点", content)
        self.assertNotIn("复习题", content)

    def test_simple_profile_asks_for_brief_explanation(self):
        from ai_explainer import explain_blocks

        captured = {}

        def provider(payload, api_key):
            captured["payload"] = payload
            return _ok_response()

        explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test",
            provider=provider,
            prompt_profile="simple",
        )

        content = captured["payload"]["messages"][1]["content"]
        self.assertIn("简洁", content)
        self.assertIn("一眼明了", content)
        self.assertIn("三个以内", content)
        self.assertNotIn("易错点", content)
        self.assertNotIn("复习题", content)

    def test_profile_sections_are_normalized_for_frontend(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return {
                "block_id": "s1_b1",
                "short_explanation": "培训说明。",
                "detail": "只基于来源说明。",
                "sections": [
                    {"label": "操作步骤", "items": ["先观察图示", "再说明动作"]},
                    {"label": "风险提醒", "items": "不要编造来源"},
                ],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                "missing_context": [],
                "confidence": "medium",
            }

        result = explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test",
            provider=provider,
            prompt_profile="training",
        )

        self.assertEqual(
            result["explanation"]["sections"],
            [
                {"label": "操作步骤", "items": ["先观察图示", "再说明动作"]},
                {"label": "风险提醒", "items": ["不要编造来源"]},
            ],
        )

    def test_training_profile_maps_legacy_fields_to_training_sections(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return {
                "block_id": "s1_b1",
                "short_explanation": "培训说明。",
                "detail": "只基于来源说明。",
                "key_points": ["核心动作"],
                "common_misunderstanding": ["风险边界"],
                "review_questions": ["执行检查"],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                "missing_context": [],
                "confidence": "medium",
            }

        result = explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test",
            provider=provider,
            prompt_profile="training",
        )

        self.assertEqual(
            result["explanation"]["sections"],
            [
                {"label": "培训要点", "items": ["核心动作"]},
                {"label": "风险提醒", "items": ["风险边界"]},
                {"label": "执行清单", "items": ["执行检查"]},
            ],
        )

    def test_visual_input_is_sent_as_multimodal_message_content(self):
        from ai_explainer import explain_blocks

        captured = {}

        def provider(payload, api_key):
            captured["payload"] = payload
            return _ok_response()

        result = explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test",
            provider=provider,
            visual_inputs=[{"data_url": "data:image/png;base64,abc", "label": "第 1 页图"}],
        )

        user_content = captured["payload"]["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[0]["type"], "text")
        self.assertEqual(user_content[1]["type"], "image_url")
        self.assertEqual(user_content[1]["image_url"]["url"], "data:image/png;base64,abc")
        self.assertEqual(result["usage"]["visual_input_count"], 1)

    def test_explain_page_sends_one_whole_page_request(self):
        from ai_explainer import explain_page

        calls = []

        def provider(payload, api_key):
            calls.append(payload)
            return {
                "block_id": "page_1",
                "short_explanation": "整页解释。",
                "detail": "这一页整体讲公式和图的关系。",
                "key_points": [],
                "common_misunderstanding": [],
                "review_questions": [],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                "missing_context": [],
                "confidence": "medium",
            }

        result = explain_page(
            _knowledge_index()["slides"][0],
            api_key="sk-test",
            provider=provider,
            prompt_profile="study",
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(result["mode"], "whole_page")
        self.assertEqual(result["context_block_ids"], ["s1_b1", "s1_b2"])


def _ok_response():
    return json.dumps(
        {
            "block_id": "s1_b1",
            "short_explanation": "解释。",
            "detail": "只基于来源解释。",
            "key_points": [],
            "common_misunderstanding": [],
            "review_questions": [],
            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
            "missing_context": [],
            "confidence": "medium",
        }
    )


def _knowledge_index():
    return {
        "kind": "knowledge_blocks",
        "version": "v5a",
        "slides": [
            {
                "number": 1,
                "title": "洛伦兹力",
                "blocks": [
                    {
                        "id": "s1_b1",
                        "type": "formula_group",
                        "title": "半径公式",
                        "texts": ["r = mv / qB"],
                        "summary": "解释半径公式。",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                    },
                    {
                        "id": "s1_b2",
                        "type": "diagram_group",
                        "title": "图示",
                        "texts": ["速度方向与磁场方向。"],
                        "summary": "解释图示。",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "5"}],
                    },
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
