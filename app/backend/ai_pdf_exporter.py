from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont


PROMPT_VERSION = "v5b"
NOTE_STYLE_VERSION = "study_note_v2"
NOTE_BORDER = (0.12, 0.35, 0.29)
NOTE_FILL = (0.982, 0.996, 0.974)
NOTE_SHADOW = (0.28, 0.34, 0.31)
NOTE_ACCENT = (0.05, 0.48, 0.37)
NOTE_SIDE_FILL = (0.978, 0.99, 0.982)
NOTE_TEXT = (0.06, 0.12, 0.1)


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
    normalized, dropped = _normalize_explanations(knowledge_blocks, explanations)
    if not normalized:
        raise ValueError("No valid AI explanations to export.")

    page_layouts = _page_layouts(knowledge_blocks)
    by_page: dict[int, list[dict[str, Any]]] = {}
    for item in normalized:
        by_page.setdefault(int(item["slide_number"]), []).append(item)

    output.mkdir(parents=True, exist_ok=True)
    ai_pdf_path = output / "ai_guide.pdf"
    manifest_pages: list[dict[str, Any]] = []
    source = fitz.open(guide_path)
    try:
        for source_index in range(source.page_count):
            source_page_number = source_index + 1
            result_page = source[source_index]
            page_explanations = by_page.get(source_page_number, [])
            if not page_explanations:
                continue
            source_rect = fitz.Rect(result_page.rect)
            inline_items, overflow_items = _place_inline_notes(
                result_page,
                page_layouts.get(source_page_number, {}),
                page_explanations,
            )
            placed_items = [*inline_items]
            if overflow_items:
                placed_items.extend(_place_expanded_margin_notes(result_page, overflow_items, source_rect))
            if placed_items:
                manifest_pages.append(
                    {
                        "source_page": source_page_number,
                        "explanation_page": None,
                        "block_ids": [item["block_id"] for item in placed_items],
                        "layout_modes": [item["placement"]["mode"] for item in placed_items],
                        "placements": [item["placement"] for item in placed_items],
                    }
                )
        source.save(ai_pdf_path, garbage=4, deflate=True)
    finally:
        source.close()

    manifest = {
        "kind": "ai_guide_manifest",
        "version": PROMPT_VERSION,
        "pdf": "ai_guide.pdf",
        "source_pdf": guide_path.name,
        "pages": manifest_pages,
        "explanation_count": sum(len(items) for items in by_page.values()),
        "dropped": dropped,
    }
    (output / "ai_guide_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ai_pdf_path


def _normalize_explanations(
    knowledge_blocks: dict[str, Any],
    explanations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    block_map = _block_map(knowledge_blocks)
    page_map = _page_map(knowledge_blocks)
    normalized = []
    dropped = []
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
            if item.get("include_in_pdf") is False:
                dropped.append(_dropped_item(f"page_{page_number}", page_number, item))
                continue
            export_explanation = _export_explanation(explanation)
            normalized.append(
                {
                    "block_id": f"page_{page_number}",
                    "slide_number": page_number,
                    "block_title": export_explanation.get("pdf_title") or "Whole page",
                    "block_type": "whole_page",
                    "layout_intent": item.get("layout_intent") or export_explanation.get("layout_intent") or "margin_note",
                    "display_bbox": None,
                    "explanation": export_explanation,
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
        if item.get("include_in_pdf") is False:
            dropped.append(_dropped_item(block_id, int(block["slide_number"]), item))
            continue
        export_explanation = _export_explanation(explanation)
        normalized.append(
            {
                "block_id": block_id,
                "slide_number": int(block["slide_number"]),
                "block_title": export_explanation.get("pdf_title") or block.get("title") or block_id,
                "block_type": block.get("type") or "",
                "layout_intent": item.get("layout_intent") or export_explanation.get("layout_intent") or "margin_note",
                "display_bbox": block.get("display_bbox"),
                "explanation": export_explanation,
            }
        )
    return normalized, dropped


def _export_explanation(explanation: dict[str, Any]) -> dict[str, Any]:
    snippet = str(explanation.get("pdf_snippet") or "").strip()
    if not snippet:
        return dict(explanation)
    return {
        **explanation,
        "short_explanation": snippet,
        "detail": "",
        "sections": [],
        "key_points": [],
        "common_misunderstanding": [],
        "review_questions": [],
    }


def _dropped_item(block_id: str, source_page: int, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "source_page": source_page,
        "drop_reason": str(item.get("drop_reason") or "").strip(),
        "layout_intent": "drop",
    }


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


def _page_layouts(knowledge_blocks: dict[str, Any]) -> dict[int, dict[str, Any]]:
    layouts: dict[int, dict[str, Any]] = {}
    for slide in knowledge_blocks.get("slides", []) or []:
        slide_number = int(slide.get("number") or 0)
        if not slide_number:
            continue
        occupied = []
        for block in slide.get("blocks", []) or []:
            bbox = block.get("display_bbox")
            if _is_normalized_bbox(bbox):
                occupied.append(bbox)
        layouts[slide_number] = {"occupied_bboxes": occupied}
    return layouts


def _is_normalized_bbox(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = ("x", "y", "w", "h")
    return all(isinstance(value.get(key), (int, float)) for key in required)


def _place_inline_notes(
    page: fitz.Page,
    page_layout: dict[str, Any],
    page_explanations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    occupied = [_inflate_rect(rect, 6, page.rect) for rect in _rendered_page_rects(page)]
    occupied.extend(
        _inflate_rect(rect, 6, page.rect)
        for rect in (
            _rect_from_normalized_bbox(bbox, page.rect)
            for bbox in page_layout.get("occupied_bboxes", []) or []
        )
        if rect is not None
    )
    inline_items: list[dict[str, Any]] = []
    extension_items: list[dict[str, Any]] = []
    for item in page_explanations:
        intent = str(item.get("layout_intent") or "margin_note")
        if intent not in {"blank_note", "margin_note", "callout"}:
            intent = "margin_note"
        target_rect = _rect_from_normalized_bbox(item.get("display_bbox"), page.rect)
        placement = _find_inline_placement(page.rect, occupied, target_rect, item, intent)
        if not placement:
            extension_items.append({**item, "layout_intent": "margin_note"})
            continue
        _draw_inline_note(page, placement["rect"], item)
        occupied.append(_inflate_rect(placement["rect"], 4, page.rect))
        inline_items.append({**item, "placement": _manifest_placement(item, placement)})
    return inline_items, extension_items


def _place_expanded_margin_notes(
    page: fitz.Page,
    page_explanations: list[dict[str, Any]],
    source_rect: fitz.Rect,
) -> list[dict[str, Any]]:
    lane_width = 240
    margin = 22
    gap = 12
    expanded_rect = fitz.Rect(source_rect.x0, source_rect.y0, source_rect.x1 + lane_width, source_rect.y1)
    page.set_mediabox(expanded_rect)
    side_rect = fitz.Rect(source_rect.x1 + 8, source_rect.y0, source_rect.x1 + lane_width, source_rect.y1)
    page.draw_rect(side_rect, color=None, fill=NOTE_SIDE_FILL, width=0, overlay=True)
    divider_x = source_rect.x1 + 9
    page.draw_line(
        (divider_x, source_rect.y0 + 18),
        (divider_x, source_rect.y1 - 18),
        color=(0.68, 0.8, 0.74),
        width=0.6,
        overlay=True,
    )
    header_x = source_rect.x1 + margin
    _draw_line(page, (header_x, source_rect.y0 + 19), "AI 笔记", 9, bold=True)
    page.draw_line(
        (header_x, source_rect.y0 + 23),
        (header_x + 36, source_rect.y0 + 23),
        color=NOTE_ACCENT,
        width=0.6,
        overlay=True,
    )
    y = source_rect.y0 + 38
    placed: list[dict[str, Any]] = []
    for item in page_explanations:
        note_width = lane_width - margin * 2
        max_chars = max(14, int((note_width - 16) / 5.4))
        lines = _inline_note_lines(item, max_chars)
        if not lines:
            raise ValueError(f"AI note for {item['block_id']} has no short text.")
        needed_height = 22 + len(lines) * 12
        if y + needed_height > source_rect.y1 - margin:
            raise ValueError(f"AI note for {item['block_id']} cannot be safely placed on page {item['slide_number']}.")
        rect = fitz.Rect(source_rect.x1 + margin, y, source_rect.x1 + lane_width - margin, y + needed_height)
        _draw_inline_note(page, rect, item)
        target_rect = _rect_from_normalized_bbox(item.get("display_bbox"), source_rect)
        if target_rect:
            start = (target_rect.x1, (target_rect.y0 + target_rect.y1) / 2)
            elbow = (source_rect.x1 + 5, rect.y0 + 12)
            page.draw_line(
                start,
                elbow,
                color=NOTE_BORDER,
                width=0.45,
                stroke_opacity=0.9,
                overlay=True,
            )
            page.draw_line(
                elbow,
                (rect.x0, rect.y0 + 12),
                color=NOTE_BORDER,
                width=0.45,
                stroke_opacity=0.9,
                overlay=True,
            )
        placement = {"rect": rect, "score": 0.0, "mode": "expanded_margin_note"}
        placed.append({**item, "placement": _manifest_placement(item, placement)})
        y = rect.y1 + gap
    return placed


def _find_inline_placement(
    page_rect: fitz.Rect,
    occupied: list[fitz.Rect],
    target_rect: fitz.Rect | None,
    item: dict[str, Any],
    intent: str,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    for candidate in _free_rect_candidates(page_rect, occupied):
        max_chars = max(16, int((candidate.width - 16) / 5.4))
        lines = _inline_note_lines(item, max_chars)
        if not lines:
            continue
        needed_height = 22 + len(lines) * 12
        if needed_height > candidate.height:
            continue
        note_rect = fitz.Rect(candidate.x0, candidate.y0, candidate.x1, candidate.y0 + needed_height)
        score = _placement_score(note_rect, target_rect, page_rect, intent)
        if not best or score > best["score"]:
            best = {"rect": note_rect, "score": score, "mode": intent}
    return best


def _free_rect_candidates(page_rect: fitz.Rect, occupied: list[fitz.Rect]) -> list[fitz.Rect]:
    margin = 24
    min_width = 150
    min_height = 50
    content = fitz.Rect(page_rect.x0 + margin, page_rect.y0 + margin, page_rect.x1 - margin, page_rect.y1 - margin)
    xs = {round(content.x0, 2), round(content.x1, 2)}
    ys = {round(content.y0, 2), round(content.y1, 2)}
    for rect in occupied:
        xs.add(round(max(content.x0, min(content.x1, rect.x0)), 2))
        xs.add(round(max(content.x0, min(content.x1, rect.x1)), 2))
        ys.add(round(max(content.y0, min(content.y1, rect.y0)), 2))
        ys.add(round(max(content.y0, min(content.y1, rect.y1)), 2))
    x_values = sorted(xs)
    y_values = sorted(ys)
    candidates: list[fitz.Rect] = []
    for left_index, x0 in enumerate(x_values[:-1]):
        for x1 in x_values[left_index + 1 :]:
            if x1 - x0 < min_width:
                continue
            for top_index, y0 in enumerate(y_values[:-1]):
                for y1 in y_values[top_index + 1 :]:
                    if y1 - y0 < min_height:
                        continue
                    rect = fitz.Rect(x0, y0, x1, y1)
                    if any(rect.intersects(blocker) for blocker in occupied):
                        continue
                    candidates.append(rect)
    return candidates


def _placement_score(note_rect: fitz.Rect, target_rect: fitz.Rect | None, page_rect: fitz.Rect, intent: str) -> float:
    area_score = min(1.0, (note_rect.width * note_rect.height) / (page_rect.width * page_rect.height * 0.18))
    distance_score = 0.0
    if target_rect:
        note_center = ((note_rect.x0 + note_rect.x1) / 2, (note_rect.y0 + note_rect.y1) / 2)
        target_center = ((target_rect.x0 + target_rect.x1) / 2, (target_rect.y0 + target_rect.y1) / 2)
        distance = ((note_center[0] - target_center[0]) ** 2 + (note_center[1] - target_center[1]) ** 2) ** 0.5
        diagonal = (page_rect.width**2 + page_rect.height**2) ** 0.5
        distance_score = 1.0 - min(1.0, distance / diagonal)
    edge_bonus = 0.0
    if intent == "margin_note":
        near_left = note_rect.x0 - page_rect.x0 < 40
        near_right = page_rect.x1 - note_rect.x1 < 40
        edge_bonus = 0.15 if near_left or near_right else 0.0
    return area_score * 0.45 + distance_score * 0.45 + edge_bonus


def _draw_inline_note(page: fitz.Page, rect: fitz.Rect, item: dict[str, Any]) -> None:
    shadow = fitz.Rect(rect.x0 + 1.8, rect.y0 + 2.0, rect.x1 + 1.8, rect.y1 + 2.0)
    page.draw_rect(
        shadow,
        color=None,
        fill=NOTE_SHADOW,
        width=0,
        fill_opacity=0.13,
        radius=0.08,
        overlay=True,
    )
    page.draw_rect(rect, color=NOTE_BORDER, fill=NOTE_FILL, width=0.6, radius=0.08, overlay=True)
    accent = fitz.Rect(rect.x0 + 0.8, rect.y0 + 5, rect.x0 + 4.0, rect.y1 - 5)
    page.draw_rect(accent, color=None, fill=NOTE_ACCENT, width=0, radius=0.45, overlay=True)
    x = rect.x0 + 11
    y = rect.y0 + 13
    _draw_line(page, (x, y), _short_note_title(item), 8, bold=True)
    y += 13
    max_chars = max(16, int((rect.width - 22) / 5.4))
    for line in _inline_note_lines(item, max_chars):
        if y > rect.y1 - 5:
            break
        _draw_line(page, (x, y), line, 8)
        y += 12


def _inline_note_lines(item: dict[str, Any], max_chars: int) -> list[str]:
    explanation = item.get("explanation") or {}
    snippet = str(explanation.get("short_explanation") or "").strip()
    if not snippet:
        return []
    return _wrap_text(snippet, max_chars)


def _short_note_title(item: dict[str, Any]) -> str:
    title = " ".join(str(item.get("block_title") or "").split())
    if not title:
        return "AI 补充"
    return title if len(title) <= 24 else f"{title[:23]}…"


def _manifest_placement(item: dict[str, Any], placement: dict[str, Any]) -> dict[str, Any]:
    rect = placement["rect"]
    rect_values = [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]
    mode = placement["mode"]
    return {
        "block_id": item["block_id"],
        "mode": mode,
        "note_type": "margin_note" if mode == "expanded_margin_note" else mode,
        "style_version": NOTE_STYLE_VERSION,
        "rect": rect_values,
        "placement_rect": rect_values,
        "anchor_bbox": item.get("display_bbox") if _is_normalized_bbox(item.get("display_bbox")) else None,
    }


def _rect_from_normalized_bbox(value: Any, page_rect: fitz.Rect) -> fitz.Rect | None:
    if not _is_normalized_bbox(value):
        return None
    return fitz.Rect(
        page_rect.x0 + float(value["x"]) * page_rect.width,
        page_rect.y0 + float(value["y"]) * page_rect.height,
        page_rect.x0 + (float(value["x"]) + float(value["w"])) * page_rect.width,
        page_rect.y0 + (float(value["y"]) + float(value["h"])) * page_rect.height,
    )


def _rendered_page_rects(page: fitz.Page) -> list[fitz.Rect]:
    rects: list[fitz.Rect] = []
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []) or []:
        bbox = block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            continue
        rect = fitz.Rect(*bbox)
        if rect.is_empty or rect.width < 2 or rect.height < 2:
            continue
        rects.append(rect)
    return rects


def _inflate_rect(rect: fitz.Rect, amount: float, bounds: fitz.Rect) -> fitz.Rect:
    return fitz.Rect(
        max(bounds.x0, rect.x0 - amount),
        max(bounds.y0, rect.y0 - amount),
        min(bounds.x1, rect.x1 + amount),
        min(bounds.y1, rect.y1 + amount),
    )


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


def _draw_line(page: fitz.Page, point: tuple[float, float], text: str, size: int, *, bold: bool = False) -> None:
    needs_raster = _needs_raster_text(text)
    raster_font_file = _font_file_for_text(text, bold=bold) if needs_raster else None
    render_mode = 3 if needs_raster else 0
    page.insert_text(
        point,
        text,
        fontsize=size,
        fontname=_font_for_text(text),
        color=NOTE_TEXT,
        render_mode=render_mode,
    )
    if render_mode == 3:
        if not raster_font_file:
            raise RuntimeError("CJK text requires an installed Chinese font.")
        _draw_raster_text(page, point, text, size, raster_font_file)

def _font_for_text(text: str) -> str:
    if re.search(r"[\u3400-\u9fff]", text):
        return "china-s"
    return "helv"


def _font_file_for_text(text: str, *, bold: bool = False) -> str | None:
    if not _needs_raster_text(text):
        return None
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    if not bold:
        candidates = candidates[1:] + candidates[:1]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _needs_raster_text(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def _draw_raster_text(page: fitz.Page, point: tuple[float, float], text: str, size: int, font_file: str) -> None:
    scale = 2
    font_size = max(1, int(round(size * scale)))
    font = ImageFont.truetype(font_file, font_size)
    measure = ImageDraw.Draw(Image.new("RGBA", (1, 1), (255, 255, 255, 0)))
    bbox = measure.textbbox((0, 0), text, font=font)
    padding = max(2, int(round(size * 0.35)))
    width = bbox[2] - bbox[0] + padding * 2
    height = bbox[3] - bbox[1] + padding * 2
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.text((padding - bbox[0], padding - bbox[1]), text, font=font, fill=(15, 31, 26, 255))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    x, y = point
    rect = fitz.Rect(x, y - height / scale + size * 0.25, x + width / scale, y + size * 0.25)
    page.insert_image(rect, stream=stream.getvalue(), overlay=True)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    value = " ".join(str(text or "").split())
    if not value:
        return []
    lines = []
    current = ""
    for token in value.split(" "):
        pieces = _split_long_token(token, max_chars)
        for piece in pieces[:-1]:
            if current:
                lines.append(current)
                current = ""
            lines.append(piece)
        token = pieces[-1]
        if not current:
            current = token
            continue
        if _display_width_units(current) + 1 + _display_width_units(token) <= max_chars:
            current += " " + token
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return lines


def _split_long_token(token: str, max_chars: int) -> list[str]:
    if _display_width_units(token) <= max_chars:
        return [token]
    pieces: list[str] = []
    current = ""
    current_units = 0
    for char in token:
        units = _char_width_units(char)
        if current and current_units + units > max_chars:
            pieces.append(current)
            current = ""
            current_units = 0
        current += char
        current_units += units
    if current:
        pieces.append(current)
    return pieces


def _display_width_units(text: str) -> int:
    return sum(_char_width_units(char) for char in text)


def _char_width_units(char: str) -> int:
    code = ord(char)
    if 0x3400 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
        return 2
    return 1


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
