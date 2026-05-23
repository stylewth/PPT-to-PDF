from __future__ import annotations

import json
import re
from typing import Any


REQUIRED_FIELDS = {
    "block_id",
    "short_explanation",
    "detail",
    "key_points",
    "common_misunderstanding",
    "review_questions",
    "source_refs",
    "missing_context",
    "confidence",
}


def audit_ai_explanation(explanation: dict[str, Any], valid_refs: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    if not isinstance(explanation, dict):
        return {
            "kind": "ai_audit",
            "version": "v4a",
            "passed": False,
            "errors": ["AI 输出必须是单个 JSON 对象。"],
            "valid_ref_count": len(valid_refs),
        }
    missing_fields = sorted(REQUIRED_FIELDS - set(explanation))
    if missing_fields:
        errors.append(f"Missing fields: {', '.join(missing_fields)}")

    source_refs = explanation.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        errors.append("source_refs is required.")
        source_refs = []

    valid_ref_keys = {_canonical_ref(ref) for ref in valid_refs}
    normalized_refs = []
    for ref in source_refs:
        normalized = _normalize_ref(ref)
        if not normalized or _canonical_ref(normalized) not in valid_ref_keys:
            errors.append(f"Invalid source ref: {ref}")
            continue
        normalized_refs.append(normalized)
    if isinstance(explanation.get("source_refs"), list):
        explanation["source_refs"] = normalized_refs

    return {
        "kind": "ai_audit",
        "version": "v4a",
        "passed": not errors,
        "errors": errors,
        "valid_ref_count": len(valid_ref_keys),
    }


def _canonical_ref(ref: dict[str, Any]) -> str:
    normalized = _normalize_ref(ref)
    return json.dumps(normalized or ref, ensure_ascii=False, sort_keys=True)


def _normalize_ref(ref: Any) -> dict[str, Any] | None:
    if isinstance(ref, str):
        match = re.fullmatch(r"([A-Za-z_]+)@p(\d+)#(.+)", ref.strip())
        if not match:
            return None
        return {
            "kind": match.group(1),
            "slide": int(match.group(2)),
            "object_id": match.group(3),
        }
    if not isinstance(ref, dict):
        return None
    kind = str(ref.get("kind") or "")
    if not kind:
        return None
    normalized: dict[str, Any] = {"kind": kind}
    if "slide" in ref:
        try:
            normalized["slide"] = int(ref.get("slide"))
        except (TypeError, ValueError):
            normalized["slide"] = ref.get("slide")
    if ref.get("object_id") is not None:
        normalized["object_id"] = str(ref.get("object_id"))
    elif ref.get("block_id") is not None:
        normalized["block_id"] = str(ref.get("block_id"))
    return normalized
