from __future__ import annotations

from typing import Any


def build_study_document(presentation: dict[str, Any]) -> dict[str, Any]:
    slides = [_build_slide(slide) for slide in presentation["slides"]]
    return {
        "kind": "study_document",
        "version": "v2",
        "source": {
            "name": presentation.get("source_name", ""),
            "slide_count": presentation.get("slide_count", len(slides)),
        },
        "slides": slides,
    }


def _build_slide(slide: dict[str, Any]) -> dict[str, Any]:
    warnings = _detect_warnings(slide)
    steps = _build_steps(slide)
    return {
        "number": slide["number"],
        "title": slide["title"],
        "original_objects": slide["objects"],
        "steps": steps,
        "warnings": warnings,
        "explanation": _build_explanation(slide),
        "notes_area": True,
    }


def _build_steps(slide: dict[str, Any]) -> list[dict[str, Any]]:
    animations = slide.get("animations", [])
    if animations:
        return [
            {
                "order": animation["order"],
                "source": "animation",
                "animation": animation["kind"],
                "target_id": animation["target_id"],
                "target_text": animation.get("target_text") or animation.get("target_name") or "未命名对象",
                "summary": _step_summary(animation),
            }
            for animation in animations
        ]

    text_objects = [obj for obj in slide.get("objects", []) if obj.get("text")]
    return [
        {
            "order": index + 1,
            "source": "z_order",
            "animation": "static",
            "target_id": obj["id"],
            "target_text": obj["text"],
            "summary": f"按页面层级阅读：{obj['text']}",
        }
        for index, obj in enumerate(text_objects)
    ]


def _step_summary(animation: dict[str, Any]) -> str:
    target = animation.get("target_text") or animation.get("target_name") or "该对象"
    kind = animation.get("kind", "appear")
    if kind == "fade":
        return f"淡入展示“{target}”，通常用于引入新概念。"
    if kind == "wipe":
        return f"擦除展示“{target}”，通常表示按顺序展开。"
    if kind == "appear":
        return f"出现“{target}”，作为当前讲解步骤。"
    return f"检测到暂不支持的动画“{kind}”，保留为问题提示。"


def _detect_warnings(slide: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    warnings.extend(_detect_occlusion(slide.get("objects", [])))
    for animation in slide.get("animations", []):
        if not animation.get("supported", False):
            warnings.append(
                {
                    "code": "unsupported_animation",
                    "message": f"暂不支持动画 {animation.get('kind')}，已保留对象文本。",
                }
            )
    if not slide.get("notes"):
        warnings.append(
            {
                "code": "missing_notes",
                "message": "本页没有备注解释，生成解释时只能使用页内文字。",
            }
        )
    return warnings


def _detect_occlusion(objects: list[dict[str, Any]]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for lower in objects:
        lower_box = lower.get("bbox")
        if not lower_box:
            continue
        for upper in objects:
            if upper["z_order"] <= lower["z_order"]:
                continue
            upper_box = upper.get("bbox")
            if not upper_box:
                continue
            ratio = _overlap_ratio(lower_box, upper_box)
            if ratio >= 0.15:
                warnings.append(
                    {
                        "code": "top_layer_occlusion",
                        "message": f"“{upper.get('text') or upper.get('name')}”可能遮挡“{lower.get('text') or lower.get('name')}”。",
                    }
                )
                return warnings
    return warnings


def _overlap_ratio(a: dict[str, int], b: dict[str, int]) -> float:
    left = max(a["x"], b["x"])
    top = max(a["y"], b["y"])
    right = min(a["x"] + a["w"], b["x"] + b["w"])
    bottom = min(a["y"] + a["h"], b["y"] + b["h"])
    if right <= left or bottom <= top:
        return 0.0
    overlap = (right - left) * (bottom - top)
    smaller = min(a["w"] * a["h"], b["w"] * b["h"])
    return overlap / smaller if smaller else 0.0


def _build_explanation(slide: dict[str, Any]) -> str:
    notes = slide.get("notes", "").strip()
    if notes:
        return notes
    texts = [obj["text"] for obj in slide.get("objects", []) if obj.get("text")]
    if texts:
        return "本页仅基于页内文字整理：" + "；".join(texts[:4])
    return "本页缺少可解释文本，需教师或培训负责人补充。"
