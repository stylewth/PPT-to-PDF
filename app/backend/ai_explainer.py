from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from ai_audit import audit_ai_explanation
from ai_context import build_ai_context, build_whole_page_context
from ai_provider import call_openai_compatible


PROMPT_VERSION = "v5d-2026-05-24"
DEFAULT_MODEL = "gpt-4.1-mini"
Provider = Callable[[dict[str, Any], str], Any]

PROMPT_PROFILES = {
    "study": {
        "system": "你是课件学习 Agent。只解释用户选中的知识块；不得补充来源之外的事实；所有结论必须带 source_refs。",
        "style": "学习讲义版：解释概念、公式关系、动画意图、易错点和复习问题，适合学生课后复习。",
        "sections": ["学习要点", "易错点", "复习题"],
    },
    "training": {
        "system": "你是工作培训 Agent。只基于课件证据提炼培训要点、操作流程、风险提醒和适用场景；所有结论必须带 source_refs。",
        "style": "工作培训版：面向员工培训，突出流程步骤、执行动作、注意事项、风险和培训要点。",
        "sections": ["培训目标", "操作步骤", "风险提醒", "执行清单"],
    },
    "simple": {
        "system": "你是简单解释 Agent。只基于课件证据，用简洁语言让用户一眼明了；所有结论必须带 source_refs。",
        "style": "简单解释版：简洁、一眼明了，少术语，优先给一句话解释和三个以内关键点，不做长篇展开。",
        "sections": ["关键点", "看图提示"],
    },
}


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
    prompt_profile: str = "study",
    visual_inputs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("API key is required.")

    context = build_ai_context(knowledge_blocks, block_ids, mode=mode, max_chars=max_chars)
    cache_key = cache_key_for_request(model, mode, context, prompt_profile=prompt_profile, visual_inputs=visual_inputs)
    cache_path = _cache_path(cache_dir, cache_key)
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {**cached, "from_cache": True}

    payload = _build_payload(model, mode, context, prompt_profile=prompt_profile, visual_inputs=visual_inputs)
    raw_response = provider(payload, api_key) if provider else call_openai_compatible(payload, api_key, base_url=base_url)
    explanation = _parse_response(raw_response)
    explanation = _normalize_explanation(explanation, prompt_profile=prompt_profile)
    audit = audit_ai_explanation(explanation, context["source_refs"])
    if not audit["passed"]:
        raise ValueError("; ".join(audit["errors"]))

    result = {
        "status": "ok",
        "model": model,
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "prompt_profile": _normalize_prompt_profile(prompt_profile),
        "cache_key": cache_key,
        "context_block_ids": block_ids,
        "explanation": explanation,
        "audit": audit,
        "usage": {
            "estimated_context_tokens": context["estimated_token_count"],
            "selected_block_count": len(context["blocks"]),
            "visual_input_count": len(visual_inputs or []),
        },
        "from_cache": False,
    }
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def explain_page(
    page: dict[str, Any],
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    base_url: str | None = None,
    provider: Provider | None = None,
    cache_dir: str | Path | None = None,
    max_chars: int = 3000,
    prompt_profile: str = "study",
    visual_inputs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("API key is required.")

    mode = "whole_page"
    context = build_whole_page_context(page, max_chars=max_chars)
    block_ids = [str(block.get("id")) for block in context.get("blocks", []) if str(block.get("id") or "")]
    cache_key = cache_key_for_request(model, mode, context, prompt_profile=prompt_profile, visual_inputs=visual_inputs)
    cache_path = _cache_path(cache_dir, cache_key)
    if cache_path and cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return {**cached, "from_cache": True}

    payload = _build_payload(model, mode, context, prompt_profile=prompt_profile, visual_inputs=visual_inputs)
    raw_response = provider(payload, api_key) if provider else call_openai_compatible(payload, api_key, base_url=base_url)
    explanation = _parse_response(raw_response)
    explanation = _normalize_explanation(explanation, prompt_profile=prompt_profile)
    audit = audit_ai_explanation(explanation, context["source_refs"])
    if not audit["passed"]:
        raise ValueError("; ".join(audit["errors"]))

    result = {
        "status": "ok",
        "model": model,
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "prompt_profile": _normalize_prompt_profile(prompt_profile),
        "cache_key": cache_key,
        "context_block_ids": block_ids,
        "explanation": explanation,
        "audit": audit,
        "usage": {
            "estimated_context_tokens": context["estimated_token_count"],
            "selected_block_count": len(block_ids),
            "visual_input_count": len(visual_inputs or []),
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
    prompt_profile: str = "study",
    visual_inputs: list[dict[str, str]] | None = None,
) -> str:
    stable = {
        "model": model,
        "mode": mode,
        "prompt_version": prompt_version,
        "prompt_profile": _normalize_prompt_profile(prompt_profile),
        "visual_inputs": [
            {
                "label": visual.get("label"),
                "data_hash": hashlib.sha256(str(visual.get("data_url") or "").encode("utf-8")).hexdigest(),
            }
            for visual in visual_inputs or []
        ],
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


def _build_payload(
    model: str,
    mode: str,
    context: dict[str, Any],
    *,
    prompt_profile: str = "study",
    visual_inputs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    profile = PROMPT_PROFILES[_normalize_prompt_profile(prompt_profile)]
    section_labels = "、".join(profile["sections"])
    text_content = (
        f"模式: {mode}\n"
        f"角色: {_normalize_prompt_profile(prompt_profile)}\n"
        f"输出风格: {profile['style']}\n"
        f"请只返回一个 JSON 对象，不要返回数组。字段包含 block_id, short_explanation, detail, "
        f"sections, source_refs, missing_context, confidence。sections 是数组，每项包含 label 和 items；"
        f"本角色只使用这些 section label：{section_labels}。source_refs 必须从可用来源 JSON 中复制，"
        f"不要编造新 object_id；不要输出本角色以外的栏目。\n"
        f"可用来源 JSON: {json.dumps(context['source_refs'], ensure_ascii=False)}\n\n"
        f"证据:\n{context['context_text']}"
    )
    user_content: str | list[dict[str, Any]] = text_content
    if visual_inputs:
        user_content = [{"type": "text", "text": text_content}]
        for visual in visual_inputs:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": visual["data_url"]},
                }
            )
    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": profile["system"],
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
    }


def _normalize_prompt_profile(prompt_profile: str) -> str:
    value = str(prompt_profile or "study").strip()
    return value if value in PROMPT_PROFILES else "study"


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


def _normalize_explanation(explanation: dict[str, Any], *, prompt_profile: str = "study") -> dict[str, Any]:
    normalized = dict(explanation)
    normalized["sections"] = _normalize_sections(normalized.get("sections"))
    if not normalized["sections"]:
        normalized["sections"] = _legacy_sections(normalized, prompt_profile)
    for field in ("key_points", "common_misunderstanding", "review_questions", "missing_context"):
        normalized[field] = _as_list(normalized.get(field))
    return normalized


def _normalize_sections(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    sections: list[dict[str, Any]] = []
    if isinstance(value, dict):
        iterable = [{"label": label, "items": items} for label, items in value.items()]
    elif isinstance(value, list):
        iterable = value
    else:
        iterable = [{"label": "说明", "items": value}]
    for section in iterable:
        if isinstance(section, dict):
            label = str(section.get("label") or section.get("title") or "").strip()
            items = _as_list(section.get("items") if "items" in section else section.get("text"))
        else:
            label = "说明"
            items = _as_list(section)
        if label and items:
            sections.append({"label": label, "items": items})
    return sections


def _legacy_sections(explanation: dict[str, Any], prompt_profile: str) -> list[dict[str, Any]]:
    profile = _normalize_prompt_profile(prompt_profile)
    if profile == "study":
        pairs = (
            ("学习要点", explanation.get("key_points")),
            ("易错点", explanation.get("common_misunderstanding")),
            ("复习题", explanation.get("review_questions")),
        )
    elif profile == "training":
        pairs = (
            ("培训目标", explanation.get("training_goals")),
            ("培训要点", explanation.get("training_points") or explanation.get("key_points")),
            ("操作步骤", explanation.get("action_steps")),
            ("风险提醒", explanation.get("risk_warnings") or explanation.get("common_misunderstanding")),
            ("执行清单", explanation.get("execution_checklist") or explanation.get("review_questions")),
        )
    else:
        pairs = (
            ("关键点", explanation.get("key_points") or explanation.get("quick_points")),
            ("看图提示", explanation.get("visual_hint")),
        )
    return [{"label": label, "items": items} for label, raw in pairs if (items := _as_list(raw))]


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
