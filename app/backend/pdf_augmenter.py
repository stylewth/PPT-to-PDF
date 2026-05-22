from __future__ import annotations

import json
import posixpath
import re
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from native_converter import convert_pptx_to_pdf
from ooxml_slide_editor import apply_shape_operations, apply_text_box_repairs, label_shape_xml, parse_slide_shapes
from pdf_micro_reflow import apply_micro_reflow_pdf


P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
RELATION_LINE_CLEARANCE = 160000

def generate_guide_pdf(
    pptx_path: str | Path,
    output_dir: str | Path,
    plan: dict[str, Any],
    *,
    base_pdf_path: str | Path | None = None,
    media_manifest: dict[str, Any] | None = None,
    soffice_path: str | Path | None = None,
    command_runner=None,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    plan_path = output / "augment_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    guide_pdf_path = output / "guide.pdf"
    if _has_micro_reflow(plan) and not _has_object_reflow(plan):
        if base_pdf_path is None:
            raise ValueError("PDF micro-reflow requires base_pdf_path.")
        apply_micro_reflow_pdf(base_pdf_path, guide_pdf_path, plan)
        _overlay_media_if_present(guide_pdf_path, media_manifest)
        _apply_page_compact_if_present(guide_pdf_path, plan)
        return {"augment_plan_path": plan_path, "guide_pdf_path": guide_pdf_path}

    if not _has_augments(plan):
        if base_pdf_path is None:
            return {"augment_plan_path": plan_path}
        shutil.copyfile(base_pdf_path, guide_pdf_path)
        _overlay_media_if_present(guide_pdf_path, media_manifest)
        return {"augment_plan_path": plan_path, "guide_pdf_path": guide_pdf_path}

    guide_deck_path = output / "guide_deck.pptx"
    write_guide_deck(pptx_path, guide_deck_path, plan)
    convert_pptx_to_pdf(
        guide_deck_path,
        output,
        soffice_path=soffice_path,
        command_runner=command_runner,
        output_name="guide.pdf",
    )
    if base_pdf_path is not None:
        _overlay_graphic_frame_regions(pptx_path, base_pdf_path, guide_pdf_path, plan)
    _overlay_media_if_present(guide_pdf_path, media_manifest)
    _apply_page_compact_if_present(guide_pdf_path, plan)
    return {
        "augment_plan_path": plan_path,
        "guide_deck_path": guide_deck_path,
        "guide_pdf_path": guide_pdf_path,
    }


def write_guide_deck(pptx_path: str | Path, output_path: str | Path, plan: dict[str, Any]) -> Path:
    source = Path(pptx_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(source, "r") as package:
        entries = {name: package.read(name) for name in package.namelist()}

    slide_paths = _slide_paths(entries)
    _enhance_source_slides(entries, slide_paths, plan)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in entries.items():
            package.writestr(name, data)
    return output


def _has_augments(plan: dict[str, Any]) -> bool:
    return any(
        slide.get("inline_markers")
        or slide.get("micro_reflow")
        or slide.get("object_reflow")
        or slide.get("page_compact")
        or slide.get("text_box_repairs")
        for slide in plan.get("slides", [])
    )


def _has_micro_reflow(plan: dict[str, Any]) -> bool:
    return any(slide.get("strategy") == "pdf_micro_reflow" for slide in plan.get("slides", []))


def _has_object_reflow(plan: dict[str, Any]) -> bool:
    return any(slide.get("strategy") == "object_reflow" for slide in plan.get("slides", []))


def _overlay_media_if_present(guide_pdf_path: str | Path, media_manifest: dict[str, Any] | None) -> None:
    if media_manifest:
        overlay_media_summaries(guide_pdf_path, media_manifest)


def _apply_page_compact_if_present(guide_pdf_path: str | Path, plan: dict[str, Any]) -> None:
    compact_by_page = {
        int(slide.get("source_slide") or 0): slide.get("page_compact")
        for slide in plan.get("slides", [])
        if slide.get("page_compact")
    }
    if not compact_by_page:
        return

    import fitz

    guide_path = Path(guide_pdf_path)
    temp_path = guide_path.with_name(f"{guide_path.stem}.compact.tmp{guide_path.suffix}")
    source = fitz.open(guide_path)
    target = fitz.open()
    try:
        for page_index, source_page in enumerate(source):
            compact = compact_by_page.get(page_index + 1)
            page_rect = source_page.rect
            output_page = target.new_page(width=page_rect.width, height=page_rect.height)
            if not compact:
                output_page.show_pdf_page(page_rect, source, page_index)
                continue
            scale = max(0.88, min(0.98, float(compact.get("scale") or 0.94)))
            target_width = page_rect.width * scale
            target_height = page_rect.height * scale
            target_rect = fitz.Rect(
                page_rect.x0 + (page_rect.width - target_width) / 2,
                page_rect.y0 + (page_rect.height - target_height) / 2,
                page_rect.x0 + (page_rect.width + target_width) / 2,
                page_rect.y0 + (page_rect.height + target_height) / 2,
            )
            output_page.draw_rect(page_rect, color=None, fill=(1, 1, 1), width=0)
            output_page.show_pdf_page(target_rect, source, page_index)
        target.save(temp_path)
    finally:
        target.close()
        source.close()
    temp_path.replace(guide_path)


def overlay_media_summaries(guide_pdf_path: str | Path, media_manifest: dict[str, Any]) -> None:
    items = [
        item
        for item in media_manifest.get("items", [])
        if item.get("kind") == "gif"
        and item.get("status") == "ok"
        and ((item.get("preview") or {}).get("grid_path") or (item.get("preview") or {}).get("strip_path"))
    ]
    if not items:
        return

    import fitz

    guide_path = Path(guide_pdf_path)
    root = guide_path.parent
    temp_path = guide_path.with_name(f"{guide_path.stem}.media.tmp{guide_path.suffix}")
    page_size = _media_manifest_page_size(media_manifest)
    doc = fitz.open(guide_path)
    try:
        for item in items:
            slide_number = int(item.get("slide_number") or 0)
            if slide_number < 1 or slide_number > len(doc):
                continue
            bbox = item.get("bbox") or {}
            if not _valid_box(bbox):
                continue
            preview = item.get("preview") or {}
            preview_path = root / str(preview.get("grid_path") or preview.get("strip_path"))
            if not preview_path.exists():
                raise ValueError(f"GIF preview image not found: {preview_path}")
            page = doc[slide_number - 1]
            source_rect = _pdf_rect_from_exact_slide_box(bbox, page_size, page.rect)
            occupied_rects = _occupied_rects_for_media_item(item, page_size, page.rect)
            layout = _media_keyframe_layout(
                fitz,
                page.rect,
                source_rect,
                int(preview.get("grid_width") or preview.get("strip_width") or 1),
                int(preview.get("grid_height") or preview.get("strip_height") or 1),
                occupied_rects,
                frame_count=len(preview.get("frames") or preview.get("sampled_frame_indices") or []) or 1,
            )
            _draw_media_keyframe_replacement(fitz, page, source_rect, layout, preview_path, item, root)
            _restore_media_text_boxes(fitz, page, item, page_size, page.rect, source_rect, layout)
        doc.save(temp_path)
    finally:
        doc.close()
    temp_path.replace(guide_path)


def _draw_media_keyframe_replacement(
    fitz: Any,
    page: Any,
    source_rect: Any,
    layout: dict[str, Any],
    preview_path: Path,
    item: dict[str, Any],
    root: Path | None = None,
) -> None:
    replacement_rect = layout["rect"]
    preview = item.get("preview") or {}
    frames = preview.get("frames") or []
    if frames:
        _draw_scored_media_keyframes(fitz, page, source_rect, layout, frames, root or preview_path.parent)
        return

    page.draw_rect(replacement_rect, color=(0.13, 0.48, 0.34), fill=(1, 1, 1), width=0.8, overlay=True)
    image_rect = fitz.Rect(
        replacement_rect.x0 + 6,
        replacement_rect.y0 + 6,
        replacement_rect.x1 - 6,
        replacement_rect.y1 - 6,
    )
    page.insert_image(image_rect, filename=str(preview_path), keep_proportion=True, overlay=True)


def _draw_scored_media_keyframes(
    fitz: Any,
    page: Any,
    source_rect: Any,
    layout: dict[str, Any],
    frames: list[dict[str, Any]],
    root: Path,
) -> None:
    replacement_rect = layout["rect"]
    display_frames = _select_media_frames(frames, int(layout.get("frame_count") or len(frames)))
    page.draw_rect(_inflate_rect(fitz, source_rect, 1, 1), color=None, fill=(1, 1, 1), width=0, overlay=True)
    if layout.get("mode") == "split_source" and len(display_frames) > 1:
        source_frame_rect = layout.get("source_frame_rect") or source_rect
        page.draw_rect(source_frame_rect, color=(0.13, 0.48, 0.34), fill=(1, 1, 1), width=0.8, overlay=True)
        first_path = root / str(display_frames[0].get("path") or "")
        if not first_path.exists():
            raise ValueError(f"GIF frame image not found: {first_path}")
        first_rect = fitz.Rect(
            source_frame_rect.x0 + 4,
            source_frame_rect.y0 + 4,
            source_frame_rect.x1 - 4,
            source_frame_rect.y1 - 4,
        )
        page.insert_image(first_rect, filename=str(first_path), keep_proportion=True, overlay=True)
        display_frames = display_frames[1:]
    page.draw_rect(replacement_rect, color=(0.13, 0.48, 0.34), fill=(1, 1, 1), width=0.8, overlay=True)
    _insert_frame_grid(
        fitz,
        page,
        replacement_rect,
        display_frames,
        root,
        cols=int(layout.get("cols") or 0) or None,
        rows=int(layout.get("rows") or 0) or None,
    )


def _select_media_frames(frames: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(frames) <= count:
        return frames
    count = max(1, min(count, len(frames)))
    if count == 1:
        return [frames[0]]
    indexes = [round(index * (len(frames) - 1) / (count - 1)) for index in range(count)]
    return [frames[index] for index in sorted(set(indexes))]


def _insert_frame_grid(
    fitz: Any,
    page: Any,
    rect: Any,
    frames: list[dict[str, Any]],
    root: Path,
    *,
    cols: int | None = None,
    rows: int | None = None,
) -> None:
    count = len(frames)
    cols = cols or min(3, max(1, count))
    rows = rows or (count + cols - 1) // cols
    pad = 6
    gap = 6
    usable_width = max(1.0, rect.width - 2 * pad - gap * (cols - 1))
    usable_height = max(1.0, rect.height - 2 * pad - gap * (rows - 1))
    cell_width = usable_width / cols
    cell_height = usable_height / rows
    for index, frame in enumerate(frames):
        frame_path = root / str(frame.get("path") or "")
        if not frame_path.exists():
            raise ValueError(f"GIF frame image not found: {frame_path}")
        col = index % cols
        row = index // cols
        cell = fitz.Rect(
            rect.x0 + pad + col * (cell_width + gap),
            rect.y0 + pad + row * (cell_height + gap),
            rect.x0 + pad + col * (cell_width + gap) + cell_width,
            rect.y0 + pad + row * (cell_height + gap) + cell_height,
        )
        page.insert_image(cell, filename=str(frame_path), keep_proportion=True, overlay=True)


def _restore_media_text_boxes(
    fitz: Any,
    page: Any,
    item: dict[str, Any],
    page_size: dict[str, int],
    page_rect: Any,
    source_rect: Any,
    layout: dict[str, Any],
) -> None:
    source_frame_rect = layout.get("source_frame_rect") or source_rect
    for entry in item.get("occupied_boxes") or []:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        box = entry.get("bbox")
        if not _valid_box(box):
            continue
        text_rect = _pdf_rect_from_exact_slide_box(box, page_size, page_rect)
        if not _media_text_needs_restore(fitz, text_rect, source_rect):
            continue
        restore_bottom = min(page_rect.y1, max(text_rect.y1, source_rect.y0 + 8))
        if source_frame_rect != source_rect:
            restore_bottom = min(restore_bottom, source_frame_rect.y0 - 4)
        restore_bottom = max(restore_bottom, text_rect.y1)
        restore_rect = fitz.Rect(
            text_rect.x0,
            text_rect.y0,
            text_rect.x1,
            restore_bottom,
        )
        align = fitz.TEXT_ALIGN_CENTER if len(text) <= 18 else fitz.TEXT_ALIGN_LEFT
        font_args = _restore_text_font_args(text)
        page.draw_rect(restore_rect, color=None, fill=(1, 1, 1), width=0, overlay=True)
        for font_size in _restore_text_font_sizes(text_rect, text):
            spare = page.insert_textbox(
                restore_rect,
                text,
                fontsize=font_size,
                color=(0, 0, 0),
                align=align,
                overlay=True,
                **font_args,
            )
            if spare >= 0:
                break


def _media_text_needs_restore(fitz: Any, text_rect: Any, source_rect: Any) -> bool:
    if text_rect.intersects(source_rect):
        overlap_ratio = _rect_area(text_rect & source_rect) / max(_rect_area(text_rect), 1.0)
        if overlap_ratio >= 0.12:
            return True
    horizontal_overlap = max(0.0, min(text_rect.x1, source_rect.x1) - max(text_rect.x0, source_rect.x0))
    horizontal_ratio = horizontal_overlap / max(text_rect.width, 1.0)
    gap = source_rect.y0 - text_rect.y1
    return 0 <= gap <= 44 and horizontal_ratio >= 0.45


def _restore_text_font_args(text: str) -> dict[str, str]:
    if not any(ord(char) > 127 for char in text):
        return {"fontname": "helv"}
    for font_path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"):
        if Path(font_path).exists():
            return {"fontname": "restore-cjk", "fontfile": font_path}
    return {"fontname": "china-s"}


def _restore_text_font_sizes(text_rect: Any, text: str) -> list[float]:
    if len(text) <= 18 and text_rect.height >= 40:
        base = min(38.0, max(14.0, text_rect.height * 0.5))
    else:
        base = min(18.0, max(8.0, text_rect.height * 0.62))
    return [base, base * 0.86, base * 0.72, max(7.0, base * 0.6)]


def _media_manifest_page_size(media_manifest: dict[str, Any]) -> dict[str, int]:
    page = media_manifest.get("page") or {}
    return {
        "width": int(page.get("width") or 12192000),
        "height": int(page.get("height") or 6858000),
    }


def _pdf_rect_from_exact_slide_box(box: dict[str, Any], slide_size: dict[str, int], page_rect: Any) -> Any:
    import fitz

    slide_width = max(1, int(slide_size["width"]))
    slide_height = max(1, int(slide_size["height"]))
    x0 = page_rect.x0 + int(box["x"]) / slide_width * page_rect.width
    y0 = page_rect.y0 + int(box["y"]) / slide_height * page_rect.height
    x1 = page_rect.x0 + (int(box["x"]) + int(box["w"])) / slide_width * page_rect.width
    y1 = page_rect.y0 + (int(box["y"]) + int(box["h"])) / slide_height * page_rect.height
    return fitz.Rect(x0, y0, x1, y1)


def _occupied_rects_for_media_item(item: dict[str, Any], page_size: dict[str, int], page_rect: Any) -> list[Any]:
    rects = []
    for entry in item.get("occupied_boxes") or []:
        box = entry.get("bbox") if isinstance(entry, dict) and "bbox" in entry else entry
        if _valid_box(box):
            rects.append(_pdf_rect_from_exact_slide_box(box, page_size, page_rect))
    return rects


def _media_keyframe_replacement_rect(
    fitz: Any,
    page_rect: Any,
    source_rect: Any,
    preview_width: int,
    preview_height: int,
    occupied_rects: list[Any] | None = None,
) -> Any:
    return _media_keyframe_layout(
        fitz,
        page_rect,
        source_rect,
        preview_width,
        preview_height,
        occupied_rects,
        frame_count=6,
    )["rect"]


def _media_keyframe_layout(
    fitz: Any,
    page_rect: Any,
    source_rect: Any,
    preview_width: int,
    preview_height: int,
    occupied_rects: list[Any] | None = None,
    *,
    frame_count: int = 6,
) -> dict[str, Any]:
    margin = 18
    obstacles = occupied_rects or []
    frame_count = max(1, min(int(frame_count or 1), 6))
    frame_aspect = _media_frame_aspect(preview_width, preview_height, frame_count)
    source_frame_rect, source_frame_score = _source_media_frame_rect(
        fitz,
        page_rect,
        source_rect,
        frame_aspect,
        obstacles,
    )
    candidates: list[dict[str, Any]] = []

    for count in _media_frame_count_options(frame_count):
        cols, rows = _grid_dimensions(count)
        for cell_width in (170, 150, 132, 116, 100):
            rect_width, rect_height, actual_cell_width, actual_cell_height = _media_panel_size(
                cols,
                rows,
                cell_width,
                frame_aspect,
            )
            for rect in _media_panel_candidates(fitz, page_rect, source_rect, rect_width, rect_height, margin):
                candidates.append(
                    _scored_media_layout(
                        rect,
                        "single_panel",
                        count,
                        cols,
                        rows,
                        actual_cell_width,
                        actual_cell_height,
                        source_rect,
                        page_rect,
                        obstacles,
                        margin,
                    )
                )

    if frame_count > 1:
        for count in _media_frame_count_options(frame_count):
            if count < 2:
                continue
            panel_count = count - 1
            cols, rows = _grid_dimensions(panel_count, prefer_wide=True)
            for cell_width in (170, 150, 132, 116, 100):
                rect_width, rect_height, actual_cell_width, actual_cell_height = _media_panel_size(
                    cols,
                    rows,
                    cell_width,
                    frame_aspect,
                )
                for rect in _media_panel_candidates(fitz, page_rect, source_rect, rect_width, rect_height, margin, detached=True):
                    candidates.append(
                        _scored_media_layout(
                            rect,
                            "split_source",
                            count,
                            cols,
                            rows,
                            actual_cell_width,
                            actual_cell_height,
                            source_rect,
                            page_rect,
                            [source_rect, *obstacles],
                            margin,
                            source_frame_rect=source_frame_rect,
                            source_frame_score=source_frame_score,
                        )
                    )

    valid = [candidate for candidate in candidates if candidate["score"] > float("-inf")]
    if not valid:
        return {
            "mode": "single_panel",
            "rect": source_rect,
            "frame_count": 1,
            "cols": 1,
            "rows": 1,
            "cell_width": source_rect.width,
            "cell_height": source_rect.height,
            "score": 0.0,
            "source_frame_rect": source_rect,
        }
    return max(valid, key=lambda candidate: candidate["score"])


def _media_frame_count_options(frame_count: int) -> list[int]:
    options = [min(frame_count, 6), min(frame_count, 4), min(frame_count, 3), min(frame_count, 2)]
    result = []
    for value in options:
        if value >= 1 and value not in result:
            result.append(value)
    return result


def _media_frame_aspect(preview_width: int, preview_height: int, frame_count: int) -> float:
    grid_aspect = max(float(preview_width) / max(float(preview_height), 1.0), 1.0)
    cols, rows = _grid_dimensions(max(1, min(frame_count, 6)))
    return max(1.2, min(1.9, grid_aspect * rows / cols))


def _grid_dimensions(count: int, *, prefer_wide: bool = False) -> tuple[int, int]:
    count = max(1, int(count))
    if count == 1:
        return 1, 1
    if count == 2:
        return 2, 1
    if count == 3 or prefer_wide and count <= 3:
        return 3, 1
    if count == 4:
        return 2, 2
    return 3, 2


def _media_panel_size(cols: int, rows: int, cell_width: float, frame_aspect: float) -> tuple[float, float, float, float]:
    pad = 6
    gap = 6
    cell_height = cell_width / max(frame_aspect, 0.1)
    width = cols * cell_width + (cols - 1) * gap + pad * 2
    height = rows * cell_height + (rows - 1) * gap + pad * 2
    return width, height, cell_width, cell_height


def _media_panel_candidates(
    fitz: Any,
    page_rect: Any,
    source_rect: Any,
    width: float,
    height: float,
    margin: float,
    *,
    detached: bool = False,
) -> list[Any]:
    gap = 12
    center_x = source_rect.x0 + source_rect.width / 2
    center_y = source_rect.y0 + source_rect.height / 2
    centered_x = center_x - width / 2
    centered_y = center_y - height / 2
    candidates = []
    if not detached:
        candidates.extend(
            [
                fitz.Rect(centered_x, centered_y, centered_x + width, centered_y + height),
                fitz.Rect(source_rect.x0, source_rect.y0, source_rect.x0 + width, source_rect.y0 + height),
                fitz.Rect(source_rect.x1 - width, source_rect.y0, source_rect.x1, source_rect.y0 + height),
                fitz.Rect(centered_x, source_rect.y1 - height, centered_x + width, source_rect.y1),
            ]
        )
    below_start = source_rect.y1 + gap
    above_start = source_rect.y0 - gap - height
    for dy in (0, 24, 48, 72, 104):
        y = below_start + dy
        candidates.extend(
            [
                fitz.Rect(centered_x, y, centered_x + width, y + height),
                fitz.Rect(source_rect.x0, y, source_rect.x0 + width, y + height),
                fitz.Rect(source_rect.x1 - width, y, source_rect.x1, y + height),
            ]
        )
    for dy in (0, 24, 48):
        y = above_start - dy
        candidates.append(fitz.Rect(centered_x, y, centered_x + width, y + height))
    candidates.extend(
        [
            fitz.Rect(source_rect.x1 + gap, centered_y, source_rect.x1 + gap + width, centered_y + height),
            fitz.Rect(source_rect.x0 - gap - width, centered_y, source_rect.x0 - gap, centered_y + height),
            fitz.Rect(centered_x, page_rect.y1 - margin - height, centered_x + width, page_rect.y1 - margin),
        ]
    )
    return [_clamped_panel_rect(fitz, candidate, page_rect, margin) for candidate in candidates]


def _source_media_frame_rect(
    fitz: Any,
    page_rect: Any,
    source_rect: Any,
    frame_aspect: float,
    obstacles: list[Any],
) -> tuple[Any, float]:
    inflated_obstacles = [_inflate_rect(fitz, rect, 4, 36) for rect in obstacles]
    max_width = max(1.0, source_rect.width - 8)
    max_height = max(1.0, source_rect.height - 8)
    candidates = []
    for scale in (1.0, 0.88, 0.76, 0.64):
        box_width = max_width * scale
        box_height = max_height * scale
        if box_width / max(box_height, 1.0) > frame_aspect:
            height = box_height
            width = height * frame_aspect
        else:
            width = box_width
            height = width / max(frame_aspect, 0.1)
        x_positions = [
            source_rect.x0 + (source_rect.width - width) / 2,
            source_rect.x0 + 4,
            source_rect.x1 - 4 - width,
        ]
        y_positions = [
            source_rect.y1 - 4 - height,
            source_rect.y0 + (source_rect.height - height) / 2,
            source_rect.y0 + 4,
        ]
        for x0 in _unique_float_positions(x_positions):
            for y0 in _unique_float_positions(y_positions):
                rect = fitz.Rect(x0, y0, x0 + width, y0 + height)
                if not _rect_inside(rect, page_rect, 4):
                    continue
                area = max(_rect_area(rect), 1.0)
                overlap = _rects_overlap_area(rect, inflated_obstacles) / area
                if overlap > 0.08:
                    continue
                distance = _rect_center_distance(rect, source_rect) / max(
                    (page_rect.width**2 + page_rect.height**2) ** 0.5,
                    1.0,
                )
                area_ratio = area / max(_rect_area(source_rect), 1.0)
                score = area_ratio * 110 - distance * 130 - overlap * 1600
                candidates.append((score, rect))
    if not candidates:
        return source_rect, -160.0
    score, rect = max(candidates, key=lambda item: item[0])
    return rect, score


def _inflate_rect(fitz: Any, rect: Any, x_pad: float, y_pad: float) -> Any:
    return fitz.Rect(rect.x0 - x_pad, rect.y0 - y_pad, rect.x1 + x_pad, rect.y1 + y_pad)


def _unique_float_positions(values: list[float]) -> list[float]:
    result = []
    seen = set()
    for value in values:
        key = round(value, 3)
        if key not in seen:
            result.append(value)
            seen.add(key)
    return result


def _scored_media_layout(
    rect: Any,
    mode: str,
    frame_count: int,
    cols: int,
    rows: int,
    cell_width: float,
    cell_height: float,
    source_rect: Any,
    page_rect: Any,
    obstacles: list[Any],
    margin: float,
    *,
    source_frame_rect: Any | None = None,
    source_frame_score: float = 0.0,
) -> dict[str, Any]:
    if not _rect_inside(rect, page_rect, margin):
        score = float("-inf")
    elif mode == "split_source" and rect.intersects(source_rect):
        score = float("-inf")
    elif mode == "split_source" and source_frame_rect is None:
        score = float("-inf")
    elif mode == "single_panel" and _rect_area(rect & source_rect) / max(_rect_area(source_rect), 1.0) < 0.5:
        score = float("-inf")
    else:
        overlap = _rects_overlap_area(rect, obstacles) / max(_rect_area(rect), 1.0)
        if overlap > 0.08:
            score = float("-inf")
        else:
            distance = _rect_center_distance(rect, source_rect) / max((page_rect.width**2 + page_rect.height**2) ** 0.5, 1.0)
            relation_bonus = 35 if mode == "split_source" else (50 if rect.intersects(source_rect) else -20)
            count_bonus = frame_count * 7
            readability = min(cell_width, cell_height * 1.45) * 2.1
            split_source_bonus = source_frame_score if mode == "split_source" else 0
            score = readability + count_bonus + relation_bonus + split_source_bonus - distance * 120 - overlap * 1800
    return {
        "mode": mode,
        "rect": rect,
        "frame_count": frame_count,
        "cols": cols,
        "rows": rows,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "score": score,
        "source_frame_rect": source_frame_rect,
    }


def _rect_area(rect: Any) -> float:
    return max(0.0, float(rect.width)) * max(0.0, float(rect.height))


def _rects_overlap_area(rect: Any, others: list[Any]) -> float:
    return sum(_rect_area(rect & other) for other in others if rect.intersects(other))


def _rect_center_distance(first: Any, second: Any) -> float:
    first_x = first.x0 + first.width / 2
    first_y = first.y0 + first.height / 2
    second_x = second.x0 + second.width / 2
    second_y = second.y0 + second.height / 2
    return ((first_x - second_x) ** 2 + (first_y - second_y) ** 2) ** 0.5


def _anchored_expansion_candidates(fitz: Any, source_rect: Any, width: float, height: float) -> list[Any]:
    center_x = source_rect.x0 + source_rect.width / 2
    center_y = source_rect.y0 + source_rect.height / 2
    return [
        fitz.Rect(source_rect.x0, source_rect.y0, source_rect.x0 + width, source_rect.y0 + height),
        fitz.Rect(center_x - width / 2, center_y - height / 2, center_x + width / 2, center_y + height / 2),
        fitz.Rect(source_rect.x0, source_rect.y1 - height, source_rect.x0 + width, source_rect.y1),
        fitz.Rect(source_rect.x1 - width, source_rect.y0, source_rect.x1, source_rect.y0 + height),
        fitz.Rect(source_rect.x1 - width, source_rect.y1 - height, source_rect.x1, source_rect.y1),
    ]


def _nearby_blank_media_candidates(fitz: Any, source_rect: Any, width: float, height: float, *, gap: float) -> list[Any]:
    center_x = source_rect.x0 + source_rect.width / 2
    center_y = source_rect.y0 + source_rect.height / 2
    below_y = source_rect.y1 + gap
    above_y = source_rect.y0 - gap - height
    right_x = source_rect.x1 + gap
    left_x = source_rect.x0 - gap - width
    centered_x = center_x - width / 2
    centered_y = center_y - height / 2
    return [
        fitz.Rect(centered_x, below_y, centered_x + width, below_y + height),
        fitz.Rect(source_rect.x0, below_y, source_rect.x0 + width, below_y + height),
        fitz.Rect(source_rect.x1 - width, below_y, source_rect.x1, below_y + height),
        fitz.Rect(centered_x, above_y, centered_x + width, above_y + height),
        fitz.Rect(source_rect.x0, above_y, source_rect.x0 + width, above_y + height),
        fitz.Rect(source_rect.x1 - width, above_y, source_rect.x1, above_y + height),
        fitz.Rect(right_x, centered_y, right_x + width, centered_y + height),
        fitz.Rect(left_x, centered_y, left_x + width, centered_y + height),
    ]


def _contains_rect(outer: Any, inner: Any) -> bool:
    return outer.x0 <= inner.x0 and outer.y0 <= inner.y0 and outer.x1 >= inner.x1 and outer.y1 >= inner.y1


def _media_summary_rect(
    fitz: Any,
    page_rect: Any,
    source_rect: Any,
    strip_width: int,
    strip_height: int,
    occupied_rects: list[Any] | None = None,
) -> Any:
    margin = 18
    gap = 12
    aspect = max(float(strip_width) / max(float(strip_height), 1.0), 1.2)
    base_width = min(page_rect.width * 0.35, max(source_rect.width * 1.16, 160))
    obstacles = [source_rect, *(occupied_rects or [])]
    first_candidate = None
    for scale in (1.0, 0.78, 0.6, 0.46, 0.36):
        panel_width = max(96, base_width * scale)
        panel_height = max(48, min(page_rect.height * 0.34, panel_width / aspect + 24))
        center_y = source_rect.y0 + source_rect.height / 2 - panel_height / 2
        center_x = source_rect.x0 + source_rect.width / 2 - panel_width / 2
        candidates = [
            fitz.Rect(source_rect.x1 + gap, center_y, source_rect.x1 + gap + panel_width, center_y + panel_height),
            fitz.Rect(center_x, source_rect.y1 + gap, center_x + panel_width, source_rect.y1 + gap + panel_height),
            fitz.Rect(source_rect.x0 - gap - panel_width, center_y, source_rect.x0 - gap, center_y + panel_height),
            fitz.Rect(center_x, source_rect.y0 - gap - panel_height, center_x + panel_width, source_rect.y0 - gap),
        ]
        first_candidate = first_candidate or candidates[0]
        for candidate in candidates:
            if _rect_inside(candidate, page_rect, margin) and _clear_of_rects(candidate, obstacles):
                return candidate
    return _clamped_panel_rect(fitz, first_candidate, page_rect, margin)


def _rect_inside(rect: Any, page_rect: Any, margin: float) -> bool:
    return (
        rect.x0 >= page_rect.x0 + margin
        and rect.y0 >= page_rect.y0 + margin
        and rect.x1 <= page_rect.x1 - margin
        and rect.y1 <= page_rect.y1 - margin
    )


def _clear_of_rects(rect: Any, others: list[Any]) -> bool:
    return not any(rect.intersects(other) for other in others)


def _clamped_panel_rect(fitz: Any, rect: Any, page_rect: Any, margin: float) -> Any:
    x0 = min(max(rect.x0, page_rect.x0 + margin), page_rect.x1 - margin - rect.width)
    y0 = min(max(rect.y0, page_rect.y0 + margin), page_rect.y1 - margin - rect.height)
    return fitz.Rect(x0, y0, x0 + rect.width, y0 + rect.height)


def _draw_media_summary_panel(fitz: Any, page: Any, panel_rect: Any, strip_path: Path, item: dict[str, Any]) -> None:
    page.draw_rect(panel_rect, color=(0.13, 0.48, 0.34), fill=(1, 1, 1), width=0.8, overlay=True)
    header_height = min(18, max(14, panel_rect.height * 0.16))
    header = fitz.Rect(panel_rect.x0 + 4, panel_rect.y0 + 2, panel_rect.x1 - 4, panel_rect.y0 + header_height)
    frame_count = (item.get("preview") or {}).get("frame_count")
    title = "GIF keyframes" if not frame_count else f"GIF keyframes - {frame_count} frames"
    page.insert_textbox(header, title, fontsize=7, color=(0.08, 0.25, 0.19), overlay=True)
    image_rect = fitz.Rect(panel_rect.x0 + 4, panel_rect.y0 + header_height + 3, panel_rect.x1 - 4, panel_rect.y1 - 4)
    page.insert_image(image_rect, filename=str(strip_path), keep_proportion=True, overlay=True)


def _overlay_graphic_frame_regions(
    source_pptx_path: str | Path,
    base_pdf_path: str | Path,
    guide_pdf_path: str | Path,
    plan: dict[str, Any],
) -> None:
    import fitz

    source_pptx = Path(source_pptx_path)
    guide_path = Path(guide_pdf_path)
    temp_path = guide_path.with_name(f"{guide_path.stem}.overlay.tmp{guide_path.suffix}")
    previews: dict[tuple[int, str], dict[str, Any]] = {}
    moved_operations = list(_graphic_frame_overlay_operations(plan))
    moved_keys = {
        (slide_index + 1, str(operation.get("id") or ""))
        for slide_index, _slide_plan, operation in moved_operations
    }

    guide_doc = fitz.open(guide_path)
    try:
        operations = [
            *moved_operations,
            *_stable_graphic_frame_overlay_operations(fitz, guide_doc, plan, moved_keys),
        ]
        if not operations:
            return
        for slide_index, slide_plan, operation in operations:
            if slide_index < 0 or slide_index >= len(guide_doc):
                continue
            source_box = operation.get("from") or {}
            target_box = operation.get("to") or {}
            if not _valid_box(source_box) or not _valid_box(target_box):
                continue

            page_size = _slide_page_size(slide_plan)
            target_page = guide_doc[slide_index]
            target_rect = _pdf_rect_from_slide_box(target_box, page_size, target_page.rect, pad=False)
            target_rect = target_rect & target_page.rect
            if target_rect.is_empty:
                continue
            object_id = str(operation.get("id") or "")
            preview_key = (slide_index + 1, object_id)
            if preview_key not in previews:
                previews[preview_key] = _graphic_frame_preview(source_pptx, slide_index + 1, object_id) or {}
            preview = previews[preview_key]
            if preview and (not operation.get("stable") or _graphic_frame_preview_is_usable(preview)):
                _draw_graphic_frame_preview(target_page, target_rect, preview)

        guide_doc.save(temp_path)
    finally:
        guide_doc.close()
    temp_path.replace(guide_path)


def _graphic_frame_overlay_operations(plan: dict[str, Any]):
    for slide_plan in plan.get("slides", []):
        slide_index = int(slide_plan.get("source_slide") or 0) - 1
        operations = (slide_plan.get("object_reflow") or {}).get("operations") or []
        for operation in operations:
            if operation.get("render_mode") != "pdf_region_overlay":
                continue
            if str(operation.get("object_type") or "") != "graphicFrame":
                continue
            yield slide_index, slide_plan, operation


def _stable_graphic_frame_overlay_operations(fitz: Any, guide_doc: Any, plan: dict[str, Any], moved_keys: set[tuple[int, str]]):
    for slide_plan in plan.get("slides", []):
        slide_number = int(slide_plan.get("source_slide") or 0)
        slide_index = slide_number - 1
        if slide_index < 0 or slide_index >= len(guide_doc):
            continue
        page = guide_doc[slide_index]
        page_size = _slide_page_size(slide_plan)
        for obj in slide_plan.get("object_boxes", []):
            object_id = str(obj.get("id") or "")
            if not object_id or (slide_number, object_id) in moved_keys:
                continue
            if str(obj.get("type") or "") != "graphicFrame":
                continue
            if bool(obj.get("in_group")):
                continue
            bbox = obj.get("bbox") or {}
            if not _valid_box(bbox):
                continue
            target_rect = _pdf_rect_from_slide_box(bbox, page_size, page.rect, pad=False) & page.rect
            if target_rect.is_empty:
                continue
            yield slide_index, slide_plan, {
                "id": object_id,
                "object_type": "graphicFrame",
                "from": bbox,
                "to": bbox,
                "stable": True,
                "repair_required": _graphic_frame_render_needs_repair(fitz, page, target_rect),
            }


def _graphic_frame_render_needs_repair(fitz: Any, page: Any, target_rect: Any) -> bool:
    from PIL import Image
    from render_visual_check import check_rendered_image

    pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), clip=target_rect, alpha=False)
    image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
    result = check_rendered_image(
        image,
        formula_regions=[{"x0": 0, "y0": 0, "x1": image.width, "y1": image.height}],
    )
    return not result["passed"]


def _graphic_frame_preview_is_usable(preview: dict[str, Any]) -> bool:
    from PIL import Image
    from render_visual_check import check_rendered_image

    image = Image.open(BytesIO(preview["bytes"])).convert("RGB")
    result = check_rendered_image(
        image,
        formula_regions=[{"x0": 0, "y0": 0, "x1": image.width, "y1": image.height}],
    )
    if result["passed"]:
        return True
    return not _preview_has_dense_dark_ink(image)


def _preview_has_dense_dark_ink(image: Any) -> bool:
    width, height = image.size
    if width <= 0 or height <= 0:
        return False
    dark = 0
    ink = 0
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            red, green, blue = pixels[x, y]
            if red < 80 and green < 80 and blue < 80:
                dark += 1
                ink += 1
            elif blue > 120 and red < 120 and green < 160:
                ink += 1
            elif red > 140 and green < 90 and blue < 90:
                ink += 1
    area = width * height
    return dark / area > 0.12 or (dark / area > 0.08 and ink / area > 0.22)


def _graphic_frame_preview(
    pptx_path: Path,
    slide_number: int,
    object_id: str,
) -> dict[str, Any] | None:
    slide_path = f"ppt/slides/slide{slide_number}.xml"
    rels_path = f"ppt/slides/_rels/slide{slide_number}.xml.rels"
    if not pptx_path.exists():
        return None
    with zipfile.ZipFile(pptx_path, "r") as package:
        if slide_path not in package.namelist() or rels_path not in package.namelist():
            return None
        slide_root = ET.fromstring(package.read(slide_path))
        rels = _relationship_map(package.read(rels_path))
        namespaces = {
            "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            "p": P_NS,
            "r": R_NS,
        }
        for frame in slide_root.findall(".//p:graphicFrame", namespaces):
            cnv = frame.find(".//p:nvGraphicFramePr/p:cNvPr", namespaces)
            if cnv is None or str(cnv.attrib.get("id") or "") != object_id:
                continue
            blip = frame.find(".//a:blip", namespaces)
            if blip is None:
                continue
            embed_id = blip.attrib.get(f"{{{R_NS}}}embed")
            media_target = rels.get(str(embed_id or ""))
            if not media_target:
                continue
            media_path = posixpath.normpath(posixpath.join(posixpath.dirname(slide_path), media_target))
            if media_path not in package.namelist():
                continue
            fill = _graphic_frame_fill(frame, namespaces)
            image = _pdf_ready_image(package.read(media_path), media_path)
            if image is None:
                continue
            image["fill"] = fill
            return image
    return None


def _relationship_map(rels_xml: bytes) -> dict[str, str]:
    root = ET.fromstring(rels_xml)
    result: dict[str, str] = {}
    for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id and target:
            result[rel_id] = target
    return result


def _graphic_frame_fill(frame: ET.Element, namespaces: dict[str, str]) -> tuple[float, float, float] | None:
    fill = frame.find(".//p:pic/p:spPr/a:solidFill/a:srgbClr", namespaces)
    if fill is None:
        return None
    value = fill.attrib.get("val")
    if not value or not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
        return None
    return (
        int(value[0:2], 16) / 255,
        int(value[2:4], 16) / 255,
        int(value[4:6], 16) / 255,
    )


def _pdf_ready_image(data: bytes, media_path: str) -> dict[str, Any] | None:
    suffix = Path(media_path).suffix.lower()
    if suffix in {".emf", ".wmf"}:
        try:
            from PIL import Image

            image = _render_metafile_at_working_resolution(Image.open(BytesIO(data)))
            image = _prepare_preview_image(image)
            output = BytesIO()
            image.save(output, format="PNG")
            return {"bytes": output.getvalue(), "width": image.width, "height": image.height}
        except Exception:
            return None
    if suffix in {".png", ".jpg", ".jpeg"}:
        try:
            from PIL import Image

            image = _prepare_preview_image(Image.open(BytesIO(data)))
            output = BytesIO()
            image.save(output, format="PNG")
            return {"bytes": output.getvalue(), "width": image.width, "height": image.height}
        except Exception:
            return None
    return None


def _render_metafile_at_working_resolution(image: Any) -> Any:
    width, height = image.size
    scale = max(8.0, min(24.0, 1600.0 / max(1, width, height)))
    image._size = (max(1, int(width * scale)), max(1, int(height * scale)))
    image.load()
    return image


def _prepare_preview_image(image: Any) -> Any:
    return _trim_transparent(_transparent_white(image.convert("RGBA")))


def _transparent_white(image: Any) -> Any:
    pixels = []
    for red, green, blue, alpha in image.getdata():
        if red >= 248 and green >= 248 and blue >= 248:
            pixels.append((red, green, blue, 0))
        else:
            pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    return image


def _trim_transparent(image: Any) -> Any:
    bbox = image.getchannel("A").getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    pad = 2
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(image.width, right + pad)
    bottom = min(image.height, bottom + pad)
    return image.crop((left, top, right, bottom))


def _draw_graphic_frame_preview(page: Any, target_rect: Any, preview: dict[str, Any]) -> None:
    fill = preview.get("fill") or (1, 1, 1)
    page.draw_rect(target_rect, color=fill, fill=fill, overlay=True)
    page.insert_image(target_rect, stream=preview["bytes"], keep_proportion=True, overlay=True)


def _slide_page_size(slide_plan: dict[str, Any]) -> dict[str, int]:
    size = slide_plan.get("size") or {}
    return {
        "width": int(size.get("width") or 12192000),
        "height": int(size.get("height") or 6858000),
    }


def _valid_box(box: dict[str, Any]) -> bool:
    return all(key in box for key in ("x", "y", "w", "h")) and int(box["w"]) > 0 and int(box["h"]) > 0


def _pdf_rect_from_slide_box(
    box: dict[str, Any],
    slide_size: dict[str, int],
    page_rect: Any,
    *,
    pad: bool = True,
) -> Any:
    import fitz

    slide_width = max(1, int(slide_size["width"]))
    slide_height = max(1, int(slide_size["height"]))
    padded = _padded_overlay_box(box, slide_width, slide_height) if pad else {
        "x": int(box["x"]),
        "y": int(box["y"]),
        "w": int(box["w"]),
        "h": int(box["h"]),
    }
    x0 = page_rect.x0 + padded["x"] / slide_width * page_rect.width
    y0 = page_rect.y0 + padded["y"] / slide_height * page_rect.height
    x1 = page_rect.x0 + (padded["x"] + padded["w"]) / slide_width * page_rect.width
    y1 = page_rect.y0 + (padded["y"] + padded["h"]) / slide_height * page_rect.height
    return fitz.Rect(x0, y0, x1, y1)


def _padded_overlay_box(box: dict[str, Any], page_width: int, page_height: int) -> dict[str, int]:
    x = int(box["x"])
    y = int(box["y"])
    w = int(box["w"])
    h = int(box["h"])
    pad_x = max(0, min(int(w * 0.04), int(page_width * 0.01)))
    pad_y = max(0, min(int(h * 0.06), int(page_height * 0.01)))
    left = _clamp(x - pad_x, 0, page_width)
    top = _clamp(y - pad_y, 0, page_height)
    right = _clamp(x + w + pad_x, left + 1, page_width)
    bottom = _clamp(y + h + pad_y, top + 1, page_height)
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _enhance_source_slides(
    entries: dict[str, bytes],
    slide_paths: list[str],
    plan: dict[str, Any],
) -> None:
    for slide_plan in plan.get("slides", []):
        slide_path = _source_slide_path(slide_paths, slide_plan.get("source_slide", 0))
        if slide_path is None or slide_path not in entries:
            continue
        repairs = slide_plan.get("text_box_repairs") or []
        if repairs:
            slide_xml = entries[slide_path].decode("utf-8")
            entries[slide_path] = apply_text_box_repairs(slide_xml, repairs).encode("utf-8")
        if slide_plan.get("strategy") == "object_reflow":
            slide_xml = entries[slide_path].decode("utf-8")
            operations = (slide_plan.get("object_reflow") or {}).get("operations") or []
            slide_xml = apply_shape_operations(slide_xml, operations)
            relation_xml = _reflow_relation_lines_xml(slide_xml, operations)
            if relation_xml:
                slide_xml = _insert_before_close(slide_xml, "spTree", relation_xml)
            entries[slide_path] = slide_xml.encode("utf-8")
            continue
        if slide_plan.get("strategy") == "pdf_micro_reflow":
            continue
        markers = slide_plan.get("inline_markers") or []
        if not markers:
            continue
        slide_xml = entries[slide_path].decode("utf-8")
        marker_xml = _inline_marker_shapes_xml(slide_xml, markers, slide_plan.get("size", {}))
        if marker_xml:
            entries[slide_path] = _insert_before_close(slide_xml, "spTree", marker_xml).encode("utf-8")


def _source_slide_path(slide_paths: list[str], source_slide: int) -> str | None:
    if source_slide < 1 or source_slide > len(slide_paths):
        return None
    return slide_paths[source_slide - 1]


def _slide_paths(entries: dict[str, bytes]) -> list[str]:
    paths = [name for name in entries if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)]
    return sorted(paths, key=lambda value: int(re.search(r"slide(\d+)\.xml", value).group(1)))


