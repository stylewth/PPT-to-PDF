from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz


PROMPT_VERSION = "v5a"


def export_ai_guide_pdf(
    guide_pdf_path: str | Path,
    knowledge_blocks: dict[str, Any],
    explanations: list[dict[str, Any]],
    output_dir: str | Path,
) -> Path:
    guide_path = Path(guide_pdf_path)
    output = Path(output_dir)
    if not guide_path.exists():
        raise FileNotFoundError(f"Guide PDF not found: {guide_path}")
    normalized = _normalize_explanations(knowledge_blocks, explanations)
    if not normalized:
        raise ValueError("No valid AI explanations to export.")

    by_page: dict[int, list[dict[str, Any]]] = {}
    for item in normalized:
        by_page.setdefault(int(item["slide_number"]), []).append(item)

    output.mkdir(parents=True, exist_ok=True)
    ai_pdf_path = output / "ai_guide.pdf"
    manifest_pages: list[dict[str, Any]] = []
    result = fitz.open()
    source = fitz.open(guide_path)
    try:
        for source_index in range(source.page_count):
            source_page_number = source_index + 1
            result.insert_pdf(source, from_page=source_index, to_page=source_index)
            page_explanations = by_page.get(source_page_number, [])
            if not page_explanations:
                continue
            explanation_page_number = result.page_count + 1
            _append_explanation_page(result, source[source_index].rect, source_page_number, page_explanations)
            manifest_pages.append(
                {
                    "source_page": source_page_number,
                    "explanation_page": explanation_page_number,
                    "block_ids": [item["block_id"] for item in page_explanations],
                }
            )
        result.save(ai_pdf_path)
    finally:
        source.close()
        result.close()

    manifest = {
        "kind": "ai_guide_manifest",
        "version": PROMPT_VERSION,
        "pdf": "ai_guide.pdf",
        "source_pdf": guide_path.name,
        "pages": manifest_pages,
        "explanation_count": sum(len(items) for items in by_page.values()),
    }
    (output / "ai_guide_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ai_pdf_path


def _normalize_explanations(
    knowledge_blocks: dict[str, Any],
    explanations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    block_map = _block_map(knowledge_blocks)
    page_map = _page_map(knowledge_blocks)
    normalized = []
    for item in explanations:
        if not isinstance(item, dict):
            raise ValueError("Each explanation item must be an object.")
        block_id = str(item.get("block_id") or "")
        page_number = int(item.get("page_number") or 0)
        if not block_id and page_number:
            page = page_map.get(page_number)
            if not page:
                raise ValueError(f"Unknown page number: {page_number}")
            explanation = item.get("explanation") or item
            if not isinstance(explanation, dict):
                raise ValueError(f"Explanation for page {page_number} must be an object.")
            page_block = {
                "id": f"page_{page_number}",
                "slide_number": page_number,
                "title": "Whole page",
                "type": "whole_page",
                "source_refs": page["source_refs"],
            }
            _validate_sources(page_block, explanation)
            normalized.append(
                {
                    "block_id": f"page_{page_number}",
                    "slide_number": page_number,
                    "block_title": "Whole page",
                    "block_type": "whole_page",
                    "explanation": explanation,
                }
            )
            continue
        if not block_id or block_id not in block_map:
            raise ValueError(f"Unknown block id: {block_id}")
        block = block_map[block_id]
        explanation = item.get("explanation") or item
        if not isinstance(explanation, dict):
            raise ValueError(f"Explanation for {block_id} must be an object.")
        _validate_sources(block, explanation)
        normalized.append(
            {
                "block_id": block_id,
                "slide_number": int(block["slide_number"]),
                "block_title": block.get("title") or block_id,
                "block_type": block.get("type") or "",
                "explanation": explanation,
            }
        )
    return normalized


def _page_map(knowledge_blocks: dict[str, Any]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for slide in knowledge_blocks.get("slides", []) or []:
        slide_number = int(slide.get("number") or 0)
        source_refs: list[Any] = []
        for block in slide.get("blocks", []) or []:
            source_refs.extend(block.get("source_refs", []) or [])
        if slide_number:
            result[slide_number] = {
                "slide_number": slide_number,
                "title": slide.get("title") or f"Page {slide_number}",
                "source_refs": _unique_refs(source_refs),
            }
    return result


def _block_map(knowledge_blocks: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for slide in knowledge_blocks.get("slides", []) or []:
        slide_number = int(slide.get("number") or 0)
        for block in slide.get("blocks", []) or []:
            block_id = str(block.get("id") or "")
            if block_id:
                result[block_id] = {"slide_number": slide_number, **block}
    return result


def _unique_refs(refs: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for ref in refs:
        key = _canonical_ref(ref)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _validate_sources(block: dict[str, Any], explanation: dict[str, Any]) -> None:
    source_refs = explanation.get("source_refs") or []
    if not isinstance(source_refs, list) or not source_refs:
        raise ValueError(f"Explanation for {block.get('id')} has no source_refs.")
    valid = {_canonical_ref(ref) for ref in block.get("source_refs", []) or []}
    for ref in source_refs:
        if _canonical_ref(ref) not in valid:
            raise ValueError(f"Invalid source ref for {block.get('id')}: {ref}")


def _append_explanation_page(
    result: fitz.Document,
    source_rect: fitz.Rect,
    source_page_number: int,
    page_explanations: list[dict[str, Any]],
) -> None:
    page = result.new_page(width=source_rect.width, height=source_rect.height)
    margin = 42
    y = 42
    line_height = 15
    max_width_chars = max(42, int((source_rect.width - margin * 2) / 7))
    _draw_line(page, (margin, y), f"AI Explanation · Page {source_page_number}", 16, bold=True)
    y += 28
    _draw_line(page, (margin, y), "This page is generated from selected knowledge blocks and keeps the original guide.pdf unchanged.", 9)
    y += 24
    for index, item in enumerate(page_explanations, start=1):
        title = f"{index}. {item['block_title']} ({item['block_id']})"
        _draw_line(page, (margin, y), title, 12, bold=True)
        y += 19
        for line in _explanation_lines(item["explanation"], max_width_chars):
            if y > source_rect.height - 48:
                _draw_line(page, (margin, source_rect.height - 30), "Continued on next AI page.", 8)
                page = result.new_page(width=source_rect.width, height=source_rect.height)
                y = 42
                _draw_line(page, (margin, y), f"AI Explanation · Page {source_page_number} continued", 16, bold=True)
                y += 28
            _draw_line(page, (margin, y), line, 10)
            y += line_height
        y += 12


def _explanation_lines(explanation: dict[str, Any], max_chars: int) -> list[str]:
    parts: list[str] = []
    if explanation.get("short_explanation"):
        parts.append(f"Summary: {explanation.get('short_explanation')}")
    if explanation.get("detail"):
        parts.append(f"Detail: {explanation.get('detail')}")
    sections = _as_sections(explanation.get("sections"))
    if sections:
        for section in sections:
            for value in section["items"]:
                parts.append(f"{section['label']}: {value}")
    else:
        for label, field in (("Key point", "key_points"), ("Misunderstanding", "common_misunderstanding"), ("Review", "review_questions")):
            values = _as_list(explanation.get(field))
            for value in values:
                parts.append(f"{label}: {value}")
    lines: list[str] = []
    for part in parts:
        lines.extend(_wrap_text(str(part), max_chars))
    return lines


def _draw_line(page: fitz.Page, point: tuple[float, float], text: str, size: int, *, bold: bool = False) -> None:
    font_file = _font_file_for_text(text)
    font = "slide2study-cjk" if font_file else _font_for_text(text)
    page.insert_text(
        point,
        text,
        fontsize=size,
        fontname=font,
        fontfile=font_file,
        color=(0.07, 0.13, 0.1),
        render_mode=0,
    )
    if bold:
        x, y = point
        page.draw_line((x, y + 2), (x + min(len(text) * size * 0.38, page.rect.width - x - 42), y + 2), color=(0.08, 0.32, 0.23), width=0.6)


def _font_for_text(text: str) -> str:
    if re.search(r"[\u3400-\u9fff]", text):
        return "china-s"
    return "helv"


def _font_file_for_text(text: str) -> str | None:
    if not re.search(r"[\u3400-\u9fff]", text):
        return None
    for candidate in (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _wrap_text(text: str, max_chars: int) -> list[str]:
    value = " ".join(str(text or "").split())
    if not value:
        return []
    lines = []
    current = ""
    for token in value.split(" "):
        if not current:
            current = token
            continue
        if len(current) + 1 + len(token) <= max_chars:
            current += " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [value]


def _as_sections(value: Any) -> list[dict[str, list[Any]]]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        raw_sections = [{"label": label, "items": items} for label, items in value.items()]
    elif isinstance(value, list):
        raw_sections = value
    else:
        raw_sections = [{"label": "Section", "items": value}]
    sections: list[dict[str, list[Any]]] = []
    for section in raw_sections:
        if isinstance(section, dict):
            label = str(section.get("label") or section.get("title") or "").strip()
            items = _as_list(section.get("items") if "items" in section else section.get("text"))
        else:
            label = "Section"
            items = _as_list(section)
        if label and items:
            sections.append({"label": label, "items": items})
    return sections


def _canonical_ref(ref: Any) -> str:
    if isinstance(ref, str):
        return ref
    if not isinstance(ref, dict):
        return ""
    normalized = {"kind": str(ref.get("kind") or "")}
    if "slide" in ref:
        normalized["slide"] = int(ref.get("slide") or 0)
    if ref.get("object_id") is not None:
        normalized["object_id"] = str(ref.get("object_id"))
    if ref.get("block_id") is not None:
        normalized["block_id"] = str(ref.get("block_id"))
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)

