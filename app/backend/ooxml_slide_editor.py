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
    z_order = 0
    for child in list(sp_tree):
        tag = _local_name(child.tag)
        if tag not in {"sp", "pic", "graphicFrame"}:
            continue
        c_nv_pr = child.find(f".//{{{P_NS}}}cNvPr")
        shape_id = c_nv_pr.attrib.get("id", str(z_order + 1)) if c_nv_pr is not None else str(z_order + 1)
        name = c_nv_pr.attrib.get("name", tag) if c_nv_pr is not None else tag
        bbox = _bbox(child)
        shapes.append(
            {
                "id": shape_id,
                "name": name,
                "type": tag,
                "text": _text(child),
                "bbox": bbox,
                "z_order": z_order,
            }
        )
        z_order += 1
    return shapes


def apply_shape_operations(slide_xml: str | bytes, operations: list[dict[str, Any]]) -> str:
    root = _root(slide_xml)
    used_ids = {shape["id"] for shape in parse_slide_shapes(slide_xml)}
    for operation in operations:
        op = operation.get("op")
        shape_id = str(operation.get("id") or "")
        if op == "move_resize":
            shape = _shape_by_id(root, shape_id)
            if shape is None:
                continue
            _apply_box(shape, operation.get("to") or {})
        elif op == "move":
            shape = _shape_by_id(root, shape_id)
            if shape is None:
                continue
            _apply_position(shape, operation.get("to") or {})
        elif op == "resize":
            shape = _shape_by_id(root, shape_id)
            if shape is None:
                continue
            _apply_size(shape, operation.get("to") or {})
        elif op == "clone":
            _clone_shape(root, shape_id, operation, used_ids)
    return ET.tostring(root, encoding="unicode")


def _root(slide_xml: str | bytes) -> ET.Element:
    data = slide_xml.encode("utf-8") if isinstance(slide_xml, str) else slide_xml
    return ET.fromstring(data)


def _shape_by_id(root: ET.Element, shape_id: str) -> ET.Element | None:
    for child in root.findall(f".//{{{P_NS}}}spTree/*"):
        c_nv_pr = child.find(f".//{{{P_NS}}}cNvPr")
        if c_nv_pr is not None and c_nv_pr.attrib.get("id") == shape_id:
            return child
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
