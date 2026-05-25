from __future__ import annotations

import json
import math
import hashlib
import re
from pathlib import Path
from typing import Any


FRAGMENT_TYPES = {"shape", "cxnSp", "connector", "line", "freeform"}
VISUAL_TYPES = FRAGMENT_TYPES | {"pic", "graphicFrame", "grpSp"}
DYNAMIC_MEDIA_TYPES = {"gif", "video", "audio"}
PROMPT_VERSION = "v5a"


def build_knowledge_blocks(
    presentation: dict[str, Any],
    analysis: dict[str, Any],
    augment_plan: dict[str, Any] | None = None,
    media_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page = analysis.get("page") or presentation.get("page") or {}
    media_by_slide = _media_items_by_slide(media_manifest or {}, presentation)
    reflow_targets_by_slide = _reflow_targets_by_slide(augment_plan or {})
    slides = []
    for slide in analysis.get("slides", []):
        slide_number = int(slide.get("number") or 0)
        objects = [
            _with_reflowed_bbox(obj, reflow_targets_by_slide.get(slide_number, {}))
            for obj in slide.get("object_boxes", [])
            if obj.get("bbox")
        ]
        object_by_id = {str(obj.get("id") or ""): obj for obj in objects}
        title = str(slide.get("title") or "").strip()
        used: set[str] = set()
        blocks: list[dict[str, Any]] = []

        _add_media_blocks(blocks, slide_number, media_by_slide.get(slide_number, []), object_by_id, used, page)
        _add_dense_diagram_block(blocks, slide_number, objects, used, page, title)
        _add_formula_blocks(blocks, slide_number, objects, used, page, title)
        _add_fragment_diagram_block(blocks, slide_number, objects, used, page, title)
        _add_text_blocks(blocks, slide_number, objects, used, page, title)
        _attach_title_to_first_block(blocks, slide_number, objects, used, page, title)
        _attach_animation_steps_to_blocks(blocks, slide, object_by_id, page)

        raw_blocks = blocks
        blocks = merge_animation_duplicates(blocks)
        if should_use_whole_page_fallback(raw_blocks):
            fallback_reason = "duplicate_animation_text"
            slide_blocks = [build_whole_page_block({"number": slide_number, "title": title, "blocks": raw_blocks}, fallback_reason)]
            mode = "whole_page"
        else:
            fallback_reason = ""
            slide_blocks = _assign_block_ids(slide_number, blocks)
            mode = "blocks"
        slides.append(
            {
                "number": slide_number,
                "title": title,
                "mode": mode,
                "fallback_reason": fallback_reason,
                "blocks": slide_blocks,
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


def _reflow_targets_by_slide(augment_plan: dict[str, Any]) -> dict[int, dict[str, dict[str, int]]]:
    result: dict[int, dict[str, dict[str, int]]] = {}
    for slide in augment_plan.get("slides", []) or []:
        slide_number = int(slide.get("source_slide") or slide.get("number") or 0)
        if not slide_number:
            continue
        operations = (slide.get("object_reflow") or {}).get("operations") or []
        for operation in operations:
            object_id = str(operation.get("id") or "")
            target = operation.get("to") or {}
            if not object_id or not all(key in target for key in ("x", "y", "w", "h")):
                continue
            result.setdefault(slide_number, {})[object_id] = {
                key: int(target[key])
                for key in ("x", "y", "w", "h")
            }
    return result


def _with_reflowed_bbox(obj: dict[str, Any], targets: dict[str, dict[str, int]]) -> dict[str, Any]:
    item = dict(obj)
    target = targets.get(str(item.get("id") or ""))
    if target:
        item["bbox"] = dict(target)
    return item


def merge_animation_duplicates(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for block in blocks:
        current = dict(block)
        current.setdefault("content_hash", _content_hash(current))
        key = _duplicate_key(current)
        existing = by_key.get(key)
        if not existing:
            by_key[key] = current
            merged.append(current)
            continue
        existing["texts"] = _dedupe_strings([*existing.get("texts", []), *current.get("texts", [])])
        existing["object_ids"] = _dedupe_strings([*existing.get("object_ids", []), *current.get("object_ids", [])])
        existing["source_refs"] = _unique_refs([*existing.get("source_refs", []), *current.get("source_refs", [])])
        existing["animation_refs"] = _unique_refs([*existing.get("animation_refs", []), *current.get("animation_refs", [])])
        existing["source_bbox"] = _union_bbox([existing.get("source_bbox", {}) or {}, current.get("source_bbox", {}) or {}])
        existing["display_bbox"] = _union_float_bbox(
            [existing.get("display_bbox", {}) or {}, current.get("display_bbox", {}) or {}]
        )
        existing["animation_steps"] = sorted(
            {
                int(step)
                for step in [*existing.get("animation_steps", []), *current.get("animation_steps", [])]
                if str(step).strip()
            }
        )
        existing["token_estimate"] = _estimate_tokens(
            [existing.get("title", ""), existing.get("summary", ""), *existing.get("texts", [])]
        )
        if existing.get("type") == "animation_flow" and existing.get("texts"):
            existing["type"] = "text_concept"
        existing["content_hash"] = _content_hash(existing)
    return merged


def should_use_whole_page_fallback(
    page_blocks: list[dict[str, Any]],
    duplicate_ratio: float | None = None,
    block_count: int | None = None,
) -> bool:
    count = block_count if block_count is not None else len(page_blocks)
    if count <= 0:
        return False
    if duplicate_ratio is None:
        hashes = [_duplicate_key(block) for block in page_blocks]
        duplicate_ratio = 1 - (len(set(hashes)) / max(len(hashes), 1))
    if duplicate_ratio >= 0.5 and count >= 5:
        return True
    animation_only = [
        block
        for block in page_blocks
        if block.get("type") == "animation_flow" and not any(str(text).strip() for text in block.get("texts", []))
    ]
    return len(animation_only) == count and count >= 3


def build_whole_page_block(page: dict[str, Any], fallback_reason: str) -> dict[str, Any]:
    slide_number = int(page.get("number") or 0)
    blocks = page.get("blocks", []) or []
    texts = _dedupe_strings(
        [
            str(text).strip()
            for block in blocks
            for text in block.get("texts", []) or []
            if str(text).strip()
        ]
    )
    source_refs = _unique_refs([ref for block in blocks for ref in block.get("source_refs", []) or []])
    if not source_refs and slide_number:
        source_refs = [{"kind": "slide", "slide": slide_number, "object_id": "page"}]
    animation_refs = _unique_refs([ref for block in blocks for ref in block.get("animation_refs", []) or []])
    block = {
        "id": f"s{slide_number}_page",
        "type": "whole_page",
        "title": f"第 {slide_number} 页整页解释" if slide_number else "整页解释",
        "summary": fallback_reason,
        "source_bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
        "display_bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
        "object_ids": _dedupe_strings([obj for block in blocks for obj in block.get("object_ids", []) or []]),
        "texts": texts,
        "animation_steps": sorted(
            {
                int(step)
                for block in blocks
                for step in block.get("animation_steps", []) or []
                if str(step).strip()
            }
        ),
        "source_refs": source_refs,
        "animation_refs": animation_refs,
        "token_estimate": _estimate_tokens([page.get("title", ""), *texts]),
    }
    block["content_hash"] = _content_hash(block)
    return block


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
                animation_refs=[
                    {
                        "kind": "animation",
                        "slide": slide_number,
                        "object_id": target_id,
                        "effect": step.get("effect") or step.get("action") or "",
                    }
                ],
            )
        )


def _attach_animation_steps_to_blocks(
    blocks: list[dict[str, Any]],
    slide: dict[str, Any],
    object_by_id: dict[str, dict[str, Any]],
    page: dict[str, Any],
) -> None:
    slide_number = int(slide.get("number") or 0)
    for step in slide.get("animation_steps", []):
        covered_ids = [str(item) for item in step.get("covered_object_ids", []) if str(item)]
        if not covered_ids and not step.get("covers_prior_object"):
            continue
        target_id = str(step.get("target_id") or "")
        ids = _dedupe_strings([*covered_ids, target_id])
        ids = [item for item in ids if item in object_by_id]
        if not ids:
            continue
        order = int(step.get("order") or 0)
        animation_ref = {
            "kind": "animation",
            "slide": slide_number,
            "object_id": target_id,
            "effect": step.get("effect") or step.get("action") or step.get("kind") or "",
        }
        source_ref = {"kind": "animation", "slide": slide_number, "object_id": target_id}
        related_blocks = [
            block
            for block in blocks
            if any(object_id in (block.get("object_ids") or []) for object_id in ids)
        ]
        if related_blocks:
            target = _animation_target_block(related_blocks, ids)
            for block in list(related_blocks):
                if block is target or block.get("type") == "media_timeline":
                    continue
                _merge_block_into_block(target, block, page)
                if block in blocks:
                    blocks.remove(block)
            for object_id in ids:
                if object_id not in (target.get("object_ids") or []):
                    _append_object_into_block(target, object_by_id[object_id], slide_number, page)
            _attach_animation_ref(target, order, source_ref, animation_ref)
            continue

        objs = [object_by_id[object_id] for object_id in ids]
        blocks.append(
            _make_block(
                "diagram_group",
                slide_number,
                objs,
                page,
                title=_first_text(objs) or "动画相关图示",
                summary="这些对象在动画中形成同一关系，按内容整体解释。",
                animation_steps=[order],
                extra_refs=[source_ref],
                animation_refs=[animation_ref],
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


def _add_dense_diagram_block(
    blocks: list[dict[str, Any]],
    slide_number: int,
    objects: list[dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
    title: str,
) -> None:
    available = [
        obj
        for obj in objects
        if str(obj.get("id") or "")
        and str(obj.get("id") or "") not in used
        and obj.get("bbox")
    ]
    if not available:
        return

    title_objs = [obj for obj in available if _is_title(obj, title)]
    content_objs = [obj for obj in available if obj not in title_objs]
    dense_parts = [obj for obj in content_objs if _is_dense_diagram_part(obj)]
    short_text_count = sum(1 for obj in dense_parts if _is_short_label(obj))
    visual_count = sum(1 for obj in dense_parts if str(obj.get("type") or "") in VISUAL_TYPES)
    formula_count = sum(1 for obj in dense_parts if _is_formula_object(obj))

    if len(dense_parts) < 8:
        return
    if formula_count < 2 and visual_count < 6:
        return
    if short_text_count + formula_count < 5:
        return

    grouped = [*title_objs, *content_objs]
    used.update(str(item.get("id") or "") for item in grouped)
    blocks.append(
        _make_block(
            "diagram_group",
            slide_number,
            grouped,
            page,
            title=_first_text(grouped) or title or "图示结构",
            summary="图示、公式和短标签共同构成一个知识点，按整体解释避免碎片化。",
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


def _attach_title_to_first_block(
    blocks: list[dict[str, Any]],
    slide_number: int,
    objects: list[dict[str, Any]],
    used: set[str],
    page: dict[str, Any],
    title: str,
) -> None:
    if not blocks:
        return
    title_objs = [
        obj
        for obj in objects
        if str(obj.get("id") or "")
        and str(obj.get("id") or "") not in used
        and _is_title(obj, title)
    ]
    if not title_objs:
        return
    candidates = [
        block
        for block in blocks
        if block.get("type") in {"text_concept", "formula_group", "diagram_group"}
        and any(str(text).strip() for text in block.get("texts", []) or [])
    ]
    if not candidates:
        return
    target = min(
        candidates,
        key=lambda block: (
            float((block.get("source_bbox") or {}).get("y") or 0),
            float((block.get("source_bbox") or {}).get("x") or 0),
        ),
    )
    for obj in title_objs:
        _merge_object_into_block(target, obj, slide_number, page)
        used.add(str(obj.get("id") or ""))


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
    animation_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    texts = [str(obj.get("text") or "").strip() for obj in objects if str(obj.get("text") or "").strip()]
    object_ids = [str(obj.get("id") or "") for obj in objects if str(obj.get("id") or "")]
    bbox = _union_bbox([obj.get("bbox") or {} for obj in objects])
    bbox = _expand_bbox_for_text_overflow(block_type, bbox, texts, page)
    source_refs = _unique_refs(
        [
            {"kind": "slide_text", "slide": slide_number, "object_id": str(obj.get("id") or "")}
            for obj in objects
            if str(obj.get("text") or "").strip()
        ]
        + [
            {"kind": "visual", "slide": slide_number, "object_id": str(obj.get("id") or "")}
            for obj in objects
            if not str(obj.get("text") or "").strip()
            and str(obj.get("id") or "")
            and str(obj.get("type") or "") in VISUAL_TYPES
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
        "animation_refs": animation_refs or [],
        "token_estimate": _estimate_tokens([title, summary, *texts]),
    }
    if media:
        block["media"] = media
    block["content_hash"] = _content_hash(block)
    return block


def _merge_object_into_block(block: dict[str, Any], obj: dict[str, Any], slide_number: int, page: dict[str, Any]) -> None:
    object_id = str(obj.get("id") or "")
    text = str(obj.get("text") or "").strip()
    block["object_ids"] = _dedupe_strings([object_id, *block.get("object_ids", [])])
    if text:
        block["texts"] = _dedupe_strings([text, *block.get("texts", [])])
    block["source_bbox"] = _union_bbox([obj.get("bbox") or {}, block.get("source_bbox") or {}])
    block["display_bbox"] = _display_bbox(block["source_bbox"], page)
    source_refs = list(block.get("source_refs", []))
    if text:
        source_refs.insert(0, {"kind": "slide_text", "slide": slide_number, "object_id": object_id})
    elif str(obj.get("type") or "") in VISUAL_TYPES:
        source_refs.insert(0, {"kind": "visual", "slide": slide_number, "object_id": object_id})
    block["source_refs"] = _unique_refs(source_refs)
    block["token_estimate"] = _estimate_tokens([block.get("title", ""), block.get("summary", ""), *block.get("texts", [])])
    block["content_hash"] = _content_hash(block)


def _append_object_into_block(block: dict[str, Any], obj: dict[str, Any], slide_number: int, page: dict[str, Any]) -> None:
    object_id = str(obj.get("id") or "")
    text = str(obj.get("text") or "").strip()
    block["object_ids"] = _dedupe_strings([*block.get("object_ids", []), object_id])
    if text:
        block["texts"] = _dedupe_strings([*block.get("texts", []), text])
    block["source_bbox"] = _union_bbox([block.get("source_bbox") or {}, obj.get("bbox") or {}])
    block["display_bbox"] = _display_bbox(block["source_bbox"], page)
    source_refs = list(block.get("source_refs", []))
    if text:
        source_refs.append({"kind": "slide_text", "slide": slide_number, "object_id": object_id})
    elif str(obj.get("type") or "") in VISUAL_TYPES:
        source_refs.append({"kind": "visual", "slide": slide_number, "object_id": object_id})
    block["source_refs"] = _unique_refs(source_refs)
    block["token_estimate"] = _estimate_tokens([block.get("title", ""), block.get("summary", ""), *block.get("texts", [])])
    block["content_hash"] = _content_hash(block)


def _merge_block_into_block(target: dict[str, Any], source: dict[str, Any], page: dict[str, Any]) -> None:
    target["object_ids"] = _dedupe_strings([*target.get("object_ids", []), *source.get("object_ids", [])])
    target["texts"] = _dedupe_strings([*target.get("texts", []), *source.get("texts", [])])
    target["source_refs"] = _unique_refs([*target.get("source_refs", []), *source.get("source_refs", [])])
    target["animation_refs"] = _unique_refs([*target.get("animation_refs", []), *source.get("animation_refs", [])])
    target["source_bbox"] = _union_bbox([target.get("source_bbox") or {}, source.get("source_bbox") or {}])
    target["display_bbox"] = _display_bbox(target["source_bbox"], page)
    target["animation_steps"] = sorted(
        {
            int(step)
            for step in [*target.get("animation_steps", []), *source.get("animation_steps", [])]
            if str(step).strip()
        }
    )
    target["token_estimate"] = _estimate_tokens([target.get("title", ""), target.get("summary", ""), *target.get("texts", [])])
    target["content_hash"] = _content_hash(target)


def _attach_animation_ref(
    block: dict[str, Any],
    order: int,
    source_ref: dict[str, Any],
    animation_ref: dict[str, Any],
) -> None:
    block["animation_steps"] = sorted({*block.get("animation_steps", []), order})
    block["source_refs"] = _unique_refs([*block.get("source_refs", []), source_ref])
    block["animation_refs"] = _unique_refs([*block.get("animation_refs", []), animation_ref])
    block["token_estimate"] = _estimate_tokens([block.get("title", ""), block.get("summary", ""), *block.get("texts", [])])
    block["content_hash"] = _content_hash(block)


def _animation_target_block(blocks: list[dict[str, Any]], object_ids: list[str]) -> dict[str, Any]:
    eligible = [block for block in blocks if block.get("type") != "media_timeline"] or blocks
    return max(
        eligible,
        key=lambda block: (
            sum(1 for object_id in object_ids if object_id in (block.get("object_ids") or [])),
            len(block.get("texts", []) or []),
        ),
    )


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


def _is_dense_diagram_part(obj: dict[str, Any]) -> bool:
    obj_type = str(obj.get("type") or "")
    if obj_type in VISUAL_TYPES:
        return True
    return _is_formula_object(obj) or _is_short_label(obj)


def _is_short_label(obj: dict[str, Any]) -> bool:
    text = str(obj.get("text") or "").strip()
    return bool(text) and len(text) <= 18


def _is_title(obj: dict[str, Any], title: str) -> bool:
    text = str(obj.get("text") or "").strip()
    if not text or not title:
        return False
    if text != title.strip():
        return False
    bbox = obj.get("bbox") or {}
    if len(text) > 80:
        return False
    return int(bbox.get("y") or 0) <= 1200000 and int(bbox.get("h") or 0) <= 900000


def _expand_bbox_for_text_overflow(
    block_type: str,
    bbox: dict[str, int],
    texts: list[str],
    page: dict[str, Any],
) -> dict[str, int]:
    if block_type != "text_concept":
        return bbox
    item_count = _numbered_outline_count(texts)
    if item_count < 4:
        return bbox
    page_height = int(page.get("height") or 0)
    if page_height <= 0:
        return bbox
    expected_height = int(page_height * min(0.86, item_count * 0.105 + 0.035))
    if expected_height <= int(bbox.get("h") or 0):
        return bbox
    top = int(bbox.get("y") or 0)
    return {
        **bbox,
        "h": max(0, min(expected_height, page_height - top)),
    }


def _numbered_outline_count(texts: list[str]) -> int:
    joined = " ".join(str(text or "") for text in texts)
    numbers = [int(match) for match in re.findall(r"(?:^|\s)([1-9])\s+[A-Za-z]", joined)]
    if not numbers:
        return 0
    unique = sorted(set(numbers))
    count = 0
    for expected in range(1, 10):
        if expected not in unique:
            break
        count += 1
    return count


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


def _content_hash(block: dict[str, Any]) -> str:
    stable = {
        "texts": [_normalize_text(text) for text in block.get("texts", []) if str(text).strip()],
        "object_ids": sorted(str(item) for item in block.get("object_ids", []) if str(item).strip()),
        "bbox": _rounded_bbox(block.get("display_bbox") or block.get("source_bbox") or {}),
        "media": block.get("media") or {},
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _duplicate_key(block: dict[str, Any]) -> str:
    texts = [_normalize_text(text) for text in block.get("texts", []) if str(text).strip()]
    bbox = _rounded_bbox(block.get("display_bbox") or block.get("source_bbox") or {})
    if texts:
        if block.get("animation_refs") or any(ref.get("kind") == "animation" for ref in block.get("source_refs", []) if isinstance(ref, dict)):
            return json.dumps({"animation_texts": texts}, ensure_ascii=False, sort_keys=True)
        return json.dumps({"texts": texts, "bbox": bbox}, ensure_ascii=False, sort_keys=True)
    return str(block.get("content_hash") or _content_hash(block))


def _normalize_text(text: Any) -> str:
    value = " ".join(str(text or "").strip().lower().split())
    return re.sub(r"([，。,.!?！？；;：:])\1+", r"\1", value)


def _rounded_bbox(bbox: dict[str, Any]) -> dict[str, float]:
    return {
        key: round(float(bbox.get(key) or 0), 4)
        for key in ("x", "y", "w", "h")
    }


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = _normalize_text(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _union_bbox(boxes: list[dict[str, Any]]) -> dict[str, int]:
    valid = [box for box in boxes if all(key in box for key in ("x", "y", "w", "h"))]
    if not valid:
        return {"x": 0, "y": 0, "w": 0, "h": 0}
    left = min(int(box["x"]) for box in valid)
    top = min(int(box["y"]) for box in valid)
    right = max(int(box["x"]) + int(box["w"]) for box in valid)
    bottom = max(int(box["y"]) + int(box["h"]) for box in valid)
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _union_float_bbox(boxes: list[dict[str, Any]]) -> dict[str, float]:
    valid = [box for box in boxes if all(key in box for key in ("x", "y", "w", "h"))]
    if not valid:
        return {"x": 0, "y": 0, "w": 0, "h": 0}
    left = min(float(box["x"]) for box in valid)
    top = min(float(box["y"]) for box in valid)
    right = max(float(box["x"]) + float(box["w"]) for box in valid)
    bottom = max(float(box["y"]) + float(box["h"]) for box in valid)
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "w": round(right - left, 6),
        "h": round(bottom - top, 6),
    }


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
