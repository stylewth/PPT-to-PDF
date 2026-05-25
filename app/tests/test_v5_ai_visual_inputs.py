import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


class V5AIVisualInputsTest(unittest.TestCase):
    def test_page_visual_input_uses_guide_preview_page_image(self):
        from ai_visuals import build_page_visual_inputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root)

            visuals = build_page_visual_inputs(root, 1, include_images=True)

            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0]["label"], "guide page 1")
            self.assertTrue(visuals[0]["data_url"].startswith("data:image/png;base64,"))

    def test_block_visual_input_crops_selected_block_area(self):
        from ai_visuals import build_block_visual_inputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root)
            block = {
                "id": "s1_b1",
                "display_bbox": {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5},
            }

            visuals = build_block_visual_inputs(root, 1, block, include_images=True)

            data = base64.b64decode(visuals[0]["data_url"].split(",", 1)[1])
            cropped_path = root / "cropped.png"
            cropped_path.write_bytes(data)
            with Image.open(cropped_path) as image:
                self.assertEqual(image.size, (50, 40))

    def test_visual_inputs_can_be_disabled_for_text_only_models(self):
        from ai_visuals import build_page_visual_inputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_manifest(root)

            self.assertEqual(build_page_visual_inputs(root, 1, include_images=False), [])


def _write_manifest(root: Path) -> None:
    preview_dir = root / "guide_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (100, 80), "white")
    image.save(preview_dir / "page_001.png")
    (root / "guide_preview_manifest.json").write_text(
        json.dumps(
            {
                "pages": [
                    {
                        "number": 1,
                        "image": "guide_preview/page_001.png",
                        "image_width": 100,
                        "image_height": 80,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
