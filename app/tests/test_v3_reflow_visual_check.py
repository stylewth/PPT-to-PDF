import unittest

from app.backend.reflow_visual_check import check_reflow_intent


class V3ReflowVisualCheckTest(unittest.TestCase):
    def test_flags_right_column_bias_for_moved_visuals(self):
        page = {"width": 10000, "height": 6000}
        before = [
            {"id": "a", "bbox": {"x": 1000, "y": 1000, "w": 1000, "h": 800}},
            {"id": "b", "bbox": {"x": 1400, "y": 2300, "w": 1000, "h": 800}},
        ]
        after = [
            {"id": "a", "bbox": {"x": 7900, "y": 1000, "w": 1000, "h": 800}},
            {"id": "b", "bbox": {"x": 7600, "y": 2300, "w": 1000, "h": 800}},
        ]
        operations = [
            {"id": "a", "object_type": "pic", "from": before[0]["bbox"], "to": after[0]["bbox"]},
            {"id": "b", "object_type": "graphicFrame", "from": before[1]["bbox"], "to": after[1]["bbox"]},
        ]

        result = check_reflow_intent(before, after, operations, page)

        self.assertFalse(result["passed"])
        self.assertIn("视觉对象集中到右侧栏", result["warnings"])

    def test_passes_local_repair_with_small_visual_move(self):
        page = {"width": 10000, "height": 6000}
        before = [
            {"id": "body", "bbox": {"x": 2500, "y": 2000, "w": 4200, "h": 1000}},
            {"id": "formula", "bbox": {"x": 4500, "y": 2200, "w": 1200, "h": 500}},
        ]
        after = [
            {"id": "body", "bbox": {"x": 2500, "y": 2000, "w": 4200, "h": 1000}},
            {"id": "formula", "bbox": {"x": 4700, "y": 3100, "w": 1200, "h": 500}},
        ]
        operations = [
            {
                "id": "formula",
                "object_type": "graphicFrame",
                "from": before[1]["bbox"],
                "to": after[1]["bbox"],
            }
        ]

        result = check_reflow_intent(before, after, operations, page)

        self.assertTrue(result["passed"])
        self.assertEqual(result["warnings"], [])

    def test_single_visual_on_right_is_not_column_bias(self):
        page = {"width": 10000, "height": 6000}
        before = [{"id": "formula", "bbox": {"x": 5200, "y": 2300, "w": 1000, "h": 800}}]
        after = [{"id": "formula", "bbox": {"x": 7700, "y": 900, "w": 1000, "h": 800}}]
        operations = [
            {
                "id": "formula",
                "object_type": "graphicFrame",
                "from": before[0]["bbox"],
                "to": after[0]["bbox"],
            }
        ]

        result = check_reflow_intent(before, after, operations, page)

        self.assertTrue(result["passed"])
        self.assertNotIn("视觉对象集中到右侧栏", result["warnings"])

        self.assertEqual(result["right_column_bias"], 0.0)

    def test_anchor_related_visual_move_is_not_treated_as_unexplained_drift(self):
        page = {"width": 10000, "height": 6000}
        before = [
            {"id": "body", "bbox": {"x": 1200, "y": 2000, "w": 6200, "h": 900}},
            {"id": "formula", "bbox": {"x": 4400, "y": 2100, "w": 1000, "h": 800}},
        ]
        after = [
            {"id": "body", "bbox": {"x": 1200, "y": 2000, "w": 6200, "h": 900}},
            {"id": "formula", "bbox": {"x": 8200, "y": 2600, "w": 1000, "h": 800}},
        ]
        operations = [
            {
                "id": "formula",
                "object_type": "graphicFrame",
                "anchor_id": "body",
                "from": before[1]["bbox"],
                "to": after[1]["bbox"],
            }
        ]

        result = check_reflow_intent(before, after, operations, page)

        self.assertTrue(result["passed"])
        self.assertNotIn("对象移动距离过大", result["warnings"])


if __name__ == "__main__":
    unittest.main()
