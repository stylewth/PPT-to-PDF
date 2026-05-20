from __future__ import annotations

from pathlib import Path
from typing import Any


class PdfMicroReflowError(RuntimeError):
    pass


def require_pymupdf():
    try:
        import fitz
    except ModuleNotFoundError as exc:
        raise PdfMicroReflowError(
            "PyMuPDF is required for PDF micro-reflow. Install it with: python -m pip install PyMuPDF"
        ) from exc
    return fitz


def map_emu_box_to_pdf(box: dict[str, Any], slide_size: dict[str, Any], page_rect: Any):
    fitz = require_pymupdf()
    slide_width = max(float(slide_size.get("width") or 12192000), 1.0)
    slide_height = max(float(slide_size.get("height") or 6858000), 1.0)
    x0 = page_rect.x0 + (float(box.get("x", 0)) / slide_width) * page_rect.width
    y0 = page_rect.y0 + (float(box.get("y", 0)) / slide_height) * page_rect.height
    x1 = x0 + (float(box.get("w", 0)) / slide_width) * page_rect.width
    y1 = y0 + (float(box.get("h", 0)) / slide_height) * page_rect.height
    return fitz.Rect(x0, y0, x1, y1)


def apply_micro_reflow_pdf(
    base_pdf_path: str | Path,
    output_pdf_path: str | Path,
    plan: dict[str, Any],
) -> Path:
    fitz = require_pymupdf()
    base_path = Path(base_pdf_path)
    output_path = Path(output_pdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    source = fitz.open(base_path)
    target = fitz.open()
    slides = {int(slide.get("source_slide", 0)): slide for slide in plan.get("slides", [])}
    try:
        for page_index, source_page in enumerate(source):
            slide = slides.get(page_index + 1, {})
            page_rect = source_page.rect
            if slide.get("strategy") == "pdf_micro_reflow":
                width, height = _micro_reflow_canvas_size(fitz, slide, page_rect)
                output_page = target.new_page(width=width, height=height)
                _render_micro_reflow_page(fitz, source, page_index, source_page, output_page, slide)
            else:
                output_page = target.new_page(width=page_rect.width, height=page_rect.height)
                output_page.show_pdf_page(page_rect, source, page_index)
                _draw_inline_markers(fitz, output_page, slide, page_rect)
        target.save(output_path)
    finally:
        target.close()
        source.close()
    return output_path


def _micro_reflow_canvas_size(fitz, slide: dict[str, Any], page_rect: Any) -> tuple[float, float]:
    slide_size = slide.get("size") or {}
    flows = _dedupe_flows((slide.get("micro_reflow") or {}).get("occlusion_flows", []))[:3]
    slots = _blank_slots(fitz, slide, slide_size, page_rect, max(1, len(flows)))
    if slots or not flows:
        return page_rect.width, page_rect.height
    if page_rect.width >= page_rect.height:
        lane_width = min(max(page_rect.width * 0.28, 260), 340)
        return page_rect.width + lane_width, page_rect.height
    lane_height = min(max(page_rect.height * 0.28, 180), 260)
    return page_rect.width, page_rect.height + lane_height


def _render_micro_reflow_page(fitz, source, page_index: int, source_page, output_page, slide: dict[str, Any]) -> None:
    page_rect = source_page.rect
    canvas_rect = output_page.rect
    slide_size = slide.get("size") or {}
    flows = _dedupe_flows((slide.get("micro_reflow") or {}).get("occlusion_flows", []))
    flows = flows[:3]
    slots = _blank_slots(fitz, slide, slide_size, page_rect, max(1, len(flows)))
    if slots:
        content_rect = page_rect
        output_page.show_pdf_page(content_rect, source, page_index)
        placement_note = "原页空白"
    else:
        content_rect, slots = _expanded_layout(fitz, page_rect, canvas_rect, max(1, len(flows)))
        output_page.draw_rect(canvas_rect, color=None, fill=(0.975, 0.98, 0.965))
        if canvas_rect.width > page_rect.width or canvas_rect.height > page_rect.height:
            output_page.draw_line(
                (content_rect.x1 + 4, canvas_rect.y0 + 12),
                (content_rect.x1 + 4, min(content_rect.y1, canvas_rect.y1) - 12),
                color=(0.72, 0.78, 0.73),
                width=0.7,
            )
        output_page.show_pdf_page(content_rect, source, page_index)
        placement_note = "扩展侧栏" if content_rect == page_rect else "缩放让位"

    _draw_page_badge(output_page, f"学习版微调 · {placement_note}")
    for index, flow in enumerate(flows[: len(slots)], start=1):
        _draw_occlusion_flow(
            fitz,
            source,
            page_index,
            output_page,
            flow,
            slots[index - 1],
            slide_size,
            source_page.rect,
            content_rect,
            index,
        )


def _dedupe_flows(flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for flow in flows:
        target_box = flow.get("target_bbox") or {}
        covered_ids = tuple(str(item.get("id") or "") for item in (flow.get("covered") or [])[:2])
        key = (
            str(flow.get("target_id") or ""),
            tuple(round(float(target_box.get(field, 0)), -3) for field in ("x", "y", "w", "h")),
            covered_ids,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(flow)
    return unique


def _blank_slots(fitz, slide: dict[str, Any], slide_size: dict[str, Any], page_rect: Any, count: int) -> list[Any]:
    boxes = [
        map_emu_box_to_pdf(item.get("bbox") or item, slide_size, page_rect)
        for item in slide.get("object_boxes", [])
        if item.get("bbox") or {"x", "y", "w", "h"}.issubset(item)
    ]
    margin = 16
    if boxes:
        left_blank = min(box.x0 for box in boxes) - page_rect.x0
        top_blank = min(box.y0 for box in boxes) - page_rect.y0
        right_blank = page_rect.x1 - max(box.x1 for box in boxes)
        bottom_blank = page_rect.y1 - max(box.y1 for box in boxes)
    else:
        left_blank = right_blank = page_rect.width
        top_blank = bottom_blank = page_rect.height

    candidates = [
        ("right", fitz.Rect(page_rect.x1 - right_blank + margin, page_rect.y0 + margin, page_rect.x1 - margin, page_rect.y1 - margin)),
        ("left", fitz.Rect(page_rect.x0 + margin, page_rect.y0 + margin, page_rect.x0 + left_blank - margin, page_rect.y1 - margin)),
        ("bottom", fitz.Rect(page_rect.x0 + margin, page_rect.y1 - bottom_blank + margin, page_rect.x1 - margin, page_rect.y1 - margin)),
        ("top", fitz.Rect(page_rect.x0 + margin, page_rect.y0 + margin, page_rect.x1 - margin, page_rect.y0 + top_blank - margin)),
    ]
    valid: list[tuple[str, Any, int, float]] = []
    for side, zone in candidates:
        if not _edge_zone_is_safe(side, zone, page_rect):
            continue
        slots = _slots_in_zone(fitz, zone, count)
        if slots:
            valid.append((side, zone, len(slots), zone.get_area()))
    if not valid:
        return []
    valid.sort(key=lambda item: (-item[2], -item[3], {"right": 0, "bottom": 1, "left": 2, "top": 3}[item[0]]))
    return _slots_in_zone(fitz, valid[0][1], count)


def _edge_zone_is_safe(side: str, zone: Any, page_rect: Any) -> bool:
    if side == "right":
        return zone.x0 >= page_rect.x0 + page_rect.width * 0.72
    if side == "left":
        return zone.x1 <= page_rect.x0 + page_rect.width * 0.28
    if side == "bottom":
        return zone.y0 >= page_rect.y0 + page_rect.height * 0.74
    if side == "top":
        return zone.y1 <= page_rect.y0 + page_rect.height * 0.26
    return False


def _slots_in_zone(fitz, zone: Any, count: int) -> list[Any]:
    min_width = 170
    min_height = 86
    gap = 12
    if zone.width < min_width or zone.height < min_height:
        return []
    slots: list[Any] = []
    if zone.height >= zone.width:
        max_height = 220 if count <= 1 else 176 if count == 2 else 124
        slot_height = min(max_height, (zone.height - gap * (count - 1)) / max(count, 1))
        if slot_height < min_height:
            return []
        for index in range(count):
            y0 = zone.y0 + index * (slot_height + gap)
            slots.append(fitz.Rect(zone.x0, y0, zone.x1, y0 + slot_height))
    else:
        max_width = 340 if count <= 1 else 290 if count == 2 else 250
        slot_width = min(max_width, (zone.width - gap * (count - 1)) / max(count, 1))
        if slot_width < min_width:
            return []
        for index in range(count):
            x0 = zone.x0 + index * (slot_width + gap)
            slots.append(fitz.Rect(x0, zone.y0, x0 + slot_width, zone.y1))
    return slots


def _fallback_layout(fitz, page_rect: Any, count: int) -> tuple[Any, list[Any]]:
    margin = 14
    if page_rect.width >= page_rect.height:
        lane_width = min(page_rect.width * 0.34, max(page_rect.width * 0.24, 220))
        content_rect = fitz.Rect(page_rect.x0, page_rect.y0, page_rect.x1 - lane_width, page_rect.y1)
        zone = fitz.Rect(content_rect.x1 + margin, page_rect.y0 + margin, page_rect.x1 - margin, page_rect.y1 - margin)
    else:
        lane_height = min(page_rect.height * 0.34, max(page_rect.height * 0.24, 160))
        content_rect = fitz.Rect(page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1 - lane_height)
        zone = fitz.Rect(page_rect.x0 + margin, content_rect.y1 + margin, page_rect.x1 - margin, page_rect.y1 - margin)
    return content_rect, _slots_in_zone(fitz, zone, count)


def _expanded_layout(fitz, page_rect: Any, canvas_rect: Any, count: int) -> tuple[Any, list[Any]]:
    margin = 14
    if canvas_rect.width > page_rect.width:
        content_rect = fitz.Rect(page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1)
        zone = fitz.Rect(page_rect.x1 + margin + 6, page_rect.y0 + margin, canvas_rect.x1 - margin, page_rect.y1 - margin)
        slots = _slots_in_zone(fitz, zone, count)
        if slots:
            return content_rect, slots
    if canvas_rect.height > page_rect.height:
        content_rect = fitz.Rect(page_rect.x0, page_rect.y0, page_rect.x1, page_rect.y1)
        zone = fitz.Rect(page_rect.x0 + margin, page_rect.y1 + margin + 6, page_rect.x1 - margin, canvas_rect.y1 - margin)
        slots = _slots_in_zone(fitz, zone, count)
        if slots:
            return content_rect, slots
    return _fallback_layout(fitz, page_rect, count)


def _draw_occlusion_flow(
    fitz,
    source,
    page_index: int,
    output_page,
    flow: dict[str, Any],
    slot: Any,
    slide_size: dict[str, Any],
    source_rect: Any,
    content_rect: Any,
    index: int,
) -> None:
    covered = (flow.get("covered") or [{}])[0]
    covered_box = covered.get("bbox") or flow.get("target_bbox")
    target_box = flow.get("target_bbox") or covered_box
    covered_clip = _context_clip(map_emu_box_to_pdf(covered_box, slide_size, source_rect), source_rect)
    target_clip = _context_clip(map_emu_box_to_pdf(target_box, slide_size, source_rect), source_rect)

    output_page.draw_rect(slot, color=(0.74, 0.82, 0.78), fill=(1, 1, 1), width=0.7)
    title_rect = fitz.Rect(slot.x0 + 6, slot.y0 + 4, slot.x1 - 6, slot.y0 + 20)
    _insert_textbox(
        output_page,
        title_rect,
        f"{index}. 流程：遮挡前 -> 覆盖后",
        fontsize=7.6,
        color=(0.08, 0.25, 0.19),
    )

    before_text = str(covered.get("text") or "遮挡前")
    after_text = str(flow.get("target_text") or "覆盖后")
    if slot.width < 320 and slot.height >= 112:
        inner = fitz.Rect(slot.x0 + 7, slot.y0 + 24, slot.x1 - 7, slot.y1 - 8)
        label_height = 10
        gap = 6
        panel_height = max(24, (inner.height - gap - label_height * 2 - 4) / 2)
        before_label = fitz.Rect(inner.x0, inner.y0, inner.x1, inner.y0 + label_height)
        before_panel = fitz.Rect(inner.x0, before_label.y1 + 2, inner.x1, before_label.y1 + 2 + panel_height)
        after_label = fitz.Rect(inner.x0, before_panel.y1 + gap, inner.x1, before_panel.y1 + gap + label_height)
        after_panel = fitz.Rect(inner.x0, after_label.y1 + 2, inner.x1, inner.y1)
        _insert_textbox(output_page, before_label, "遮挡前：" + _fit_label(before_text, 20), fontsize=6.1, color=(0.08, 0.25, 0.19))
        _insert_textbox(output_page, after_label, "覆盖后：" + _fit_label(after_text, 20), fontsize=6.1, color=(0.30, 0.17, 0.05))
        output_page.show_pdf_page(before_panel, source, page_index, clip=covered_clip)
        output_page.show_pdf_page(after_panel, source, page_index, clip=target_clip)
        output_page.draw_rect(before_panel, color=(0.13, 0.48, 0.34), width=0.7)
        output_page.draw_rect(after_panel, color=(0.72, 0.42, 0.08), width=0.7)
        _draw_down_arrow(output_page, before_panel, after_panel)
    else:
        inner = fitz.Rect(slot.x0 + 7, slot.y0 + 24, slot.x1 - 7, slot.y1 - 18)
        left = fitz.Rect(inner.x0, inner.y0, inner.x0 + inner.width * 0.46, inner.y1)
        right = fitz.Rect(inner.x1 - inner.width * 0.46, inner.y0, inner.x1, inner.y1)
        output_page.show_pdf_page(left, source, page_index, clip=covered_clip)
        output_page.show_pdf_page(right, source, page_index, clip=target_clip)
        output_page.draw_rect(left, color=(0.13, 0.48, 0.34), width=0.7)
        output_page.draw_rect(right, color=(0.72, 0.42, 0.08), width=0.7)
        _draw_arrow(output_page, left, right)
        _insert_textbox(
            output_page,
            fitz.Rect(left.x0, slot.y1 - 16, left.x1, slot.y1 - 4),
            _fit_label(before_text),
            fontsize=6.6,
            color=(0.08, 0.25, 0.19),
            align=1,
        )
        _insert_textbox(
            output_page,
            fitz.Rect(right.x0, slot.y1 - 16, right.x1, slot.y1 - 4),
            _fit_label(after_text),
            fontsize=6.6,
            color=(0.30, 0.17, 0.05),
            align=1,
        )

    # Long connector lines often cross dense lecture content. The slot-internal
    # arrow carries the flow relation while keeping the original slide readable.


def _draw_inline_markers(fitz, page, slide: dict[str, Any], page_rect: Any) -> None:
    slide_size = slide.get("size") or {}
    for marker in (slide.get("inline_markers") or [])[:3]:
        bbox = marker.get("bbox")
        if not bbox:
            continue
        rect = map_emu_box_to_pdf(bbox, slide_size, page_rect)
        badge = fitz.Rect(rect.x0, max(page_rect.y0 + 10, rect.y0 - 18), rect.x0 + 16, max(page_rect.y0 + 26, rect.y0 - 2))
        page.draw_oval(badge, color=(0.13, 0.48, 0.34), fill=(0.13, 0.48, 0.34))
        _insert_textbox(page, badge, str(marker.get("label") or ""), fontsize=8, color=(1, 1, 1), align=1)


def _draw_page_badge(page, text: str) -> None:
    rect = page.rect
    badge = rect + (12, 10, -rect.width * 0.68, -rect.height + 30)
    page.draw_rect(badge, color=None, fill=(0.09, 0.20, 0.30))
    _insert_textbox(page, badge, text, fontsize=8, color=(1, 1, 1), align=1)


def _draw_arrow(page, left: Any, right: Any) -> None:
    y = (left.y0 + left.y1) / 2
    start = (left.x1 + 2, y)
    end = (right.x0 - 2, y)
    page.draw_line(start, end, color=(0.13, 0.48, 0.34), width=0.8)
    page.draw_line(end, (end[0] - 4, end[1] - 3), color=(0.13, 0.48, 0.34), width=0.8)
    page.draw_line(end, (end[0] - 4, end[1] + 3), color=(0.13, 0.48, 0.34), width=0.8)


def _draw_down_arrow(page, top: Any, bottom: Any) -> None:
    x = (top.x0 + top.x1) / 2
    start = (x, top.y1 + 1)
    end = (x, bottom.y0 - 1)
    page.draw_line(start, end, color=(0.13, 0.48, 0.34), width=0.8)
    page.draw_line(end, (end[0] - 3, end[1] - 4), color=(0.13, 0.48, 0.34), width=0.8)
    page.draw_line(end, (end[0] + 3, end[1] - 4), color=(0.13, 0.48, 0.34), width=0.8)


def _safe_clip(rect: Any, page_rect: Any) -> Any:
    fitz = require_pymupdf()
    clipped = rect & page_rect
    if clipped.is_empty or clipped.width < 1 or clipped.height < 1:
        return fitz.Rect(page_rect.x0, page_rect.y0, min(page_rect.x1, page_rect.x0 + 80), min(page_rect.y1, page_rect.y0 + 60))
    return clipped


def _context_clip(rect: Any, page_rect: Any) -> Any:
    fitz = require_pymupdf()
    clipped = _safe_clip(rect, page_rect)
    x_pad = max(clipped.width * 0.24, page_rect.width * 0.025)
    y_pad = max(clipped.height * 0.24, page_rect.height * 0.025)
    if clipped.width < page_rect.width * 0.16:
        x_pad = max(x_pad, page_rect.width * 0.055)
    if clipped.height < page_rect.height * 0.16:
        y_pad = max(y_pad, page_rect.height * 0.055)
    expanded = fitz.Rect(clipped.x0 - x_pad, clipped.y0 - y_pad, clipped.x1 + x_pad, clipped.y1 + y_pad)
    return _safe_clip(expanded, page_rect)


def _map_point_to_content_rect(point: Any, source_rect: Any, content_rect: Any):
    fitz = require_pymupdf()
    x = content_rect.x0 + ((point.x - source_rect.x0) / source_rect.width) * content_rect.width
    y = content_rect.y0 + ((point.y - source_rect.y0) / source_rect.height) * content_rect.height
    return fitz.Point(x, y)


def _fit_label(text: str, limit: int = 12) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _insert_textbox(page, rect: Any, text: str, *, fontsize: float, color: tuple[float, float, float], align: int = 0) -> None:
    font = _cjk_font_file()
    if font:
        page.insert_textbox(
            rect,
            text,
            fontsize=fontsize,
            color=color,
            align=align,
            fontname="cjk",
            fontfile=str(font),
        )
        return
    page.insert_textbox(rect, text, fontsize=fontsize, color=color, align=align, fontname="helv")


def _cjk_font_file() -> Path | None:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\msyh.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
    ]
    return next((path for path in candidates if path.exists()), None)
