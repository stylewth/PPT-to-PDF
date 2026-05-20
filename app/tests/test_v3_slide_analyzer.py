import json
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEST_DIR))
TMP_ROOT = Path(__file__).resolve().parent / ".tmp_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

from converter import convert_pptx
from pptx_parser import parse_pptx
from slide_analyzer import analyze_presentation
from test_v2_pipeline import write_minimal_pptx


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class V3SlideAnalyzerTest(unittest.TestCase):
    def test_analyze_presentation_outputs_page_metrics_and_animation_steps(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)
            presentation = parse_pptx(pptx_path)

        analysis = analyze_presentation(presentation)
        slide = analysis["slides"][0]

        self.assertEqual(analysis["kind"], "slide_analysis")
        self.assertEqual(analysis["version"], "v3b")
        self.assertEqual(analysis["page"], {"width": 12192000, "height": 6858000})
        self.assertEqual(slide["object_count"], 3)
        self.assertEqual(slide["text_box_count"], 3)
        self.assertEqual(len(slide["object_boxes"]), 3)
        self.assertEqual(slide["object_boxes"][0]["id"], "2")
        self.assertEqual(slide["object_boxes"][0]["bbox"]["w"], 5000000)
        self.assertEqual(slide["animation_target_count"], 2)
        self.assertTrue(slide["notes_present"])
        self.assertEqual([step["target_text"] for step in slide["animation_steps"]], ["当前位置", "最终公式"])
        self.assertEqual(slide["animation_steps"][1]["covered_objects"][0]["text"], "当前位置")
        self.assertEqual(slide["animation_steps"][1]["covered_objects"][0]["bbox"]["x"], 100000)
        self.assertGreater(slide["metrics"]["object_coverage_ratio"], 0)
        self.assertGreater(slide["metrics"]["max_object_overlap_ratio"], 0.3)
        self.assertEqual(slide["crowding"], "high")
        self.assertEqual(slide["decision_hint"]["strategy"], "reflow_or_expand")

    def test_convert_pptx_writes_analysis_json_and_report_reference(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            output_dir = tmp / "out"
            write_minimal_pptx(pptx_path)

            result = convert_pptx(pptx_path, output_dir, render_pdf=False)

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["analysis_path"]).exists())
            analysis = json.loads(Path(result["analysis_path"]).read_text(encoding="utf-8"))
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(analysis["version"], "v3b")
            self.assertEqual(report["version"], "v3g")
            self.assertEqual(report["outputs"]["analysis_json"], "analysis.json")
            self.assertEqual(report["outputs"]["augment_plan_json"], "augment_plan.json")
            self.assertEqual(report["summary"]["high_crowding_pages"], [1])


if __name__ == "__main__":
    unittest.main()
