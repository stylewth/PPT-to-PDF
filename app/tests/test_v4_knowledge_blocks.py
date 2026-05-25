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


class V4KnowledgeBlocksTest(unittest.TestCase):
    def test_build_blocks_skips_title_and_groups_formula_with_neighbor_text(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_formula_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        slide_blocks = index["slides"][0]["blocks"]
        self.assertEqual(index["kind"], "knowledge_blocks")
        self.assertEqual(index["version"], "v5a")
        self.assertFalse(any(block["title"] == "洛伦兹力半径" for block in slide_blocks))
        formula = next(block for block in slide_blocks if block["type"] == "formula_group")
        self.assertIn("4", formula["object_ids"])
        self.assertIn("5", formula["object_ids"])
        self.assertIn("r = mv / qB", "\n".join(formula["texts"]))
        self.assertIn("半径由速度", "\n".join(formula["texts"]))
        self.assertGreater(formula["token_estimate"], 0)
        self.assertIn({"kind": "slide_text", "slide": 1, "object_id": "5"}, formula["source_refs"])

    def test_single_large_text_box_is_not_dropped_as_title(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_single_large_text_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        slide_blocks = index["slides"][0]["blocks"]
        self.assertEqual(len(slide_blocks), 1)
        self.assertEqual(slide_blocks[0]["type"], "text_concept")
        self.assertIn("Keywords:", "\n".join(slide_blocks[0]["texts"]))

    def test_numbered_outline_bbox_expands_to_cover_visual_overflow(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_numbered_outline_overflow_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        block = next(block for block in index["slides"][0]["blocks"] if block["title"].startswith("1 Electric"))
        self.assertGreaterEqual(block["display_bbox"]["y"] + block["display_bbox"]["h"], 0.78)
        self.assertIn("5 Calculating Field from Potential", block["texts"][0])

    def test_title_text_is_attached_to_first_body_block(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_title_and_body_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        block = index["slides"][0]["blocks"][0]
        self.assertEqual(block["type"], "text_concept")
        self.assertIn("章节标题", block["texts"])
        self.assertIn("正文解释第一句。", block["texts"])
        self.assertIn("2", block["object_ids"])
        self.assertIn("3", block["object_ids"])

    def test_dense_formula_diagram_merges_labels_formulas_and_visuals(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_dense_formula_diagram_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        blocks = index["slides"][0]["blocks"]
        self.assertEqual(len(blocks), 1)
        diagram = blocks[0]
        self.assertEqual(diagram["type"], "diagram_group")
        self.assertIn("q = q1 + q2 + q3", "\n".join(diagram["texts"]))
        self.assertIn("+q1", diagram["texts"])
        self.assertIn("caption", diagram["object_ids"])
        self.assertIn("formula", diagram["object_ids"])
        self.assertGreaterEqual(len(diagram["object_ids"]), 12)

    def test_media_manifest_creates_media_timeline_block(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_media_slide()])
        analysis = analyze_presentation(presentation)
        media_manifest = {
            "items": [
                {
                    "slide_number": 1,
                    "object_id": "7",
                    "kind": "gif",
                    "status": "ok",
                    "preview": {"frame_count": 4},
                }
            ]
        }

        index = build_knowledge_blocks(presentation, analysis, {}, media_manifest)

        media = next(block for block in index["slides"][0]["blocks"] if block["type"] == "media_timeline")
        self.assertEqual(media["object_ids"], ["7"])
        self.assertEqual(media["media"]["kind"], "gif")
        self.assertIn({"kind": "media", "slide": 1, "object_id": "7"}, media["source_refs"])

    def test_static_picture_media_is_not_a_media_timeline_block(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_static_picture_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        self.assertFalse(any(block["type"] == "media_timeline" for block in index["slides"][0]["blocks"]))

    def test_many_small_graphic_fragments_merge_into_one_diagram_group(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_diagram_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        blocks = index["slides"][0]["blocks"]
        diagram_blocks = [block for block in blocks if block["type"] == "diagram_group"]
        self.assertEqual(len(diagram_blocks), 1)
        self.assertGreaterEqual(len(diagram_blocks[0]["object_ids"]), 8)
        self.assertLess(len(blocks), 4)

    def test_animation_cover_relation_attaches_to_content_block(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_animation_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        blocks = index["slides"][0]["blocks"]
        self.assertFalse(any(block["type"] == "animation_flow" for block in blocks))
        content = next(block for block in blocks if {"4", "5"}.issubset(set(block["object_ids"])))
        self.assertEqual(content["type"], "text_concept")
        self.assertIn("初始位置", content["texts"])
        self.assertIn("最终公式", content["texts"])
        self.assertEqual(content["animation_steps"], [2])
        self.assertIn({"kind": "animation", "slide": 1, "object_id": "5"}, content["source_refs"])

    def test_dense_diagram_with_animation_stays_one_content_block(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_dense_formula_diagram_with_animation_slide()])
        analysis = analyze_presentation(presentation)

        index = build_knowledge_blocks(presentation, analysis, {}, {})

        blocks = index["slides"][0]["blocks"]
        self.assertEqual(len(blocks), 1)
        diagram = blocks[0]
        self.assertEqual(diagram["type"], "diagram_group")
        self.assertNotEqual(diagram["summary"], "动画步骤会覆盖前序对象，适合按前后关系解释。")
        self.assertIn("q = q1 + q2 + q3", "\n".join(diagram["texts"]))
        self.assertEqual(diagram["animation_steps"], [2])
        self.assertIn({"kind": "animation", "slide": 1, "object_id": "q2"}, diagram["source_refs"])

    def test_reflowed_visual_bbox_is_used_for_reader_overlay(self):
        from knowledge_blocks import build_knowledge_blocks

        presentation = _sample_presentation([_animation_visual_slide()])
        analysis = analyze_presentation(presentation)
        plan = {
            "slides": [
                {
                    "source_slide": 1,
                    "object_reflow": {
                        "operations": [
                            {
                                "op": "move_resize",
                                "id": "5",
                                "from": {"x": 260, "y": 130, "w": 180, "h": 100},
                                "to": {"x": 650, "y": 140, "w": 180, "h": 100},
                            }
                        ]
                    },
                }
            ]
        }

        index = build_knowledge_blocks(presentation, analysis, plan, {})

        block = index["slides"][0]["blocks"][0]
        self.assertIn("4", block["object_ids"])
        self.assertIn("5", block["object_ids"])
        self.assertEqual(block["display_bbox"]["x"], 0.06)
        self.assertEqual(block["display_bbox"]["w"], 0.77)
        self.assertIn({"kind": "visual", "slide": 1, "object_id": "5"}, block["source_refs"])

    def test_converter_writes_knowledge_blocks_and_server_frontend_expose_it(self):
        from server import build_convert_response

        with workspace_tmpdir() as tmp:
            pptx_path = tmp / "course.pptx"
            output_dir = tmp / "out"
            write_minimal_pptx(pptx_path)

            result = convert_pptx(pptx_path, output_dir, render_pdf=False)

            knowledge_path = Path(result["knowledge_blocks_path"])
            report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
            payload = build_convert_response("job1", result)
            frontend_js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
            frontend_html = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
            knowledge_exists = knowledge_path.exists()

        self.assertTrue(knowledge_exists)
        self.assertEqual(report["outputs"]["knowledge_blocks_json"], "knowledge_blocks.json")
        self.assertEqual(payload["knowledge_blocks_url"], "/outputs/job1/knowledge_blocks.json")
        self.assertIn("knowledge_blocks_url", frontend_js)
        self.assertIn("知识块", frontend_html)


def _sample_presentation(slides):
    return {
        "source_name": "sample.pptx",
        "slide_count": len(slides),
        "page": {"width": 1000, "height": 600},
        "slides": [
            {**slide, "number": index}
            for index, slide in enumerate(slides, start=1)
        ],
    }


def _formula_slide():
    return {
        "title": "洛伦兹力半径",
        "notes": "公式块要和解释文字绑定。",
        "animations": [],
        "objects": [
            _obj("2", "sp", "洛伦兹力半径", 60, 30, 520, 56, z=1),
            _obj("3", "sp", "带电粒子进入磁场后做圆周运动。", 70, 130, 360, 48, z=2),
            _obj("4", "graphicFrame", "r = mv / qB", 450, 126, 170, 48, z=3, name="公式"),
            _obj("5", "sp", "半径由速度、质量、电荷量和磁感应强度共同决定。", 450, 190, 360, 52, z=4),
        ],
    }


def _single_large_text_slide():
    text = (
        "Keywords: Conservative Force, Potential Energy "
        "Electric Potential, Electric Potential Energy, Electron-volt "
        "Equipotential Surface Potential Difference, Zero Potential"
    )
    return {
        "title": text,
        "notes": "",
        "animations": [],
        "objects": [
            _obj("2", "sp", text, 40, 40, 700, 260, z=1),
        ],
    }


def _title_and_body_slide():
    return {
        "title": "章节标题",
        "notes": "",
        "animations": [],
        "objects": [
            _obj("2", "sp", "章节标题", 60, 30, 420, 48, z=1),
            _obj("3", "sp", "正文解释第一句。", 70, 120, 520, 58, z=2),
        ],
    }


def _numbered_outline_overflow_slide():
    text = (
        "1 Electric Potential & Potential Energy 电势和势能 "
        "2 Electric Potential due to Point Charges 点电荷电势 "
        "3 Calculating Potential from Field 从电场算电势 "
        "4 Calculating Potential by Superposition 叠加原理算电势 "
        "5 Calculating Field from Potential 从电势算电场"
    )
    return {
        "title": text,
        "notes": "",
        "animations": [],
        "objects": [
            _obj("outline", "sp", text, 70, 136, 900, 260, z=1),
            _obj("heading", "sp", "24 Electric Potential", 230, 42, 574, 56, z=2),
        ],
    }


def _dense_formula_diagram_slide():
    objects = [
        _obj("title", "sp", "电容并联", 60, 30, 420, 48, z=1),
        _obj("caption", "sp", "电路图和公式描述同一个并联电容关系。", 60, 500, 600, 58, z=30),
        _obj("formula", "graphicFrame", "q = q1 + q2 + q3", 400, 370, 220, 50, z=29, name="公式"),
        _obj("vformula", "graphicFrame", "V = V1 = V2 = V3", 70, 370, 220, 50, z=28, name="公式"),
        _obj("q1", "sp", "+q1", 210, 140, 60, 32, z=20),
        _obj("q2", "sp", "+q2", 360, 140, 60, 32, z=21),
        _obj("q3", "sp", "+q3", 510, 140, 60, 32, z=22),
        _obj("c1", "sp", "C1", 230, 250, 50, 32, z=23),
        _obj("c2", "sp", "C2", 380, 250, 50, 32, z=24),
        _obj("c3", "sp", "C3", 530, 250, 50, 32, z=25),
    ]
    for index in range(8):
        objects.append(_obj(f"wire{index}", "shape", "", 160 + index * 55, 170 + (index % 2) * 70, 48, 18, z=2 + index))
    return {"title": "电容并联", "notes": "", "animations": [], "objects": objects}


def _dense_formula_diagram_with_animation_slide():
    slide = _dense_formula_diagram_slide()
    q1_box = next(obj for obj in slide["objects"] if obj["id"] == "q1")["bbox"]
    next(obj for obj in slide["objects"] if obj["id"] == "q2")["bbox"] = dict(q1_box)
    slide["animations"] = [
        {"order": 1, "target_id": "q1", "target_text": "+q1", "kind": "appear", "supported": True},
        {"order": 2, "target_id": "q2", "target_text": "+q2", "kind": "appear", "supported": True},
    ]
    return slide


def _media_slide():
    return {
        "title": "机械运动",
        "notes": "",
        "animations": [],
        "objects": [
            _obj("2", "sp", "机械运动", 60, 30, 520, 56, z=1),
            _obj("7", "pic", "", 160, 150, 320, 180, z=2, name="rolling.gif", media={"kind": "gif"}),
        ],
    }


def _static_picture_slide():
    return {
        "title": "静态图片",
        "notes": "",
        "animations": [],
        "objects": [
            _obj("2", "sp", "静态图片", 60, 30, 520, 56, z=1),
            _obj("7", "pic", "", 160, 150, 320, 180, z=2, name="cover.png", media={"kind": "image"}),
        ],
    }


def _diagram_slide():
    objects = [_obj("2", "sp", "电路图", 60, 30, 420, 56, z=1)]
    for index in range(8):
        objects.append(_obj(str(10 + index), "shape", "", 160 + index * 35, 180 + (index % 2) * 30, 28, 18, z=2 + index))
    return {"title": "电路图", "notes": "", "animations": [], "objects": objects}


def _animation_slide():
    return {
        "title": "动画遮挡",
        "notes": "",
        "animations": [
            {"order": 1, "target_id": "4", "target_text": "初始位置", "kind": "appear", "supported": True},
            {"order": 2, "target_id": "5", "target_text": "最终公式", "kind": "appear", "supported": True},
        ],
        "objects": [
            _obj("2", "sp", "动画遮挡", 60, 30, 520, 56, z=1),
            _obj("4", "sp", "初始位置", 180, 180, 220, 80, z=2),
            _obj("5", "sp", "最终公式", 190, 190, 220, 80, z=3),
        ],
    }


def _animation_visual_slide():
    return {
        "title": "动画图示",
        "notes": "",
        "animations": [
            {"order": 1, "target_id": "4", "target_text": "核心文字", "kind": "appear", "supported": True},
            {"order": 2, "target_id": "5", "target_text": "图片 1", "kind": "appear", "supported": True},
        ],
        "objects": [
            _obj("2", "sp", "动画图示", 60, 30, 520, 56, z=1),
            _obj("4", "sp", "核心文字", 180, 130, 360, 100, z=2),
            _obj("5", "pic", "", 260, 130, 180, 100, z=3, name="diagram.png"),
        ],
    }


def _obj(object_id, obj_type, text, x, y, w, h, *, z=0, name="", media=None):
    item = {
        "id": object_id,
        "name": name,
        "type": obj_type,
        "text": text,
        "bbox": {"x": x, "y": y, "w": w, "h": h},
        "z_order": z,
    }
    if media:
        item["media"] = media
    return item


if __name__ == "__main__":
    unittest.main()
