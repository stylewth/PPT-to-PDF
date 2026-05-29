import json
import shutil
import subprocess
import sys
import unittest
import uuid
import zipfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEST_DIR))
TMP_ROOT = Path(__file__).resolve().parent / ".tmp_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)
SIMPLE_ANIMATED_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "animation_guide_smoke.pptx"
REVIEW_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"
TEST_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

from augment_planner import build_augment_plan
from converter import _compact_render_box, convert_pptx
from ooxml_slide_editor import parse_slide_shapes
from pdf_augmenter import _apply_page_compact_if_present, _overlay_graphic_frame_regions, _reflow_step_labels_xml, write_guide_deck
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


class FakeSofficeRunner:
    def __init__(self):
        self.commands = []

    def __call__(self, command, *, timeout, capture_output, text, **kwargs):
        self.commands.append(command)
        outdir = Path(command[command.index("--outdir") + 1])
        source = Path(command[-1])
        _write_valid_pdf(outdir / f"{source.stem}.pdf")
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")


class V3PdfAugmenterTest(unittest.TestCase):
    def test_review_sample_reflows_complex_pages_without_growing_page_count(self):
        analysis = analyze_presentation(parse_pptx(REVIEW_SAMPLE))

        plan = build_augment_plan(analysis)
        slide_count = plan["summary"]["source_slide_count"]
        guide_page_count = plan["summary"]["guide_page_count"]
        reflow_pages = plan["summary"]["object_reflow_pages"]

        self.assertEqual(slide_count, 42)
        self.assertEqual(guide_page_count, 0)
        self.assertGreater(len(reflow_pages), 5)
        self.assertTrue(all(slide["page_budget"] == 1 for slide in plan["slides"]))
        self.assertTrue(
            all(len(slide["inline_markers"]) <= 3 for slide in plan["slides"])
        )

    def test_augment_plan_keeps_simple_animation_on_one_page(self):
        analysis = analyze_presentation(parse_pptx(SIMPLE_ANIMATED_SAMPLE))

        plan = build_augment_plan(analysis)
        slide_plan = plan["slides"][0]

        self.assertEqual(slide_plan["strategy"], "native_enhance")
        self.assertEqual(slide_plan["page_budget"], 1)
        self.assertEqual(slide_plan["guide_pages"], [])
        self.assertEqual(plan["summary"]["guide_page_count"], 0)
        self.assertEqual(slide_plan["inline_markers"], [])

    def test_augment_plan_object_reflows_high_crowding_animation_without_extra_pages(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))

        plan = build_augment_plan(analysis)
        slide_plan = plan["slides"][0]

        self.assertEqual(plan["version"], "v3g")
        self.assertEqual(slide_plan["strategy"], "object_reflow")
        self.assertEqual(slide_plan["page_budget"], 1)
        self.assertEqual(slide_plan["inline_markers"], [])
        self.assertEqual(slide_plan["guide_pages"], [])
        self.assertEqual(plan["summary"]["guide_page_count"], 0)
        self.assertEqual(plan["summary"]["object_reflow_pages"], [1])
        self.assertEqual(slide_plan["object_reflow"]["policy"], "move_shapes_then_convert")
        self.assertEqual(slide_plan["micro_reflow"]["occlusion_flows"][0]["covered"][0]["text"], "当前位置")

    def test_augment_plan_downgrades_object_reflow_when_no_shape_operation_is_available(self):
        analysis = {
            "source": {"name": "unit.pptx", "slide_count": 1},
            "slides": [
                {
                    "number": 1,
                    "title": "Grouped guide",
                    "size": {"width": 12192000, "height": 6858000},
                    "object_count": 5,
                    "animation_target_count": 5,
                    "unsupported_animation_count": 0,
                    "complexity": "medium",
                    "animation_steps": [
                        {"target_id": "1", "target_text": "入口概念", "kind": "fade", "covers_prior_object": False},
                        {"target_id": "2", "target_text": "过程一", "kind": "appear", "covers_prior_object": False},
                        {"target_id": "3", "target_text": "遮挡说明", "kind": "wipe", "covers_prior_object": True},
                        {"target_id": "4", "target_text": "过程二", "kind": "appear", "covers_prior_object": False},
                        {"target_id": "5", "target_text": "最终结论", "kind": "fade", "covers_prior_object": False},
                    ],
                    "decision_hint": {"strategy": "reflow_or_expand", "reason": "crowded"},
                }
            ],
        }

        slide_plan = build_augment_plan(analysis)["slides"][0]
        self.assertEqual(slide_plan["strategy"], "native_enhance")
        self.assertIsNone(slide_plan["object_reflow"])

    def test_test_sample_complex_slides_are_planned_as_reflow_pages(self):
        analysis = analyze_presentation(parse_pptx(TEST_SAMPLE))

        plan = build_augment_plan(analysis)

        self.assertEqual(plan["summary"]["source_slide_count"], len(plan["slides"]))
        self.assertEqual(plan["summary"]["guide_page_count"], 0)
        self.assertEqual(plan["summary"]["object_reflow_pages"], [1, 2])
        strategies = [slide["strategy"] for slide in plan["slides"]]
        self.assertEqual(strategies[:2], ["object_reflow", "object_reflow"])
        self.assertTrue(all(strategy == "keep_native" for strategy in strategies[2:]))
        self.assertTrue(all(slide["page_budget"] == 1 for slide in plan["slides"]))
        self.assertTrue(
            all(
                flow["target_bbox"]
                for slide in plan["slides"]
                if slide["strategy"] == "object_reflow"
                for flow in slide["micro_reflow"]["occlusion_flows"]
            )
        )

    def test_augment_plan_marks_final_clear_change_as_key_result(self):
        analysis = {
            "source": {"name": "unit.pptx", "slide_count": 1},
            "slides": [
                {
                    "number": 1,
                    "title": "Non-overlap",
                    "size": {"width": 12192000, "height": 6858000},
                    "animation_target_count": 2,
                    "unsupported_animation_count": 0,
                    "animation_steps": [
                        {
                            "target_id": "3",
                            "target_text": "A",
                            "kind": "fade",
                            "bbox": {"x": 100000, "y": 900000, "w": 1000000, "h": 500000},
                            "covers_prior_object": False,
                        },
                        {
                            "target_id": "4",
                            "target_text": "B",
                            "kind": "wipe",
                            "bbox": {"x": 3000000, "y": 900000, "w": 1000000, "h": 500000},
                            "covers_prior_object": False,
                        },
                    ],
                    "decision_hint": {"strategy": "native_enhance", "reason": ""},
                }
            ],
        }

        plan = build_augment_plan(analysis)
        markers = plan["slides"][0]["inline_markers"]

        self.assertEqual(markers, [])

    def test_augment_plan_places_hints_in_available_blank_zone(self):
        analysis = {
            "source": {"name": "unit.pptx", "slide_count": 1},
            "slides": [
                {
                    "number": 1,
                    "title": "Right blank",
                    "size": {"width": 12000000, "height": 7000000},
                    "object_boxes": [
                        {"id": "content", "bbox": {"x": 0, "y": 0, "w": 7600000, "h": 7000000}},
                    ],
                    "animation_target_count": 2,
                    "unsupported_animation_count": 0,
                    "animation_steps": [
                        {
                            "target_id": "3",
                            "target_text": "A",
                            "kind": "fade",
                            "bbox": {"x": 100000, "y": 900000, "w": 1000000, "h": 500000},
                            "covers_prior_object": False,
                        },
                        {
                            "target_id": "4",
                            "target_text": "B",
                            "kind": "wipe",
                            "bbox": {"x": 3000000, "y": 900000, "w": 1000000, "h": 500000},
                            "covers_prior_object": False,
                        },
                    ],
                    "decision_hint": {"strategy": "native_enhance", "reason": ""},
                }
            ],
        }

        markers = build_augment_plan(analysis)["slides"][0]["inline_markers"]

        self.assertEqual(markers, [])

    def test_augment_plan_skips_inline_markers_without_blank_zone(self):
        analysis = {
            "source": {"name": "unit.pptx", "slide_count": 1},
            "slides": [
                {
                    "number": 1,
                    "title": "No blank",
                    "size": {"width": 12000000, "height": 7000000},
                    "object_boxes": [
                        {"id": "content", "bbox": {"x": 0, "y": 0, "w": 12000000, "h": 7000000}},
                    ],
                    "animation_target_count": 1,
                    "unsupported_animation_count": 0,
                    "animation_steps": [
                        {
                            "target_id": "3",
                            "target_text": "A",
                            "kind": "fade",
                            "bbox": {"x": 100000, "y": 900000, "w": 1000000, "h": 500000},
                            "covers_prior_object": False,
                        },
                    ],
                    "decision_hint": {"strategy": "native_enhance", "reason": ""},
                }
            ],
        }

        slide_plan = build_augment_plan(analysis)["slides"][0]

        self.assertEqual(slide_plan["inline_markers"], [])

    def test_write_guide_deck_does_not_embed_inline_markers_by_default(self):
        with workspace_tmpdir() as tmp:
            guide_deck = tmp / "guide_deck.pptx"
            analysis = analyze_presentation(parse_pptx(SIMPLE_ANIMATED_SAMPLE))
            plan = build_augment_plan(analysis)

            write_guide_deck(SIMPLE_ANIMATED_SAMPLE, guide_deck, plan)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertNotIn("Guide Inline Marker", source_slide_xml)
        self.assertNotIn("Guide Inline Hint", source_slide_xml)
        self.assertNotIn("先出现", source_slide_xml)
        self.assertNotIn("关键结果", source_slide_xml)
        self.assertNotIn("Guide Highlight", source_slide_xml)

    def test_write_guide_deck_does_not_draw_large_debug_frames_for_review_sample(self):
        with workspace_tmpdir() as tmp:
            guide_deck = tmp / "guide_deck.pptx"
            analysis = analyze_presentation(parse_pptx(REVIEW_SAMPLE))
            plan = build_augment_plan(analysis)

            write_guide_deck(REVIEW_SAMPLE, guide_deck, plan)
            parsed = parse_pptx(guide_deck)
            slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide4.xml")

        self.assertLessEqual(parsed["slide_count"], 48)
        self.assertNotIn("Guide Highlight", slide_xml)

    def test_write_guide_deck_protects_short_math_text_boxes_from_wrapping(self):
        with workspace_tmpdir() as tmp:
            guide_deck = tmp / "guide_deck.pptx"
            analysis = analyze_presentation(parse_pptx(REVIEW_SAMPLE))
            plan = build_augment_plan(analysis)

            write_guide_deck(REVIEW_SAMPLE, guide_deck, plan)
            slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide23.xml")
            math_box = _sp_shape_by_id(slide_xml, "566294")

        self.assertIn(23, plan["summary"]["text_box_repair_pages"])
        body_pr = math_box.find(f"{{{P_NS}}}txBody/{{{A_NS}}}bodyPr")
        ext = math_box.find(f"{{{P_NS}}}spPr/{{{A_NS}}}xfrm/{{{A_NS}}}ext")
        self.assertEqual(body_pr.attrib.get("wrap"), "none")
        self.assertGreater(int(ext.attrib["cx"]), 1357630)

    def test_write_guide_deck_keeps_simple_animation_as_single_enhanced_slide(self):
        with workspace_tmpdir() as tmp:
            guide_deck = tmp / "guide_deck.pptx"
            analysis = analyze_presentation(parse_pptx(SIMPLE_ANIMATED_SAMPLE))
            plan = build_augment_plan(analysis)

            write_guide_deck(SIMPLE_ANIMATED_SAMPLE, guide_deck, plan)
            parsed = parse_pptx(guide_deck)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertEqual(parsed["slide_count"], 1)
        self.assertNotIn("Guide Inline Marker", source_slide_xml)
        self.assertNotIn("Guide Inline Hint", source_slide_xml)
        self.assertNotIn("Guide Highlight", source_slide_xml)

    def test_write_guide_deck_keeps_object_reflow_inside_source_slide(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))
            plan = build_augment_plan(analysis)

            write_guide_deck(pptx_path, guide_deck, plan)
            parsed = parse_pptx(guide_deck)
            slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertEqual(parsed["slide_count"], 1)
        self.assertNotIn("Guide Reflow Background", slide_xml)
        self.assertEqual(parsed["slides"][0]["title"], "梯度下降")

    def test_reflow_step_labels_avoid_target_shape_boxes(self):
        slide_xml = """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="3" name="Text"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="1200000" y="1800000"/><a:ext cx="5600000" cy="1200000"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>Text</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:graphicFrame>
        <p:nvGraphicFramePr><p:cNvPr id="4" name="Formula"/></p:nvGraphicFramePr>
        <p:xfrm><a:off x="7600000" y="4100000"/><a:ext cx="3000000" cy="650000"/></p:xfrm>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>"""
        label_xml = _reflow_step_labels_xml(
            slide_xml,
            [{"op": "move_resize", "id": "4", "to": {"x": 7600000, "y": 4100000, "w": 3000000, "h": 650000}}],
        )
        full_xml = slide_xml.replace("</p:spTree>", f"{label_xml}</p:spTree>")
        shapes = {shape["name"]: shape for shape in parse_slide_shapes(full_xml)}

        self.assertLess(_overlap_ratio(shapes["Guide Reflow Step 1"]["bbox"], shapes["Formula"]["bbox"]), 0.01)

    def test_write_guide_deck_does_not_add_reflow_step_labels_by_default(self):
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
                                    "object_type": "graphicFrame",
                                    "to": {"x": 3300000, "y": 2100000, "w": 1900000, "h": 720000},
                                }
                            ]
                        },
                    }
                ]
            }

            write_guide_deck(pptx_path, guide_deck, plan)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertNotIn("Guide Reflow Step", source_slide_xml)

    def test_pdf_overlay_uses_graphic_frame_preview_instead_of_dirty_page_crop(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path)
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_colored_pdf(guide_pdf, {"x": 360, "y": 202.5, "w": 144, "h": 40.5}, (0, 0, 0))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "object_reflow",
                        "object_reflow": {
                            "operations": [
                                {
                                    "op": "move_resize",
                                    "id": "formula",
                                    "object_type": "graphicFrame",
                                    "render_mode": "pdf_region_overlay",
                                    "from": {"x": 100, "y": 100, "w": 200, "h": 100},
                                    "to": {"x": 500, "y": 500, "w": 200, "h": 100},
                                }
                            ]
                        },
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 363, 206)
            self.assertGreater(red, 220)
            self.assertGreater(green, 220)
            self.assertLess(blue, 80)
            red, green, blue = _sample_pdf_pixel(guide_pdf, 432, 223)
            self.assertLess(red, 80)
            self.assertLess(green, 80)
            self.assertGreater(blue, 180)
            red, green, blue = _sample_pdf_pixel(guide_pdf, 405, 223)
            self.assertLess(red, 80)
            self.assertLess(green, 80)
            self.assertGreater(blue, 180)

    def test_pdf_overlay_does_not_repaint_stable_graphic_frame_with_bad_preview(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path, preview_image=_bad_preview_image())
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_colored_pdf(guide_pdf, {"x": 120, "y": 55, "w": 48, "h": 12}, (1, 0, 0))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "keep_native",
                        "object_boxes": [
                            {
                                "id": "formula",
                                "type": "graphicFrame",
                                "bbox": {"x": 100, "y": 100, "w": 200, "h": 100},
                            }
                        ],
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 144, 61)
            self.assertGreater(red, 180)
            self.assertLess(green, 80)
            self.assertLess(blue, 80)

    def test_pdf_overlay_repairs_stable_graphic_frame_when_render_check_fails(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path)
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_bad_formula_pdf(guide_pdf)
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "keep_native",
                        "inline_markers": [{"order": 1, "label": "1"}],
                        "object_boxes": [
                            {
                                "id": "formula",
                                "type": "graphicFrame",
                                "bbox": {"x": 100, "y": 100, "w": 200, "h": 100},
                            }
                        ],
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 144, 61)
            self.assertLess(red, 80)
            self.assertLess(green, 80)
            self.assertGreater(blue, 180)

    def test_pdf_overlay_repairs_stable_graphic_frame_with_usable_preview(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path)
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_colored_pdf(guide_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 1, 1))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "keep_native",
                        "inline_markers": [{"order": 1, "label": "1"}],
                        "object_boxes": [
                            {
                                "id": "formula",
                                "type": "graphicFrame",
                                "bbox": {"x": 100, "y": 100, "w": 200, "h": 100},
                            }
                        ],
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 144, 61)
            self.assertLess(red, 80)
            self.assertLess(green, 80)
            self.assertGreater(blue, 180)

    def test_pdf_overlay_skips_stable_graphic_frame_when_preview_also_fails(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path, preview_image=_bad_preview_image())
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_colored_pdf(guide_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "keep_native",
                        "inline_markers": [{"order": 1, "label": "1"}],
                        "object_boxes": [
                            {
                                "id": "formula",
                                "type": "graphicFrame",
                                "bbox": {"x": 100, "y": 100, "w": 200, "h": 100},
                            }
                        ],
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 144, 61)
            self.assertGreater(red, 180)
            self.assertLess(green, 80)
            self.assertLess(blue, 80)

    def test_pdf_overlay_does_not_repaint_stable_grouped_graphic_frame(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path)
            _write_colored_pdf(base_pdf, {"x": 72, "y": 40.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_bad_formula_pdf(guide_pdf)
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "keep_native",
                        "object_boxes": [
                            {
                                "id": "formula",
                                "type": "graphicFrame",
                                "bbox": {"x": 100, "y": 100, "w": 200, "h": 100},
                                "in_group": True,
                            }
                        ],
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 80, 60)
            self.assertLess(red, 80)
            self.assertLess(green, 80)
            self.assertLess(blue, 80)

    def test_pdf_overlay_does_not_paint_outside_formula_target_box(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "formula_source.pptx"
            base_pdf = tmp / "base.pdf"
            guide_pdf = tmp / "guide.pdf"
            _write_formula_preview_pptx(pptx_path)
            _write_colored_pdf(base_pdf, {"x": 360, "y": 202.5, "w": 144, "h": 40.5}, (1, 0, 0))
            _write_colored_pdf(guide_pdf, {"x": 354, "y": 202.5, "w": 6, "h": 40.5}, (0, 1, 0))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "size": {"width": 1000, "height": 1000},
                        "strategy": "object_reflow",
                        "object_reflow": {
                            "operations": [
                                {
                                    "op": "move_resize",
                                    "id": "formula",
                                    "object_type": "graphicFrame",
                                    "render_mode": "pdf_region_overlay",
                                    "from": {"x": 100, "y": 100, "w": 200, "h": 100},
                                    "to": {"x": 500, "y": 500, "w": 200, "h": 100},
                                }
                            ]
                        },
                    }
                ]
            }

            _overlay_graphic_frame_regions(pptx_path, base_pdf, guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 357, 223)
            self.assertLess(red, 80)
            self.assertGreater(green, 180)
            self.assertLess(blue, 80)

    def test_page_compact_scales_content_away_from_bottom_edge(self):
        with workspace_tmpdir() as tmp:
            guide_pdf = tmp / "guide.pdf"
            _write_colored_pdf(guide_pdf, {"x": 300, "y": 382, "w": 120, "h": 18}, (0, 0, 1))
            plan = {
                "slides": [
                    {
                        "source_slide": 1,
                        "page_compact": {"type": "page_compact", "scale": 0.90},
                    }
                ]
            }

            _apply_page_compact_if_present(guide_pdf, plan)

            red, green, blue = _sample_pdf_pixel(guide_pdf, 360, 392)
            self.assertGreater(red, 240)
            self.assertGreater(green, 240)
            self.assertGreater(blue, 240)

    def test_compact_render_box_matches_page_compact_transform(self):
        box = {"x": 200, "y": 300, "w": 400, "h": 100}
        compacted = _compact_render_box(
            box,
            {"width": 1000, "height": 800},
            {"type": "page_compact", "scale": 0.90},
        )

        self.assertEqual(compacted, {"x": 230, "y": 310, "w": 360, "h": 90})

    def test_converter_outputs_guide_pdf_and_augment_plan(self):
        with workspace_tmpdir() as tmp:
            fake_soffice = tmp / "soffice.exe"
            fake_soffice.write_text("fake executable", encoding="utf-8")
            pptx_path = tmp / "course.pptx"
            output_dir = tmp / "out"
            write_minimal_pptx(pptx_path)

            result = convert_pptx(
                pptx_path,
                output_dir,
                render_pdf=True,
                soffice_path=fake_soffice,
                command_runner=FakeSofficeRunner(),
            )

            self.assertTrue(Path(result["base_pdf_path"]).exists())
            self.assertTrue(Path(result["guide_pdf_path"]).exists())
            self.assertTrue(Path(result["augment_plan_path"]).exists())
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["version"], "v3g")
            self.assertEqual(report["outputs"]["guide_pdf"], "guide.pdf")
            self.assertEqual(report["outputs"]["augment_plan_json"], "augment_plan.json")
            self.assertEqual(report["outputs"]["compare_html"], "compare.html")
            self.assertEqual(report["outputs"]["metrics_json"], "metrics.json")


