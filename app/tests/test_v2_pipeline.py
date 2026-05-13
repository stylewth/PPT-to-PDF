import sys
import shutil
import unittest
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
TMP_ROOT = Path(__file__).resolve().parents[1] / "workspace" / "test_runs"
TMP_ROOT.mkdir(parents=True, exist_ok=True)

from html_renderer import render_study_html
from converter import convert_pptx
from pptx_parser import PptxParseError, parse_pptx
from server import extract_uploaded_file
from study_builder import build_study_document


@contextmanager
def workspace_tmpdir():
    path = TMP_ROOT / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def write_minimal_pptx(path: Path) -> None:
    slide_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/></p:nvGrpSpPr>
      <p:grpSpPr/>
      <p:sp>
        <p:nvSpPr><p:cNvPr id="2" name="Title"/></p:nvSpPr>
        <p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="5000000" cy="600000"/></a:xfrm></p:spPr>
        <p:txBody><a:p><a:r><a:t>梯度下降</a:t></a:r></a:p></p:txBody>
      </p:sp>
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
  <p:timing>
    <p:tnLst>
      <p:par>
        <p:cTn id="1">
          <p:childTnLst>
            <p:seq>
              <p:cTn id="2">
                <p:childTnLst>
                  <p:par>
                    <p:cTn id="3" presetClass="entr">
                      <p:childTnLst>
                        <p:animEffect transition="in" filter="fade">
                          <p:cBhvr><p:cTn id="4"/><p:tgtEl><p:spTgt spid="3"/></p:tgtEl></p:cBhvr>
                        </p:animEffect>
                      </p:childTnLst>
                    </p:cTn>
                  </p:par>
                  <p:par>
                    <p:cTn id="5" presetClass="entr">
                      <p:childTnLst>
                        <p:animEffect transition="in" filter="wipe(r)">
                          <p:cBhvr><p:cTn id="6"/><p:tgtEl><p:spTgt spid="4"/></p:tgtEl></p:cBhvr>
                        </p:animEffect>
                      </p:childTnLst>
                    </p:cTn>
                  </p:par>
                </p:childTnLst>
              </p:cTn>
            </p:seq>
          </p:childTnLst>
        </p:cTn>
      </p:par>
    </p:tnLst>
  </p:timing>
</p:sld>
"""
    notes_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<p:notes xmlns:p="{P_NS}" xmlns:a="{A_NS}">
  <p:cSld><p:spTree><p:sp><p:txBody>
    <a:p><a:r><a:t>教师备注：先展示问题，再展示答案。</a:t></a:r></a:p>
  </p:txBody></p:sp></p:spTree></p:cSld>
</p:notes>
"""
    rels_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" Target="../notesSlides/notesSlide1.xml"/>
</Relationships>
"""
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("ppt/presentation.xml", "<p:presentation xmlns:p='%s'/>" % P_NS)
        package.writestr("ppt/slides/slide1.xml", slide_xml)
        package.writestr("ppt/slides/_rels/slide1.xml.rels", rels_xml)
        package.writestr("ppt/notesSlides/notesSlide1.xml", notes_xml)


class V2PipelineTest(unittest.TestCase):
    def test_parse_pptx_extracts_objects_notes_and_basic_animation_order(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)

            presentation = parse_pptx(pptx_path)

        slide = presentation["slides"][0]
        self.assertEqual(presentation["slide_count"], 1)
        self.assertEqual(slide["title"], "梯度下降")
        self.assertEqual([obj["text"] for obj in slide["objects"]], ["梯度下降", "当前位置", "最终公式"])
        self.assertIn("先展示问题", slide["notes"])
        self.assertEqual([anim["target_id"] for anim in slide["animations"]], ["3", "4"])
        self.assertEqual([anim["kind"] for anim in slide["animations"]], ["fade", "wipe"])

    def test_parse_pptx_rejects_non_pptx_zip_structure(self):
        with workspace_tmpdir() as tmp:
            bad_path = tmp / "bad.pptx"
            with zipfile.ZipFile(bad_path, "w") as package:
                package.writestr("readme.txt", "not a deck")

            with self.assertRaises(PptxParseError):
                parse_pptx(bad_path)

    def test_build_study_document_flags_occlusion_and_builds_animation_steps(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)
            presentation = parse_pptx(pptx_path)

        document = build_study_document(presentation)
        slide = document["slides"][0]

        self.assertEqual(document["source"]["slide_count"], 1)
        self.assertEqual(slide["title"], "梯度下降")
        self.assertEqual([step["target_text"] for step in slide["steps"]], ["当前位置", "最终公式"])
        self.assertTrue(any(warning["code"] == "top_layer_occlusion" for warning in slide["warnings"]))
        self.assertIn("教师备注", slide["explanation"])

    def test_render_study_html_outputs_safe_readable_preview(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            write_minimal_pptx(pptx_path)
            document = build_study_document(parse_pptx(pptx_path))

        html = render_study_html(document)

        self.assertIn("<!doctype html>", html)
        self.assertIn("学习型 PDF", html)
        self.assertIn("梯度下降", html)
        self.assertIn("最终公式", html)
        self.assertIn("top_layer_occlusion", html)
        self.assertNotIn("<script", html.lower())

    def test_convert_pptx_writes_report_and_preview_outputs(self):
        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            output_dir = tmp / "out"
            write_minimal_pptx(pptx_path)

            result = convert_pptx(pptx_path, output_dir, render_pdf=False)

            self.assertEqual(result["status"], "ok")
            self.assertTrue(Path(result["report_path"]).exists())
            self.assertTrue(Path(result["preview_html_path"]).exists())
            self.assertIsNone(result["base_pdf_path"])
            self.assertIsNone(result["guide_pdf_path"])
            self.assertIn("top_layer_occlusion", Path(result["preview_html_path"]).read_text(encoding="utf-8"))

    def test_extract_uploaded_file_reads_multipart_pptx_payload(self):
        boundary = "----slide2study"
        payload = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="deck"; filename="demo.pptx"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation\r\n"
            "\r\n"
        ).encode("utf-8") + b"pptx-bytes" + f"\r\n--{boundary}--\r\n".encode("utf-8")

        upload = extract_uploaded_file(
            f"multipart/form-data; boundary={boundary}",
            payload,
        )

        self.assertEqual(upload["filename"], "demo.pptx")
        self.assertEqual(upload["content"], b"pptx-bytes")


if __name__ == "__main__":
    unittest.main()
