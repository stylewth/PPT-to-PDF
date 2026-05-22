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

from augment_planner import build_augment_plan
from ooxml_slide_editor import apply_shape_operations, parse_slide_shapes
from object_reflow_planner import max_overlap_ratio, plan_object_reflow, simulate_operations
from pdf_augmenter import _relation_points, write_guide_deck
from pptx_parser import parse_pptx
from reflow_diagnostics import build_overlap_graph
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


class V3ObjectReflowTest(unittest.TestCase):
    def test_ooxml_editor_moves_and_resizes_existing_shape_without_losing_text(self):
        updated = apply_shape_operations(
            SIMPLE_SLIDE_XML,
            [
                {
                    "op": "move_resize",
                    "id": "3",
                    "to": {"x": 3000000, "y": 1200000, "w": 1600000, "h": 500000},
                    "reason": "解除遮挡",
                }
            ],
        )

        shapes = {shape["id"]: shape for shape in parse_slide_shapes(updated)}

        self.assertEqual(shapes["3"]["text"], "当前位置")
        self.assertEqual(
            shapes["3"]["bbox"],
            {"x": 3000000, "y": 1200000, "w": 1600000, "h": 500000},
        )
        self.assertEqual(shapes["4"]["bbox"]["x"], 900000)

    def test_ooxml_editor_moves_graphic_frame_using_native_transform(self):
        updated = apply_shape_operations(
            GRAPHIC_FRAME_SLIDE_XML,
            [
                {
                    "op": "move_resize",
                    "id": "4",
                    "to": {"x": 7600000, "y": 4100000, "w": 3000000, "h": 650000},
                    "reason": "移动公式",
                }
            ],
        )

        shapes = {shape["id"]: shape for shape in parse_slide_shapes(updated)}

        self.assertEqual(
            shapes["4"]["bbox"],
            {"x": 7600000, "y": 4100000, "w": 3000000, "h": 650000},
        )
        self.assertEqual(updated.count('x="7600000" y="4100000"'), 2)
        self.assertNotIn('x="3000000" y="2000000"', updated)
        self.assertIn("<p:xfrm>", updated)
        self.assertNotIn("</p:xfrm><p:spPr>", updated)

    def test_ooxml_editor_parses_and_moves_grouped_graphic_frame(self):
        updated = apply_shape_operations(
            GROUPED_GRAPHIC_FRAME_SLIDE_XML,
            [
                {
                    "op": "move_resize",
                    "id": "9",
                    "to": {"x": 6400000, "y": 2600000, "w": 2100000, "h": 720000},
                    "reason": "移动组内公式",
                }
            ],
        )

        shapes = {shape["id"]: shape for shape in parse_slide_shapes(updated)}

        self.assertIn("9", shapes)
        self.assertEqual(
            shapes["9"]["bbox"],
            {"x": 6400000, "y": 2600000, "w": 2100000, "h": 720000},
        )

    def test_overlap_graph_identifies_animation_occlusion_edges(self):
        graph = build_overlap_graph(
            {
                "number": 1,
                "object_boxes": [
                    {"id": "2", "bbox": {"x": 100000, "y": 900000, "w": 2100000, "h": 900000}},
                    {"id": "4", "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000}},
                ],
                "text_objects": [
                    {"id": "2", "text": "当前位置", "bbox": {"x": 100000, "y": 900000, "w": 2100000, "h": 900000}},
                    {"id": "4", "text": "最终公式", "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "4",
                        "target_text": "最终公式",
                        "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000},
                        "covered_objects": [
                            {"id": "2", "text": "当前位置", "bbox": {"x": 100000, "y": 900000, "w": 2100000, "h": 900000}},
                        ],
                    }
                ],
            }
        )

        edge = graph["overlap_edges"][0]
        self.assertEqual(edge["front_id"], "4")
        self.assertEqual(edge["back_id"], "2")
        self.assertGreater(edge["overlap_ratio"], 0.4)
        self.assertIn("animation_occlusion", edge["reasons"])

    def test_object_reflow_plan_reduces_overlap_for_dense_capacitance_slide(self):
        slide = _dense_capacitance_slide()
        before = max_overlap_ratio(slide["object_boxes"])

        plan = plan_object_reflow(slide)
        after_boxes = simulate_operations(slide["object_boxes"], plan["operations"])
        after = max_overlap_ratio(after_boxes)

        moved_ids = {operation["id"] for operation in plan["operations"] if operation["op"] == "move_resize"}
        self.assertIn("3", moved_ids)
        self.assertIn("20", moved_ids)
        self.assertLess(after, before * 0.45)
        self.assertLess(after, 0.2)
        text_boxes = [
            item["bbox"]
            for item in after_boxes
            if item["id"] in {"1048", "2", "19", "20"}
        ]
        text_boxes = sorted(text_boxes, key=lambda box: box["y"])
        gaps = [
            text_boxes[index + 1]["y"] - (box["y"] + box["h"])
            for index, box in enumerate(text_boxes[:-1])
        ]
        self.assertTrue(all(gap >= 260000 for gap in gaps))

    def test_object_reflow_plan_keeps_top_title_fixed(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 12192000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "2", "name": "Title", "text": "Gradient descent", "bbox": {"x": 0, "y": 0, "w": 5000000, "h": 600000}},
                    {"id": "3", "text": "current", "bbox": {"x": 100000, "y": 900000, "w": 2000000, "h": 900000}},
                    {"id": "4", "text": "final", "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000}},
                ],
                "text_objects": [
                    {"id": "2", "text": "Gradient descent", "bbox": {"x": 0, "y": 0, "w": 5000000, "h": 600000}},
                    {"id": "3", "text": "current", "bbox": {"x": 100000, "y": 900000, "w": 2000000, "h": 900000}},
                    {"id": "4", "text": "final", "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "4",
                        "target_text": "final",
                        "bbox": {"x": 900000, "y": 1000000, "w": 2100000, "h": 900000},
                        "covered_objects": [
                            {"id": "3", "text": "current", "bbox": {"x": 100000, "y": 900000, "w": 2000000, "h": 900000}},
                        ],
                    }
                ],
            }
        )

        moved_ids = {operation["id"] for operation in plan["operations"]}
        self.assertNotIn("2", moved_ids)

    def test_object_reflow_preserves_text_box_height_to_avoid_overflow(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 12192000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "a", "text": "Long paragraph", "bbox": {"x": 1000000, "y": 900000, "w": 5000000, "h": 1900000}},
                    {"id": "b", "text": "Cover", "bbox": {"x": 1600000, "y": 1100000, "w": 2500000, "h": 700000}},
                ],
                "text_objects": [
                    {"id": "a", "text": "Long paragraph", "bbox": {"x": 1000000, "y": 900000, "w": 5000000, "h": 1900000}},
                    {"id": "b", "text": "Cover", "bbox": {"x": 1600000, "y": 1100000, "w": 2500000, "h": 700000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "b",
                        "target_text": "Cover",
                        "bbox": {"x": 1600000, "y": 1100000, "w": 2500000, "h": 700000},
                        "covered_objects": [
                            {"id": "a", "text": "Long paragraph", "bbox": {"x": 1000000, "y": 900000, "w": 5000000, "h": 1900000}},
                        ],
                    }
                ],
            }
        )

        paragraph_op = next(operation for operation in plan["operations"] if operation["id"] == "a")
        self.assertGreaterEqual(paragraph_op["to"]["h"], paragraph_op["from"]["h"])

    def test_object_reflow_preserves_long_text_width_when_page_has_right_column(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 9144000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "text", "text": "Long paragraph", "bbox": {"x": 1900000, "y": 900000, "w": 5700000, "h": 1800000}},
                    {"id": "formula", "bbox": {"x": 6100000, "y": 1100000, "w": 2500000, "h": 900000}},
                ],
                "text_objects": [
                    {"id": "text", "text": "Long paragraph", "bbox": {"x": 1900000, "y": 900000, "w": 5700000, "h": 1800000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "formula",
                        "target_text": "formula",
                        "bbox": {"x": 6100000, "y": 1100000, "w": 2500000, "h": 900000},
                        "covered_objects": [
                            {"id": "text", "text": "Long paragraph", "bbox": {"x": 1900000, "y": 900000, "w": 5700000, "h": 1800000}},
                        ],
                    }
                ],
            }
        )

        ops = {operation["id"]: operation for operation in plan["operations"]}

        self.assertNotIn("text", ops)
        self.assertIn("formula", ops)

    def test_object_reflow_keeps_unoccluded_visual_objects_in_place(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 12192000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "text-a", "text": "first paragraph", "bbox": {"x": 1600000, "y": 1600000, "w": 4800000, "h": 900000}},
                    {"id": "text-b", "text": "cover paragraph", "bbox": {"x": 1900000, "y": 1700000, "w": 4200000, "h": 850000}},
                    {
                        "id": "decor-pic",
                        "type": "pic",
                        "text": "",
                        "bbox": {"x": 7600000, "y": 3400000, "w": 1600000, "h": 900000},
                    },
                ],
                "text_objects": [
                    {"id": "text-a", "text": "first paragraph", "bbox": {"x": 1600000, "y": 1600000, "w": 4800000, "h": 900000}},
                    {"id": "text-b", "text": "cover paragraph", "bbox": {"x": 1900000, "y": 1700000, "w": 4200000, "h": 850000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "text-b",
                        "target_text": "cover paragraph",
                        "bbox": {"x": 1900000, "y": 1700000, "w": 4200000, "h": 850000},
                        "covered_objects": [
                            {"id": "text-a", "text": "first paragraph", "bbox": {"x": 1600000, "y": 1600000, "w": 4800000, "h": 900000}},
                        ],
                    }
                ],
            }
        )

        moved_ids = {operation["id"] for operation in plan["operations"]}
        self.assertIn("text-a", moved_ids)
        self.assertIn("text-b", moved_ids)
        self.assertNotIn("decor-pic", moved_ids)

    def test_object_reflow_keeps_related_formula_near_its_text_anchor(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 12192000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2700000, "y": 2100000, "w": 5600000, "h": 1300000}},
                    {"id": "cover", "text": "Animated cover", "bbox": {"x": 3000000, "y": 2250000, "w": 3800000, "h": 760000}},
                    {
                        "id": "formula",
                        "type": "graphicFrame",
                        "text": "",
                        "bbox": {"x": 4300000, "y": 3500000, "w": 2600000, "h": 520000},
                    },
                ],
                "text_objects": [
                    {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2700000, "y": 2100000, "w": 5600000, "h": 1300000}},
                    {"id": "cover", "text": "Animated cover", "bbox": {"x": 3000000, "y": 2250000, "w": 3800000, "h": 760000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "cover",
                        "target_text": "Animated cover",
                        "bbox": {"x": 3000000, "y": 2250000, "w": 3800000, "h": 760000},
                        "covered_objects": [
                            {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2700000, "y": 2100000, "w": 5600000, "h": 1300000}},
                        ],
                    }
                ],
            }
        )

        ops = {operation["id"]: operation for operation in plan["operations"]}
        self.assertIn("formula", ops)
        body_to = ops["body"]["to"]
        formula_to = ops["formula"]["to"]
        self.assertLess(_overlap_ratio(formula_to, body_to), 0.02)
        self.assertLess(
            abs((formula_to["y"] + formula_to["h"] // 2) - (body_to["y"] + body_to["h"] // 2)),
            2400000,
        )

    def test_object_reflow_places_related_visual_in_local_blank_area_before_right_column(self):
        plan = plan_object_reflow(
            {
                "number": 1,
                "size": {"width": 12192000, "height": 6858000},
                "crowding": "high",
                "complexity": "complex",
                "object_boxes": [
                    {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2100000, "y": 2300000, "w": 5700000, "h": 900000}},
                    {"id": "cover", "text": "Animated cover", "bbox": {"x": 2400000, "y": 2380000, "w": 4200000, "h": 680000}},
                    {
                        "id": "diagram",
                        "type": "pic",
                        "text": "",
                        "bbox": {"x": 3300000, "y": 3600000, "w": 2100000, "h": 1100000},
                    },
                ],
                "text_objects": [
                    {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2100000, "y": 2300000, "w": 5700000, "h": 900000}},
                    {"id": "cover", "text": "Animated cover", "bbox": {"x": 2400000, "y": 2380000, "w": 4200000, "h": 680000}},
                ],
                "animation_steps": [
                    {
                        "target_id": "cover",
                        "target_text": "Animated cover",
                        "bbox": {"x": 2400000, "y": 2380000, "w": 4200000, "h": 680000},
                        "covered_objects": [
                            {"id": "body", "text": "The explanation paragraph", "bbox": {"x": 2100000, "y": 2300000, "w": 5700000, "h": 900000}},
                        ],
                    }
                ],
            }
        )

        ops = {operation["id"]: operation for operation in plan["operations"]}
        body_to = ops["body"]["to"]
        diagram_to = ops["diagram"]["to"]

        self.assertLess(diagram_to["x"], body_to["x"] + body_to["w"])
        self.assertGreaterEqual(diagram_to["y"], body_to["y"] + body_to["h"])

    def test_text_overlap_repair_stays_near_original_horizontal_band(self):
        slide = {
            "number": 1,
            "size": {"width": 12192000, "height": 6858000},
            "crowding": "high",
            "complexity": "complex",
            "object_boxes": [
                {"id": "a", "text": "Middle right paragraph", "bbox": {"x": 5200000, "y": 1900000, "w": 3600000, "h": 900000}},
                {"id": "b", "text": "Animated cover text", "bbox": {"x": 5400000, "y": 2050000, "w": 3200000, "h": 820000}},
            ],
            "text_objects": [
                {"id": "a", "text": "Middle right paragraph", "bbox": {"x": 5200000, "y": 1900000, "w": 3600000, "h": 900000}},
                {"id": "b", "text": "Animated cover text", "bbox": {"x": 5400000, "y": 2050000, "w": 3200000, "h": 820000}},
            ],
            "animation_steps": [
                {
                    "target_id": "b",
                    "target_text": "Animated cover text",
                    "bbox": {"x": 5400000, "y": 2050000, "w": 3200000, "h": 820000},
                    "covered_objects": [
                        {"id": "a", "text": "Middle right paragraph", "bbox": {"x": 5200000, "y": 1900000, "w": 3600000, "h": 900000}},
                    ],
                }
            ],
        }

        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        self.assertGreater(after["a"]["x"], 4600000)
        self.assertGreater(after["b"]["x"], 4600000)
        self.assertLess(_overlap_ratio(after["a"], after["b"]), 0.02)

    def test_visual_overlap_repair_uses_local_blank_instead_of_right_column(self):
        slide = {
            "number": 1,
            "size": {"width": 12192000, "height": 6858000},
            "crowding": "high",
            "complexity": "complex",
            "object_boxes": [
                {"id": "formula", "type": "graphicFrame", "bbox": {"x": 2200000, "y": 2300000, "w": 2600000, "h": 700000}},
                {"id": "diagram", "type": "pic", "bbox": {"x": 2500000, "y": 2380000, "w": 2100000, "h": 900000}},
            ],
            "text_objects": [],
            "animation_steps": [
                {
                    "target_id": "diagram",
                    "target_text": "",
                    "bbox": {"x": 2500000, "y": 2380000, "w": 2100000, "h": 900000},
                    "covered_objects": [
                        {"id": "formula", "text": "", "bbox": {"x": 2200000, "y": 2300000, "w": 2600000, "h": 700000}},
                    ],
                }
            ],
        }

        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        self.assertLess(after["diagram"]["x"], slide["size"]["width"] * 0.55)
        self.assertLess(_overlap_ratio(after["formula"], after["diagram"]), 0.02)

    def test_object_reflow_avoids_collisions_between_related_visuals(self):
        slide = {
            "number": 1,
            "size": {"width": 12192000, "height": 6858000},
            "crowding": "high",
            "complexity": "complex",
            "object_boxes": [
                {"id": "body", "text": "A lower paragraph", "bbox": {"x": 3200000, "y": 3900000, "w": 6400000, "h": 1700000}},
                {"id": "cover", "text": "Cover text", "bbox": {"x": 3600000, "y": 4100000, "w": 4200000, "h": 760000}},
                {"id": "diagram", "type": "pic", "text": "", "bbox": {"x": 7800000, "y": 4050000, "w": 1500000, "h": 1650000}},
                {"id": "formula", "type": "graphicFrame", "text": "", "bbox": {"x": 4100000, "y": 5900000, "w": 3200000, "h": 620000}},
            ],
            "text_objects": [
                {"id": "body", "text": "A lower paragraph", "bbox": {"x": 3200000, "y": 3900000, "w": 6400000, "h": 1700000}},
                {"id": "cover", "text": "Cover text", "bbox": {"x": 3600000, "y": 4100000, "w": 4200000, "h": 760000}},
            ],
            "animation_steps": [
                {
                    "target_id": "cover",
                    "target_text": "Cover text",
                    "bbox": {"x": 3600000, "y": 4100000, "w": 4200000, "h": 760000},
                    "covered_objects": [
                        {"id": "body", "text": "A lower paragraph", "bbox": {"x": 3200000, "y": 3900000, "w": 6400000, "h": 1700000}},
                    ],
                }
            ],
        }

        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        self.assertLess(_overlap_ratio(after["diagram"], after["formula"]), 0.12)

    def test_review_sample_moved_formula_or_picture_boxes_do_not_collide(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        analysis = analyze_presentation(parse_pptx(sample))

        for slide in analysis["slides"]:
            plan = plan_object_reflow(slide)
            operations = plan["operations"]
            if not operations:
                continue
            after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], operations)}
            before = {
                str(item.get("id") or ""): item["bbox"]
                for item in slide["object_boxes"]
                if item.get("bbox")
            }
            moved_ids = {str(operation.get("id") or "") for operation in operations}
            object_types = {str(item.get("id") or ""): str(item.get("type") or "") for item in slide["object_boxes"]}
            ids = list(after)
            for index, first_id in enumerate(ids):
                for second_id in ids[index + 1 :]:
                    pair_types = {object_types.get(first_id), object_types.get(second_id)}
                    if pair_types != {"graphicFrame", "pic"}:
                        continue
                    ratio = _overlap_ratio(after[first_id], after[second_id])
                    if first_id in moved_ids or second_id in moved_ids:
                        self.assertLess(
                            ratio,
                            0.02,
                            f"slide {slide['number']} moved visual pair {first_id}/{second_id} overlaps",
                        )
                    else:
                        self.assertLessEqual(
                            ratio,
                            _overlap_ratio(before[first_id], before[second_id]) + 0.001,
                            f"slide {slide['number']} stable visual pair {first_id}/{second_id} got worse",
                        )

    def test_moved_picture_avoids_moved_formula_final_position(self):
        slide = {
            "number": 1,
            "size": {"width": 12192000, "height": 6858000},
            "crowding": "high",
            "complexity": "complex",
            "object_boxes": [
                {"id": "body", "text": "Question text", "bbox": {"x": 1000000, "y": 1000000, "w": 3600000, "h": 800000}},
                {"id": "cover", "text": "Animated cover", "bbox": {"x": 1100000, "y": 1100000, "w": 3300000, "h": 760000}},
                {"id": "formula", "type": "graphicFrame", "text": "", "bbox": {"x": 4200000, "y": 2050000, "w": 2400000, "h": 700000}},
                {"id": "diagram", "type": "pic", "text": "", "bbox": {"x": 4400000, "y": 2100000, "w": 2100000, "h": 1100000}},
            ],
            "text_objects": [
                {"id": "body", "text": "Question text", "bbox": {"x": 1000000, "y": 1000000, "w": 3600000, "h": 800000}},
                {"id": "cover", "text": "Animated cover", "bbox": {"x": 1100000, "y": 1100000, "w": 3300000, "h": 760000}},
            ],
            "animation_steps": [
                {
                    "target_id": "cover",
                    "target_text": "Animated cover",
                    "bbox": {"x": 1100000, "y": 1100000, "w": 3300000, "h": 760000},
                    "covered_objects": [
                        {"id": "body", "text": "Question text", "bbox": {"x": 1000000, "y": 1000000, "w": 3600000, "h": 800000}},
                    ],
                }
            ],
        }

        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        self.assertIn("formula", {operation["id"] for operation in plan["operations"]})
        self.assertIn("diagram", {operation["id"] for operation in plan["operations"]})
        self.assertLess(_overlap_ratio(after["formula"], after["diagram"]), 0.02)

    def test_graphic_frame_operations_do_not_enlarge_or_become_tiny(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        analysis = analyze_presentation(parse_pptx(sample))

        for slide in analysis["slides"]:
            plan = plan_object_reflow(slide)
            for operation in plan["operations"]:
                if operation.get("object_type") != "graphicFrame":
                    continue
                width_scale = operation["to"]["w"] / operation["from"]["w"]
                height_scale = operation["to"]["h"] / operation["from"]["h"]
                self.assertLessEqual(width_scale, 1.001)
                self.assertLessEqual(height_scale, 1.001)
                self.assertGreaterEqual(width_scale, 0.60)
                self.assertGreaterEqual(height_scale, 0.60)

    def test_review_slide_35_abandons_reflow_when_quality_gate_fails(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][34]

        plan = plan_object_reflow(slide)

        self.assertFalse(plan["quality_gate"]["passed"])
        self.assertEqual(plan["operations"], [])

    def test_review_slide_36_does_not_reflow_circuit_diagram_primitives(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][35]

        plan = plan_object_reflow(slide)

        self.assertFalse(plan["quality_gate"]["passed"])
        self.assertEqual(plan["operations"], [])

    def test_write_guide_deck_applies_object_reflow_operations_to_source_slide(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "strategy": "object_reflow",
                        "object_reflow": {
                            "operations": [
                                {
                                    "op": "move_resize",
                                    "id": "4",
                                    "to": {"x": 3300000, "y": 2100000, "w": 1900000, "h": 720000},
                                    "reason": "移动最终公式到空白区",
                                }
                            ]
                        },
                        "guide_pages": [],
                        "inline_markers": [],
                    }
                ]
            }

            write_guide_deck(pptx_path, guide_deck, plan)
            parsed = parse_pptx(guide_deck)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        moved = next(obj for obj in parsed["slides"][0]["objects"] if obj["id"] == "4")
        self.assertEqual(
            moved["bbox"],
            {"x": 3300000, "y": 2100000, "w": 1900000, "h": 720000},
        )
        self.assertNotIn("Guide Reflow Step", source_slide_xml)

    def test_write_guide_deck_draws_relation_line_for_grouped_reflow_operation(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "strategy": "object_reflow",
                        "object_reflow": {
                            "operations": [
                                {
                                    "op": "move_resize",
                                    "id": "4",
                                    "anchor_id": "3",
                                    "anchor_to": {"x": 100000, "y": 900000, "w": 2000000, "h": 900000},
                                    "to": {"x": 3300000, "y": 2100000, "w": 1900000, "h": 720000},
                                    "reason": "移动最终公式到空白区",
                                }
                            ]
                        },
                        "guide_pages": [],
                        "inline_markers": [],
                    }
                ]
            }

            write_guide_deck(pptx_path, guide_deck, plan)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertIn("Guide Reflow Relation 1", source_slide_xml)
        self.assertIn('prst="line"', source_slide_xml)

    def test_relation_line_uses_outer_edges_instead_of_box_centers(self):
        anchor = {"x": 1000000, "y": 2000000, "w": 4000000, "h": 1000000}
        target = {"x": 6500000, "y": 2600000, "w": 1200000, "h": 700000}

        start_x, start_y, end_x, end_y = _relation_points(anchor, target)

        self.assertLess(start_x, end_x)
        self.assertLess(end_x, target["x"])
        self.assertLess(abs(end_x - start_x), 420000)
        self.assertEqual(start_y, end_y)

    def test_relation_line_points_toward_target_without_crossing_it(self):
        anchor = {"x": 3000000, "y": 500000, "w": 1200000, "h": 500000}
        target = {"x": 3000000, "y": 1800000, "w": 1200000, "h": 700000}

        start_x, start_y, end_x, end_y = _relation_points(anchor, target)

        self.assertLess(start_y, end_y)
        self.assertLess(end_y, target["y"])
        self.assertEqual(start_x, end_x)
        self.assertLess(abs(end_y - start_y), 420000)

    def test_build_augment_plan_routes_test_sample_to_object_reflow(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        plan = build_augment_plan(analyze_presentation(parse_pptx(sample)))

        self.assertEqual(plan["summary"]["object_reflow_pages"], [1, 2])
        strategies = [slide["strategy"] for slide in plan["slides"]]
        self.assertEqual(strategies[:2], ["object_reflow", "object_reflow"])
        self.assertTrue(all(strategy == "keep_native" for strategy in strategies[2:]))
        self.assertGreater(len(plan["slides"][1]["object_reflow"]["operations"]), 0)

    def test_test_sample_keeps_lower_formula_readable_after_group_reflow(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        before = {str(item["id"]): item["bbox"] for item in slide["object_boxes"]}

        self.assertGreaterEqual(after["23"]["w"], int(before["23"]["w"] * 0.62))
        self.assertGreaterEqual(after["23"]["h"], int(before["23"]["h"] * 0.62))
        self.assertLess(_overlap_ratio(after["4"], after["23"]), 0.02)

    def test_test_sample_keeps_original_text_horizontal_intent(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        before = {str(item["id"]): item["bbox"] for item in slide["object_boxes"]}

        text_ids = ["18", "9", "21"]
        before_left = min(before[item_id]["x"] for item_id in text_ids)
        after_left = min(after[item_id]["x"] for item_id in text_ids)

        self.assertGreaterEqual(after_left, before_left - 220000)

    def test_test_sample_does_not_push_charge_diagram_to_left_margin(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        before = {str(item["id"]): item["bbox"] for item in slide["object_boxes"]}

        self.assertGreater(after["4"]["x"], before["21"]["x"] - 800000)
        self.assertLess(abs(after["4"]["y"] - before["4"]["y"]), 1200000)

    def test_review_page4_grouped_formulas_do_not_push_charge_diagram_left(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][3]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        before = {str(item["id"]): item["bbox"] for item in slide["object_boxes"]}

        self.assertGreater(after["4"]["x"], before["4"]["x"] - 1500000)

    def test_review_page22_keeps_inline_formula_placeholders_in_text_rows(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][21]
        plan = plan_object_reflow(slide)

        moved_ids = {str(operation.get("id") or "") for operation in plan["operations"]}

        self.assertNotIn("11", moved_ids)
        self.assertNotIn("14", moved_ids)
        self.assertNotIn("19", moved_ids)
        self.assertNotIn("23", moved_ids)
        self.assertNotIn("2", moved_ids)
        self.assertNotIn("16", moved_ids)

    def test_test_sample_preserves_visual_group_proximity(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        paragraph = after["21"]
        diagram = after["4"]
        formula = after["23"]

        self.assertLess(_center_distance(diagram, paragraph), 4800000)
        self.assertLess(_center_distance(formula, paragraph), 5200000)

    def test_test_sample_keeps_upper_formula_in_local_gap(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        page_width = slide["size"]["width"]

        formula_center_x = after["11"]["x"] + after["11"]["w"] / 2

        self.assertLess(formula_center_x, page_width * 0.70)

    def test_test_sample_keeps_formula_clear_of_text_rendering_margin(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][1]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

        self.assertLess(_overlap_ratio(after["3"], after["1048"]), 0.02)
        self.assertLess(_overlap_ratio(after["3"], after["10"]), 0.02)

    def test_test_sample_does_not_push_capacitance_formula_to_left_margin(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][1]
        plan = plan_object_reflow(slide)
        after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
        page_width = slide["size"]["width"]

        self.assertGreater(after["3"]["x"], page_width * 0.25)

    def test_test_sample_marks_moved_formula_for_pdf_region_overlay(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][1]
        plan = plan_object_reflow(slide)

        formula_op = next(operation for operation in plan["operations"] if operation["id"] == "3")

        self.assertEqual(formula_op["object_type"], "graphicFrame")
        self.assertEqual(formula_op["render_mode"], "pdf_region_overlay")

    def test_associated_visual_operations_keep_anchor_relation_metadata(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
        slide = analyze_presentation(parse_pptx(sample))["slides"][0]
        plan = plan_object_reflow(slide)

        grouped_ops = [operation for operation in plan["operations"] if operation.get("anchor_id")]

        self.assertTrue(grouped_ops)
        for operation in grouped_ops:
            self.assertIn("anchor_to", operation)
            self.assertIn("flow_relation", operation)


def _dense_capacitance_slide():
    return {
        "number": 2,
        "size": {"width": 12192000, "height": 6858000},
        "object_boxes": [
            {"id": "2", "bbox": {"x": 2022957, "y": 2375379, "w": 8406534, "h": 829945}},
            {"id": "3", "bbox": {"x": 5414818, "y": 2392052, "w": 1061886, "h": 865187}},
            {"id": "1048", "bbox": {"x": 1896349, "y": 2165713, "w": 8098823, "h": 1353185}},
            {"id": "19", "bbox": {"x": 2817103, "y": 3728564, "w": 5137881, "h": 523220}},
            {"id": "20", "bbox": {"x": 2817103, "y": 3791409, "w": 5616104, "h": 460375}},
            {"id": "10", "bbox": {"x": 4354288, "y": 1153145, "w": 3743871, "h": 521970}},
        ],
        "text_objects": [
            {"id": "2", "text": "The capability of how much charge a capacitor can store is called capacitance.", "bbox": {"x": 2022957, "y": 2375379, "w": 8406534, "h": 829945}},
            {"id": "1048", "text": "q is the charge of a plate and Vab is the potential difference.", "bbox": {"x": 1896349, "y": 2165713, "w": 8098823, "h": 1353185}},
            {"id": "19", "text": "Unit: farad", "bbox": {"x": 2817103, "y": 3728564, "w": 5137881, "h": 523220}},
            {"id": "20", "text": "1uF=10-6F 1pF=10-12F", "bbox": {"x": 2817103, "y": 3791409, "w": 5616104, "h": 460375}},
        ],
        "animation_steps": [
            {
                "target_id": "3",
                "target_text": "formula",
                "bbox": {"x": 5414818, "y": 2392052, "w": 1061886, "h": 865187},
                "covered_objects": [
                    {"id": "2", "text": "The capability...", "bbox": {"x": 2022957, "y": 2375379, "w": 8406534, "h": 829945}},
                ],
            }
        ],
    }


def _read_zip_text(path: Path, name: str) -> str:
    import zipfile

    with zipfile.ZipFile(path) as package:
        return package.read(name).decode("utf-8")


def _overlap_ratio(first: dict[str, int], second: dict[str, int]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    overlap = max(0, right - left) * max(0, bottom - top)
    smaller = min(first["w"] * first["h"], second["w"] * second["h"])
    return overlap / smaller if smaller else 0.0


def _center_distance(first: dict[str, int], second: dict[str, int]) -> float:
    return abs(first["x"] + first["w"] / 2 - second["x"] - second["w"] / 2) + abs(
        first["y"] + first["h"] / 2 - second["y"] - second["h"] / 2
    )


SIMPLE_SLIDE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="Step A"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="100000" y="900000"/><a:ext cx="2000000" cy="900000"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>当前位置</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="4" name="Cover"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="900000" y="1000000"/><a:ext cx="2100000" cy="900000"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>最终公式</a:t></a:r></a:p></p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""

GRAPHIC_FRAME_SLIDE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:graphicFrame>
        <p:nvGraphicFramePr><p:cNvPr id="4" name="Formula"/></p:nvGraphicFramePr>
        <p:xfrm><a:off x="3000000" y="2000000"/><a:ext cx="3000000" cy="650000"/></p:xfrm>
        <a:graphic><a:graphicData><p:oleObj>
          <p:pic>
            <p:nvPicPr><p:cNvPr id="40" name="Formula fallback"/></p:nvPicPr>
            <p:spPr><a:xfrm><a:off x="3000000" y="2000000"/><a:ext cx="3000000" cy="650000"/></a:xfrm></p:spPr>
          </p:pic>
        </p:oleObj></a:graphicData></a:graphic>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>
"""

GROUPED_GRAPHIC_FRAME_SLIDE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:grpSp>
        <p:nvGrpSpPr><p:cNvPr id="8" name="Formula group"/></p:nvGrpSpPr>
        <p:grpSpPr>
          <a:xfrm>
            <a:off x="3000000" y="1600000"/><a:ext cx="4200000" cy="1900000"/>
            <a:chOff x="3000000" y="1600000"/><a:chExt cx="4200000" cy="1900000"/>
          </a:xfrm>
        </p:grpSpPr>
        <p:graphicFrame>
          <p:nvGraphicFramePr><p:cNvPr id="9" name="Grouped Formula"/></p:nvGraphicFramePr>
          <p:xfrm><a:off x="5200000" y="2100000"/><a:ext cx="1800000" cy="650000"/></p:xfrm>
          <a:graphic><a:graphicData><p:oleObj>
            <p:pic>
              <p:nvPicPr><p:cNvPr id="90" name="Formula fallback"/></p:nvPicPr>
              <p:spPr><a:xfrm><a:off x="5200000" y="2100000"/><a:ext cx="1800000" cy="650000"/></a:xfrm></p:spPr>
            </p:pic>
          </p:oleObj></a:graphicData></a:graphic>
        </p:graphicFrame>
      </p:grpSp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
