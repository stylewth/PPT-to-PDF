from __future__ import annotations

from copy import deepcopy
from html import escape
from typing import Any
from xml.etree import ElementTree as ET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

ET.register_namespace("p", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)


def parse_slide_shapes(slide_xml: str | bytes) -> list[dict[str, Any]]:
    root = _root(slide_xml)
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return []

    shapes: list[dict[str, Any]] = []
    for z_order, (child, transform, in_group) in enumerate(_iter_shape_refs(sp_tree)):
        tag = _local_name(child.tag)
        c_nv_pr = _owner_c_nv_pr(child)
        shape_id = c_nv_pr.attrib.get("id", str(z_order + 1)) if c_nv_pr is not None else str(z_order + 1)
        name = c_nv_pr.attrib.get("name", tag) if c_nv_pr is not None else tag
        bbox = _transform_box(_bbox(child), transform)
        shapes.append(
            {
                "id": shape_id,
                "name": name,
                "type": tag,
                "text": _text(child),
                "bbox": bbox,
                "z_order": z_order,
                "in_group": in_group,
            }
        )
    return shapes


def apply_shape_operations(slide_xml: str | bytes, operations: list[dict[str, Any]]) -> str:
    root = _root(slide_xml)
    used_ids = {shape["id"] for shape in parse_slide_shapes(slide_xml)}
    for operation in operations:
        op = operation.get("op")
        shape_id = str(operation.get("id") or "")
        if op == "move_resize":
            shape_ref = _shape_ref_by_id(root, shape_id)
            if shape_ref is None:
                continue
            shape, transform = shape_ref
            _apply_box(shape, _inverse_transform_box(operation.get("to") or {}, transform))
        elif op == "move":
            shape_ref = _shape_ref_by_id(root, shape_id)
            if shape_ref is None:
                continue
            shape, transform = shape_ref
            _apply_position(shape, _inverse_transform_box(operation.get("to") or {}, transform))
        elif op == "resize":
            shape_ref = _shape_ref_by_id(root, shape_id)
            if shape_ref is None:
                continue
            shape, transform = shape_ref
            _apply_size(shape, _inverse_transform_box(operation.get("to") or {}, transform))
        elif op == "clone":
            _clone_shape(root, shape_id, operation, used_ids)
    return ET.tostring(root, encoding="unicode")


def apply_text_box_repairs(slide_xml: str | bytes, repairs: list[dict[str, Any]]) -> str:
    root = _root(slide_xml)
    for repair in repairs:
        shape_id = str(repair.get("id") or "")
        shape_ref = _shape_ref_by_id(root, shape_id)
        if shape_ref is None:
            continue
        shape, transform = shape_ref
        if _local_name(shape.tag) != "sp":
            continue
        body_pr = shape.find(f"{{{P_NS}}}txBody/{{{A_NS}}}bodyPr")
        if body_pr is not None and repair.get("wrap") == "none":
            body_pr.set("wrap", "none")
        target = repair.get("to") or {}
        if "w" in target:
            _apply_size(shape, _inverse_transform_box(target, transform))
    return ET.tostring(root, encoding="unicode")


def _root(slide_xml: str | bytes) -> ET.Element:
    data = slide_xml.encode("utf-8") if isinstance(slide_xml, str) else slide_xml
    return ET.fromstring(data)


def _shape_by_id(root: ET.Element, shape_id: str) -> ET.Element | None:
    shape_ref = _shape_ref_by_id(root, shape_id)
    return shape_ref[0] if shape_ref else None


def _shape_ref_by_id(root: ET.Element, shape_id: str) -> tuple[ET.Element, tuple[float, float, float, float]] | None:
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return None
    for child, transform, _in_group in _iter_shape_refs(sp_tree):
        c_nv_pr = _owner_c_nv_pr(child)
        if c_nv_pr is not None and c_nv_pr.attrib.get("id") == shape_id:
            return child, transform
    return None


