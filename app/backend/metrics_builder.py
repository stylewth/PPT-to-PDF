from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_metrics(
    analysis: dict[str, Any],
    plan: dict[str, Any],
    *,
    knowledge_blocks: dict[str, Any] | None = None,
    runtime_seconds: float,
) -> dict[str, Any]:
    slides = analysis.get("slides", [])
    summary = plan.get("summary", {})
    animated_pages = [slide for slide in slides if slide.get("animation_target_count", 0) > 0]
    unsupported_count = sum(int(slide.get("unsupported_animation_count", 0)) for slide in slides)
    warning_count = sum(len(slide.get("warnings", [])) for slide in slides)
    micro_pages = summary.get("micro_reflow_pages", [])
    object_pages = summary.get("object_reflow_pages", [])
    source_slide_count = int(summary.get("source_slide_count") or len(slides))
    guide_page_count = source_slide_count + int(summary.get("guide_page_count", 0))

    manual_minutes = (
        source_slide_count * 1.2
        + len(animated_pages) * 2.8
        + len(micro_pages) * 4.5
        + len(object_pages) * 4.5
        + warning_count * 0.8
    )
    tool_minutes = runtime_seconds / 60.0 + max(1.0, source_slide_count * 0.25)
    saved = max(0.0, manual_minutes - tool_minutes)
    ai_metrics = _ai_metrics(analysis, knowledge_blocks)

    return {
        "kind": "efficiency_metrics",
        "version": "v3j",
        "runtime_seconds": round(float(runtime_seconds), 2),
        "source_slide_count": source_slide_count,
        "guide_page_count": guide_page_count,
        "animated_page_count": len(animated_pages),
        "unsupported_animation_count": unsupported_count,
        "overlap_warning_count": sum(
            1
            for slide in slides
            for warning in slide.get("warnings", [])
            if warning.get("code") in {"object_overlap", "top_layer_occlusion"}
        ),
        "warning_count": warning_count,
        "micro_reflow_page_count": len(micro_pages),
        "object_reflow_page_count": len(object_pages),
        "estimated_manual_review_minutes": round(manual_minutes, 1),
        "estimated_tool_minutes": round(tool_minutes, 1),
        "estimated_saved_minutes": round(saved, 1),
        **ai_metrics,
        "roi_note": "该指标用于比赛演示：估算人工整理动态 PPT、检查遮挡和补充流程说明的时间。",
        "notes": "估算公式：人工分钟=幻灯片*1.2 + 动画页*2.8 + 微调重排页*4.5 + warning*0.8；工具分钟=运行耗时/60 + 幻灯片*0.25。",
    }


def write_metrics(path: str | Path, metrics: dict[str, Any]) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _ai_metrics(analysis: dict[str, Any], knowledge_blocks: dict[str, Any] | None) -> dict[str, Any]:
    if not knowledge_blocks:
        return {
            "ai_block_count": 0,
            "ai_selected_block_count": 0,
            "estimated_full_slide_tokens": 0,
            "estimated_block_tokens": 0,
            "estimated_token_saved_ratio": 0.0,
        }
    blocks = [
        block
        for slide in knowledge_blocks.get("slides", [])
        for block in slide.get("blocks", [])
    ]
    block_tokens = sum(int(block.get("token_estimate") or 0) for block in blocks)
    full_slide_chars = sum(
        int((slide.get("metrics") or {}).get("character_count") or 0)
        for slide in analysis.get("slides", [])
    )
    full_slide_tokens = max(block_tokens, round(full_slide_chars / 2) + len(analysis.get("slides", [])) * 80)
    saved_ratio = 0.0 if not full_slide_tokens else max(0.0, 1.0 - block_tokens / full_slide_tokens)
    return {
        "ai_block_count": len(blocks),
        "ai_selected_block_count": 0,
        "estimated_full_slide_tokens": int(full_slide_tokens),
        "estimated_block_tokens": int(block_tokens),
        "estimated_token_saved_ratio": round(saved_ratio, 4),
    }