if __name__ == "__main__":
    unittest.main()


def _read_zip_text(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as package:
        return package.read(name).decode("utf-8")


def _sp_shape_by_id(slide_xml: str, shape_id: str):
    root = ET.fromstring(slide_xml)
    for shape in root.findall(f".//{{{P_NS}}}sp"):
        c_nv_pr = shape.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        if c_nv_pr is not None and c_nv_pr.attrib.get("id") == shape_id:
            return shape
    raise AssertionError(f"shape {shape_id} not found")


def _overlap_ratio(first: dict[str, int], second: dict[str, int]) -> float:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    overlap = max(0, right - left) * max(0, bottom - top)
    smaller = min(first["w"] * first["h"], second["w"] * second["h"])
    return overlap / smaller if smaller else 0.0


def _write_valid_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text((72, 72), "fake native pdf")
    doc.save(path)
    doc.close()


def _write_colored_pdf(path: Path, rect: dict[str, float], color: tuple[float, float, float]) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(
        fitz.Rect(rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"]),
        color=color,
        fill=color,
    )
    doc.save(path)
    doc.close()


def _write_bad_formula_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(fitz.Rect(72, 40.5, 216, 81), color=(1, 1, 0), fill=(1, 1, 0))
    page.draw_rect(fitz.Rect(72, 48, 96, 74), color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)
    doc.close()


def _write_formula_preview_pptx(path: Path, preview_image=None) -> None:
    preview = BytesIO()
    (preview_image or _preview_image()).save(preview, format="PNG")
    entries = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="png" ContentType="image/png"/>
  <Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>
</Types>""".encode("utf-8"),
        "ppt/slides/slide1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:graphicFrame>
        <p:nvGraphicFramePr><p:cNvPr id="formula" name="Formula"/></p:nvGraphicFramePr>
        <p:xfrm><a:off x="100" y="100"/><a:ext cx="200" cy="100"/></p:xfrm>
        <a:graphic><a:graphicData><p:oleObj>
          <p:pic>
            <p:nvPicPr><p:cNvPr id="formula" name="Formula fallback"/></p:nvPicPr>
            <p:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
            <p:spPr><a:xfrm><a:off x="100" y="100"/><a:ext cx="200" cy="100"/></a:xfrm><a:solidFill><a:srgbClr val="FFFF00"/></a:solidFill></p:spPr>
          </p:pic>
        </p:oleObj></a:graphicData></a:graphic>
      </p:graphicFrame>
    </p:spTree>
  </p:cSld>
</p:sld>""".encode("utf-8"),
        "ppt/slides/_rels/slide1.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/formula.png"/>
</Relationships>""".encode("utf-8"),
        "ppt/media/formula.png": preview.getvalue(),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)


def _preview_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (120, 60), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((36, 18, 84, 42), fill="blue")
    return image


def _bad_preview_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (120, 60), "white")
    draw = ImageDraw.Draw(image)
    for y in range(8, 54, 4):
        draw.line((4, y, 116, y), fill="black", width=2)
    for x in range(6, 114, 8):
        draw.rectangle((x, 6, x + 4, 56), fill="black")
    return image


def _sample_pdf_pixel(path: Path, x: int, y: int) -> tuple[int, int, int]:
    import fitz

    doc = fitz.open(path)
    pix = doc[0].get_pixmap(alpha=False)
    offset = (y * pix.width + x) * pix.n
    rgb = tuple(pix.samples[offset : offset + 3])
    doc.close()
    return rgb