def _clone_shape(root: ET.Element, shape_id: str, operation: dict[str, Any], used_ids: set[str]) -> None:
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    source = _shape_by_id(root, shape_id)
    if sp_tree is None or source is None:
        return
    clone = deepcopy(source)
    new_id = str(operation.get("new_id") or _next_shape_id(used_ids))
    used_ids.add(new_id)
    c_nv_pr = clone.find(f".//{{{P_NS}}}cNvPr")
    if c_nv_pr is not None:
        c_nv_pr.set("id", new_id)
        c_nv_pr.set("name", str(operation.get("new_name") or f"Guide Reflow Clone {new_id}"))
    _apply_box(clone, operation.get("to") or {})
    sp_tree.append(clone)


def _next_shape_id(used_ids: set[str]) -> int:
    numeric = [int(value) for value in used_ids if str(value).isdigit()]
    return max(numeric, default=1) + 1


def _apply_box(shape: ET.Element, box: dict[str, Any]) -> None:
    _apply_position(shape, box)
    _apply_size(shape, box)


def _apply_position(shape: ET.Element, box: dict[str, Any]) -> None:
    for xfrm in _target_xfrms(shape):
        off = _ensure_child(xfrm, A_NS, "off")
        if "x" in box:
            off.set("x", str(int(box["x"])))
        if "y" in box:
            off.set("y", str(int(box["y"])))


def _apply_size(shape: ET.Element, box: dict[str, Any]) -> None:
    for xfrm in _target_xfrms(shape):
        ext = _ensure_child(xfrm, A_NS, "ext")
        if "w" in box:
            ext.set("cx", str(max(1, int(box["w"]))))
        if "h" in box:
            ext.set("cy", str(max(1, int(box["h"]))))


def _target_xfrms(shape: ET.Element) -> list[ET.Element]:
    primary = _ensure_xfrm(shape)
    if _local_name(shape.tag) != "graphicFrame":
        return [primary]
    xfrms = [primary]
    for nested in shape.findall(f".//{{{A_NS}}}xfrm"):
        if nested is not primary:
            xfrms.append(nested)
    return xfrms


def _ensure_xfrm(shape: ET.Element) -> ET.Element:
    if _local_name(shape.tag) == "graphicFrame":
        xfrm = shape.find(f"{{{P_NS}}}xfrm")
        if xfrm is None:
            xfrm = ET.Element(f"{{{P_NS}}}xfrm")
            shape.insert(1 if len(shape) else 0, xfrm)
        return xfrm
    sp_pr = shape.find(f"{{{P_NS}}}spPr")
    if sp_pr is None:
        sp_pr = ET.SubElement(shape, f"{{{P_NS}}}spPr")
    xfrm = sp_pr.find(f"{{{A_NS}}}xfrm")
    if xfrm is None:
        xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    return xfrm


def _ensure_child(parent: ET.Element, namespace: str, local_name: str) -> ET.Element:
    child = parent.find(f"{{{namespace}}}{local_name}")
    if child is None:
        child = ET.SubElement(parent, f"{{{namespace}}}{local_name}")
    return child


def _bbox(shape: ET.Element) -> dict[str, int] | None:
    xfrm = shape.find(f"{{{P_NS}}}xfrm") if _local_name(shape.tag) == "graphicFrame" else None
    if xfrm is None:
        xfrm = shape.find(f".//{{{A_NS}}}xfrm")
    if xfrm is None:
        xfrm = shape.find(f".//{{{P_NS}}}xfrm")
    if xfrm is None:
        return None
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    if off is None or ext is None:
        return None
    try:
        return {
            "x": int(off.attrib.get("x", "0")),
            "y": int(off.attrib.get("y", "0")),
            "w": int(ext.attrib.get("cx", "0")),
            "h": int(ext.attrib.get("cy", "0")),
        }
    except ValueError:
        return None