def _insert_before_close(xml: str, local_name: str, insertion: str) -> str:
    pattern = re.compile(rf"</(?:[A-Za-z0-9_]+:)?{re.escape(local_name)}>")
    match = pattern.search(xml)
    if not match:
        self_closing = re.search(rf"<((?:[A-Za-z0-9_]+:)?{re.escape(local_name)})\b([^>]*)/>", xml)
        if not self_closing:
            raise ValueError(f"Missing closing tag for {local_name}.")
        tag = self_closing.group(1)
        replacement = f"<{tag}{self_closing.group(2)}>{insertion}</{tag}>"
        return xml[: self_closing.start()] + replacement + xml[self_closing.end() :]
    return xml[: match.start()] + insertion + xml[match.start() :]


def _inline_marker_shapes_xml(
    slide_xml: str,
    markers: list[dict[str, Any]],
    page_size: dict[str, int],
) -> str:
    page_width = int(page_size.get("width") or 12192000)
    page_height = int(page_size.get("height") or 6858000)
    next_shape_id = _next_shape_id(slide_xml)
    shapes = []
    for marker in markers[:3]:
        order = int(marker.get("order") or len(shapes) + 1)
        label = str(marker.get("label") or order)
        bbox = marker.get("bbox")
        if not bbox:
            bbox = _default_marker_box(order, page_width)
        badge = _badge_box(bbox, page_width)
        shapes.append(
            _text_shape(
                next_shape_id,
                f"Guide Inline Marker {order}",
                badge["x"],
                badge["y"],
                badge["w"],
                badge["h"],
                label,
                1800,
                "FFFFFF",
                fill="237A57",
                line=None,
                body_inset_x=25000,
                body_inset_y=25000,
                align="ctr",
                vertical_anchor="ctr",
            )
        )
        next_shape_id += 1
        hint = str(marker.get("hint") or "")
        if hint:
            hint_box = marker.get("hint_box") or _hint_box(badge, page_width, page_height)
            shapes.append(
                _text_shape(
                    next_shape_id,
                    f"Guide Inline Hint {order}",
                    hint_box["x"],
                    hint_box["y"],
                    hint_box["w"],
                    hint_box["h"],
                    hint,
                    1150,
                    "1E4637",
                    fill="F5FBF7",
                    line="A9D1BF",
                )
            )
            next_shape_id += 1
    return "".join(shapes)


