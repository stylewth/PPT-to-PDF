from __future__ import annotations

import json
import posixpath
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from native_converter import convert_pptx_to_pdf


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
SLIDE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
SLIDE_LAYOUT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"

def generate_guide_pdf(
    pptx_path: str | Path,
    output_dir: str | Path,
    plan: dict[str, Any],
    *,
    base_pdf_path: str | Path | None = None,
    soffice_path: str | Path | None = None,
    command_runner=None,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    plan_path = output / "augment_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    guide_pdf_path = output / "guide.pdf"
    if not _has_augments(plan):
        if base_pdf_path is None:
            return {"augment_plan_path": plan_path}
        shutil.copyfile(base_pdf_path, guide_pdf_path)
        return {"augment_plan_path": plan_path, "guide_pdf_path": guide_pdf_path}

    guide_deck_path = output / "guide_deck.pptx"
    write_guide_deck(pptx_path, guide_deck_path, plan)
    convert_pptx_to_pdf(
        guide_deck_path,
        output,
        soffice_path=soffice_path,
        command_runner=command_runner,
        output_name="guide.pdf",
    )
    return {
        "augment_plan_path": plan_path,
        "guide_deck_path": guide_deck_path,
        "guide_pdf_path": guide_pdf_path,
    }


def write_guide_deck(pptx_path: str | Path, output_path: str | Path, plan: dict[str, Any]) -> Path:
    source = Path(pptx_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as package:
        entries = {name: package.read(name) for name in package.namelist()}

    slide_paths = _slide_paths(entries)
    _enhance_source_slides(entries, slide_paths, plan)
    next_slide_number = _next_slide_number(slide_paths)
    layout_target = _first_layout_target(entries, slide_paths)
    presentation_xml = entries.get(
        "ppt/presentation.xml",
        f"<p:presentation xmlns:p='{P_NS}' xmlns:r='{R_NS}'><p:sldIdLst/></p:presentation>".encode(),
    ).decode("utf-8")
    rels_xml = entries.get(
        "ppt/_rels/presentation.xml.rels",
        f"<Relationships xmlns='{PKG_REL_NS}'/>".encode(),
    ).decode("utf-8")
    content_types_xml = entries.get(
        "[Content_Types].xml",
        f"<Types xmlns='{CT_NS}'/>".encode(),
    ).decode("utf-8")

    presentation_xml = _ensure_relationship_namespace(presentation_xml)
    presentation_xml = _ensure_sld_id_list_xml(presentation_xml)
    max_slide_id = _max_slide_id(_xml(presentation_xml.encode("utf-8")).find(f"{{{P_NS}}}sldIdLst"))
    next_rid = _next_rid(_xml(rels_xml.encode("utf-8")))

    for slide_plan in plan.get("slides", []):
        for guide_page in slide_plan.get("guide_pages", []):
            slide_number = next_slide_number
            next_slide_number += 1
            rid = f"rId{next_rid}"
            next_rid += 1
            max_slide_id += 1

            slide_path = f"ppt/slides/slide{slide_number}.xml"
            entries[slide_path] = _guide_slide_xml(guide_page)
            if layout_target:
                entries[f"ppt/slides/_rels/slide{slide_number}.xml.rels"] = _slide_rels_xml(layout_target)

            rel_xml = (
                f'<Relationship Id="{rid}" Type="{SLIDE_REL_TYPE}" '
                f'Target="slides/slide{slide_number}.xml"/>'
            )
            sld_id_xml = f'<p:sldId id="{max_slide_id}" r:id="{rid}"/>'
            presentation_xml = _insert_before_close(presentation_xml, "sldIdLst", sld_id_xml)
            rels_xml = _insert_before_close(rels_xml, "Relationships", rel_xml)
            content_types_xml = _ensure_slide_content_type_xml(content_types_xml, slide_number)

    entries["ppt/presentation.xml"] = presentation_xml.encode("utf-8")
    entries["ppt/_rels/presentation.xml.rels"] = rels_xml.encode("utf-8")
    entries["[Content_Types].xml"] = content_types_xml.encode("utf-8")

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)
    return output


def _has_guide_pages(plan: dict[str, Any]) -> bool:
    return any(slide.get("guide_pages") for slide in plan.get("slides", []))


def _has_augments(plan: dict[str, Any]) -> bool:
    return any(
        slide.get("guide_pages") or slide.get("inline_markers")
        for slide in plan.get("slides", [])
    )


def _enhance_source_slides(
    entries: dict[str, bytes],
    slide_paths: list[str],
    plan: dict[str, Any],
) -> None:
    for slide_plan in plan.get("slides", []):
        markers = slide_plan.get("inline_markers") or []
        if not markers:
            continue
        slide_path = _source_slide_path(slide_paths, slide_plan.get("source_slide", 0))
        if slide_path is None or slide_path not in entries:
            continue
        slide_xml = entries[slide_path].decode("utf-8")
        marker_xml = _inline_marker_shapes_xml(slide_xml, markers, slide_plan.get("size", {}))
        if marker_xml:
            entries[slide_path] = _insert_before_close(slide_xml, "spTree", marker_xml).encode("utf-8")


def _source_slide_path(slide_paths: list[str], source_slide: int) -> str | None:
    if source_slide < 1 or source_slide > len(slide_paths):
        return None
    return slide_paths[source_slide - 1]


def _slide_paths(entries: dict[str, bytes]) -> list[str]:
    paths = [name for name in entries if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
    return sorted(paths, key=lambda value: int(re.search(r"slide(\d+)\.xml", value).group(1)))


def _next_slide_number(slide_paths: list[str]) -> int:
    numbers = [int(re.search(r"slide(\d+)\.xml", path).group(1)) for path in slide_paths]
    return max(numbers, default=0) + 1


def _first_layout_target(entries: dict[str, bytes], slide_paths: list[str]) -> str | None:
    if not slide_paths:
        return None
    rels_path = _slide_rels_path(slide_paths[0])
    if rels_path not in entries:
        return None
    root = _xml(entries[rels_path])
    for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if rel.attrib.get("Type") == SLIDE_LAYOUT_REL_TYPE:
            return rel.attrib.get("Target")
    return None


def _slide_rels_path(slide_path: str) -> str:
    directory, file_name = posixpath.split(slide_path)
    return posixpath.join(directory, "_rels", f"{file_name}.rels")


def _xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _max_slide_id(sld_id_list: ET.Element | None) -> int:
    if sld_id_list is None:
        return 255
    values = []
    for item in sld_id_list.findall(f"{{{P_NS}}}sldId"):
        try:
            values.append(int(item.attrib.get("id", "255")))
        except ValueError:
            values.append(255)
    return max(values, default=255)


def _next_rid(rels_root: ET.Element) -> int:
    numbers = []
    for rel in rels_root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        match = re.fullmatch(r"rId(\d+)", rel.attrib.get("Id", ""))
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _ensure_sld_id_list_xml(xml: str) -> str:
    if re.search(r"<[^>]*sldIdLst[\s>/]", xml):
        return xml
    self_closing = re.search(r"<((?:[A-Za-z0-9_]+:)?presentation)\b([^>]*)/>", xml)
    if self_closing:
        tag = self_closing.group(1)
        replacement = f"<{tag}{self_closing.group(2)}><p:sldIdLst></p:sldIdLst></{tag}>"
        return xml[: self_closing.start()] + replacement + xml[self_closing.end() :]
    return _insert_before_close(xml, "presentation", "<p:sldIdLst></p:sldIdLst>")


def _ensure_relationship_namespace(xml: str) -> str:
    if "xmlns:r=" in xml:
        return xml
    return re.sub(
        r"(<(?:[A-Za-z0-9_]+:)?presentation\b)",
        rf'\1 xmlns:r="{R_NS}"',
        xml,
        count=1,
    )


def _ensure_slide_content_type_xml(xml: str, slide_number: int) -> str:
    part_name = f"/ppt/slides/slide{slide_number}.xml"
    if part_name in xml:
        return xml
    override = f'<Override PartName="{part_name}" ContentType="{SLIDE_CONTENT_TYPE}"/>'
    return _insert_before_close(xml, "Types", override)


def _insert_before_close(xml: str, local_name: str, insertion: str) -> str:
    pattern = re.compile(rf"</(?:[A-Za-z0-9_]+:)?{re.escape(local_name)}>")
    match = pattern.search(xml)
    if not match:
        self_closing = re.search(rf"<((?:[A-Za-z0-9_]+:)?{re.escape(local_name)})\b([^>]*)/>", xml)
        if not self_closing:
            raise ValueError(f"Missing closing tag for {local_name}.")
        tag = self_closing.group(1)
        replacement = f"<{tag}{self_closing.group(2)}>{insertion}</{tag}>"
        return xml[: self_closing.start()] + replacement + xml[self_closing.end() :]
    return xml[: match.start()] + insertion + xml[match.start() :]


def _slide_rels_xml(layout_target: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PKG_REL_NS}">'
        f'<Relationship Id="rId1" Type="{SLIDE_LAYOUT_REL_TYPE}" Target="{escape(layout_target)}"/>'
        "</Relationships>"
    ).encode("utf-8")


def _inline_marker_shapes_xml(
    slide_xml: str,
    markers: list[dict[str, Any]],
    page_size: dict[str, int],
) -> str:
    page_width = int(page_size.get("width") or 12192000)
    page_height = int(page_size.get("height") or 6858000)
    next_shape_id = _next_shape_id(slide_xml)
    shapes = []
    for marker in markers[:3]:
        order = int(marker.get("order") or len(shapes) + 1)
        label = str(marker.get("label") or order)
        bbox = marker.get("bbox")
        if not bbox:
            bbox = _default_marker_box(order, page_width)
        badge = _badge_box(bbox, page_width)
        shapes.append(
            _text_shape(
                next_shape_id,
                f"Guide Inline Marker {order}",
                badge["x"],
                badge["y"],
                badge["w"],
                badge["h"],
                label,
                1800,
                "FFFFFF",
                fill="237A57",
                line=None,
                body_inset_x=25000,
                body_inset_y=25000,
                align="ctr",
                vertical_anchor="ctr",
            )
        )
        next_shape_id += 1
        hint = str(marker.get("hint") or "")
        if hint:
            hint_box = _hint_box(badge, page_width, page_height)
            shapes.append(
                _text_shape(
                    next_shape_id,
                    f"Guide Inline Hint {order}",
                    hint_box["x"],
                    hint_box["y"],
                    hint_box["w"],
                    hint_box["h"],
                    hint,
                    1150,
                    "1E4637",
                    fill="F5FBF7",
                    line="A9D1BF",
                )
            )
            next_shape_id += 1
    return "".join(shapes)


def _next_shape_id(slide_xml: str) -> int:
    ids = [
        int(value)
        for value in re.findall(r"<(?:[A-Za-z0-9_]+:)?cNvPr\b[^>]*\bid=[\"'](\d+)[\"']", slide_xml)
    ]
    return max(ids, default=1) + 1


def _default_marker_box(order: int, page_width: int) -> dict[str, int]:
    return {
        "x": max(120000, page_width - 800000),
        "y": 180000 + (order - 1) * 460000,
        "w": 360000,
        "h": 360000,
    }


def _frame_box(bbox: dict[str, int], page_width: int, page_height: int) -> dict[str, int]:
    pad = 85000
    x = _clamp(int(bbox.get("x", 0)) - pad, 0, page_width - 1)
    y = _clamp(int(bbox.get("y", 0)) - pad, 0, page_height - 1)
    right = _clamp(int(bbox.get("x", 0)) + int(bbox.get("w", 0)) + pad, x + 1, page_width)
    bottom = _clamp(int(bbox.get("y", 0)) + int(bbox.get("h", 0)) + pad, y + 1, page_height)
    return {"x": x, "y": y, "w": right - x, "h": bottom - y}


def _badge_box(bbox: dict[str, int], page_width: int) -> dict[str, int]:
    size = 330000
    margin = 120000
    x = _clamp(int(bbox.get("x", 0)), margin, page_width - size - margin)
    y = max(margin, int(bbox.get("y", 0)) - size - 90000)
    return {"x": x, "y": y, "w": size, "h": size}


def _hint_box(badge: dict[str, int], page_width: int, page_height: int) -> dict[str, int]:
    margin = 120000
    gap = 65000
    width = 880000
    height = 330000
    right_x = badge["x"] + badge["w"] + gap
    if right_x + width <= page_width - margin:
        x = right_x
    else:
        x = _clamp(badge["x"] - gap - width, margin, page_width - width - margin)
    y = _clamp(badge["y"], margin, page_height - height - margin)
    return {"x": x, "y": y, "w": width, "h": height}


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _frame_shape(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    color: str,
) -> str:
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln w="25400"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln></p:spPr>
</p:sp>'''


def _guide_slide_xml(page: dict[str, Any]) -> bytes:
    title = str(page.get("title", "动画导读"))
    subtitle = str(page.get("subtitle", ""))
    steps = page.get("steps", [])
    lines = [
        _text_shape(2, "Guide Background", 0, 0, 12192000, 6858000, "", 100, "17201B", fill="F7F8F4", line=None),
        _text_shape(3, "Guide Header", 520000, 320000, 11150000, 760000, "动画导读", 3200, "FFFFFF", fill="17324D", line=None),
        _text_shape(4, "Guide Title", 720000, 1220000, 9800000, 460000, title, 2300, "17324D", fill=None, line=None),
        _text_shape(5, "Guide Subtitle", 720000, 1660000, 9800000, 420000, subtitle, 1600, "66746D", fill=None, line=None),
        _text_shape(6, "Guide Section", 720000, 2140000, 3600000, 360000, "本页变化顺序", 1800, "237A57", fill=None, line=None),
    ]
    y = 2640000
    for index, step in enumerate(steps[:5], start=1):
        text = str(step.get("text", ""))
        base_id = 10 + index * 3
        lines.append(_text_shape(base_id, f"Step Card {index}", 720000, y, 10750000, 620000, "", 100, "17201B", fill="FFFFFF", line="D8DFDA"))
        lines.append(_text_shape(base_id + 1, f"Step Badge {index}", 900000, y + 100000, 900000, 410000, str(index), 2200, "FFFFFF", fill="237A57", line=None))
        lines.append(_text_shape(base_id + 2, f"Step Text {index}", 1980000, y + 110000, 8900000, 430000, text, 1750, "17201B", fill=None, line=None))
        y += 760000
    metrics = page.get("metrics", {})
    footer = f"策略：{metrics.get('strategy', 'native_enhance')}    拥挤度：{metrics.get('crowding', 'unknown')}    复杂度：{metrics.get('complexity', 'unknown')}"
    lines.append(_text_shape(30, "Guide Footer", 720000, 6040000, 10750000, 420000, footer, 1450, "7A4A12", fill="FFF4DF", line="F4D9A9"))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="{R_NS}" xmlns:p="{P_NS}">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {''.join(lines)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>'''.encode("utf-8")


def _text_shape(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    size: int,
    color: str,
    *,
    fill: str | None = None,
    line: str | None = None,
    body_inset_x: int = 180000,
    body_inset_y: int = 90000,
    align: str | None = None,
    vertical_anchor: str | None = None,
) -> str:
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else "<a:ln><a:noFill/></a:ln>"
    anchor_xml = f' anchor="{vertical_anchor}"' if vertical_anchor else ""
    paragraph_xml = f'<a:pPr algn="{align}"/>' if align else ""
    text_xml = escape(text)
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>{fill_xml}{line_xml}</p:spPr>
  <p:txBody><a:bodyPr wrap="square"{anchor_xml} lIns="{body_inset_x}" tIns="{body_inset_y}" rIns="{body_inset_x}" bIns="{body_inset_y}"/><a:lstStyle/><a:p>{paragraph_xml}<a:r><a:rPr lang="zh-CN" sz="{size}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>{text_xml}</a:t></a:r></a:p></p:txBody>
</p:sp>'''
