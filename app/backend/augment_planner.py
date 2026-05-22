from __future__ import annotations

import re
from typing import Any

from layout_decider import decide_slide_layout
from object_reflow_planner import plan_object_reflow

MAX_GUIDE_TEXT = 90


def build_augment_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    slides = [_plan_slide(slide) for slide in analysis.get("slides", [])]
    return {
        "kind": "augment_plan",
        "version": "v3g",
        "mode": "animation_guide_basic",
        "source": analysis.get("source", {}),
        "slides": slides,
        "summary": {
            "source_slide_count": len(slides),
            "guide_page_count": sum(len(slide["guide_pages"]) for slide in slides),
            "micro_reflow_pages": [
                slide["source_slide"]
                for slide in slides
                if slide["strategy"] == "pdf_micro_reflow"
            ],
            "object_reflow_pages": [
                slide["source_slide"]
                for slide in slides
                if slide["strategy"] == "object_reflow"
            ],
            "report_only_pages": [
                slide["source_slide"]
                for slide in slides
                if slide["strategy"] == "report_only"
            ],
            "text_box_repair_pages": [
                slide["source_slide"]
                for slide in slides
                if slide["text_box_repairs"]
            ],
        },
    }


def _plan_slide(slide: dict[str, Any]) -> dict[str, Any]:
    layout = decide_slide_layout(slide)
    strategy = layout["strategy"]
    object_reflow = _object_reflow(slide, strategy)
    page_compact = _page_compact(slide, object_reflow)
    if strategy == "object_reflow" and not ((object_reflow or {}).get("operations")):
        strategy = "native_compact" if page_compact else "native_enhance" if slide.get("animation_target_count", 0) > 0 else "keep_native"
        object_reflow = None
    return {
        "source_slide": slide.get("number", 0),
        "title": slide.get("title", ""),
        "size": slide.get("size", {}),
        "strategy": strategy,
        "page_budget": 1,
        "reason": layout.get("reason", ""),
        "object_boxes": slide.get("object_boxes", []),
        "inline_markers": _inline_markers(slide, strategy),
        "text_box_repairs": _text_box_repairs(slide),
        "guide_pages": [],
        "micro_reflow": _micro_reflow(slide, strategy),
        "page_compact": page_compact,
        "object_reflow": object_reflow,
    }


