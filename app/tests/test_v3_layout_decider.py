import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from layout_decider import annotation_slot, decide_slide_layout, select_annotation_zone


class V3LayoutDeciderTest(unittest.TestCase):
    def test_decide_slide_layout_routes_complex_supported_pages_to_object_reflow(self):
        self.assertEqual(
            decide_slide_layout(
                {
                    "animation_target_count": 1,
                    "unsupported_animation_count": 1,
                    "animation_steps": [{"target_id": "1"}],
                    "decision_hint": {"strategy": "reflow_or_expand", "reason": "unsupported"},
                }
            )["strategy"],
            "report_only",
        )
        self.assertEqual(
            decide_slide_layout(
                {
                    "animation_target_count": 2,
                    "unsupported_animation_count": 0,
                    "animation_steps": [{"target_id": "1"}, {"target_id": "2"}],
                    "decision_hint": {"strategy": "reflow_or_expand", "reason": "crowded"},
                    "complexity": "medium",
                    "object_count": 4,
                }
            )["strategy"],
            "object_reflow",
        )
        self.assertEqual(
            decide_slide_layout(
                {
                    "animation_target_count": 1,
                    "unsupported_animation_count": 0,
                    "animation_steps": [{"target_id": "1"}],
                    "decision_hint": {"strategy": "native_enhance", "reason": "simple"},
                }
            )["strategy"],
            "native_enhance",
        )
        self.assertEqual(
            decide_slide_layout(
                {
                    "animation_target_count": 0,
                    "unsupported_animation_count": 0,
                    "animation_steps": [],
                    "decision_hint": {"strategy": "keep_native", "reason": "static"},
                }
            )["strategy"],
            "keep_native",
        )

    def test_select_annotation_zone_prefers_clear_right_edge(self):
        zone = select_annotation_zone(
            {
                "size": {"width": 12000000, "height": 7000000},
                "object_boxes": [
                    {"x": 0, "y": 0, "w": 7600000, "h": 7000000},
                ],
            },
            marker_count=2,
        )

        self.assertIsNotNone(zone)
        self.assertEqual(zone["side"], "right")
        self.assertGreaterEqual(zone["capacity"], 2)
        first = annotation_slot(zone, 1)
        second = annotation_slot(zone, 2)
        self.assertGreaterEqual(first["x"], 7600000)
        self.assertGreaterEqual(first["w"], 1150000)
        self.assertGreater(second["y"], first["y"])

    def test_select_annotation_zone_returns_none_when_edges_are_occupied(self):
        zone = select_annotation_zone(
            {
                "size": {"width": 12000000, "height": 7000000},
                "object_boxes": [
                    {"x": 0, "y": 0, "w": 12000000, "h": 7000000},
                ],
            },
            marker_count=1,
        )

        self.assertIsNone(zone)


if __name__ == "__main__":
    unittest.main()
