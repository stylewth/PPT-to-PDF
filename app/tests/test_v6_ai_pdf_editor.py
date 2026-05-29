import json
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V6AIPdfEditorTest(unittest.TestCase):
    def test_editor_returns_compact_decisions_and_export_payload(self):
        from ai_pdf_editor import edit_explanations_for_pdf

        captured = {}

        def provider(payload, api_key):
            captured["payload"] = payload
            captured["api_key"] = api_key
            return json.dumps(
                {
                    "items": [
                        {
                            "target_kind": "block",
                            "target_id": "s1_b1",
                            "include_in_pdf": True,
                            "priority": 1,
                            "pdf_title": "介质中的电场",
                            "pdf_snippet": "介质加入后，电场减弱不是电荷消失，而是束缚电荷产生反向场。",
                            "importance_reason": "解释公式背后的物理含义。",
                            "drop_reason": "",
                            "layout_intent": "blank_note",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        },
                        {
                            "target_kind": "block",
                            "target_id": "s1_b2",
                            "include_in_pdf": False,
                            "priority": 9,
                            "pdf_title": "",
                            "pdf_snippet": "",
                            "importance_reason": "",
                            "drop_reason": "只是复述原文。",
                            "layout_intent": "drop",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape2"}],
                        },
                    ]
                }
            )

        result = edit_explanations_for_pdf(
            _knowledge_index(),
            [
                _block_card("s1_b1", "长解释 1", "shape1"),
                _block_card("s1_b2", "长解释 2", "shape2"),
            ],
            api_key="sk-test",
            provider=provider,
        )

        self.assertEqual(captured["api_key"], "sk-test")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["decisions"]), 2)
        self.assertEqual(result["decisions"][0]["pdf_snippet"], "介质加入后，电场减弱不是电荷消失，而是束缚电荷产生反向场。")
        self.assertTrue(result["decisions"][1]["include_in_pdf"])
        self.assertEqual(result["decisions"][1]["pdf_snippet"], "s1_b2 短讲解")
        self.assertEqual(len(result["export_explanations"]), 2)
        self.assertEqual(result["export_explanations"][0]["block_id"], "s1_b1")
        self.assertTrue(result["export_explanations"][0]["include_in_pdf"])
        self.assertTrue(result["export_explanations"][1]["include_in_pdf"])
        prompt = captured["payload"]["messages"][1]["content"]
        self.assertIn("不要把完整解释原文直接放进 PDF", prompt)
        self.assertIn("用户界面默认不展示 reason", prompt)

    def test_editor_rejects_overlong_pdf_snippet(self):
        from ai_pdf_editor import edit_explanations_for_pdf

        def provider(payload, api_key):
            return {
                "items": [
                    {
                        "target_kind": "block",
                        "target_id": "s1_b1",
                        "include_in_pdf": True,
                        "priority": 1,
                        "pdf_title": "太长",
                        "pdf_snippet": "长" * 121,
                        "importance_reason": "重要",
                        "drop_reason": "",
                        "layout_intent": "blank_note",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                    }
                ]
            }

        with self.assertRaisesRegex(ValueError, "pdf_snippet"):
            edit_explanations_for_pdf(
                _knowledge_index(),
                [_block_card("s1_b1", "长解释", "shape1")],
                api_key="sk-test",
                provider=provider,
                max_snippet_chars=120,
            )

    def test_editor_rejects_internal_source_ref_text_in_snippet(self):
        from ai_pdf_editor import edit_explanations_for_pdf

        def provider(payload, api_key):
            return {
                "items": [
                    {
                        "target_kind": "block",
                        "target_id": "s1_b1",
                        "include_in_pdf": True,
                        "priority": 1,
                        "pdf_title": "来源泄露",
                        "pdf_snippet": "参考 slide_text@p1#shape1 可以看出结论。",
                        "importance_reason": "重要",
                        "drop_reason": "",
                        "layout_intent": "blank_note",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                    }
                ]
            }

        with self.assertRaisesRegex(ValueError, "内部来源"):
            edit_explanations_for_pdf(
                _knowledge_index(),
                [_block_card("s1_b1", "长解释", "shape1")],
                api_key="sk-test",
                provider=provider,
            )

    def test_editor_keeps_selected_card_when_model_omits_it(self):
        from ai_pdf_editor import edit_explanations_for_pdf

        def provider(payload, api_key):
            return {
                "items": [
                    {
                        "target_kind": "block",
                        "target_id": "s1_b1",
                        "include_in_pdf": True,
                        "priority": 1,
                        "pdf_title": "短稿",
                        "pdf_snippet": "第一块短稿。",
                        "importance_reason": "重要",
                        "drop_reason": "",
                        "layout_intent": "blank_note",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                    }
                ]
            }

        result = edit_explanations_for_pdf(
            _knowledge_index(),
            [
                _block_card("s1_b1", "长解释 1", "shape1"),
                _block_card("s1_b2", "长解释 2", "shape2"),
            ],
            api_key="sk-test",
            provider=provider,
        )

        self.assertEqual([item["block_id"] for item in result["export_explanations"]], ["s1_b1", "s1_b2"])
        self.assertEqual(result["export_explanations"][1]["explanation"]["short_explanation"], "s1_b2 短讲解")


class V6AIPdfEditorEndpointTest(unittest.TestCase):
    def test_edit_ai_pdf_for_job_returns_decisions_without_exporting_key(self):
        from server import edit_ai_pdf_for_job

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            (output_dir / "knowledge_blocks.json").write_text(
                json.dumps(_knowledge_index(), ensure_ascii=False),
                encoding="utf-8",
            )

            def provider(payload, api_key):
                return {
                    "items": [
                        {
                            "target_kind": "block",
                            "target_id": "s1_b1",
                            "include_in_pdf": True,
                            "priority": 1,
                            "pdf_title": "短稿",
                            "pdf_snippet": "这是进入 PDF 的短补充。",
                            "importance_reason": "重要",
                            "drop_reason": "",
                            "layout_intent": "extension_panel",
                            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                        }
                    ]
                }

            result = edit_ai_pdf_for_job(
                "jobx",
                output_dir,
                [_block_card("s1_b1", "长解释", "shape1")],
                api_key="sk-test",
                provider=provider,
            )

        self.assertEqual(result["status"], "ok")
        self.assertNotIn("api_key", json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["export_explanations"][0]["explanation"]["short_explanation"], "这是进入 PDF 的短补充。")
        self.assertEqual(result["export_explanations"][0]["layout_intent"], "margin_note")


def _block_card(block_id: str, detail: str, object_id: str) -> dict:
    return {
        "block_id": block_id,
        "explanation": {
            "short_explanation": f"{block_id} 短讲解",
            "detail": detail,
            "sections": [{"label": "学习要点", "items": [detail]}],
            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": object_id}],
        },
    }


def _knowledge_index() -> dict:
    return {
        "slides": [
            {
                "number": 1,
                "blocks": [
                    {
                        "id": "s1_b1",
                        "title": "公式块",
                        "summary": "解释公式",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
                    },
                    {
                        "id": "s1_b2",
                        "title": "重复块",
                        "summary": "重复原文",
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape2"}],
                    },
                ],
            }
        ]
    }


if __name__ == "__main__":
    unittest.main()
