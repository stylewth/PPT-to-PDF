from __future__ import annotations

import math
import json
from typing import Any


def build_ai_context(
    knowledge_blocks: dict[str, Any],
    block_ids: list[str],
    *,
    mode: str = "explain",
    max_chars: int = 1500,
) -> dict[str, Any]:
    if not block_ids:
        raise ValueError("At least one block id is required.")
    block_by_id = _flatten_blocks(knowledge_blocks)
    selected = []
    for block_id in block_ids:
        if block_id not in block_by_id:
            raise ValueError(f"Knowledge block not found: {block_id}")
        selected.append(block_by_id[block_id])

    context_text = _clip("\n\n".join(_block_context(block) for block in selected), max_chars)
    source_refs = _unique_refs([ref for block in selected for ref in block.get("source_refs", [])])
    return {
        "mode": mode,
        "blocks": selected,
        "context_text": context_text,
        "source_refs": source_refs,
        "estimated_token_count": max(1, math.ceil(len(context_text) / 2)),
    }


def _flatten_blocks(knowledge_blocks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for slide in knowledge_blocks.get("slides", []) or []:
        slide_number = int(slide.get("number") or 0)
        slide_title = str(slide.get("title") or "")
        for block in slide.get("blocks", []) or []:
            block_id = str(block.get("id") or "")
            if not block_id:
                continue
            result[block_id] = {
                "slide_number": slide_number,
                "slide_title": slide_title,
                **block,
            }
    return result


def _block_context(block: dict[str, Any]) -> str:
    refs = ", ".join(_ref_label(ref) for ref in block.get("source_refs", []))
    refs_json = json.dumps(block.get("source_refs", []), ensure_ascii=False)
    texts = "\n".join(f"- {text}" for text in block.get("texts", []) if str(text).strip())
    media = block.get("media") or {}
    media_line = f"\n媒体: {media.get('kind')} {media.get('status')}" if media else ""
    return (
        f"块ID: {block.get('id')}\n"
        f"页码: {block.get('slide_number')}\n"
        f"页标题: {block.get('slide_title')}\n"
        f"类型: {block.get('type')}\n"
        f"标题: {block.get('title')}\n"
        f"摘要: {block.get('summary')}{media_line}\n"
        f"文本证据:\n{texts}\n"
        f"来源短标: {refs}\n"
        f"source_refs JSON: {refs_json}"
    )


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


def _ref_label(ref: dict[str, Any]) -> str:
    return f"{ref.get('kind')}@p{ref.get('slide')}#{ref.get('object_id') or ref.get('block_id')}"


def _unique_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    unique = []
    for ref in refs:
        key = tuple(sorted(ref.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(ref)
    return unique
