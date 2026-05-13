from __future__ import annotations

from typing import Any

MAX_GUIDE_PAGE_RATIO = 0.15
MAX_INLINE_MARKERS = 3


def build_augment_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    slides = [_plan_slide(slide) for slide in analysis.get("slides", [])]
    slides = _apply_deck_budget(slides)
    return {
        "kind": "augment_plan",
        "version": "v3d",
        "mode": "animation_guide_basic",
        "source": analysis.get("source", {}),
        "slides": slides,
        "summary": {
            "source_slide_count": len(slides),
            "guide_page_count": sum(len(slide["guide_pages"]) for slide in slides),
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
    strategy = _strategy(slide)
    guide_pages = _guide_pages(slide, strategy)
    return {
        "source_slide": slide.get("number", 0),
        "title": slide.get("title", ""),
        "size": slide.get("size", {}),
        "strategy": strategy,
        "page_budget": 1 + len(guide_pages),
        "reason": slide.get("decision_hint", {}).get("reason", ""),
        "inline_markers": _inline_markers(slide, strategy),
        "guide_pages": guide_pages,
    }


def _strategy(slide: dict[str, Any]) -> str:
    hint = slide.get("decision_hint", {}).get("strategy")
    if hint == "reflow_or_expand":
        if _needs_report_only(slide):
            return "report_only"
        return "expand_after_native"
    if slide.get("animation_target_count", 0) > 0:
        return "native_enhance"
    return "keep_native"


def _needs_report_only(slide: dict[str, Any]) -> bool:
    if slide.get("unsupported_animation_count", 0) > 0:
        return True
    if slide.get("animation_target_count", 0) == 0:
        return True
    if len(slide.get("animation_steps", [])) > 5:
        return True
    if slide.get("complexity") == "complex" and slide.get("object_count", 0) >= 6:
        return True
    return False


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

    steps = [_step_text(step) for step in slide.get("animation_steps", [])]
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
            }
        )
    return markers


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


def _step_text(step: dict[str, Any]) -> str:
    target = step.get("target_text") or "未命名对象"
    kind = step.get("kind") or "appear"
    if kind == "fade":
        verb = "淡入"
    elif kind == "wipe":
        verb = "擦除展开"
    elif kind == "appear":
        verb = "出现"
    else:
        verb = f"{kind} 动画"
    return f"{verb}：{target}"
