from __future__ import annotations

from typing import Any

from layout_decider import annotation_slot, decide_slide_layout, select_annotation_zone
from object_reflow_planner import plan_object_reflow

MAX_INLINE_MARKERS = 3
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
        },
    }


def _plan_slide(slide: dict[str, Any]) -> dict[str, Any]:
    layout = decide_slide_layout(slide)
    strategy = layout["strategy"]
    object_reflow = _object_reflow(slide, strategy)
    if strategy == "object_reflow" and not ((object_reflow or {}).get("operations")):
        strategy = "native_enhance" if slide.get("animation_target_count", 0) > 0 else "keep_native"
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
        "guide_pages": [],
        "micro_reflow": _micro_reflow(slide, strategy),
        "object_reflow": object_reflow,
    }


def _inline_markers(slide: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    if strategy != "native_enhance":
        return []
    markers = []
    steps = slide.get("animation_steps", [])[:MAX_INLINE_MARKERS]
    zone = select_annotation_zone(slide, marker_count=len(steps))
    if not zone:
        return []
    steps = steps[: min(len(steps), int(zone["capacity"]))]
    total = len(steps)
    for index, step in enumerate(steps, start=1):
        role = _marker_role(index, total, step)
        markers.append(
            {
                "order": index,
                "label": str(index),
                "role": role,
                "hint": _marker_hint(role),
                "target_id": step.get("target_id", ""),
                "target_text": step.get("target_text", ""),
                "kind": step.get("kind", ""),
                "bbox": step.get("bbox"),
                "text": _step_text(step),
                "placement": zone,
                "hint_box": annotation_slot(zone, index),
            }
        )
    return markers


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


def _marker_role(index: int, total: int, step: dict[str, Any]) -> str:
    if step.get("covers_prior_object"):
        return "covered_content"
    if index == 1:
        return "first_change"
    if index == total:
        return "key_result"
    return "next_change"


def _marker_hint(role: str) -> str:
    hints = {
        "first_change": "先出现",
        "next_change": "随后出现",
        "key_result": "关键结果",
        "covered_content": "遮挡变化",
    }
    return hints.get(role, "发生变化")


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
