import json
import shutil
import subprocess
import sys
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree as ET


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
TEST_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(TEST_DIR))
TMP_ROOT = Path(__file__).resolve().parents[1] / "workspace" / "test_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)
SIMPLE_ANIMATED_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "animation_guide_smoke.pptx"
REVIEW_SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "Review+chapter24-27.pptx"

from augment_planner import build_augment_plan
from converter import convert_pptx
from pdf_augmenter import write_guide_deck
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
        (outdir / f"{source.stem}.pdf").write_bytes(b"%PDF-1.7\n%fake pdf\n")
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")


class V3PdfAugmenterTest(unittest.TestCase):
    def test_review_sample_uses_bounded_report_only_budget_for_complex_pages(self):
        analysis = analyze_presentation(parse_pptx(REVIEW_SAMPLE))

        plan = build_augment_plan(analysis)
        slide_count = plan["summary"]["source_slide_count"]
        guide_page_count = plan["summary"]["guide_page_count"]
        report_only_pages = plan["summary"]["report_only_pages"]

        self.assertEqual(slide_count, 42)
        self.assertLessEqual(guide_page_count, int(slide_count * 0.15))
        self.assertGreater(len(report_only_pages), 20)
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
        self.assertEqual(len(slide_plan["inline_markers"]), 1)
        self.assertEqual(slide_plan["inline_markers"][0]["role"], "first_change")
        self.assertEqual(slide_plan["inline_markers"][0]["hint"], "先出现")

    def test_augment_plan_adds_expand_page_for_high_crowding_animation(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))

        plan = build_augment_plan(analysis)
        slide_plan = plan["slides"][0]

        self.assertEqual(plan["version"], "v3d")
        self.assertEqual(slide_plan["strategy"], "expand_after_native")
        self.assertEqual(slide_plan["page_budget"], 2)
        self.assertEqual(
            slide_plan["inline_markers"][0]["bbox"],
            {"x": 100000, "y": 900000, "w": 2000000, "h": 900000},
        )
        self.assertEqual(
            [marker["role"] for marker in slide_plan["inline_markers"]],
            ["first_change", "covered_content"],
        )
        self.assertEqual(
            [marker["hint"] for marker in slide_plan["inline_markers"]],
            ["先出现", "遮挡变化"],
        )
        self.assertEqual(len(slide_plan["guide_pages"]), 1)
        self.assertIn("当前位置", slide_plan["guide_pages"][0]["steps"][0]["text"])

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

        self.assertEqual([marker["role"] for marker in markers], ["first_change", "key_result"])
        self.assertEqual([marker["hint"] for marker in markers], ["先出现", "关键结果"])

    def test_write_guide_deck_embeds_inline_markers_on_source_slide(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))
            plan = build_augment_plan(analysis)

            write_guide_deck(pptx_path, guide_deck, plan)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertIn("Guide Inline Marker 1", source_slide_xml)
        self.assertIn("Guide Inline Marker 2", source_slide_xml)
        self.assertIn("Guide Inline Hint 1", source_slide_xml)
        self.assertIn("Guide Inline Hint 2", source_slide_xml)
        self.assertIn('anchor="ctr"', source_slide_xml)
        self.assertIn('algn="ctr"', source_slide_xml)
        self.assertIn("先出现", source_slide_xml)
        self.assertIn("遮挡变化", source_slide_xml)
        self.assertNotIn("Guide Highlight", source_slide_xml)
        self.assertLess(source_slide_xml.index("Guide Inline Marker 1"), source_slide_xml.index("</p:spTree>"))

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

    def test_write_guide_deck_keeps_simple_animation_as_single_enhanced_slide(self):
        with workspace_tmpdir() as tmp:
            guide_deck = tmp / "guide_deck.pptx"
            analysis = analyze_presentation(parse_pptx(SIMPLE_ANIMATED_SAMPLE))
            plan = build_augment_plan(analysis)

            write_guide_deck(SIMPLE_ANIMATED_SAMPLE, guide_deck, plan)
            parsed = parse_pptx(guide_deck)
            source_slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide1.xml")

        self.assertEqual(parsed["slide_count"], 1)
        self.assertIn("Guide Inline Marker 1", source_slide_xml)
        self.assertNotIn("Guide Highlight", source_slide_xml)

    def test_write_guide_deck_appends_readable_guide_slide(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))
            plan = build_augment_plan(analysis)

            write_guide_deck(pptx_path, guide_deck, plan)
            parsed = parse_pptx(guide_deck)

        self.assertEqual(parsed["slide_count"], 2)
        self.assertIn("动画导读", parsed["slides"][1]["title"])
        self.assertTrue(any("最终公式" in obj.get("text", "") for obj in parsed["slides"][1]["objects"]))

    def test_guide_slide_uses_structured_non_overlapping_layout(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            guide_deck = tmp / "guide_deck.pptx"
            write_minimal_pptx(pptx_path)
            analysis = analyze_presentation(parse_pptx(pptx_path))
            plan = build_augment_plan(analysis)

            write_guide_deck(pptx_path, guide_deck, plan)
            slide_xml = _read_zip_text(guide_deck, "ppt/slides/slide2.xml")

        self.assertIn("Guide Background", slide_xml)
        self.assertIn("Guide Header", slide_xml)
        self.assertIn("Step Card 1", slide_xml)
        root = ET.fromstring(slide_xml)
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        y_positions = [
            int(off.attrib["y"])
            for off in root.findall(".//a:xfrm/a:off", ns)
            if int(off.attrib["y"]) > 0
        ]
        self.assertEqual(y_positions, sorted(y_positions))
        self.assertGreaterEqual(min(_shape_widths(root)), 900000)

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
            self.assertEqual(report["version"], "v3d")
            self.assertEqual(report["outputs"]["guide_pdf"], "guide.pdf")
            self.assertEqual(report["outputs"]["augment_plan_json"], "augment_plan.json")


if __name__ == "__main__":
    unittest.main()


def _read_zip_text(path: Path, name: str) -> str:
    import zipfile

    with zipfile.ZipFile(path) as package:
        return package.read(name).decode("utf-8")


def _shape_widths(root: ET.Element) -> list[int]:
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    return [
        int(ext.attrib["cx"])
        for ext in root.findall(".//a:xfrm/a:ext", ns)
        if int(ext.attrib["cx"]) > 0
    ]
