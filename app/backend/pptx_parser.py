from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NOTES_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
DEFAULT_SLIDE_WIDTH = 12192000
DEFAULT_SLIDE_HEIGHT = 6858000
SUPPORTED_ANIMATION_KINDS = {
    "appear",
    "fade",
    "wipe",
    "blinds",
    "wheel_in",
    "wheel_out",
    "motion",
    "motion_x",
    "motion_y",
}


class PptxParseError(ValueError):
    pass


def parse_pptx(path: str | Path) -> dict[str, Any]:
    pptx_path = Path(path)
    if pptx_path.suffix.lower() != ".pptx":
        raise PptxParseError("Only .pptx files are supported in V2.")

    try:
        with zipfile.ZipFile(pptx_path) as package:
            names = set(package.namelist())
            _validate_package(names)
            presentation_root = _xml(package.read("ppt/presentation.xml"))
            page = _parse_page_size(presentation_root)
            slide_paths = _slide_paths(names)
            slides = [
                _parse_slide(package, slide_path, index + 1)
                for index, slide_path in enumerate(slide_paths)
            ]
    except zipfile.BadZipFile as exc:
        raise PptxParseError("The uploaded file is not a valid PPTX package.") from exc

    return {
        "source_name": pptx_path.name,
        "slide_count": len(slides),
        "page": page,
        "slides": slides,
    }


def _validate_package(names: set[str]) -> None:
    if "[Content_Types].xml" not in names or "ppt/presentation.xml" not in names:
        raise PptxParseError("Missing required PPTX package entries.")
    if not any(name.startswith("ppt/slides/slide") and name.endswith(".xml") for name in names):
        raise PptxParseError("No slide XML files found.")


def _slide_paths(names: set[str]) -> list[str]:
    paths = [
        name
        for name in names
        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
    ]
    return sorted(paths, key=lambda value: int(re.search(r"slide(\d+)\.xml", value).group(1)))


def _parse_slide(package: zipfile.ZipFile, slide_path: str, slide_number: int) -> dict[str, Any]:
    root = _xml(package.read(slide_path))
    relationships = _slide_relationships(package, slide_path)
    objects = _parse_objects(root, relationships)
    animations = _parse_animations(root, objects)
    notes = _parse_notes(package, slide_path)
    title = next((obj["text"] for obj in objects if obj["text"]), f"Slide {slide_number}")

    return {
        "number": slide_number,
        "path": slide_path,
        "title": title,
        "objects": objects,
        "animations": animations,
        "notes": notes,
    }


def _xml(data: bytes) -> ET.Element:
    return ET.fromstring(data)


def _parse_page_size(root: ET.Element) -> dict[str, int]:
    size = root.find(f".//{{{P_NS}}}sldSz")
    if size is None:
        return {"width": DEFAULT_SLIDE_WIDTH, "height": DEFAULT_SLIDE_HEIGHT}
    try:
        return {
            "width": int(size.attrib.get("cx", str(DEFAULT_SLIDE_WIDTH))),
            "height": int(size.attrib.get("cy", str(DEFAULT_SLIDE_HEIGHT))),
        }
    except ValueError:
        return {"width": DEFAULT_SLIDE_WIDTH, "height": DEFAULT_SLIDE_HEIGHT}


