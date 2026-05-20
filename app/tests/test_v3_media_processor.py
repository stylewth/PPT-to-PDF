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


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
TMP_ROOT = Path(__file__).resolve().parent / ".tmp_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

from converter import convert_pptx
from pptx_parser import parse_pptx


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class FakeSofficeRunner:
    def __call__(self, command, *, timeout, capture_output, text, **kwargs):
        outdir = Path(command[command.index("--outdir") + 1])
        source = Path(command[-1])
        _write_valid_pdf(outdir / f"{source.stem}.pdf")
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")


class MediaProcessorTest(unittest.TestCase):
    def test_parse_pptx_marks_gif_picture_media(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "gif_sample.pptx"
            write_gif_media_pptx(pptx_path)

            presentation = parse_pptx(pptx_path)

        slide = presentation["slides"][0]
        gif_object = next(obj for obj in slide["objects"] if obj["id"] == "4")
        self.assertEqual(gif_object["type"], "pic")
        self.assertEqual(gif_object["media"]["kind"], "gif")
        self.assertEqual(gif_object["media"]["path"], "ppt/media/roll.gif")
        self.assertEqual(gif_object["media"]["rel_id"], "rId2")
        self.assertEqual(gif_object["media"]["extension"], ".gif")

    def test_parse_pptx_marks_video_file_media(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "video_sample.pptx"
            write_video_media_pptx(pptx_path)

            presentation = parse_pptx(pptx_path)

        slide = presentation["slides"][0]
        video_object = next(obj for obj in slide["objects"] if obj["id"] == "5")
        self.assertEqual(video_object["type"], "pic")
        self.assertEqual(video_object["media"]["kind"], "video")
        self.assertEqual(video_object["media"]["path"], "ppt/media/movie.mp4")
        self.assertEqual(video_object["media"]["rel_id"], "rId3")
        self.assertEqual(video_object["media"]["extension"], ".mp4")

    def test_process_presentation_media_exports_gif_and_keyframe_strip(self):
        from media_processor import process_presentation_media

        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "gif_sample.pptx"
            output_dir = tmp / "out"
            write_gif_media_pptx(pptx_path)
            presentation = parse_pptx(pptx_path)

            manifest = process_presentation_media(pptx_path, presentation, output_dir)

            manifest_path = output_dir / "media_manifest.json"
            self.assertTrue(manifest_path.exists())
            self.assertEqual(manifest["kind"], "media_manifest")
            self.assertEqual(manifest["summary"]["media_count"], 1)
            self.assertEqual(manifest["summary"]["gif_count"], 1)
            item = manifest["items"][0]
            self.assertEqual(item["slide_number"], 1)
            self.assertEqual(item["object_id"], "4")
            self.assertEqual(item["kind"], "gif")
            self.assertEqual(item["status"], "ok")
            self.assertTrue((output_dir / item["export_path"]).exists())
            self.assertTrue((output_dir / item["preview"]["poster_path"]).exists())
            self.assertTrue((output_dir / item["preview"]["strip_path"]).exists())
            self.assertTrue((output_dir / item["preview"]["grid_path"]).exists())
            self.assertEqual(len(item["preview"]["frames"]), 4)
            self.assertTrue((output_dir / item["preview"]["frames"][0]["path"]).exists())
            self.assertEqual(item["preview"]["frame_count"], 4)
            self.assertGreaterEqual(item["preview"]["duration_ms"], 240)
            self.assertEqual(item["preview"]["sampled_frame_indices"], [0, 1, 2, 3])

    def test_process_presentation_media_exports_video_original_without_preview(self):
        from media_processor import process_presentation_media

        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "video_sample.pptx"
            output_dir = tmp / "out"
            write_video_media_pptx(pptx_path)
            presentation = parse_pptx(pptx_path)

            manifest = process_presentation_media(pptx_path, presentation, output_dir)

            self.assertEqual(manifest["summary"]["media_count"], 1)
            self.assertEqual(manifest["summary"]["video_count"], 1)
            item = manifest["items"][0]
            self.assertEqual(item["kind"], "video")
            self.assertEqual(item["status"], "exported_original_only")
            self.assertTrue((output_dir / item["export_path"]).exists())
            self.assertNotIn("preview", item)

    def test_converter_reports_media_manifest_output(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "gif_sample.pptx"
            output_dir = tmp / "out"
            fake_soffice = tmp / "soffice.exe"
            fake_soffice.write_text("fake executable", encoding="utf-8")
            write_gif_media_pptx(pptx_path)

            result = convert_pptx(
                pptx_path,
                output_dir,
                render_pdf=True,
                soffice_path=fake_soffice,
                command_runner=FakeSofficeRunner(),
            )

            manifest_path = Path(result["media_manifest_path"])
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            self.assertTrue(manifest_path.exists())
            self.assertEqual(report["outputs"]["media_manifest_json"], "media_manifest.json")
            self.assertEqual(report["media"]["summary"]["gif_count"], 1)

    def test_overlay_media_summaries_replaces_gif_box_with_keyframes(self):
        from pdf_augmenter import overlay_media_summaries

        with workspace_tmpdir() as tmp:
            pdf_path = tmp / "guide.pdf"
            grid_path = tmp / "media" / "previews" / "grid.png"
            grid_path.parent.mkdir(parents=True)
            _write_colored_grid(grid_path)
            _write_source_media_pdf(pdf_path)
            manifest = {
                "page": {"width": 1000, "height": 1000},
                "items": [
                    {
                        "slide_number": 1,
                        "object_id": "4",
                        "kind": "gif",
                        "status": "ok",
                        "bbox": {"x": 100, "y": 100, "w": 300, "h": 200},
                        "preview": {
                            "grid_path": "media/previews/grid.png",
                            "grid_width": 220,
                            "grid_height": 80,
                        },
                    }
                ],
            }

            overlay_media_summaries(pdf_path, manifest)

            red, green, blue = _sample_pdf_pixel(pdf_path, 110, 70)
            self.assertLess(red, 80)
            self.assertLess(green, 120)
            self.assertGreater(blue, 180)
            red, green, blue = _sample_pdf_pixel(pdf_path, 336, 84)
            self.assertGreater(red, 240)
            self.assertGreater(green, 240)
            self.assertGreater(blue, 240)

    def test_overlay_media_summary_replaces_source_without_covering_title(self):
        from pdf_augmenter import overlay_media_summaries

        with workspace_tmpdir() as tmp:
            pdf_path = tmp / "guide.pdf"
            grid_path = tmp / "media" / "previews" / "grid.png"
            grid_path.parent.mkdir(parents=True)
            _write_colored_grid(grid_path)
            _write_media_pdf_with_title(pdf_path)
            manifest = {
                "page": {"width": 12192000, "height": 6858000},
                "items": [
                    {
                        "slide_number": 1,
                        "object_id": "4",
                        "kind": "gif",
                        "status": "ok",
                        "bbox": {"x": 2526580, "y": 1825461, "w": 6667500, "h": 3848100},
                        "occupied_boxes": [
                            {
                                "id": "2",
                                "bbox": {"x": 3926175, "y": 714329, "w": 4339650, "h": 923330},
                            }
                        ],
                        "preview": {
                            "grid_path": "media/previews/grid.png",
                            "grid_width": 1478,
                            "grid_height": 181,
                        },
                    }
                ],
            }

            overlay_media_summaries(pdf_path, manifest)

            red, green, blue = _sample_pdf_pixel(pdf_path, 360, 70)
            self.assertLess(red, 80)
            self.assertLess(green, 120)
            self.assertGreater(blue, 180)
            red, green, blue = _sample_pdf_pixel(pdf_path, 170, 170)
            self.assertLess(red, 80)
            self.assertLess(green, 120)
            self.assertGreater(blue, 180)

    def test_large_gif_keyframe_grid_clears_full_original_cover(self):
        from pdf_augmenter import overlay_media_summaries

        with workspace_tmpdir() as tmp:
            pdf_path = tmp / "guide.pdf"
            preview_dir = tmp / "media" / "previews"
            preview_dir.mkdir(parents=True)
            grid_path = preview_dir / "grid.png"
            frame_paths = []
            _write_colored_grid(grid_path)
            for index, color in enumerate(["blue", "green", "purple", "cyan", "yellow", "magenta"]):
                frame_path = preview_dir / f"frame{index + 1}.png"
                _write_colored_frame(frame_path, color)
                frame_paths.append(
                    {
                        "path": f"media/previews/frame{index + 1}.png",
                        "frame_index": index,
                        "width": 120,
                        "height": 80,
                    }
                )
            _write_media_pdf_with_title(pdf_path)
            manifest = {
                "page": {"width": 12192000, "height": 6858000},
                "items": [
                    {
                        "slide_number": 1,
                        "object_id": "4",
                        "kind": "gif",
                        "status": "ok",
                        "bbox": {"x": 2526580, "y": 1825461, "w": 6667500, "h": 3848100},
                        "occupied_boxes": [
                            {
                                "id": "2",
                                "bbox": {"x": 3926175, "y": 714329, "w": 4339650, "h": 923330},
                            }
                        ],
                        "preview": {
                            "grid_path": "media/previews/grid.png",
                            "grid_width": 1478,
                            "grid_height": 181,
                            "frames": frame_paths,
                        },
                    }
                ],
            }

            overlay_media_summaries(pdf_path, manifest)

            red, green, blue = _sample_pdf_pixel(pdf_path, 160, 115)
            self.assertGreater(red, 240)
            self.assertGreater(green, 240)
            self.assertGreater(blue, 240)

    def test_overlay_media_summary_expands_small_gif_into_nearby_blank(self):
        from pdf_augmenter import overlay_media_summaries

        with workspace_tmpdir() as tmp:
            pdf_path = tmp / "guide.pdf"
            grid_path = tmp / "media" / "previews" / "grid.png"
            grid_path.parent.mkdir(parents=True)
            _write_colored_grid(grid_path)
            _write_small_media_pdf_with_title(pdf_path)
            manifest = {
                "page": {"width": 1000, "height": 1000},
                "items": [
                    {
                        "slide_number": 1,
                        "object_id": "4",
                        "kind": "gif",
                        "status": "ok",
                        "bbox": {"x": 120, "y": 240, "w": 100, "h": 80},
                        "occupied_boxes": [
                            {
                                "id": "2",
                                "bbox": {"x": 120, "y": 80, "w": 360, "h": 80},
                            }
                        ],
                        "preview": {
                            "grid_path": "media/previews/grid.png",
                            "grid_width": 220,
                            "grid_height": 80,
                        },
                    }
                ],
            }

            overlay_media_summaries(pdf_path, manifest)

            red, green, blue = _sample_pdf_pixel(pdf_path, 110, 130)
            self.assertLess(red, 80)
            self.assertGreater(max(green, blue), 120)
            red, green, blue = _sample_pdf_pixel(pdf_path, 100, 40)
            self.assertGreater(red, 240)
            self.assertLess(green, 80)
            self.assertLess(blue, 80)

    def test_small_gif_uses_nearby_blank_when_anchor_expansion_is_blocked(self):
        from pdf_augmenter import _media_keyframe_layout, _media_keyframe_replacement_rect
        import fitz

        page_rect = fitz.Rect(0, 0, 720, 405)
        source_rect = fitz.Rect(298, 179, 442, 262)
        occupied_rects = [
            fitz.Rect(298, 104, 443, 159),
            fitz.Rect(149, 209, 306, 232),
            fitz.Rect(470, 209, 570, 232),
        ]

        replacement = _media_keyframe_replacement_rect(
            fitz,
            page_rect,
            source_rect,
            746,
            344,
            occupied_rects,
        )
        layout = _media_keyframe_layout(
            fitz,
            page_rect,
            source_rect,
            746,
            344,
            occupied_rects,
            frame_count=6,
        )

        self.assertGreater(replacement.width, source_rect.width * 1.45)
        self.assertGreaterEqual(replacement.y0, source_rect.y1 + 4)
        self.assertTrue(all(not replacement.intersects(rect) for rect in occupied_rects))
        self.assertEqual(layout["mode"], "split_source")
        self.assertEqual(layout["frame_count"], 4)
        self.assertEqual(layout["cols"], 3)
        self.assertEqual(layout["rows"], 1)
        self.assertGreater(layout["rect"].width, 360)
        self.assertGreater(layout["cell_width"], 110)
        self.assertGreater(layout["source_frame_rect"].y0, source_rect.y0 + 10)
        self.assertLess(layout["source_frame_rect"].height, source_rect.height)

    def test_blocked_small_gif_replaces_original_source_with_unified_keyframe_panel(self):
        from pdf_augmenter import overlay_media_summaries

        with workspace_tmpdir() as tmp:
            pdf_path = tmp / "guide.pdf"
            preview_dir = tmp / "media" / "previews"
            preview_dir.mkdir(parents=True)
            grid_path = preview_dir / "grid.png"
            frame_paths = []
            _write_colored_grid(grid_path)
            for index, color in enumerate(["blue", "green", "purple"]):
                frame_path = preview_dir / f"frame{index + 1}.png"
                _write_colored_frame(frame_path, color)
                frame_paths.append(
                    {
                        "path": f"media/previews/frame{index + 1}.png",
                        "frame_index": index,
                        "width": 120,
                        "height": 80,
                    }
                )
            _write_blocked_small_media_pdf(pdf_path)
            manifest = {
                "page": {"width": 720, "height": 405},
                "items": [
                    {
                        "slide_number": 1,
                        "object_id": "4",
                        "kind": "gif",
                        "status": "ok",
                        "bbox": {"x": 298, "y": 179, "w": 144, "h": 83},
                        "occupied_boxes": [
                            {"id": "title", "text": "Title 2.0", "bbox": {"x": 298, "y": 104, "w": 145, "h": 55}},
                            {"id": "left", "bbox": {"x": 149, "y": 209, "w": 157, "h": 23}},
                            {"id": "right", "bbox": {"x": 470, "y": 209, "w": 100, "h": 23}},
                        ],
                        "preview": {
                            "grid_path": "media/previews/grid.png",
                            "grid_width": 746,
                            "grid_height": 344,
                            "frames": frame_paths,
                        },
                    }
                ],
            }

            overlay_media_summaries(pdf_path, manifest)

            red, green, blue = _sample_pdf_pixel(pdf_path, 340, 210)
            self.assertLess(red, 245)
            self.assertLess(green, 245)
            self.assertLess(blue, 245)
            red, green, blue = _sample_pdf_pixel(pdf_path, 370, 220)
            self.assertLess(red, 90)
            self.assertLess(green, 120)
            self.assertGreater(blue, 150)
            red, green, blue = _sample_pdf_pixel(pdf_path, 250, 300)
            self.assertLess(red, 150)
            self.assertGreater(max(green, blue), 100)

    def test_server_and_frontend_expose_media_manifest_download(self):
        from server import build_convert_response

        payload = build_convert_response(
            "abc123",
            {
                "source": {"name": "demo.pptx", "slide_count": 1},
                "warnings": [],
                "base_pdf_path": "base.pdf",
                "guide_pdf_path": "guide.pdf",
                "compare_html_path": "compare.html",
                "analysis_path": "analysis.json",
                "augment_plan_path": "augment_plan.json",
                "metrics_path": "metrics.json",
                "media_manifest_path": "media_manifest.json",
                "report_path": "report.json",
                "preview_html_path": "preview.html",
            },
        )
        frontend_js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")

        self.assertEqual(payload["media_manifest_url"], "/outputs/abc123/media_manifest.json")
        self.assertIn("media_manifest_url", frontend_js)
        self.assertIn("媒体清单", frontend_js)


def write_gif_media_pptx(path: Path) -> None:
    gif_data = make_test_gif()
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="1000000" y="300000"/><a:ext cx="5000000" cy="500000"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>GIF motion sample</a:t></a:r></a:p></p:txBody>
      </p:sp>
      <p:pic>
        <p:nvPicPr><p:cNvPr id="4" name="Rolling GIF"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr>
        <p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="2600000" y="1500000"/><a:ext cx="4200000" cy="2400000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    rels_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/roll.gif"/>
</Relationships>
"""
    presentation_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P_NS}">
  <p:sldSz cx="12192000" cy="6858000"/>
</p:presentation>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("ppt/presentation.xml", presentation_xml)
        package.writestr("ppt/slides/slide1.xml", slide_xml)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels_xml)
        package.writestr("ppt/media/roll.gif", gif_data)


def write_video_media_pptx(path: Path) -> None:
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:pic>
        <p:nvPicPr>
          <p:cNvPr id="5" name="Rolling video"/>
          <p:cNvPicPr/>
          <p:nvPr><a:videoFile r:link="rId3"/></p:nvPr>
        </p:nvPicPr>
        <p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>
        <p:spPr><a:xfrm><a:off x="2600000" y="1500000"/><a:ext cx="4200000" cy="2400000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>
      </p:pic>
    </p:spTree>
  </p:cSld>
</p:sld>
"""
    rels_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{PKG_REL_NS}">
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/poster.png"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/video" Target="../media/movie.mp4"/>
</Relationships>
"""
    presentation_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:presentation xmlns:p="{P_NS}">
  <p:sldSz cx="12192000" cy="6858000"/>
</p:presentation>
"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("ppt/presentation.xml", presentation_xml)
        package.writestr("ppt/slides/slide1.xml", slide_xml)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels_xml)
        package.writestr("ppt/media/poster.png", b"poster")
        package.writestr("ppt/media/movie.mp4", b"fake mp4")


def make_test_gif() -> bytes:
    from PIL import Image, ImageDraw

    frames = []
    colors = ["#d73027", "#fc8d59", "#91bfdb", "#4575b4"]
    for index, color in enumerate(colors):
        image = Image.new("RGB", (160, 90), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 159, 89), outline="#222222", width=2)
        draw.ellipse((10 + index * 32, 28, 44 + index * 32, 62), fill=color)
        frames.append(image)
    output = BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=80, loop=0)
    return output.getvalue()


def _write_valid_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.insert_text((72, 72), "fake native pdf")
    doc.save(path)
    doc.close()


def _write_source_media_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(fitz.Rect(72, 40.5, 288, 121.5), color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(path)
    doc.close()


def _write_media_pdf_with_title(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(fitz.Rect(232, 42, 488, 97), color=(0, 0, 1), fill=(0, 0, 1))
    page.draw_rect(fitz.Rect(149, 108, 543, 335), color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(path)
    doc.close()


def _write_small_media_pdf_with_title(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(fitz.Rect(86.4, 32.4, 345.6, 64.8), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(fitz.Rect(86.4, 97.2, 158.4, 129.6), color=(1, 1, 1), fill=(1, 1, 1))
    doc.save(path)
    doc.close()


def _write_colored_strip(path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (220, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 109, 79), fill="blue")
    draw.rectangle((110, 0, 219, 79), fill="green")
    image.save(path)


def _write_colored_grid(path: Path) -> None:
    _write_colored_strip(path)


def _write_colored_frame(path: Path, color: str) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (120, 80), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 119, 79), outline="black", width=3)
    image.save(path)


def _write_blocked_small_media_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=720, height=405)
    page.draw_rect(fitz.Rect(298, 179, 442, 262), color=(1, 0, 0), fill=(1, 0, 0))
    page.draw_rect(fitz.Rect(298, 104, 443, 159), color=(1, 1, 1), fill=(1, 1, 1))
    page.draw_rect(fitz.Rect(149, 209, 306, 232), color=(1, 1, 1), fill=(1, 1, 1))
    page.draw_rect(fitz.Rect(470, 209, 570, 232), color=(1, 1, 1), fill=(1, 1, 1))
    page.insert_textbox(
        fitz.Rect(298, 104, 443, 210),
        "Title\n2.0",
        fontsize=24,
        align=fitz.TEXT_ALIGN_CENTER,
    )
    doc.save(path)
    doc.close()


def _sample_pdf_pixel(path: Path, x: int, y: int) -> tuple[int, int, int]:
    import fitz

    doc = fitz.open(path)
    pix = doc[0].get_pixmap(alpha=False)
    offset = (y * pix.width + x) * pix.n
    rgb = tuple(pix.samples[offset : offset + 3])
    doc.close()
    return rgb


if __name__ == "__main__":
    unittest.main()
