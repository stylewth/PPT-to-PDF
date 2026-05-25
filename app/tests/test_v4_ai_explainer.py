import json
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


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class V4AIExplainerTest(unittest.TestCase):
    def test_explain_blocks_calls_provider_and_caches_structured_result(self):
        from ai_explainer import explain_blocks

        calls = []

        def provider(payload, api_key):
            calls.append({"payload": payload, "api_key": api_key})
            return json.dumps(
                {
                    "block_id": "s1_b1",
                    "short_explanation": "这个公式描述半径。",
                    "detail": "半径与速度和质量成正比，与电荷量和磁感应强度成反比。",
                    "key_points": ["只解释选中公式块"],
                    "common_misunderstanding": [],
                    "review_questions": ["半径和磁感应强度是什么关系？"],
                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                    "missing_context": [],
                    "confidence": "medium",
                }
            )

        with workspace_tmpdir() as tmp:
            result = explain_blocks(
                _knowledge_index(),
                ["s1_b1"],
                api_key="sk-test-secret",
                model="demo-model",
                provider=provider,
                cache_dir=tmp,
            )
            cache_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp.glob("*.json"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["explanation"]["block_id"], "s1_b1")
        self.assertEqual(calls[0]["api_key"], "sk-test-secret")
        self.assertEqual(calls[0]["payload"]["model"], "demo-model")
        self.assertIn('"kind": "slide_text"', calls[0]["payload"]["messages"][1]["content"])
        self.assertNotIn("sk-test-secret", cache_text)
        self.assertTrue(result["audit"]["passed"])

    def test_explain_blocks_accepts_compact_source_ref_labels_from_model(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return {
                "block_id": "s1_b1",
                "short_explanation": "这个公式描述半径。",
                "detail": "半径与速度和质量成正比。",
                "key_points": "短来源格式会被规范化",
                "common_misunderstanding": None,
                "review_questions": {"question": "半径和速度是什么关系？"},
                "source_refs": ["slide_text@p1#4"],
                "missing_context": [],
                "confidence": "medium",
            }

        result = explain_blocks(
            _knowledge_index(),
            ["s1_b1"],
            api_key="sk-test-secret",
            provider=provider,
        )

        self.assertTrue(result["audit"]["passed"])
        self.assertEqual(result["explanation"]["key_points"], ["短来源格式会被规范化"])
        self.assertEqual(result["explanation"]["review_questions"], ["半径和速度是什么关系？"])
        self.assertEqual(
            result["explanation"]["source_refs"],
            [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
        )

    def test_explain_blocks_rejects_response_without_valid_source_refs(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return {
                "block_id": "s1_b1",
                "short_explanation": "没有来源的解释不允许进入结果。",
                "detail": "bad",
                "key_points": [],
                "common_misunderstanding": [],
                "review_questions": [],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "missing"}],
                "missing_context": [],
                "confidence": "low",
            }

        with self.assertRaises(ValueError):
            explain_blocks(
                _knowledge_index(),
                ["s1_b1"],
                api_key="sk-test-secret",
                provider=provider,
            )

    def test_explain_blocks_rejects_json_array_without_unhashable_error(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return json.dumps(
                [
                    {
                        "block_id": "s1_b1",
                        "short_explanation": "数组格式不符合约定。",
                        "detail": "bad",
                        "key_points": [],
                        "common_misunderstanding": [],
                        "review_questions": [],
                        "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                        "missing_context": [],
                        "confidence": "low",
                    }
                ]
            )

        with self.assertRaises(ValueError) as raised:
            explain_blocks(
                _knowledge_index(),
                ["s1_b1"],
                api_key="sk-test-secret",
                provider=provider,
            )

        message = str(raised.exception)
        self.assertIn("JSON 对象", message)
        self.assertNotIn("unhashable", message)

    def test_explain_blocks_rejects_non_json_instead_of_displaying_raw_content(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            return (
                '{"block_id":"s1_b1","short_explanation":"解释。"}\n'
                'source_refs: [{"kind":"slide_text","slide":1,"object_id":"4"}]'
            )

        with self.assertRaises(ValueError) as raised:
            explain_blocks(
                _knowledge_index(),
                ["s1_b1"],
                api_key="sk-test-secret",
                provider=provider,
            )

        self.assertIn("合法 JSON", str(raised.exception))
        self.assertNotIn("source_refs", str(raised.exception))


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
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
