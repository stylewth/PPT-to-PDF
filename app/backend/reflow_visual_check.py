from __future__ import annotations

from typing import Any


VISUAL_TYPES = {"pic", "graphicFrame", "cxnSp"}
TEXT_TYPES = {"sp", "text"}


def check_reflow_intent(
    before_boxes: list[dict[str, Any]],
    after_boxes: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    page_size: dict[str, Any],
) -> dict[str, Any]:
    page_width = int(page_size.get("width") or 1)
    before = _boxes_by_id(before_boxes)
    after = _boxes_by_id(after_boxes)
    moved_visuals = [op for op in operations if _is_visual_operation(op)]
    moved_texts = [op for op in operations if _is_text_operation(op)]

    warnings: list[str] = []
    right_column_ratio = _right_column_ratio(moved_visuals, after, page_width)
    left_column_ratio = _left_column_ratio(moved_texts, after, page_width)
    max_move_ratio = _max_move_ratio(operations, before, after, page_width)
    max_unexplained_move_ratio = _max_move_ratio(
        [operation for operation in operations if not _has_anchor_relation(operation)],
        before,
        after,
        page_width,
    )

    if len(moved_visuals) >= 2 and right_column_ratio > 0.60:
        warnings.append("视觉对象集中到右侧栏")
    if moved_texts and left_column_ratio > 0.60:
        warnings.append("正文对象集中到左侧栏")
    if max_unexplained_move_ratio > 0.38:
        warnings.append("对象移动距离过大")

    return {
        "passed": not warnings,
        "warnings": warnings,
        "right_column_bias": round(right_column_ratio, 4),
        "left_column_bias": round(left_column_ratio, 4),
        "max_move_ratio": round(max_move_ratio, 4),
        "max_unexplained_move_ratio": round(max_unexplained_move_ratio, 4),
    }


def _boxes_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for item in items:
        object_id = str(item.get("id") or "")
        bbox = item.get("bbox") or item
        if object_id and all(key in bbox for key in ("x", "y", "w", "h")):
            result[object_id] = {key: int(bbox[key]) for key in ("x", "y", "w", "h")}
    return result


def _is_visual_operation(operation: dict[str, Any]) -> bool:
    object_type = str(operation.get("object_type") or "")
    return object_type in VISUAL_TYPES


def _is_text_operation(operation: dict[str, Any]) -> bool:
    object_type = str(operation.get("object_type") or "")
    return object_type in TEXT_TYPES or (object_type and object_type not in VISUAL_TYPES)


def _has_anchor_relation(operation: dict[str, Any]) -> bool:
    return bool(
        operation.get("anchor_id")
        or operation.get("anchor_to")
        or operation.get("flow_relation") == "anchor_to_visual"
    )


def _right_column_ratio(
    operations: list[dict[str, Any]],
    after: dict[str, dict[str, int]],
    page_width: int,
) -> float:
    if len(operations) < 2:
        return 0.0
    count = 0
    for operation in operations:
        box = after.get(str(operation.get("id") or "")) or operation.get("to") or {}
        original = operation.get("from") or {}
        original_center_x = int(original.get("x", 0)) + int(original.get("w", 0)) / 2
        center_x = int(box.get("x", 0)) + int(box.get("w", 0)) / 2
        if original_center_x <= page_width * 0.70 and center_x > page_width * 0.70:
            count += 1
    return count / len(operations)


def _left_column_ratio(
    operations: list[dict[str, Any]],
    after: dict[str, dict[str, int]],
    page_width: int,
) -> float:
    if len(operations) < 2:
        return 0.0
    count = 0
    for operation in operations:
        box = after.get(str(operation.get("id") or "")) or operation.get("to") or {}
        original = operation.get("from") or {}
        original_center_x = int(original.get("x", 0)) + int(original.get("w", 0)) / 2
        center_x = int(box.get("x", 0)) + int(box.get("w", 0)) / 2
        if original_center_x >= page_width * 0.35 and center_x < page_width * 0.35:
            count += 1
    return count / len(operations)


def _max_move_ratio(
    operations: list[dict[str, Any]],
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
    page_width: int,
) -> float:
    maximum = 0.0
    for operation in operations:
        object_id = str(operation.get("id") or "")
        from_box = operation.get("from") or before.get(object_id)
        to_box = operation.get("to") or after.get(object_id)
        if not from_box or not to_box:
            continue
        maximum = max(maximum, _center_distance(from_box, to_box) / max(1, page_width))
    return maximum


def _center_distance(first: dict[str, Any], second: dict[str, Any]) -> float:
    first_x = int(first.get("x", 0)) + int(first.get("w", 0)) / 2
    first_y = int(first.get("y", 0)) + int(first.get("h", 0)) / 2
    second_x = int(second.get("x", 0)) + int(second.get("w", 0)) / 2
    second_y = int(second.get("y", 0)) + int(second.get("h", 0)) / 2
    return ((first_x - second_x) ** 2 + (first_y - second_y) ** 2) ** 0.5
