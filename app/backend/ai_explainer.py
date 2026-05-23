from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ai_audit import audit_ai_explanation
from ai_context import build_ai_context
from ai_provider import call_openai_compatible


PROMPT_VERSION = "v4a-2026-05-22"
DEFAULT_MODEL = "gpt-4.1-mini"
Provider = Callable[[dict[str, Any], str], Any]


def explain_blocks(
    knowledge_blocks: dict[str, Any],
    block_ids: list[str],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    mode: str = "explain",
    provider: Provider | None = None,
    cache_dir: str | Path | None = None,
    max_chars: int = 1500,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("API key is required.")

    context = build_ai_context(knowledge_blocks, block_ids, mode=mode, max_chars=max_chars)
    cache_key = cache_key_for_request(model, mode, context)
    cache_path = _cache_path(cache_dir, cache_key)
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {**cached, "from_cache": True}

    payload = _build_payload(model, mode, context)
    raw_response = provider(payload, api_key) if provider else call_openai_compatible(payload, api_key, base_url=base_url)
    explanation = _parse_response(raw_response)
    explanation = _normalize_explanation(explanation)
    audit = audit_ai_explanation(explanation, context["source_refs"])
    if not audit["passed"]:
        raise ValueError("; ".join(audit["errors"]))

    result = {
        "status": "ok",
        "model": model,
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "cache_key": cache_key,
        "context_block_ids": block_ids,
        "explanation": explanation,
        "audit": audit,
        "usage": {
            "estimated_context_tokens": context["estimated_token_count"],
            "selected_block_count": len(context["blocks"]),
        },
        "from_cache": False,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def cache_key_for_request(
    model: str,
    mode: str,
    context: dict[str, Any],
    *,
    prompt_version: str = PROMPT_VERSION,
) -> str:
    stable = {
        "model": model,
        "mode": mode,
        "prompt_version": prompt_version,
        "blocks": [
            {
                "id": block.get("id"),
                "type": block.get("type"),
                "title": block.get("title"),
                "summary": block.get("summary"),
                "texts": block.get("texts", []),
                "source_refs": block.get("source_refs", []),
            }
            for block in context.get("blocks", [])
        ],
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_payload(model: str, mode: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是课件学习 Agent。只解释用户选中的知识块；"
                    "不得补充来源之外的事实；所有结论必须带 source_refs。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"模式: {mode}\n"
                    f"请只返回一个 JSON 对象，不要返回数组。字段包含 block_id, short_explanation, detail, "
                    f"key_points, common_misunderstanding, review_questions, "
                    f"source_refs, missing_context, confidence。source_refs 必须从可用来源 JSON 中复制，"
                    f"不要编造新 object_id。\n"
                    f"可用来源 JSON: {json.dumps(context['source_refs'], ensure_ascii=False)}\n\n"
                    f"证据:\n{context['context_text']}"
                ),
            },
        ],
    }


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
        raise ValueError("AI 输出必须是单个 JSON 对象，不能是数组或普通文本。")
    return value


def _normalize_explanation(explanation: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(explanation)
    for field in ("key_points", "common_misunderstanding", "review_questions", "missing_context"):
        normalized[field] = _as_list(normalized.get(field))
    return normalized


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        for key in ("question", "text", "value"):
            if value.get(key):
                return [value[key]]
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    return [value]


def _cache_path(cache_dir: str | Path | None, cache_key: str) -> Path | None:
    if cache_dir is None:
        return None
    return Path(cache_dir) / f"{cache_key}.json"
