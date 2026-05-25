import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from server import explain_blocks_for_job, explain_page_for_job


class V5AIPageEndpointTest(unittest.TestCase):
    def test_explain_page_for_job_uses_whole_page_context_and_page_image(self):
        calls = []

        def provider(payload, api_key):
            calls.append(payload)
            return {
                "block_id": "page_1",
                "short_explanation": "整页解释。",
                "detail": "整页整体说明。",
                "key_points": [],
                "common_misunderstanding": [],
                "review_questions": [],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                "missing_context": [],
                "confidence": "medium",
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_job_files(root)

            result = explain_page_for_job(
                "jobx",
                root,
                1,
                api_key="sk-test",
                provider=provider,
                prompt_profile="training",
                include_images=True,
            )

        self.assertEqual(result["mode"], "whole_page")
        self.assertEqual(result["context_block_ids"], ["s1_b1", "s1_b2"])
        self.assertIn("工作培训", calls[0]["messages"][0]["content"])
        user_content = calls[0]["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[1]["type"], "image_url")

    def test_explain_blocks_for_job_can_attach_block_crop(self):
        calls = []

        def provider(payload, api_key):
            calls.append(payload)
            return {
                "block_id": "s1_b1",
                "short_explanation": "块解释。",
                "detail": "块级说明。",
                "key_points": [],
                "common_misunderstanding": [],
                "review_questions": [],
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                "missing_context": [],
                "confidence": "medium",
            }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_job_files(root)

            result = explain_blocks_for_job(
                "jobx",
                root,
                ["s1_b1"],
                api_key="sk-test",
                provider=provider,
                include_images=True,
            )

        self.assertEqual(result["mode"], "explain")
        user_content = calls[0]["messages"][1]["content"]
        self.assertIsInstance(user_content, list)
        self.assertEqual(user_content[1]["type"], "image_url")


def _write_job_files(root: Path) -> None:
    (root / "knowledge_blocks.json").write_text(
        json.dumps(
            {
                "slides": [
                    {
                        "number": 1,
                        "title": "洛伦兹力",
                        "blocks": [
                            {
                                "id": "s1_b1",
                                "title": "半径公式",
                                "type": "formula_group",
                                "texts": ["r = mv / qB"],
                                "summary": "解释半径公式。",
                                "display_bbox": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.4},
                                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "4"}],
                            },
                            {
                                "id": "s1_b2",
                                "title": "图示",
                                "type": "diagram_group",
                                "texts": ["速度方向与磁场方向。"],
                                "summary": "解释图示。",
                                "display_bbox": {"x": 0.5, "y": 0.5, "w": 0.3, "h": 0.3},
                                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "5"}],
                            },
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    preview_dir = root / "guide_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 80), "white").save(preview_dir / "page_001.png")
    (root / "guide_preview_manifest.json").write_text(
        json.dumps({"pages": [{"number": 1, "image": "guide_preview/page_001.png"}]}),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