def _parse_objects(root: ET.Element, relationships: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return []

    relationships = relationships or {}
    objects: list[dict[str, Any]] = []
    for z_order, (child, transform, in_group) in enumerate(_iter_object_refs(sp_tree)):
        tag = _local_name(child.tag)
        c_nv_pr = _owner_c_nv_pr(child)
        object_id = c_nv_pr.attrib.get("id", str(z_order + 1)) if c_nv_pr is not None else str(z_order + 1)
        name = c_nv_pr.attrib.get("name", tag) if c_nv_pr is not None else tag
        text = _collect_text(child)
        bbox = _transform_box(_parse_bbox(child), transform)
        item = {
            "id": object_id,
            "name": name,
            "type": tag,
            "text": text,
            "bbox": bbox,
            "z_order": z_order,
            "in_group": in_group,
        }
        media = _parse_object_media(child, relationships)
        if media:
            item["media"] = media
        objects.append(item)
    return objects


def _slide_relationships(package: zipfile.ZipFile, slide_path: str) -> dict[str, dict[str, str]]:
    rels_path = _rels_path(slide_path)
    try:
        rels_root = _xml(package.read(rels_path))
    except KeyError:
        return {}

    relationships: dict[str, dict[str, str]] = {}
    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        rel_id = rel.attrib.get("Id", "")
        target = rel.attrib.get("Target", "")
        if not rel_id or not target:
            continue
        relationships[rel_id] = {
            "id": rel_id,
            "type": rel.attrib.get("Type", ""),
            "target": target,
            "target_mode": rel.attrib.get("TargetMode", ""),
            "path": posixpath.normpath(posixpath.join(posixpath.dirname(slide_path), target)),
        }
    return relationships


def _parse_object_media(element: ET.Element, relationships: dict[str, dict[str, str]]) -> dict[str, str] | None:
    rel_id, relationship = _object_media_relationship(element, relationships)
    if not relationship:
        return None
    media_path = relationship.get("path", "")
    extension = Path(media_path).suffix.lower()
    if not extension:
        return None
    return {
        "rel_id": rel_id,
        "relationship_type": relationship.get("type", ""),
        "target": relationship.get("target", ""),
        "path": media_path,
        "extension": extension,
        "kind": _media_kind(extension, relationship.get("type", "")),
        "target_mode": relationship.get("target_mode", ""),
    }


def _object_media_relationship(
    element: ET.Element,
    relationships: dict[str, dict[str, str]],
) -> tuple[str, dict[str, str] | None]:
    for node in element.iter():
        if _local_name(node.tag) not in {"videoFile", "audioFile"}:
            continue
        rel_id = node.attrib.get(f"{{{R_NS}}}embed") or node.attrib.get(f"{{{R_NS}}}link")
        if rel_id and rel_id in relationships:
            return rel_id, relationships[rel_id]

    blip = element.find(f".//{{{A_NS}}}blip")
    if blip is None:
        return "", None
    rel_id = blip.attrib.get(f"{{{R_NS}}}embed") or blip.attrib.get(f"{{{R_NS}}}link")
    if not rel_id:
        return "", None
    return rel_id, relationships.get(rel_id)


def _media_kind(extension: str, relationship_type: str = "") -> str:
    if relationship_type.endswith("/video"):
        return "video"
    if relationship_type.endswith("/audio"):
        return "audio"
    if extension == ".gif":
        return "gif"
    if extension in {".mp4", ".mov", ".m4v", ".avi", ".wmv", ".webm", ".mpeg", ".mpg"}:
        return "video"
    if extension in {".mp3", ".wav", ".m4a", ".aac", ".wma", ".ogg"}:
        return "audio"
    return "image"


def _collect_text(element: ET.Element) -> str:
    parts = [node.text or "" for node in element.findall(f".//{{{A_NS}}}t")]
    return " ".join(part.strip() for part in parts if part.strip())


def _parse_bbox(element: ET.Element) -> dict[str, int] | None:
    xfrm = element.find(f"{{{P_NS}}}xfrm") if _local_name(element.tag) == "graphicFrame" else None
    if xfrm is None:
        xfrm = element.find(f".//{{{A_NS}}}xfrm")
    if xfrm is None:
        xfrm = element.find(f".//{{{P_NS}}}xfrm")
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


def _iter_object_refs(
    parent: ET.Element,
    transform: tuple[float, float, float, float] = (1.0, 1.0, 0.0, 0.0),
    in_group: bool = False,
):
    for child in list(parent):
        tag = _local_name(child.tag)
        if tag == "grpSp":
            group_transform = _compose_transform(transform, _group_transform(child))
            yield from _iter_object_refs(child, group_transform, True)
            continue
        if tag in {"sp", "pic", "graphicFrame"}:
            yield child, transform, in_group


def _owner_c_nv_pr(element: ET.Element) -> ET.Element | None:
    tag = _local_name(element.tag)
    if tag == "sp":
        return element.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
    if tag == "pic":
        return element.find(f"{{{P_NS}}}nvPicPr/{{{P_NS}}}cNvPr")
    if tag == "graphicFrame":
        return element.find(f"{{{P_NS}}}nvGraphicFramePr/{{{P_NS}}}cNvPr")
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


def _parse_animations(root: ET.Element, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    object_by_id = {obj["id"]: obj for obj in objects}
    animations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for element in root.iter():
        if _local_name(element.tag) not in {
            "animEffect",
            "anim",
            "animMotion",
            "animScale",
            "animRot",
            "set",
        }:
            continue
        for target in element.findall(f".//{{{P_NS}}}spTgt"):
            target_id = target.attrib.get("spid")
            if not target_id:
                continue
            kind = _classify_animation(element)
            if not kind:
                continue
            key = (target_id, kind)
            if key in seen:
                continue
            seen.add(key)
            target_object = object_by_id.get(target_id, {})
            animations.append(
                {
                    "order": len(animations) + 1,
                    "target_id": target_id,
                    "target_name": target_object.get("name", ""),
                    "target_text": target_object.get("text", ""),
                    "kind": kind,
                    "raw_tag": _local_name(element.tag),
                    "raw_attrs": dict(element.attrib),
                    "supported": kind in SUPPORTED_ANIMATION_KINDS,
                }
            )
    return animations


def _classify_animation(element: ET.Element) -> str | None:
    attrs_by_name = {
        str(key).lower(): str(value).lower()
        for key, value in element.attrib.items()
    }
    attrs = " ".join(attrs_by_name.values())
    effect_filter = attrs_by_name.get("filter", "")
    transition = attrs_by_name.get("transition", "")
    tag = _local_name(element.tag)
    if tag == "anim":
        return _classify_numeric_animation(element)
    if "fade" in attrs:
        return "fade"
    if "wipe" in attrs:
        return "wipe"
    if "blinds" in effect_filter:
        return "blinds"
    if "wheel" in effect_filter:
        if transition == "out":
            return "wheel_out"
        return "wheel_in"
    if tag == "set" or "entr" in attrs or "appear" in attrs:
        return "appear"
    return tag


def _classify_numeric_animation(element: ET.Element) -> str | None:
    attr_names = [
        (node.text or "").strip()
        for node in element.findall(f".//{{{P_NS}}}attrName")
        if (node.text or "").strip()
    ]
    attrs = set(attr_names)
    if not attrs or not attrs.issubset({"ppt_x", "ppt_y"}):
        return "anim"

    values = [
        _normalize_animation_value(node.attrib.get("val", ""))
        for node in element.findall(f".//{{{P_NS}}}strVal")
    ]
    values = [value for value in values if value]
    if len(set(values)) <= 1:
        return None

    if attrs == {"ppt_x"}:
        return "motion_x"
    if attrs == {"ppt_y"}:
        return "motion_y"
    return "motion"


def _normalize_animation_value(value: str) -> str:
    return str(value).strip().lower().lstrip("#").replace(" ", "")


def _parse_notes(package: zipfile.ZipFile, slide_path: str) -> str:
    notes_path = _notes_path(package, slide_path)
    if not notes_path:
        return ""
    try:
        root = _xml(package.read(notes_path))
    except KeyError:
        return ""
    return _collect_text(root)


def _notes_path(package: zipfile.ZipFile, slide_path: str) -> str | None:
    rels_path = _rels_path(slide_path)
    try:
        rels_root = _xml(package.read(rels_path))
    except KeyError:
        return None

    for rel in rels_root.findall(f"{{{REL_NS}}}Relationship"):
        if rel.attrib.get("Type") == NOTES_REL_TYPE:
            target = rel.attrib.get("Target", "")
            return posixpath.normpath(posixpath.join(posixpath.dirname(slide_path), target))
    return None


def _rels_path(slide_path: str) -> str:
    directory, file_name = posixpath.split(slide_path)
    return posixpath.join(directory, "_rels", f"{file_name}.rels")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag
