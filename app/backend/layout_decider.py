from __future__ import annotations

from typing import Any


DEFAULT_PAGE = {"width": 12192000, "height": 6858000}
ANNOTATION_WIDTH = 1160000
ANNOTATION_HEIGHT = 330000
ANNOTATION_GAP = 65000
ANNOTATION_MARGIN = 120000


def decide_slide_layout(slide: dict[str, Any]) -> dict[str, str]:
    hint = slide.get("decision_hint", {})
    hinted_strategy = hint.get("strategy")
    reason = str(hint.get("reason") or "")

    if hinted_strategy == "reflow_or_expand":
        if _cannot_reflow(slide):
            return {
                "strategy": "report_only",
                "reason": reason
                or "页面没有可可靠重排的动画数据，基础版只写入报告。",
            }
        return {
            "strategy": "object_reflow",
            "reason": reason or "页面复杂，学习版将在原 PDF 画面上做微调重排。",
        }
    if slide.get("animation_target_count", 0) > 0:
        return {"strategy": "native_enhance", "reason": reason}
    return {"strategy": "keep_native", "reason": reason}


def _cannot_reflow(slide: dict[str, Any]) -> bool:
    if slide.get("unsupported_animation_count", 0) > 0:
        return True
    if slide.get("animation_target_count", 0) == 0:
        return True
    return False


def select_annotation_zone(
    slide: dict[str, Any],
    *,
    marker_count: int,
) -> dict[str, Any] | None:
    page = slide.get("size") or DEFAULT_PAGE
    page_width = int(page.get("width") or DEFAULT_PAGE["width"])
    page_height = int(page.get("height") or DEFAULT_PAGE["height"])
    boxes = [_box_value(item) for item in slide.get("object_boxes", [])]
    boxes = [box for box in boxes if box and _valid_box(box)]

    if boxes:
        left_blank = min(int(box["x"]) for box in boxes)
        top_blank = min(int(box["y"]) for box in boxes)
        right_blank = page_width - max(int(box["x"]) + int(box["w"]) for box in boxes)
        bottom_blank = page_height - max(int(box["y"]) + int(box["h"]) for box in boxes)
    else:
        left_blank = right_blank = page_width
        top_blank = bottom_blank = page_height

    candidates = [
        _vertical_zone("right", page_width - right_blank, 0, right_blank, page_height),
        _vertical_zone("left", 0, 0, left_blank, page_height),
        _horizontal_zone("bottom", 0, page_height - bottom_blank, page_width, bottom_blank),
        _horizontal_zone("top", 0, 0, page_width, top_blank),
    ]
    candidates = [zone for zone in candidates if zone and zone["capacity"] > 0]
    if not candidates:
        return None

    requested = max(1, marker_count)
    preference = {"right": 0, "left": 1, "bottom": 2, "top": 3}
    candidates.sort(
        key=lambda zone: (
            zone["capacity"] < requested,
            -zone["capacity"],
            preference[zone["side"]],
        )
    )
    return candidates[0]


def annotation_slot(zone: dict[str, Any], index: int) -> dict[str, int]:
    item_index = max(0, index - 1)
    if zone["side"] in {"left", "right"}:
        return {
            "x": int(zone["x"]),
            "y": int(zone["y"]) + item_index * (ANNOTATION_HEIGHT + ANNOTATION_GAP),
            "w": min(ANNOTATION_WIDTH, int(zone["w"])),
            "h": ANNOTATION_HEIGHT,
        }
    return {
        "x": int(zone["x"]) + item_index * (ANNOTATION_WIDTH + ANNOTATION_GAP),
        "y": int(zone["y"]),
        "w": ANNOTATION_WIDTH,
        "h": min(ANNOTATION_HEIGHT, int(zone["h"])),
    }


def _vertical_zone(
    side: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, Any] | None:
    usable_width = width - (ANNOTATION_MARGIN * 2)
    usable_height = height - (ANNOTATION_MARGIN * 2)
    if usable_width < ANNOTATION_WIDTH or usable_height < ANNOTATION_HEIGHT:
        return None
    capacity = (usable_height + ANNOTATION_GAP) // (ANNOTATION_HEIGHT + ANNOTATION_GAP)
    return {
        "side": side,
        "x": x + ANNOTATION_MARGIN,
        "y": y + ANNOTATION_MARGIN,
        "w": usable_width,
        "h": usable_height,
        "capacity": capacity,
    }


def _horizontal_zone(
    side: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, Any] | None:
    usable_width = width - (ANNOTATION_MARGIN * 2)
    usable_height = height - (ANNOTATION_MARGIN * 2)
    if usable_width < ANNOTATION_WIDTH or usable_height < ANNOTATION_HEIGHT:
        return None
    capacity = (usable_width + ANNOTATION_GAP) // (ANNOTATION_WIDTH + ANNOTATION_GAP)
    return {
        "side": side,
        "x": x + ANNOTATION_MARGIN,
        "y": y + ANNOTATION_MARGIN,
        "w": usable_width,
        "h": usable_height,
        "capacity": capacity,
    }


def _box_value(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("bbox"):
        return item["bbox"]
    if {"x", "y", "w", "h"}.issubset(item):
        return item
    return None


def _valid_box(box: dict[str, Any]) -> bool:
    return int(box.get("w", 0)) > 0 and int(box.get("h", 0)) > 0
