import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from metrics_builder import build_metrics


class V3MetricsBuilderTest(unittest.TestCase):
    def test_build_metrics_reports_transparent_time_savings(self):
        analysis = {
            "slides": [
                {"number": 1, "animation_target_count": 2, "unsupported_animation_count": 0, "warnings": [{"code": "object_overlap"}]},
                {"number": 2, "animation_target_count": 0, "unsupported_animation_count": 1, "warnings": [{"code": "unsupported_animation"}]},
            ]
        }
        plan = {
            "summary": {
                "source_slide_count": 2,
                "guide_page_count": 0,
                "micro_reflow_pages": [1],
                "object_reflow_pages": [2],
            }
        }

        metrics = build_metrics(analysis, plan, runtime_seconds=8.42)

        self.assertEqual(metrics["runtime_seconds"], 8.42)
        self.assertEqual(metrics["source_slide_count"], 2)
        self.assertEqual(metrics["guide_page_count"], 2)
        self.assertEqual(metrics["animated_page_count"], 1)
        self.assertEqual(metrics["unsupported_animation_count"], 1)
        self.assertEqual(metrics["micro_reflow_page_count"], 1)
        self.assertEqual(metrics["object_reflow_page_count"], 1)
        self.assertGreater(metrics["estimated_manual_review_minutes"], metrics["estimated_tool_minutes"])
        self.assertIn("估算公式", metrics["notes"])


if __name__ == "__main__":
    unittest.main()