def _reflow_step_labels_xml(slide_xml: str, operations: list[dict[str, Any]]) -> str:
    next_shape_id = _next_shape_id(slide_xml)
    occupied = [
        shape["bbox"]
        for shape in parse_slide_shapes(slide_xml)
        if shape.get("bbox")
    ]
    labels = []
    for index, operation in enumerate(operations[:8], start=1):
        if operation.get("op") not in {"move_resize", "move", "resize"}:
            continue
        target = operation.get("to") or {}
        if "x" not in target or "y" not in target:
            continue
        badge = _reflow_badge_box(target, occupied)
        occupied.append(badge)
        labels.append(label_shape_xml(next_shape_id, f"Guide Reflow Step {index}", badge["x"], badge["y"], str(index)))
        next_shape_id += 1
    return "".join(labels)


def _reflow_relation_lines_xml(slide_xml: str, operations: list[dict[str, Any]]) -> str:
    next_shape_id = _next_shape_id(slide_xml)
    lines = []
    for index, operation in enumerate(operations[:8], start=1):
        if not operation.get("anchor_to"):
            continue
        anchor = operation.get("anchor_to") or {}
        target = operation.get("to") or {}
        if not all(key in anchor for key in ("x", "y", "w", "h")):
            continue
        if not all(key in target for key in ("x", "y", "w", "h")):
            continue
        lines.append(_relation_line_shape_xml(next_shape_id, f"Guide Reflow Relation {index}", anchor, target))
        next_shape_id += 1
    return "".join(lines)


