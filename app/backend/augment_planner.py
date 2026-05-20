from __future__ import annotations

from typing import Any

from layout_decider import annotation_slot, decide_slide_layout, select_annotation_zone
from object_reflow_planner import plan_object_reflow

MAX_GUIDE_PAGE_RATIO = 0.15
MAX_INLINE_MARKERS = 3
MAX_GUIDE_TEXT = 90
MAX_REFLOW_CARD_TEXT = 58


def build_augment_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    slides = [_plan_slide(slide) for slide in analysis.get("slides", [])]
    slides = _apply_deck_budget(slides)
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
            "expanded_pages": [
                slide["source_slide"]
                for slide in slides
                if slide["strategy"] == "expand_after_native"
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
    guide_pages = _guide_pages(slide, strategy)
    return {
        "source_slide": slide.get("number", 0),
        "title": slide.get("title", ""),
        "size": slide.get("size", {}),
        "strategy": strategy,
        "page_budget": 1 + len(guide_pages),
        "reason": layout.get("reason", ""),
        "object_boxes": slide.get("object_boxes", []),
        "inline_markers": _inline_markers(slide, strategy),
        "guide_pages": guide_pages,
        "micro_reflow": _micro_reflow(slide, strategy),
        "object_reflow": object_reflow,
        "reflow_page": None,
    }


def _apply_deck_budget(slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
    max_extra_pages = max(1, int(len(slides) * MAX_GUIDE_PAGE_RATIO)) if slides else 0
    used_extra_pages = 0
    budgeted = []
    for slide in slides:
        if slide["strategy"] != "expand_after_native":
            budgeted.append(slide)
            continue
        if used_extra_pages < max_extra_pages:
            used_extra_pages += len(slide["guide_pages"])
            budgeted.append(slide)
            continue
        budgeted.append(_as_report_only(slide, "整份 PPT 的导读页预算已用完，本页只写入报告。"))
    return budgeted


def _as_report_only(slide: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    changed = dict(slide)
    changed["strategy"] = "report_only"
    changed["page_budget"] = 1
    changed["reason"] = reason or "页面复杂或动画不支持，基础版不硬生成低价值导读页。"
    changed["inline_markers"] = []
    changed["guide_pages"] = []
    return changed


def _guide_pages(slide: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    if strategy != "expand_after_native":
        return []

    steps = _guide_step_summaries(slide.get("animation_steps", []))
    if not steps:
        steps = ["本页没有可识别动画，保留原生页面作为阅读依据。"]

    return [
        {
            "type": "expand",
            "title": f"动画导读：{slide.get('title', '未命名页面')}",
            "subtitle": _subtitle(slide, strategy),
            "steps": [
                {
                    "order": index + 1,
                    "text": text,
                }
                for index, text in enumerate(steps[:5])
            ],
            "metrics": {
                "crowding": slide.get("crowding"),
                "complexity": slide.get("complexity"),
                "strategy": strategy,
            },
        }
    ]


def _inline_markers(slide: dict[str, Any], strategy: str) -> list[dict[str, Any]]:
    if strategy not in {"native_enhance", "expand_after_native"}:
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


def _content_items(slide: dict[str, Any]) -> list[str]:
    seen = set()
    items = []
    title = str(slide.get("title") or "").strip()
    if title:
        seen.add(title)
        items.append(_fit_text(title, MAX_REFLOW_CARD_TEXT))
    for obj in sorted(slide.get("text_objects", []), key=_object_sort_key):
        text = str(obj.get("text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            items.append(_fit_text(text, MAX_REFLOW_CARD_TEXT))
    for step in slide.get("animation_steps", []):
        text = _target_text(step)
        if text and text not in seen and text != "未命名对象":
            seen.add(text)
            items.append(_fit_text(text, MAX_REFLOW_CARD_TEXT))
    if not items:
        items.append("本页没有可抽取文字，保留原生页作为对照。")
    return items


def _object_sort_key(obj: dict[str, Any]) -> tuple[int, int]:
    box = obj.get("bbox") or {}
    return (int(box.get("y", 0)), int(box.get("x", 0)))


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


def _subtitle(slide: dict[str, Any], strategy: str) -> str:
    if strategy == "expand_after_native":
        return "本页存在遮挡或拥挤风险，已追加展开说明页。"
    return "本页保留原生排版，并补充动画阅读顺序。"


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