def _inline_markers(slide: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    # Page-level animation badges were more distracting than useful for course slides.
    return []


def _micro_reflow(slide: dict[str, Any], strategy: str) -> dict[str, Any] | None:
    if strategy not in {"pdf_micro_reflow", "object_reflow"}:
        return None
    steps = _guide_step_summaries(slide.get("animation_steps", []))
    flows = _occlusion_flows(slide)
    return {
        "type": "pdf_micro_reflow",
        "placement_policy": "blank_space_first",
        "steps": [{"order": index + 1, "text": text} for index, text in enumerate(steps[:5])],
        "occlusion_flows": flows[:4],
        "metrics": {
            "crowding": slide.get("crowding"),
            "complexity": slide.get("complexity"),
            "strategy": strategy,
        },
    }


def _object_reflow(slide: dict[str, Any], strategy: str) -> dict[str, Any] | None:
    if strategy != "object_reflow":
        return None
    return plan_object_reflow(slide)


def _text_box_repairs(slide: dict[str, Any]) -> list[dict[str, Any]]:
    size = slide.get("size") or {}
    slide_width = int(size.get("width") or 12192000)
    objects = [obj for obj in slide.get("object_boxes", []) if obj.get("bbox")]
    repairs: list[dict[str, Any]] = []
    for obj in objects:
        if str(obj.get("type") or "") != "sp":
            continue
        text = _normalized_inline_text(obj.get("text") or "")
        if not _is_fragile_inline_math(text):
            continue
        bbox = dict(obj.get("bbox") or {})
        target_width = _protected_text_width(text, bbox, objects, slide_width)
        repairs.append(
            {
                "id": str(obj.get("id") or ""),
                "type": "single_line_math_text",
                "text": text,
                "wrap": "none",
                "to": {
                    "x": int(bbox["x"]),
                    "y": int(bbox["y"]),
                    "w": target_width,
                    "h": int(bbox["h"]),
                },
            }
        )
    return repairs


def _normalized_inline_text(text: str) -> str:
    return " ".join(text.replace("\u3000", " ").split())


def _is_fragile_inline_math(text: str) -> bool:
    if not (3 <= len(text) <= 28):
        return False
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        return False
    if not any(op in text for op in ("<", ">", "=", "≤", "≥")):
        return False
    if not re.fullmatch(r"[A-Za-z0-9_ .,:;：()<>＝=≤≥+\-−*/\\α-ωΑ-Ω]+", text):
        return False
    comparison_count = sum(text.count(op) for op in ("<", ">", "=", "≤", "≥"))
    if comparison_count >= 2:
        return True
    if comparison_count >= 1 and text.rstrip().endswith((".", ":", ";")):
        return True
    return bool(re.search(r"\s[<>=≤≥]\s", text))


def _protected_text_width(
    text: str,
    bbox: dict[str, Any],
    objects: list[dict[str, Any]],
    slide_width: int,
) -> int:
    x = int(bbox["x"])
    y = int(bbox["y"])
    width = int(bbox["w"])
    height = int(bbox["h"])
    desired = max(width, int(len(text) * 170000))
    right_limit = slide_width - max(80000, int(slide_width * 0.01))
    for other in objects:
        other_box = other.get("bbox") or {}
        if other_box is bbox:
            continue
        other_x = int(other_box.get("x", 0))
        if other_x <= x + width:
            continue
        if _vertical_overlap_ratio(bbox, other_box) < 0.25:
            continue
        right_limit = min(right_limit, other_x - 80000)
    return max(width, min(desired, max(width, right_limit - x)))


def _vertical_overlap_ratio(first: dict[str, Any], second: dict[str, Any]) -> float:
    top = max(int(first.get("y", 0)), int(second.get("y", 0)))
    bottom = min(
        int(first.get("y", 0)) + int(first.get("h", 0)),
        int(second.get("y", 0)) + int(second.get("h", 0)),
    )
    overlap = max(0, bottom - top)
    smaller = min(int(first.get("h", 0)), int(second.get("h", 0)))
    return overlap / smaller if smaller else 0.0


def _page_compact(slide: dict[str, Any], object_reflow: dict[str, Any] | None) -> dict[str, Any] | None:
    if not object_reflow or (object_reflow.get("quality_gate") or {}).get("passed", True):
        return None
    size = slide.get("size") or {}
    page_height = max(int(size.get("height") or 6858000), 1)
    bottoms = [
        int((obj.get("bbox") or {}).get("y", 0)) + int((obj.get("bbox") or {}).get("h", 0))
        for obj in slide.get("object_boxes", [])
        if obj.get("bbox")
    ]
    if not bottoms:
        return None
    bottom_ratio = max(bottoms) / page_height
    if bottom_ratio < 0.93:
        return None
    scale = max(0.90, min(0.96, 0.90 / bottom_ratio))
    return {
        "type": "page_compact",
        "scale": scale,
        "reason": "重排质量门禁失败且内容贴近页底，轻微缩放保留原页面关系。",
    }


def _occlusion_flows(slide: dict[str, Any]) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    for index, step in enumerate(slide.get("animation_steps", []), start=1):
        covered = [
            item
            for item in step.get("covered_objects", [])
            if item.get("bbox")
        ]
        if not covered and not step.get("covers_prior_object"):
            continue
        target_bbox = step.get("bbox")
        if not target_bbox:
            continue
        flows.append(
            {
                "order": index,
                "target_id": step.get("target_id", ""),
                "target_text": _target_text(step),
                "target_bbox": target_bbox,
                "covered": covered or [
                    {
                        "id": "",
                        "text": "遮挡前区域",
                        "bbox": target_bbox,
                    }
                ],
                "relationship": "遮挡前 -> 覆盖后",
            }
        )
    if flows:
        return flows
    for index, step in enumerate(slide.get("animation_steps", [])[:3], start=1):
        if not step.get("bbox"):
            continue
        flows.append(
            {
                "order": index,
                "target_id": step.get("target_id", ""),
                "target_text": _target_text(step),
                "target_bbox": step.get("bbox"),
                "covered": [
                    {
                        "id": step.get("target_id", ""),
                        "text": _target_text(step),
                        "bbox": step.get("bbox"),
                    }
                ],
                "relationship": "流程节点",
            }
        )
    return flows


def _guide_step_summaries(animation_steps: list[dict[str, Any]]) -> list[str]:
    if len(animation_steps) <= 3:
        return [_fit_guide_text(_step_text(step)) for step in animation_steps]

    summaries = [_fit_guide_text(f"先读：{_target_text(animation_steps[0])}")]
    covered_steps = [
        step for step in animation_steps[1:-1] if step.get("covers_prior_object")
    ]
    if covered_steps:
        summaries.append(_fit_guide_text(f"遮挡变化：{_target_list(covered_steps)}"))
    else:
        middle_count = len(animation_steps) - 2
        summaries.append(_fit_guide_text(f"中间过程：{middle_count} 个对象依次出现"))
    summaries.append(_fit_guide_text(f"最后形成：{_target_text(animation_steps[-1])}"))
    return summaries


def _step_text(step: dict[str, Any]) -> str:
    target = step.get("target_text") or "未命名对象"
    kind = step.get("kind") or "appear"
    if kind == "fade":
        verb = "淡入"
    elif kind == "wipe":
        verb = "擦除展开"
    elif kind == "blinds":
        verb = "百叶展开"
    elif kind == "wheel_in":
        verb = "轮状出现"
    elif kind == "wheel_out":
        verb = "轮状退出"
    elif kind in {"motion", "motion_x", "motion_y"}:
        verb = "位置移动"
    elif kind == "appear":
        verb = "出现"
    else:
        verb = f"{kind} 动画"
    return f"{verb}：{target}"


def _target_text(step: dict[str, Any]) -> str:
    target = str(step.get("target_text") or "").strip()
    return target or "未命名对象"


def _target_list(steps: list[dict[str, Any]]) -> str:
    names = [_target_text(step) for step in steps[:3]]
    suffix = f"等 {len(steps)} 处" if len(steps) > 3 else ""
    return "、".join(names) + suffix


def _fit_guide_text(text: str) -> str:
    return _fit_text(text, MAX_GUIDE_TEXT)


def _fit_text(text: str, limit: int) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