def _relation_line_shape_xml(
    shape_id: int,
    name: str,
    anchor: dict[str, Any],
    target: dict[str, Any],
) -> str:
    anchor_x, anchor_y, target_x, target_y = _relation_points(anchor, target)
    x = min(anchor_x, target_x)
    y = min(anchor_y, target_y)
    w = max(1, abs(target_x - anchor_x))
    h = max(1, abs(target_y - anchor_y))
    flip_h = ' flipH="1"' if target_x < anchor_x else ""
    flip_v = ' flipV="1"' if target_y < anchor_y else ""
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm{flip_h}{flip_v}><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/><a:ln w="19050"><a:solidFill><a:srgbClr val="237A57"/></a:solidFill><a:prstDash val="dash"/><a:tailEnd type="triangle"/></a:ln></p:spPr>
</p:sp>'''


def _relation_points(anchor: dict[str, Any], target: dict[str, Any]) -> tuple[int, int, int, int]:
    anchor_box = {key: int(anchor[key]) for key in ("x", "y", "w", "h")}
    target_box = {key: int(target[key]) for key in ("x", "y", "w", "h")}
    anchor_left = anchor_box["x"]
    anchor_right = anchor_box["x"] + anchor_box["w"]
    anchor_top = anchor_box["y"]
    anchor_bottom = anchor_box["y"] + anchor_box["h"]
    target_left = target_box["x"]
    target_right = target_box["x"] + target_box["w"]
    target_top = target_box["y"]
    target_bottom = target_box["y"] + target_box["h"]
    anchor_center_x = anchor_left + anchor_box["w"] // 2
    anchor_center_y = anchor_top + anchor_box["h"] // 2
    target_center_x = target_left + target_box["w"] // 2
    target_center_y = target_top + target_box["h"] // 2

    dx = target_center_x - anchor_center_x
    dy = target_center_y - anchor_center_y
    gap = 90000
    length = 300000
    if abs(dx) >= abs(dy):
        if dx >= 0:
            end_x = target_left - gap
            return end_x - length, target_center_y, end_x, target_center_y
        end_x = target_right + gap
        return end_x + length, target_center_y, end_x, target_center_y
    if dy >= 0:
        end_y = target_top - gap
        return target_center_x, end_y - length, target_center_x, end_y
    end_y = target_bottom + gap
    return target_center_x, end_y + length, target_center_x, end_y


def _relation_clearance(gap: int) -> int:
    return max(0, min(RELATION_LINE_CLEARANCE, (max(1, int(gap)) - 1) // 2))


def _reflow_badge_box(target: dict[str, Any], occupied: list[dict[str, int]]) -> dict[str, int]:
    badge_w = 300000
    badge_h = 230000
    gap = 180000
    page_width = 12192000
    page_height = 6858000
    margin = 120000
    target_box = {
        "x": int(target.get("x", 0)),
        "y": int(target.get("y", 0)),
        "w": int(target.get("w", badge_w)),
        "h": int(target.get("h", badge_h)),
    }
    center_y = target_box["y"] + target_box["h"] // 2 - badge_h // 2
    center_x = target_box["x"] + target_box["w"] // 2 - badge_w // 2
    candidates = [
        {"x": target_box["x"] - badge_w - gap, "y": center_y, "w": badge_w, "h": badge_h},
        {"x": center_x, "y": target_box["y"] - badge_h - gap, "w": badge_w, "h": badge_h},
        {"x": target_box["x"] + target_box["w"] + gap, "y": center_y, "w": badge_w, "h": badge_h},
        {"x": center_x, "y": target_box["y"] + target_box["h"] + gap, "w": badge_w, "h": badge_h},
        {"x": margin, "y": center_y, "w": badge_w, "h": badge_h},
    ]
    for candidate in candidates:
        box = _clamp_box(candidate, page_width, page_height, margin)
        if _overlaps_any(box, [target_box] + occupied, 0.01):
            continue
        return box
    return _clamp_box(candidates[1], page_width, page_height, margin)


def _clamp_box(box: dict[str, int], page_width: int, page_height: int, margin: int) -> dict[str, int]:
    return {
        "x": _clamp(int(box["x"]), margin, page_width - int(box["w"]) - margin),
        "y": _clamp(int(box["y"]), margin, page_height - int(box["h"]) - margin),
        "w": int(box["w"]),
        "h": int(box["h"]),
    }


def _overlaps_any(box: dict[str, int], others: list[dict[str, int]], threshold: float) -> bool:
    return any(_box_overlap_ratio(box, other) > threshold for other in others)


def _box_overlap_ratio(first: dict[str, int], second: dict[str, int]) -> float:
    smaller = min(max(0, first["w"]) * max(0, first["h"]), max(0, second["w"]) * max(0, second["h"]))
    if not smaller:
        return 0.0
    left = max(first["x"], second["x"])
    top = max(first["y"], second["y"])
    right = min(first["x"] + first["w"], second["x"] + second["w"])
    bottom = min(first["y"] + first["h"], second["y"] + second["h"])
    return max(0, right - left) * max(0, bottom - top) / smaller


def _next_shape_id(slide_xml: str) -> int:
    ids = [
        int(value)
        for value in re.findall(r"<(?:[A-Za-z0-9_]+:)?cNvPr\b[^>]*\bid=[\"'](\d+)[\"']", slide_xml)
    ]
    return max(ids, default=1) + 1


def _default_marker_box(order: int, page_width: int) -> dict[str, int]:
    return {
        "x": max(120000, page_width - 800000),
        "y": 180000 + (order - 1) * 460000,
        "w": 360000,
        "h": 360000,
    }


def _frame_box(bbox: dict[str, int], page_width: int, page_height: int) -> dict[str, int]:
    pad = 85000
    x = _clamp(int(bbox.get("x", 0)) - pad, 0, page_width - 1)
    y = _clamp(int(bbox.get("y", 0)) - pad, 0, page_height - 1)
    right = _clamp(int(bbox.get("x", 0)) + int(bbox.get("w", 0)) + pad, x + 1, page_width)
    bottom = _clamp(int(bbox.get("y", 0)) + int(bbox.get("h", 0)) + pad, y + 1, page_height)
    return {"x": x, "y": y, "w": right - x, "h": bottom - y}


def _badge_box(bbox: dict[str, int], page_width: int) -> dict[str, int]:
    size = 330000
    margin = 120000
    x = _clamp(int(bbox.get("x", 0)), margin, page_width - size - margin)
    y = max(margin, int(bbox.get("y", 0)) - size - 90000)
    return {"x": x, "y": y, "w": size, "h": size}


def _hint_box(badge: dict[str, int], page_width: int, page_height: int) -> dict[str, int]:
    margin = 120000
    gap = 65000
    width = 880000
    height = 330000
    right_x = badge["x"] + badge["w"] + gap
    if right_x + width <= page_width - margin:
        x = right_x
    else:
        x = _clamp(badge["x"] - gap - width, margin, page_width - width - margin)
    y = _clamp(badge["y"], margin, page_height - height - margin)
    return {"x": x, "y": y, "w": width, "h": height}


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))


def _frame_shape(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    color: str,
) -> str:
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln w="25400"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill></a:ln></p:spPr>
</p:sp>'''


def _text_shape(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str,
    size: int,
    color: str,
    *,
    fill: str | None = None,
    line: str | None = None,
    body_inset_x: int = 180000,
    body_inset_y: int = 90000,
    align: str | None = None,
    vertical_anchor: str | None = None,
) -> str:
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = f'<a:ln w="12700"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else "<a:ln><a:noFill/></a:ln>"
    anchor_xml = f' anchor="{vertical_anchor}"' if vertical_anchor else ""
    paragraph_xml = f'<a:pPr algn="{align}"/>' if align else ""
    text_xml = escape(text)
    return f'''<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>{fill_xml}{line_xml}</p:spPr>
  <p:txBody><a:bodyPr wrap="square"{anchor_xml} lIns="{body_inset_x}" tIns="{body_inset_y}" rIns="{body_inset_x}" bIns="{body_inset_y}"/><a:lstStyle/><a:p>{paragraph_xml}<a:r><a:rPr lang="zh-CN" sz="{size}"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Microsoft YaHei"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>{text_xml}</a:t></a:r></a:p></p:txBody>
</p:sp>'''
