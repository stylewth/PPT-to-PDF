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

from compare_builder import write_compare_html


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class V3CompareBuilderTest(unittest.TestCase):
    def test_write_compare_html_contains_outputs_and_metrics(self):
        with workspace_tmpdir() as tmp:
            output = tmp / "compare.html"
            html_path = write_compare_html(
                output,
                source={"name": "demo.pptx", "slide_count": 2},
                plan={"summary": {"micro_reflow_pages": [1], "guide_page_count": 0}},
                metrics={"estimated_saved_minutes": 12.5, "animated_page_count": 1},
                report={"warnings": [{"code": "object_overlap", "message": "存在遮挡"}]},
            )

            html = html_path.read_text(encoding="utf-8")

        self.assertIn("base.pdf", html)
        self.assertIn("guide.pdf", html)
        self.assertIn("遮挡展开", html)
        self.assertIn("12.5", html)
        self.assertIn("object_overlap", html)


if __name__ == "__main__":
    unittest.main()
