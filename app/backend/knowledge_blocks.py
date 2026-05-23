from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


FRAGMENT_TYPES = {"shape", "cxnSp", "connector", "line", "freeform"}
VISUAL_TYPES = FRAGMENT_TYPES | {"pic", "graphicFrame", "grpSp"}
DYNAMIC_MEDIA_TYPES = {"gif", "video", "audio"}
PROMPT_VERSION = "v4a"


def build_knowledge_blocks(
    presentation: dict[str, Any],
    analysis: dict[str, Any],
    augment_plan: dict[str, Any] | None = None,
    media_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del augment_plan
    page = analysis.get("page") or presentation.get("page") or {}
    media_by_slide = _media_items_by_slide(media_manifest or {}, presentation)
    slides = []
    for slide in analysis.get("slides", []):
        slide_number = int(slide.get("number") or 0)
        objects = [dict(obj) for obj in slide.get("object_boxes", []) if obj.get("bbox")]
        object_by_id = {str(obj.get("id") or ""): obj for obj in objects}
        title = str(slide.get("title") or "").strip()
        used: set[str] = set()
        blocks: list[dict[str, Any]] = []

        _add_animation_blocks(blocks, slide, object_by_id, used, page)
        _add_media_blocks(blocks, slide_number, media_by_slide.get(slide_number, []), object_by_id, used, page)
        _add_formula_blocks(blocks, slide_number, objects, used, page, title)
        _add_fragment_diagram_block(blocks, slide_number, objects, used, page, title)
        _add_text_blocks(blocks, slide_number, objects, used, page, title)

        slides.append(
            {
                "number": slide_number,
                "title": title,
                "blocks": _assign_block_ids(slide_number, blocks),
            }
        )

    return {
        "kind": "knowledge_blocks",
        "version": PROMPT_VERSION,
        "source": analysis.get("source")
        or {
            "name": presentation.get("source_name", ""),
            "slide_count": presentation.get("slide_count", len(slides)),
        },
        "page": page,
        "slides": slides,
        "summary": {
            "slide_count": len(slides),
            "block_count": sum(len(slide["blocks"]) for slide in slides),
        },
    }


def write_knowledge_blocks(path: str | Path, blocks: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _add_animation_blocks(
    blocks: list[dict[str, Any]],
    slide: dict[str, Any],
    object_by_id: dict[str, dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
) -> None:
    slide_number = int(slide.get("number") or 0)
    for step in slide.get("animation_steps", []):
        covered_ids = [str(item) for item in step.get("covered_object_ids", []) if str(item)]
        if not covered_ids and not step.get("covers_prior_object"):
            continue
        target_id = str(step.get("target_id") or "")
        ids = [item for item in [*covered_ids, target_id] if item and item in object_by_id]
        if not ids:
            continue
        objs = [object_by_id[item] for item in ids]
        used.update(ids)
        blocks.append(
            _make_block(
                "animation_flow",
                slide_number,
                objs,
                page,
                title=_first_text(objs) or "动画遮挡关系",
                summary="动画步骤会覆盖前序对象，适合按前后关系解释。",
                animation_steps=[int(step.get("order") or 0)],
                extra_refs=[{"kind": "animation", "slide": slide_number, "object_id": target_id}],
            )
        )


def _add_media_blocks(
    blocks: list[dict[str, Any]],
    slide_number: int,
    media_items: list[dict[str, Any]],
    object_by_id: dict[str, dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
) -> None:
    for item in media_items:
        object_id = str(item.get("object_id") or "")
        if not object_id:
            continue
        obj = object_by_id.get(object_id) or {
            "id": object_id,
            "type": "pic",
            "name": item.get("object_name", ""),
            "text": "",
            "bbox": item.get("bbox") or {},
        }
        used.add(object_id)
        kind = str(item.get("kind") or "media")
        blocks.append(
            _make_block(
                "media_timeline",
                slide_number,
                [obj],
                page,
                title=f"{kind.upper()} 关键帧",
                summary="动态媒体已抽成可解释的关键帧序列。",
                media={key: item.get(key) for key in ("kind", "status", "preview", "export_path") if key in item},
                extra_refs=[{"kind": "media", "slide": slide_number, "object_id": object_id}],
            )
        )


def _add_formula_blocks(
    blocks: list[dict[str, Any]],
    slide_number: int,
    objects: list[dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
    title: str,
) -> None:
    for obj in objects:
        object_id = str(obj.get("id") or "")
        if not object_id or object_id in used or _is_title(obj, title):
            continue
        if not _is_formula_object(obj):
            continue
        neighbor = _nearest_text_object(obj, objects, used | {object_id}, title)
        grouped = [obj]
        if neighbor:
            grouped.append(neighbor)
        used.update(str(item.get("id") or "") for item in grouped)
        blocks.append(
            _make_block(
                "formula_group",
                slide_number,
                grouped,
                page,
                title=_first_text(grouped) or "公式知识点",
                summary="公式与邻近说明文字组成一个可解释知识点。",
            )
        )


def _add_fragment_diagram_block(
    blocks: list[dict[str, Any]],
    slide_number: int,
    objects: list[dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
    title: str,
) -> None:
    page_area = max(float(page.get("width") or 1) * float(page.get("height") or 1), 1.0)
    fragments = []
    for obj in objects:
        object_id = str(obj.get("id") or "")
        if not object_id or object_id in used or _is_title(obj, title):
            continue
        text = str(obj.get("text") or "").strip()
        if text and len(text) > 12:
            continue
        if str(obj.get("type") or "") not in VISUAL_TYPES:
            continue
        if _area(obj.get("bbox") or {}) / page_area > 0.06:
            continue
        fragments.append(obj)
    long_text_anchors = [
        obj
        for obj in objects
        if str(obj.get("id") or "") not in used
        and not _is_title(obj, title)
        and len(str(obj.get("text") or "").strip()) >= 18
    ]
    if len(fragments) < 6 or len(long_text_anchors) > 1:
        return
    used.update(str(obj.get("id") or "") for obj in fragments)
    blocks.append(
        _make_block(
            "diagram_group",
            slide_number,
            fragments,
            page,
            title=title or "图示结构",
            summary="多个小图元共同构成一个语义图，避免拆成碎片解释。",
        )
    )


def _add_text_blocks(
    blocks: list[dict[str, Any]],
    slide_number: int,
    objects: list[dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
    title: str,
) -> None:
    for obj in objects:
        object_id = str(obj.get("id") or "")
        text = str(obj.get("text") or "").strip()
        if not object_id or object_id in used or not text or _is_title(obj, title):
            continue
        used.add(object_id)
        blocks.append(
            _make_block(
                "text_concept",
                slide_number,
                [obj],
                page,
                title=_short_title(text),
                summary=text,
            )
        )


def _make_block(
    block_type: str,
    slide_number: int,
    objects: list[dict[str, Any]],
    page: dict[str, Any],
    *,
    title: str,
    summary: str,
    animation_steps: list[int] | None = None,
    media: dict[str, Any] | None = None,
    extra_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    texts = [str(obj.get("text") or "").strip() for obj in objects if str(obj.get("text") or "").strip()]
    object_ids = [str(obj.get("id") or "") for obj in objects if str(obj.get("id") or "")]
    bbox = _union_bbox([obj.get("bbox") or {} for obj in objects])
    source_refs = _unique_refs(
        [
            {"kind": "slide_text", "slide": slide_number, "object_id": str(obj.get("id") or "")}
            for obj in objects
            if str(obj.get("text") or "").strip()
        ]
        + (extra_refs or [])
    )
    block = {
        "type": block_type,
        "title": _short_title(title),
        "summary": summary,
        "source_bbox": bbox,
        "display_bbox": _display_bbox(bbox, page),
        "object_ids": object_ids,
        "texts": texts,
        "animation_steps": animation_steps or [],
        "source_refs": source_refs,
        "token_estimate": _estimate_tokens([title, summary, *texts]),
    }
    if media:
        block["media"] = media
    return block


def _assign_block_ids(slide_number: int, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"id": f"s{slide_number}_b{index}", **block}
        for index, block in enumerate(blocks, start=1)
    ]


def _media_items_by_slide(media_manifest: dict[str, Any], presentation: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    items: dict[int, list[dict[str, Any]]] = {}
    for item in media_manifest.get("items", []) or []:
        if str(item.get("kind") or "") not in DYNAMIC_MEDIA_TYPES:
            continue
        slide_number = int(item.get("slide_number") or 0)
        if slide_number:
            items.setdefault(slide_number, []).append(item)
    for slide in presentation.get("slides", []):
        slide_number = int(slide.get("number") or 0)
        for obj in slide.get("objects", []):
            media = obj.get("media") or {}
            kind = media.get("kind")
            if kind not in DYNAMIC_MEDIA_TYPES:
                continue
            object_id = str(obj.get("id") or "")
            existing = {str(item.get("object_id") or "") for item in items.get(slide_number, [])}
            if object_id not in existing:
                items.setdefault(slide_number, []).append(
                    {
                        "slide_number": slide_number,
                        "object_id": object_id,
                        "object_name": obj.get("name", ""),
                        "kind": kind,
                        "bbox": obj.get("bbox"),
                        "status": "detected",
                    }
                )
    return items


def _nearest_text_object(
    anchor: dict[str, Any],
    objects: list[dict[str, Any]],
    used: set[str],
    title: str,
) -> dict[str, Any] | None:
    candidates = [
        obj
        for obj in objects
        if str(obj.get("id") or "") not in used
        and str(obj.get("text") or "").strip()
        and not _is_title(obj, title)
        and not _is_formula_object(obj)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda obj: _center_distance(anchor.get("bbox") or {}, obj.get("bbox") or {}))


def _is_formula_object(obj: dict[str, Any]) -> bool:
    text = str(obj.get("text") or "")
    name = str(obj.get("name") or "").lower()
    obj_type = str(obj.get("type") or "")
    if obj_type == "graphicFrame":
        return True
    if "formula" in name or "公式" in name:
        return True
    return any(token in text for token in ("=", "<", ">", "≤", "≥", "∑", "√", "Δ", "π", "/", "^"))


def _is_title(obj: dict[str, Any], title: str) -> bool:
    text = str(obj.get("text") or "").strip()
    if not text or not title:
        return False
    if text != title.strip():
        return False
    bbox = obj.get("bbox") or {}
    return int(bbox.get("y") or 0) <= 1200000


def _first_text(objects: list[dict[str, Any]]) -> str:
    for obj in objects:
        text = str(obj.get("text") or "").strip()
        if text:
            return text
    return ""


def _short_title(text: str, limit: int = 24) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."


def _estimate_tokens(parts: list[str]) -> int:
    chars = sum(len(str(part or "")) for part in parts)
    return max(1, math.ceil(chars / 2))


def _union_bbox(boxes: list[dict[str, Any]]) -> dict[str, int]:
    valid = [box for box in boxes if all(key in box for key in ("x", "y", "w", "h"))]
    if not valid:
        return {"x": 0, "y": 0, "w": 0, "h": 0}
    left = min(int(box["x"]) for box in valid)
    top = min(int(box["y"]) for box in valid)
    right = max(int(box["x"]) + int(box["w"]) for box in valid)
    bottom = max(int(box["y"]) + int(box["h"]) for box in valid)
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _display_bbox(bbox: dict[str, int], page: dict[str, Any]) -> dict[str, float]:
    width = max(float(page.get("width") or 1), 1.0)
    height = max(float(page.get("height") or 1), 1.0)
    return {
        "x": round(float(bbox.get("x") or 0) / width, 6),
        "y": round(float(bbox.get("y") or 0) / height, 6),
        "w": round(float(bbox.get("w") or 0) / width, 6),
        "h": round(float(bbox.get("h") or 0) / height, 6),
    }


def _area(box: dict[str, Any]) -> float:
    return max(float(box.get("w") or 0), 0.0) * max(float(box.get("h") or 0), 0.0)


def _center_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_x = float(first.get("x") or 0) + float(first.get("w") or 0) / 2
    first_y = float(first.get("y") or 0) + float(first.get("h") or 0) / 2
    second_x = float(second.get("x") or 0) + float(second.get("w") or 0) / 2
    second_y = float(second.get("y") or 0) + float(second.get("h") or 0) / 2
    return (first_x - second_x) ** 2 + (first_y - second_y) ** 2


def _unique_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique = []
    for ref in refs:
        key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique
