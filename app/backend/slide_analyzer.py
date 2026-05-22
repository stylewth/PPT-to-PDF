from __future__ import annotations

from typing import Any


DEFAULT_PAGE = {"width": 12192000, "height": 6858000}
SIGNIFICANT_OVERLAP_RATIO = 0.15


def analyze_presentation(presentation: dict[str, Any]) -> dict[str, Any]:
    page = presentation.get("page") or DEFAULT_PAGE
    slides = [_analyze_slide(slide, page) for slide in presentation.get("slides", [])]
    return {
        "kind": "slide_analysis",
        "version": "v3b",
        "source": {
            "name": presentation.get("source_name", ""),
            "slide_count": presentation.get("slide_count", len(slides)),
        },
        "page": page,
        "slides": slides,
    }


def summarize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    slides = analysis.get("slides", [])
    return {
        "slide_count": len(slides),
        "animated_pages": [slide["number"] for slide in slides if slide.get("animation_target_count", 0) > 0],
        "high_crowding_pages": [slide["number"] for slide in slides if slide.get("crowding") == "high"],
        "unsupported_animation_pages": [
            slide["number"]
            for slide in slides
            if slide.get("unsupported_animation_count", 0) > 0
        ],
        "reflow_candidate_pages": [
            slide["number"]
            for slide in slides
            if slide.get("decision_hint", {}).get("strategy") == "reflow_or_expand"
        ],
    }


def _analyze_slide(slide: dict[str, Any], page: dict[str, int]) -> dict[str, Any]:
    objects = slide.get("objects", [])
    animations = slide.get("animations", [])
    text_objects = [obj for obj in objects if obj.get("text")]
    metrics = _metrics(objects, text_objects, animations, page)
    warnings = _warnings(slide, metrics)
    crowding = _crowding(metrics)
    complexity = _complexity(metrics, animations, warnings)
    return {
        "number": slide.get("number", 0),
        "title": slide.get("title", ""),
        "size": page,
        "object_count": len(objects),
        "text_box_count": len(text_objects),
        "text_objects": _text_objects(text_objects),
        "object_boxes": _object_boxes(objects),
        "animation_target_count": len({anim.get("target_id") for anim in animations if anim.get("target_id")}),
        "supported_animation_count": sum(1 for anim in animations if anim.get("supported", False)),
        "unsupported_animation_count": sum(1 for anim in animations if not anim.get("supported", False)),
        "notes_present": bool(str(slide.get("notes", "")).strip()),
        "animation_steps": [_animation_step(animation, objects) for animation in animations],
        "metrics": metrics,
        "crowding": crowding,
        "complexity": complexity,
        "warnings": warnings,
        "decision_hint": _decision_hint(crowding, complexity, metrics),
    }


def _object_boxes(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": obj.get("id", ""),
            "name": obj.get("name", ""),
            "type": obj.get("type", ""),
            "text": obj.get("text", ""),
            "bbox": obj["bbox"],
            "z_order": obj.get("z_order", 0),
            "in_group": bool(obj.get("in_group")),
        }
        for obj in objects
        if obj.get("bbox")
    ]


def _text_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": obj.get("id", ""),
            "text": obj.get("text", ""),
            "bbox": obj.get("bbox"),
        }
        for obj in objects
        if str(obj.get("text", "")).strip()
    ]


def _metrics(
    objects: list[dict[str, Any]],
    text_objects: list[dict[str, Any]],
    animations: list[dict[str, Any]],
    page: dict[str, int],
) -> dict[str, Any]:
    page_area = max(page.get("width", 0) * page.get("height", 0), 1)
    boxes = [obj["bbox"] for obj in objects if obj.get("bbox")]
    object_area = sum(_area(box) for box in boxes)
    overlap_area = 0
    max_overlap = 0.0
    for index, first in enumerate(boxes):
        for second in boxes[index + 1 :]:
            area = _overlap_area(first, second)
            overlap_area += area
            smaller = min(_area(first), _area(second))
            if smaller:
                max_overlap = max(max_overlap, area / smaller)

    character_count = sum(len(obj.get("text", "")) for obj in text_objects)
    object_coverage = min(object_area / page_area, 1.0)
    overlap_ratio = min(overlap_area / page_area, 1.0)
    blank_ratio = max(1.0 - object_coverage, 0.0)
    text_density = character_count / (page_area / 1_000_000)

    return {
        "object_coverage_ratio": round(object_coverage, 4),
        "overlap_ratio": round(overlap_ratio, 4),
        "max_object_overlap_ratio": round(max_overlap, 4),
        "blank_ratio": round(blank_ratio, 4),
        "text_density": round(text_density, 4),
        "character_count": character_count,
        "animation_density": round(len(animations) / max(len(objects), 1), 4),
        "annotation_fit": _annotation_fit(blank_ratio, max_overlap, len(animations)),
    }


def _animation_step(animation: dict[str, Any], objects: list[dict[str, Any]]) -> dict[str, Any]:
    target_id = animation.get("target_id", "")
    target = next((obj for obj in objects if obj.get("id") == target_id), {})
    covered_objects = _covered_prior_objects(target, objects)
    return {
        "order": animation.get("order", 0),
        "target_id": target_id,
        "target_text": animation.get("target_text") or animation.get("target_name") or "",
        "kind": animation.get("kind", ""),
        "supported": bool(animation.get("supported", False)),
        "bbox": target.get("bbox"),
        "covers_prior_object": bool(covered_objects),
        "covered_object_ids": [obj.get("id", "") for obj in covered_objects],
        "covered_objects": [
            {
                "id": obj.get("id", ""),
                "text": obj.get("text", ""),
                "bbox": obj.get("bbox"),
            }
            for obj in covered_objects
        ],
    }


def _covered_prior_objects(target: dict[str, Any], objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_box = target.get("bbox")
    if not target_box:
        return []
    target_z = int(target.get("z_order", -1))
    covered = []
    for obj in objects:
        if obj.get("id") == target.get("id"):
            continue
        if int(obj.get("z_order", -1)) >= target_z:
            continue
        obj_box = obj.get("bbox")
        if not obj_box:
            continue
        smaller_area = min(_area(target_box), _area(obj_box))
        if not smaller_area:
            continue
        overlap_ratio = _overlap_area(target_box, obj_box) / smaller_area
        if overlap_ratio >= SIGNIFICANT_OVERLAP_RATIO:
            covered.append(obj)
    return covered


def _warnings(slide: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if metrics["max_object_overlap_ratio"] >= 0.15:
        warnings.append(
            {
                "code": "object_overlap",
                "message": "页面对象存在明显重叠，后续导读页可能需要重排或展开。",
            }
        )
    for animation in slide.get("animations", []):
        if not animation.get("supported", False):
            warnings.append(
                {
                    "code": "unsupported_animation",
                    "message": f"已识别 {animation.get('kind')} 数值动画；终态坐标不稳定，保留原生 PDF 画面并列入复核。",
                }
            )
    if not str(slide.get("notes", "")).strip():
        warnings.append(
            {
                "code": "missing_notes",
                "message": "本页没有备注解释。",
            }
        )
    return warnings


def _crowding(metrics: dict[str, Any]) -> str:
    if (
        metrics["object_coverage_ratio"] >= 0.55
        or metrics["max_object_overlap_ratio"] >= 0.35
        or metrics["text_density"] >= 1.2
        or metrics["annotation_fit"] == "poor"
    ):
        return "high"
    if (
        metrics["object_coverage_ratio"] >= 0.28
        or metrics["max_object_overlap_ratio"] >= 0.15
        or metrics["text_density"] >= 0.65
        or metrics["annotation_fit"] == "limited"
    ):
        return "medium"
    return "low"


def _complexity(
    metrics: dict[str, Any],
    animations: list[dict[str, Any]],
    warnings: list[dict[str, str]],
) -> str:
    unsupported = any(warning["code"] == "unsupported_animation" for warning in warnings)
    if unsupported or len(animations) > 5 or metrics["annotation_fit"] == "poor":
        return "complex"
    if len(animations) >= 2 or metrics["max_object_overlap_ratio"] >= 0.15:
        return "medium"
    return "simple"


def _decision_hint(crowding: str, complexity: str, metrics: dict[str, Any]) -> dict[str, Any]:
    if crowding == "high" or complexity == "complex":
        return {
            "strategy": "reflow_or_expand",
            "reason": "页面拥挤或动画/重叠会影响理解。",
        }
    if complexity == "medium" or metrics["animation_density"] > 0:
        return {
            "strategy": "native_enhance",
            "reason": "保留原生页并叠加编号、高亮和顺序提示。",
        }
    return {
        "strategy": "keep_native",
        "reason": "页面静态且不拥挤。",
    }


def _annotation_fit(blank_ratio: float, max_overlap: float, animation_count: int) -> str:
    if blank_ratio < 0.2 or max_overlap >= 0.35 or animation_count > 5:
        return "poor"
    if blank_ratio < 0.45 or max_overlap >= 0.15 or animation_count >= 3:
        return "limited"
    return "easy"


def _area(box: dict[str, int]) -> int:
    return max(box.get("w", 0), 0) * max(box.get("h", 0), 0)


def _overlap_area(first: dict[str, int], second: dict[str, int]) -> int:
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)