def _iter_shape_refs(
    parent: ET.Element,
    transform: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0),
    in_group: bool = False,
):
    for child in list(parent):
        tag = _local_name(child.tag)
        if tag == "grpSp":
            group_transform = _compose_transform(transform, _group_transform(child))
            yield from _iter_shape_refs(child, group_transform, True)
            continue
        if tag in {"sp", "pic", "graphicFrame"}:
            yield child, transform, in_group


def _owner_c_nv_pr(shape: ET.Element) -> ET.Element | None:
    tag = _local_name(shape.tag)
    if tag == "sp":
        return shape.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    if tag == "pic":
        return shape.find(f"{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr")
    if tag == "graphicFrame":
        return shape.find(f"{{{P_NS}}}nvGraphicFramePr/{{{P_NS}}}cNvPr")
    return None


def _group_transform(group: ET.Element) -> tuple[float, float, float, float]:
    xfrm = group.find(f"{{{P_NS}}}grpSpPr/{{{A_NS}}}xfrm")
    if xfrm is None:
        return (1.0, 1.0, 0.0, 0.0)
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    ch_off = xfrm.find(f"{{{A_NS}}}chOff")
    ch_ext = xfrm.find(f"{{{A_NS}}}chExt")
    if off is None or ext is None or ch_off is None or ch_ext is None:
        return (1.0, 1.0, 0.0, 0.0)
    try:
        sx = int(ext.attrib.get("cx", "0")) / max(int(ch_ext.attrib.get("cx", "0")), 1)
        sy = int(ext.attrib.get("cy", "0")) / max(int(ch_ext.attrib.get("cy", "0")), 1)
        dx = int(off.attrib.get("x", "0")) - int(ch_off.attrib.get("x", "0")) * sx
        dy = int(off.attrib.get("y", "0")) - int(ch_off.attrib.get("y", "0")) * sy
        return (sx, sy, dx, dy)
    except ValueError:
        return (1.0, 1.0, 0.0, 0.0)


def _compose_transform(
    parent: tuple[float, float, float, float],
    child: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    psx, psy, pdx, pdy = parent
    csx, csy, cdx, cdy = child
    return (
        psx * csx,
        psy * csy,
        pdx + psx * cdx,
        pdy + psy * cdy,
    )


def _transform_box(
    box: dict[str, int] | None,
    transform: tuple[float, float, float, float],
) -> dict[str, int] | None:
    if box is None:
        return None
    sx, sy, dx, dy = transform
    return {
        "x": int(round(box["x"] * sx + dx)),
        "y": int(round(box["y"] * sy + dy)),
        "w": int(round(box["w"] * sx)),
        "h": int(round(box["h"] * sy)),
    }


def _inverse_transform_box(
    box: dict[str, Any],
    transform: tuple[float, float, float, float],
) -> dict[str, int]:
    sx, sy, dx, dy = transform
    sx = sx or 1.0
    sy = sy or 1.0
    result: dict[str, int] = {}
    if "x" in box:
        result["x"] = int(round((int(box["x"]) - dx) / sx))
    if "y" in box:
        result["y"] = int(round((int(box["y"]) - dy) / sy))
    if "w" in box:
        result["w"] = max(1, int(round(int(box["w"]) / sx)))
    if "h" in box:
        result["h"] = max(1, int(round(int(box["h"]) / sy)))
    return result


def _text(shape: ET.Element) -> str:
    parts = [node.text or "" for node in shape.findall(f".//{{{A_NS}}}t")]
    return " ".join(part.strip() for part in parts if part.strip())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def label_shape_xml(shape_id: int, name: str, x: int, y: int, text: str) -> str:
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="300000" cy="230000"/></a:xfrm><a:prstGeom prst="ellipse"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="237A57"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr>
  <p:txBody><a:bodyPr anchor="ctr" lIns="20000" tIns="10000" rIns="20000" bIns="10000"/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="zh-CN" sz="1150"><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>{escape(text)}</a:t></a:r></a:p></p:txBody>
</p:sp>'''
