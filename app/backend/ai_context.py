from __future__ import annotations

import math
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
        "evidence_text": context_text,
        "source_refs": source_refs,
        "animation_refs": _unique_refs([ref for block in selected for ref in block.get("animation_refs", [])]),
        "estimated_token_count": max(1, math.ceil(len(context_text) / 2)),
    }


def build_single_block_context(
    block: dict[str, Any],
    *,
    page_title: str = "",
    max_chars: int = 1500,
) -> dict[str, Any]:
    selected = {"slide_title": page_title, **block}
    evidence_text = _clip(_block_context(selected), max_chars)
    return {
        "mode": "explain",
        "block": selected,
        "blocks": [selected],
        "evidence_text": evidence_text,
        "context_text": evidence_text,
        "source_refs": _unique_refs(selected.get("source_refs", []) or []),
        "animation_refs": _unique_refs(selected.get("animation_refs", []) or []),
        "estimated_token_count": max(1, math.ceil(len(evidence_text) / 2)),
    }


def build_whole_page_context(page: dict[str, Any], *, max_chars: int = 3000) -> dict[str, Any]:
    texts = _dedupe_texts(
        [
            str(text).strip()
            for block in page.get("blocks", []) or []
            for text in block.get("texts", []) or []
            if str(text).strip()
        ]
    )
    source_refs = _unique_refs([ref for block in page.get("blocks", []) or [] for ref in block.get("source_refs", []) or []])
    animation_refs = _unique_refs(
        [ref for block in page.get("blocks", []) or [] for ref in block.get("animation_refs", []) or []]
    )
    body = "\n".join(f"- {text}" for text in texts)
    evidence_text = _clip(
        (
            f"页码: {page.get('number')}\n"
            f"页标题: {page.get('title') or ''}\n"
            f"文本证据:\n{body}"
        ),
        max_chars,
    )
    return {
        "mode": "whole_page",
        "page_number": int(page.get("number") or 0),
        "blocks": page.get("blocks", []) or [],
        "evidence_text": evidence_text,
        "context_text": evidence_text,
        "source_refs": source_refs,
        "animation_refs": animation_refs,
        "estimated_token_count": max(1, math.ceil(len(evidence_text) / 2)),
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
        f"来源短标: {refs}"
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


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = " ".join(value.lower().split())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
