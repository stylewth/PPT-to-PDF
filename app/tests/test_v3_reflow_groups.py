import unittest

from app.backend.reflow_groups import build_reflow_groups


class V3ReflowGroupsTest(unittest.TestCase):
    def test_groups_formula_with_covering_text_anchor(self):
        slide = {
            "size": {"width": 12192000, "height": 6858000},
            "object_boxes": [
                {
                    "id": "body",
                    "type": "sp",
                    "text": "Capacitance explanation",
                    "bbox": {"x": 2000000, "y": 2200000, "w": 6000000, "h": 1100000},
                },
                {
                    "id": "formula",
                    "type": "graphicFrame",
                    "text": "",
                    "bbox": {"x": 5100000, "y": 2300000, "w": 1200000, "h": 900000},
                },
                {
                    "id": "title",
                    "type": "sp",
                    "text": "(2) Capacitance",
                    "bbox": {"x": 4300000, "y": 1100000, "w": 3700000, "h": 520000},
                },
            ],
            "animation_steps": [
                {
                    "target_id": "formula",
                    "covered_objects": [
                        {
                            "id": "body",
                            "text": "Capacitance explanation",
                            "bbox": {"x": 2000000, "y": 2200000, "w": 6000000, "h": 1100000},
                        }
                    ],
                }
            ],
        }

        groups = build_reflow_groups(slide)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["anchor_id"], "body")
        self.assertEqual(groups[0]["visual_ids"], ["formula"])
        self.assertNotIn("title", groups[0]["member_ids"])

    def test_keeps_unrelated_visual_out_of_group(self):
        slide = {
            "size": {"width": 12192000, "height": 6858000},
            "object_boxes": [
                {
                    "id": "body",
                    "type": "sp",
                    "text": "First paragraph",
                    "bbox": {"x": 2000000, "y": 2000000, "w": 5000000, "h": 900000},
                },
                {
                    "id": "cover",
                    "type": "sp",
                    "text": "Cover",
                    "bbox": {"x": 2100000, "y": 2050000, "w": 4500000, "h": 700000},
                },
                {
                    "id": "unrelated_pic",
                    "type": "pic",
                    "text": "",
                    "bbox": {"x": 8200000, "y": 900000, "w": 2000000, "h": 1200000},
                },
            ],
            "animation_steps": [
                {
                    "target_id": "cover",
                    "covered_objects": [
                        {
                            "id": "body",
                            "text": "First paragraph",
                            "bbox": {"x": 2000000, "y": 2000000, "w": 5000000, "h": 900000},
                        }
                    ],
                }
            ],
        }

        groups = build_reflow_groups(slide)

        self.assertEqual(groups[0]["member_ids"], ["body", "cover"])
        self.assertNotIn("unrelated_pic", groups[0]["member_ids"])


if __name__ == "__main__":
    unittest.main()
