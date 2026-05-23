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


class V4AISecurityTest(unittest.TestCase):
    def test_cache_key_ignores_api_key_by_design(self):
        from ai_context import build_ai_context
        from ai_explainer import cache_key_for_request

        context = build_ai_context(_knowledge_index(), ["s1_b1"], mode="explain")

        first = cache_key_for_request("demo-model", "explain", context)
        second = cache_key_for_request("demo-model", "explain", context)

        self.assertEqual(first, second)
        self.assertNotIn("sk-", first)

    def test_api_key_is_not_written_to_ai_cache_or_return_payload(self):
        from ai_explainer import explain_blocks

        def provider(payload, api_key):
            self.assertEqual(api_key, "sk-live-secret")
            return json.dumps(
                {
                    "block_id": "s1_b1",
                    "short_explanation": "安全解释。",
                    "detail": "只基于来源解释。",
                    "key_points": ["key 不落盘"],
                    "common_misunderstanding": [],
                    "review_questions": [],
                    "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                    "missing_context": [],
                    "confidence": "medium",
                }
            )

        with workspace_tmpdir() as tmp:
            result = explain_blocks(
                _knowledge_index(),
                ["s1_b1"],
                api_key="sk-live-secret",
                provider=provider,
                cache_dir=tmp,
            )
            cached = "\n".join(path.read_text(encoding="utf-8") for path in tmp.glob("*.json"))

        self.assertNotIn("sk-live-secret", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("sk-live-secret", cached)


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
