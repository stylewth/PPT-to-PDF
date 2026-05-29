from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from ai_explainer import DEFAULT_MODEL, _response_format_for_provider
from ai_provider import call_openai_compatible


PROMPT_VERSION = "v6b-2026-05-25"
Provider = Callable[[dict[str, Any], str], Any]
INTERNAL_REF_RE = re.compile(r"\b[A-Za-z_]+@p\d+#[^\s，。；;、）)]+")

AI_PDF_EDITOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "target_kind",
                    "target_id",
                    "include_in_pdf",
                    "priority",
                    "pdf_title",
                    "pdf_snippet",
                    "importance_reason",
                    "drop_reason",
                    "layout_intent",
                    "source_refs",
                ],
                "properties": {
                    "target_kind": {"type": "string", "enum": ["block", "page"]},
                    "target_id": {"type": "string"},
                    "include_in_pdf": {"type": "boolean"},
                    "priority": {"type": "integer"},
                    "pdf_title": {"type": "string"},
                    "pdf_snippet": {"type": "string"},
                    "importance_reason": {"type": "string"},
                    "drop_reason": {"type": "string"},
                    "layout_intent": {
                        "type": "string",
                        "enum": ["blank_note", "margin_note", "callout"],
                    },
                    "source_refs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["kind", "slide", "object_id", "block_id"],
                            "properties": {
                                "kind": {"type": "string"},
                                "slide": {"type": ["integer", "null"]},
                                "object_id": {"type": ["string", "null"]},
                                "block_id": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
            },
        }
    },
}


def edit_explanations_for_pdf(
    knowledge_blocks: dict[str, Any],
    selected_explanations: list[dict[str, Any]],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    provider: Provider | None = None,
    cache_dir: str | Path | None = None,
    max_snippet_chars: int = 120,
    max_items_per_page: int = 3,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("API key is required.")
    if not isinstance(selected_explanations, list) or not selected_explanations:
        raise ValueError("explanations must be a non-empty list.")

    target_map = _target_map(knowledge_blocks)
    cards = [_normalize_selected_card(item, target_map) for item in selected_explanations]
    cache_key = _cache_key(model, base_url, cards, max_snippet_chars, max_items_per_page)
    cache_path = _cache_path(cache_dir, cache_key)
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {**cached, "from_cache": True}

    payload = _build_payload(
        model,
        cards,
        base_url=base_url,
        max_snippet_chars=max_snippet_chars,
        max_items_per_page=max_items_per_page,
    )
    raw_response = provider(payload, api_key) if provider else call_openai_compatible(payload, api_key, base_url=base_url)
    response = _parse_response(raw_response)
    decisions = _normalize_decisions(
        response,
        cards,
        max_snippet_chars=max_snippet_chars,
        max_items_per_page=max_items_per_page,
    )
    export_explanations = [_decision_to_export_item(decision) for decision in decisions]
    result = {
        "status": "ok",
        "kind": "ai_pdf_editor",
        "version": PROMPT_VERSION,
        "model": model,
        "cache_key": cache_key,
        "decisions": decisions,
        "export_explanations": export_explanations,
        "usage": {
            "selected_card_count": len(cards),
            "included_count": sum(1 for item in decisions if item["include_in_pdf"]),
            "dropped_count": sum(1 for item in decisions if not item["include_in_pdf"]),
        },
        "from_cache": False,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _build_payload(
    model: str,
    cards: list[dict[str, Any]],
    *,
    base_url: str | None,
    max_snippet_chars: int,
    max_items_per_page: int,
) -> dict[str, Any]:
    text = (
        "你是 AI PDF 编辑 Agent。用户已经勾选了想考虑进入 PDF 的讲解卡。"
        "用户勾选就是进入 PDF 的明确意图，你不能否决这些选择。"
        "你的任务不是继续长篇讲解，而是替用户做复习版 PDF 编辑：压缩、排序、建议融入方式。\n"
        f"硬约束：每条 pdf_snippet 最多 {max_snippet_chars} 个中文字符；每页最多 {max_items_per_page} 条；"
        "不要把完整解释原文直接放进 PDF；不要输出内部来源短标；不要编造来源。"
        "用户界面默认不展示 reason，但后端会把 importance_reason/drop_reason 写入调试数据。\n"
        "layout_intent 只能从 blank_note、margin_note、callout 中选。"
        "有安全空白时优先 blank_note/margin_note；不要建议追加解释页，放不下由系统同页扩展画布或显式报错。"
        "除非来源引用无法支撑内容，否则 include_in_pdf 必须为 true，不能因为重复原文或低价值而 drop。\n"
        "只返回一个 JSON 对象，字段为 items。每个 item 必须复制 target_kind、target_id 和可用 source_refs 中的 JSON 来源；"
        "schema 要求但来源里没有的 object_id 或 block_id 填 null。\n\n"
        f"已选讲解卡 JSON: {json.dumps(cards, ensure_ascii=False)}"
    )
    return {
        "model": model,
        "temperature": 0.1,
        "response_format": _editor_response_format(model, base_url),
        "messages": [
            {"role": "system", "content": "你是严格的 PDF 编辑 Agent，只输出合法 JSON。"},
            {"role": "user", "content": text},
        ],
    }


def _editor_response_format(model: str, base_url: str | None) -> dict[str, Any]:
    base = _response_format_for_provider(model, base_url)
    if base.get("type") != "json_schema":
        return base
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "slide2study_ai_pdf_editor",
            "strict": True,
            "schema": AI_PDF_EDITOR_SCHEMA,
        },
    }


def _normalize_selected_card(item: dict[str, Any], target_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Each selected explanation must be an object.")
    target_kind = "page" if item.get("page_number") else "block"
    target_id = f"page_{int(item.get('page_number'))}" if target_kind == "page" else str(item.get("block_id") or "")
    if target_id not in target_map:
        raise ValueError(f"Unknown PDF edit target: {target_id}")
    explanation = item.get("explanation") or {}
    if not isinstance(explanation, dict):
        raise ValueError(f"Explanation for {target_id} must be an object.")
    target = target_map[target_id]
    return {
        "target_kind": target_kind,
        "target_id": target_id,
        "block_id": target.get("block_id"),
        "page_number": target.get("page_number"),
        "title": target.get("title") or target_id,
        "summary": target.get("summary") or "",
        "prompt_profile": explanation.get("prompt_profile") or item.get("prompt_profile") or "study",
        "full_explanation": _plain_explanation_text(explanation),
        "source_refs": target["source_refs"],
    }


def _target_map(knowledge_blocks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for slide in knowledge_blocks.get("slides", []) or []:
        page_number = int(slide.get("number") or 0)
        page_refs: list[Any] = []
        for block in slide.get("blocks", []) or []:
            block_id = str(block.get("id") or "")
            refs = _unique_refs(block.get("source_refs", []) or [])
            page_refs.extend(refs)
            if block_id:
                result[block_id] = {
                    "target_kind": "block",
                    "target_id": block_id,
                    "block_id": block_id,
                    "page_number": page_number,
                    "title": block.get("title") or block_id,
                    "summary": block.get("summary") or "",
                    "source_refs": refs,
                }
        if page_number:
            result[f"page_{page_number}"] = {
                "target_kind": "page",
                "target_id": f"page_{page_number}",
                "block_id": f"page_{page_number}",
                "page_number": page_number,
                "title": slide.get("title") or f"第 {page_number} 页",
                "summary": "",
                "source_refs": _unique_refs(page_refs),
            }
    return result


def _normalize_decisions(
    response: dict[str, Any],
    cards: list[dict[str, Any]],
    *,
    max_snippet_chars: int,
    max_items_per_page: int,
) -> list[dict[str, Any]]:
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("AI PDF 编辑结果必须包含 items 数组。")
    card_map = {card["target_id"]: card for card in cards}
    per_page_count: dict[int, int] = {}
    seen_targets: set[str] = set()
    decisions: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("AI PDF 编辑 item 必须是对象。")
        target_id = str(raw.get("target_id") or "")
        card = card_map.get(target_id)
        if not card:
            raise ValueError(f"Unknown PDF edit target: {target_id}")
        seen_targets.add(target_id)
        include = True
        snippet = str(raw.get("pdf_snippet") or "").strip()
        if not snippet:
            snippet = _fallback_pdf_snippet(card, max_snippet_chars)
        if len(snippet) > max_snippet_chars:
            raise ValueError(f"pdf_snippet for {target_id} exceeds {max_snippet_chars} chars.")
        if INTERNAL_REF_RE.search(snippet):
            raise ValueError("PDF 短稿不能包含内部来源短标。")
        page_number = int(card.get("page_number") or 0)
        per_page_count[page_number] = per_page_count.get(page_number, 0) + 1
        if per_page_count[page_number] > max_items_per_page:
            raise ValueError(f"Page {page_number} exceeds AI PDF snippet budget.")
        source_refs = _validate_refs(raw.get("source_refs"), card["source_refs"], target_id)
        decision = {
            "target_kind": card["target_kind"],
            "target_id": target_id,
            "block_id": card["block_id"],
            "page_number": card["page_number"],
            "prompt_profile": card["prompt_profile"],
            "include_in_pdf": include,
            "priority": int(raw.get("priority") or 99),
            "pdf_title": str(raw.get("pdf_title") or card["title"]).strip(),
            "pdf_snippet": snippet,
            "importance_reason": str(raw.get("importance_reason") or "").strip(),
            "drop_reason": "",
            "layout_intent": _normalize_layout_intent(raw.get("layout_intent"), include),
            "source_refs": source_refs,
        }
        decisions.append(decision)
    for card in cards:
        target_id = str(card["target_id"])
        if target_id in seen_targets:
            continue
        snippet = _fallback_pdf_snippet(card, max_snippet_chars)
        page_number = int(card.get("page_number") or 0)
        per_page_count[page_number] = per_page_count.get(page_number, 0) + 1
        if per_page_count[page_number] > max_items_per_page:
            raise ValueError(f"Page {page_number} exceeds AI PDF snippet budget.")
        decisions.append(
            {
                "target_kind": card["target_kind"],
                "target_id": target_id,
                "block_id": card["block_id"],
                "page_number": card["page_number"],
                "prompt_profile": card["prompt_profile"],
                "include_in_pdf": True,
                "priority": 99,
                "pdf_title": str(card.get("title") or target_id).strip(),
                "pdf_snippet": snippet,
                "importance_reason": "",
                "drop_reason": "",
                "layout_intent": "margin_note",
                "source_refs": [_normalize_ref(ref) for ref in card["source_refs"]],
            }
        )
    decisions.sort(key=lambda item: (int(item.get("page_number") or 0), int(item.get("priority") or 99)))
    return decisions


def _decision_to_export_item(decision: dict[str, Any]) -> dict[str, Any]:
    explanation = {
        "short_explanation": decision["pdf_snippet"],
        "detail": "",
        "sections": [],
        "pdf_title": decision["pdf_title"],
        "pdf_snippet": decision["pdf_snippet"],
        "layout_intent": decision["layout_intent"],
        "source_refs": decision["source_refs"],
    }
    item: dict[str, Any] = {
        "include_in_pdf": decision["include_in_pdf"],
        "drop_reason": decision["drop_reason"],
        "layout_intent": decision["layout_intent"],
        "explanation": explanation,
    }
    if decision["target_kind"] == "page":
        item["page_number"] = decision["page_number"]
    else:
        item["block_id"] = decision["block_id"]
    return item


def _validate_refs(refs: Any, valid_refs: list[Any], target_id: str) -> list[dict[str, Any]]:
    if not isinstance(refs, list) or not refs:
        raise ValueError(f"source_refs is required for {target_id}.")
    valid = {_canonical_ref(ref) for ref in valid_refs}
    normalized_refs = []
    for ref in refs:
        normalized = _normalize_ref(ref)
        if not normalized or _canonical_ref(normalized) not in valid:
            raise ValueError(f"Invalid source ref for {target_id}: {ref}")
        normalized_refs.append(normalized)
    return normalized_refs


def _normalize_layout_intent(value: Any, include: bool) -> str:
    intent = str(value or "").strip()
    allowed = {"blank_note", "margin_note", "callout"}
    if intent not in allowed:
        intent = "margin_note"
    if not include:
        return "drop"
    return intent


def _fallback_pdf_snippet(card: dict[str, Any], max_snippet_chars: int) -> str:
    for line in str(card.get("full_explanation") or "").splitlines():
        snippet = " ".join(line.split())
        if not snippet:
            continue
        if INTERNAL_REF_RE.search(snippet):
            continue
        return snippet[:max_snippet_chars]
    raise ValueError(f"pdf_snippet is required for {card['target_id']}.")


def _plain_explanation_text(explanation: dict[str, Any]) -> str:
    parts = [
        explanation.get("short_explanation"),
        explanation.get("detail"),
    ]
    for section in explanation.get("sections") or []:
        if isinstance(section, dict):
            parts.append(section.get("label"))
            items = section.get("items")
            if isinstance(items, list):
                parts.extend(items)
            else:
                parts.append(items)
    for key in ("key_points", "common_misunderstanding", "review_questions"):
        value = explanation.get(key)
        if isinstance(value, list):
            parts.extend(value)
        else:
            parts.append(value)
    return "\n".join(str(part) for part in parts if part not in (None, ""))


def _parse_response(raw_response: Any) -> dict[str, Any]:
    if isinstance(raw_response, dict) and "choices" in raw_response:
        content = raw_response["choices"][0]["message"]["content"]
        return _ensure_response_object(json.loads(content))
    if isinstance(raw_response, str):
        return _ensure_response_object(json.loads(raw_response))
    if isinstance(raw_response, dict):
        return _ensure_response_object(raw_response)
    raise ValueError("AI provider returned unsupported response.")


def _ensure_response_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("AI PDF 编辑输出必须是单个 JSON 对象。")
    return value


def _unique_refs(refs: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for ref in refs:
        normalized = _normalize_ref(ref)
        key = _canonical_ref(normalized)
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _canonical_ref(ref: Any) -> str:
    normalized = _normalize_ref(ref)
    return json.dumps(normalized or ref, ensure_ascii=False, sort_keys=True)


def _normalize_ref(ref: Any) -> dict[str, Any] | None:
    if isinstance(ref, str):
        match = re.fullmatch(r"([A-Za-z_]+)@p(\d+)#(.+)", ref.strip())
        if not match:
            return None
        return {"kind": match.group(1), "slide": int(match.group(2)), "object_id": match.group(3)}
    if not isinstance(ref, dict):
        return None
    kind = str(ref.get("kind") or "")
    if not kind:
        return None
    normalized: dict[str, Any] = {"kind": kind}
    if "slide" in ref:
        value = ref.get("slide")
        normalized["slide"] = None if value is None else int(value)
    if ref.get("object_id") is not None:
        normalized["object_id"] = str(ref.get("object_id"))
    if ref.get("block_id") is not None:
        normalized["block_id"] = str(ref.get("block_id"))
    return normalized


def _cache_key(
    model: str,
    base_url: str | None,
    cards: list[dict[str, Any]],
    max_snippet_chars: int,
    max_items_per_page: int,
) -> str:
    stable = {
        "version": PROMPT_VERSION,
        "model": model,
        "base_url": base_url or "",
        "max_snippet_chars": max_snippet_chars,
        "max_items_per_page": max_items_per_page,
        "cards": cards,
    }
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _cache_path(cache_dir: str | Path | None, cache_key: str) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / f"pdf_editor_{cache_key}.json"
