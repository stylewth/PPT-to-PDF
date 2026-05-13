from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NOTES_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
DEFAULT_SLIDE_WIDTH = 12192000
DEFAULT_SLIDE_HEIGHT = 6858000


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
    objects = _parse_objects(root)
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


def _parse_objects(root: ET.Element) -> list[dict[str, Any]]:
    sp_tree = root.find(f".//{{{P_NS}}}spTree")
    if sp_tree is None:
        return []

    objects: list[dict[str, Any]] = []
    z_order = 0
    for child in list(sp_tree):
        tag = _local_name(child.tag)
        if tag not in {"sp", "pic", "graphicFrame"}:
            continue
        c_nv_pr = child.find(f".//{{{P_NS}}}cNvPr")
        object_id = c_nv_pr.attrib.get("id", str(z_order + 1)) if c_nv_pr is not None else str(z_order + 1)
        name = c_nv_pr.attrib.get("name", tag) if c_nv_pr is not None else tag
        text = _collect_text(child)
        bbox = _parse_bbox(child)
        objects.append(
            {
                "id": object_id,
                "name": name,
                "type": tag,
                "text": text,
                "bbox": bbox,
                "z_order": z_order,
            }
        )
        z_order += 1
    return objects


def _collect_text(element: ET.Element) -> str:
    parts = [node.text or "" for node in element.findall(f".//{{{A_NS}}}t")]
    return " ".join(part.strip() for part in parts if part.strip())


def _parse_bbox(element: ET.Element) -> dict[str, int] | None:
    xfrm = element.find(f".//{{{A_NS}}}xfrm")
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
                    "supported": kind in {"appear", "fade", "wipe"},
                }
            )
    return animations


def _classify_animation(element: ET.Element) -> str:
    attrs = " ".join(str(value).lower() for value in element.attrib.values())
    tag = _local_name(element.tag)
    if "fade" in attrs:
        return "fade"
    if "wipe" in attrs:
        return "wipe"
    if tag == "set" or "entr" in attrs or "appear" in attrs:
        return "appear"
    return tag


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
