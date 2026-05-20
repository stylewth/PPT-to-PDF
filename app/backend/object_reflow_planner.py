from __future__ import annotations

from typing import Any

from reflow_diagnostics import build_overlap_graph
from reflow_groups import build_reflow_groups


DEFAULT_PAGE = {"width": 12192000, "height": 6858000}


def plan_object_reflow(slide: dict[str, Any]) -> dict[str, Any]:
    page = slide.get("size") or DEFAULT_PAGE
    page_width = int(page.get("width") or DEFAULT_PAGE["width"])
    page_height = int(page.get("height") or DEFAULT_PAGE["height"])
    objects = _objects(slide)
    graph = build_overlap_graph(slide)
    semantic_groups = build_reflow_groups(slide)
    candidate_ids = _candidate_ids(graph, objects, slide, page_height, semantic_groups)
    if not candidate_ids:
        return {"type": "object_reflow", "operations": [], "overlap_graph": graph, "semantic_groups": semantic_groups}

    candidates = [obj for obj in objects if obj["id"] in candidate_ids]
    stable = [obj for obj in objects if obj["id"] not in candidate_ids]
    operations = _pack_candidates(candidates, stable, page_width, page_height, semantic_groups)
    after_boxes = simulate_operations(slide.get("object_boxes", []), operations)

    return {
        "type": "object_reflow",
        "policy": "move_shapes_then_convert",
        "overlap_graph": graph,
        "semantic_groups": semantic_groups,
        "before_max_overlap_ratio": max_overlap_ratio(slide.get("object_boxes", [])),
        "after_max_overlap_ratio": max_overlap_ratio(after_boxes),
        "operations": operations,
    }


def simulate_operations(boxes: list[dict[str, Any]], operations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str((item.get("id") or "")): _box_record(item) for item in boxes if _box_value(item)}
    for operation in operations:
        if operation.get("op") not in {"move_resize", "move", "resize"}:
            continue
        object_id = str(operation.get("id") or "")
        if object_id not in by_id:
            continue
        to_box = operation.get("to") or {}
        record = by_id[object_id]
        for key in ("x", "y", "w", "h"):
            if key in to_box:
                record["bbox"][key] = int(to_box[key])
    return list(by_id.values())


def max_overlap_ratio(boxes: list[dict[str, Any]]) -> float:
    normalized = [_box_record(item) for item in boxes if _box_value(item)]
    maximum = 0.0
    for index, first in enumerate(normalized):
        for second in normalized[index + 1 :]:
            smaller = min(_area(first["bbox"]), _area(second["bbox"]))
            if not smaller:
                continue
            maximum = max(maximum, _overlap_area(first["bbox"], second["bbox"]) / smaller)
    return maximum


def _candidate_ids(
    graph: dict[str, Any],
    objects: list[dict[str, Any]],
    slide: dict[str, Any],
    page_height: int,
    semantic_groups: list[dict[str, Any]],
) -> set[str]:
    ids: set[str] = set()
    by_id = {obj["id"]: obj for obj in objects}
    for edge in graph.get("overlap_edges", []):
        if edge.get("severity", 0) < 0.28:
            continue
        front_id = str(edge.get("front_id") or "")
        back_id = str(edge.get("back_id") or "")
        front = by_id.get(front_id)
        back = by_id.get(back_id)
        if front is None or back is None:
            continue
        front_visual = _is_visual(front)
        back_visual = _is_visual(back)
        if front_visual and not back_visual:
            ids.add(front_id)
        elif not front_visual and back_visual:
            ids.add(front_id)
        elif not front_visual and not back_visual:
            ids.add(front_id)
            ids.add(back_id)
        else:
            ids.add(front_id)
    for group in semantic_groups:
        for visual_id in group.get("visual_ids", []):
            ids.add(str(visual_id))
    return {item for item in ids if item}


def _has_text(obj: dict[str, Any]) -> bool:
    return bool(str(obj.get("text") or "").strip())


def _is_body_object(obj: dict[str, Any], page_height: int) -> bool:
    box = obj["bbox"]
    name = str(obj.get("name") or "").strip().lower()
    text = str(obj.get("text") or "").strip()
    if box["y"] < page_height * 0.08:
        return False
    if box["y"] < page_height * 0.2 and name == "title":
        return False
    if box["y"] < page_height * 0.24 and text.startswith("("):
        return False
    return True


def _pack_candidates(
    candidates: list[dict[str, Any]],
    stable: list[dict[str, Any]],
    page_width: int,
    page_height: int,
    semantic_groups: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    text_candidates = [obj for obj in candidates if _has_text(obj)]
    visual_candidates = [obj for obj in candidates if _is_visual(obj)]
    stable_visuals = [obj for obj in stable if _is_visual(obj) and _is_body_object(obj, page_height)]
    associations = _associate_visuals(text_candidates, visual_candidates + stable_visuals, page_width, page_height)
    associations.update(_semantic_associations(semantic_groups or [], text_candidates + stable, visual_candidates + stable_visuals))
    associated_ids = set(associations)

    operations: list[dict[str, Any]] = []
    if text_candidates:
        text_stable = [obj for obj in stable if obj["id"] not in associated_ids]
        operations.extend(_repair_text_overlaps_locally(text_candidates, text_stable, page_width, page_height))
    elif not associations:
        operations.extend(_repair_loose_visuals_locally(visual_candidates, stable, page_width, page_height))

    text_targets = {
        operation["id"]: operation["to"]
        for operation in operations
        if operation.get("op") == "move_resize"
    }
    loose_visuals = [obj for obj in visual_candidates if obj["id"] not in associated_ids]
    associated_visuals = [
        obj for obj in visual_candidates + stable_visuals
        if obj["id"] in associated_ids
    ]
    operations.extend(_repair_loose_visuals_locally(loose_visuals, stable, page_width, page_height))
    placed_targets = {
        operation["id"]: operation["to"]
        for operation in operations
        if operation.get("op") == "move_resize"
    }
    operations.extend(
        _pack_associated_visuals(
            associated_visuals,
            associations,
            placed_targets,
            [obj["bbox"] for obj in stable if obj["id"] not in associated_ids],
            page_width,
            page_height,
        )
    )
    return operations


def _repair_text_overlaps_locally(
    candidates: list[dict[str, Any]],
    stable: list[dict[str, Any]],
    page_width: int,
    page_height: int,
) -> list[dict[str, Any]]:
    candidates = sorted(candidates, key=lambda obj: (obj["bbox"]["y"], obj["bbox"]["x"]))
    margin = max(120000, int(page_width * 0.012))
    gap = max(260000, int(page_height * 0.04))
    bottom_limit = page_height - max(margin, int(page_height * 0.08))
    next_y = max(margin, min(obj["bbox"]["y"] for obj in candidates) - gap // 2)

    operations: list[dict[str, Any]] = []
    placed = [dict(obj["bbox"]) for obj in stable]
    for obj in candidates:
        original = obj["bbox"]
        target = {
            "x": _clamp(original["x"], margin, page_width - margin - original["w"]),
            "y": _clamp(next_y, margin, bottom_limit - original["h"]),
            "w": original["w"],
            "h": original["h"],
        }
        target = _avoid_text_collisions(target, placed, margin, page_width, bottom_limit, gap)
        placed.append(target)
        next_y = target["y"] + target["h"] + gap
        if _changed(original, target):
            operations.append(
                {
                    "op": "move_resize",
                    "id": obj["id"],
                    "object_type": obj.get("type", ""),
                    "from": original,
                    "to": target,
                    "reason": _reason(obj),
                }
            )
    return operations


def _repair_loose_visuals_locally(
    candidates: list[dict[str, Any]],
    stable: list[dict[str, Any]],
    page_width: int,
    page_height: int,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    candidates = sorted(candidates, key=lambda obj: (obj["bbox"]["y"], obj["bbox"]["x"]))
    margin = max(120000, int(page_width * 0.012))
    gap = max(260000, int(page_height * 0.04))
    bottom_limit = page_height - max(margin, int(page_height * 0.08))
    operations: list[dict[str, Any]] = []
    placed = [dict(obj["bbox"]) for obj in stable]
    for obj in candidates:
        original = obj["bbox"]
        scale = 1.0 if _preserve_geometry(obj) else min(
            1.0,
            int(page_height * 0.22) / max(1, original["h"]),
        )
        target_w = max(1, int(original["w"] * scale))
        target_h = max(1, int(original["h"] * scale))
        target = _local_visual_target(original, target_w, target_h, placed, margin, page_width, bottom_limit, gap)
        placed.append(target)
        if _changed(original, target):
            operations.append(
                {
                    "op": "move_resize",
                    "id": obj["id"],
                    "object_type": obj.get("type", ""),
                    **({"render_mode": "pdf_region_overlay"} if _preserve_geometry(obj) else {}),
                    "from": original,
                    "to": target,
                    "reason": _reason(obj),
                }
            )
    return operations


def _pack_associated_visuals(
    visuals: list[dict[str, Any]],
    associations: dict[str, dict[str, Any]],
    text_targets: dict[str, dict[str, int]],
    occupied_boxes: list[dict[str, int]],
    page_width: int,
    page_height: int,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    placed: list[dict[str, int]] = [dict(target) for target in text_targets.values()] + [dict(box) for box in occupied_boxes]
    for obj in sorted(
        visuals,
        key=lambda item: (
            associations[item["id"]]["bbox"]["y"],
            0 if _preserve_geometry(item) else 1,
            item["bbox"]["y"],
            item["bbox"]["x"],
        ),
    ):
        anchor = associations[obj["id"]]
        anchor_target = text_targets.get(anchor["id"], anchor["bbox"])
        target = _target_near_anchor(obj, anchor, anchor_target, page_width, page_height, placed)
        placed.append(target)
        if _changed(obj["bbox"], target):
            operations.append(
                {
                    "op": "move_resize",
                    "id": obj["id"],
                    "object_type": obj.get("type", ""),
                    **({"render_mode": "pdf_region_overlay"} if _preserve_geometry(obj) else {}),
                    "from": obj["bbox"],
                    "to": target,
                    "anchor_id": anchor["id"],
                    "anchor_to": anchor_target,
                    "flow_relation": "anchor_to_visual",
                    "reason": "随相关正文微调位置，保留图文对应关系。",
                }
            )
    return operations


def _target_near_anchor(
    obj: dict[str, Any],
    anchor: dict[str, Any],
    anchor_target: dict[str, int],
    page_width: int,
    page_height: int,
    placed: list[dict[str, int]],
) -> dict[str, int]:
    original = obj["bbox"]
    anchor_original = anchor["bbox"]
    margin = max(120000, int(page_width * 0.012))
    gap = max(220000, int(page_width * 0.018))
    preserve_geometry = _preserve_geometry(obj)
    if preserve_geometry:
        gap = max(gap, int(page_width * 0.055))
    bottom_limit = page_height - max(margin, int(page_height * 0.08))
    original_side = _relative_side(original, anchor_original)

    scale = 1.0 if preserve_geometry else min(1.0, int(page_height * 0.24) / max(1, original["h"]))
    if preserve_geometry and original_side == "below":
        vertical_room = _vertical_room_below(anchor_target, placed, bottom_limit)
        if vertical_room < original["h"]:
            scale = max(0.62, vertical_room / max(1, original["h"]))
    right_x = anchor_target["x"] + anchor_target["w"] + gap
    right_width = page_width - margin - right_x
    if right_width > page_width * 0.10 and not preserve_geometry:
        scale = min(scale, right_width / max(1, original["w"]))
    target_w = max(1, int(original["w"] * scale))
    target_h = max(1, int(original["h"] * scale))

    candidates = _visual_position_candidates(
        original,
        anchor_original,
        anchor_target,
        target_w,
        target_h,
        margin,
        page_width,
        bottom_limit,
        gap,
    )
    scored: list[tuple[float, dict[str, int]]] = []
    for candidate in candidates:
        adjusted = _avoid_visual_collisions(
            candidate,
            placed,
            margin,
            page_width,
            bottom_limit,
            gap,
            allow_scale=True,
        )
        scored.append(
            (
                _visual_candidate_score(adjusted, original, anchor_original, anchor_target, placed, original_side, page_width, page_height),
                adjusted,
            )
        )
    return min(scored, key=lambda item: item[0])[1]


def _avoid_text_collisions(
    target: dict[str, int],
    placed: list[dict[str, int]],
    margin: int,
    page_width: int,
    bottom_limit: int,
    gap: int,
) -> dict[str, int]:
    adjusted = dict(target)
    for _ in range(8):
        previous = next((item for item in placed if _overlap_ratio(adjusted, item) > 0.02), None)
        if previous is None:
            break
        below = previous["y"] + previous["h"] + gap
        if below + adjusted["h"] <= bottom_limit:
            adjusted["y"] = below
            continue
        above = previous["y"] - gap - adjusted["h"]
        if above >= margin:
            adjusted["y"] = above
            continue
        right = previous["x"] + previous["w"] + gap
        if right + adjusted["w"] <= page_width - margin:
            adjusted["x"] = right
            adjusted["y"] = _clamp(adjusted["y"], margin, bottom_limit - adjusted["h"])
            continue
        left = previous["x"] - gap - adjusted["w"]
        if left >= margin:
            adjusted["x"] = left
            adjusted["y"] = _clamp(adjusted["y"], margin, bottom_limit - adjusted["h"])
            continue
        adjusted["y"] = _clamp(below, margin, bottom_limit - adjusted["h"])
    return adjusted


def _local_visual_target(
    original: dict[str, int],
    target_w: int,
    target_h: int,
    placed: list[dict[str, int]],
    margin: int,
    page_width: int,
    bottom_limit: int,
    gap: int,
) -> dict[str, int]:
    original_x = _clamp(original["x"], margin, page_width - margin - target_w)
    original_y = _clamp(original["y"], margin, bottom_limit - target_h)
    boxes = [
        {"x": original_x, "y": original_y, "w": target_w, "h": target_h},
        {"x": original_x, "y": _clamp(original["y"] + original["h"] + gap, margin, bottom_limit - target_h), "w": target_w, "h": target_h},
        {"x": original_x, "y": _clamp(original["y"] - gap - target_h, margin, bottom_limit - target_h), "w": target_w, "h": target_h},
        {"x": _clamp(original["x"] + original["w"] + gap, margin, page_width - margin - target_w), "y": original_y, "w": target_w, "h": target_h},
        {"x": _clamp(original["x"] - gap - target_w, margin, page_width - margin - target_w), "y": original_y, "w": target_w, "h": target_h},
    ]
    scored: list[tuple[float, dict[str, int]]] = []
    for box in boxes:
        adjusted = _avoid_visual_collisions(box, placed, margin, page_width, bottom_limit, gap, allow_scale=True)
        overlap = max([_overlap_ratio(adjusted, item) for item in placed] or [0.0])
        movement = _center_distance(adjusted, original)
        right_bias = page_width * 0.22 if adjusted["x"] + adjusted["w"] / 2 > page_width * 0.70 else 0
        scored.append((overlap * page_width * 20 + movement + right_bias, adjusted))
    return min(scored, key=lambda item: item[0])[1]


def _visual_position_candidates(
    original: dict[str, int],
    anchor_original: dict[str, int],
    anchor_target: dict[str, int],
    target_w: int,
    target_h: int,
    margin: int,
    page_width: int,
    bottom_limit: int,
    gap: int,
) -> list[dict[str, int]]:
    relative_x = original["x"] - anchor_original["x"]
    relative_y = original["y"] - anchor_original["y"]
    aligned_x = _clamp(anchor_target["x"] + relative_x, margin, page_width - margin - target_w)
    centered_x = _clamp(anchor_target["x"] + anchor_target["w"] // 2 - target_w // 2, margin, page_width - margin - target_w)
    original_x = _clamp(original["x"], margin, page_width - margin - target_w)
    boxes = [
        {
            "x": aligned_x,
            "y": _clamp(anchor_target["y"] + relative_y, margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": aligned_x,
            "y": _clamp(anchor_target["y"] + anchor_target["h"], margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": _clamp(anchor_target["x"] + max(0, min(relative_x, anchor_target["w"] - target_w)), margin, page_width - margin - target_w),
            "y": _clamp(anchor_target["y"] + anchor_target["h"] + gap // 2, margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": centered_x,
            "y": _clamp(anchor_target["y"] - gap // 2 - target_h, margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": _clamp(anchor_target["x"] + anchor_target["w"] + gap // 2, margin, page_width - margin - target_w),
            "y": _clamp(anchor_target["y"] + relative_y, margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": _clamp(anchor_target["x"] - gap // 2 - target_w, margin, page_width - margin - target_w),
            "y": _clamp(anchor_target["y"] + relative_y, margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
        {
            "x": original_x,
            "y": _clamp(original["y"], margin, bottom_limit - target_h),
            "w": target_w,
            "h": target_h,
        },
    ]
    result: list[dict[str, int]] = []
    seen: set[tuple[int, int, int, int]] = set()
    for box in boxes:
        key = (box["x"], box["y"], box["w"], box["h"])
        if key in seen:
            continue
        seen.add(key)
        result.append(box)
    return result


def _visual_candidate_score(
    candidate: dict[str, int],
    original: dict[str, int],
    anchor_original: dict[str, int],
    anchor_target: dict[str, int],
    placed: list[dict[str, int]],
    original_side: str,
    page_width: int,
    page_height: int,
) -> float:
    overlap = max([_overlap_ratio(candidate, item) for item in placed] or [0.0])
    movement = _center_distance(candidate, original)
    anchor_distance = _center_distance(candidate, anchor_target)
    side = _relative_side(candidate, anchor_target)
    side_penalty = 0 if side == original_side else page_width * 0.12
    right_bias_penalty = page_width * 0.10 if side == "right" and original_side != "right" else 0
    left_bias_penalty = page_width * 0.18 if side == "left" and original_side != "left" else 0
    edge_penalty = page_width * 0.04 if candidate["x"] + candidate["w"] > page_width * 0.90 else 0
    vertical_band_penalty = _vertical_band_penalty(candidate, original, anchor_original, anchor_target, page_width)
    scale_penalty = abs(candidate["w"] - original["w"]) + abs(candidate["h"] - original["h"])
    return (
        overlap * page_width * 20
        + movement * 0.80
        + anchor_distance * 0.18
        + side_penalty
        + right_bias_penalty
        + left_bias_penalty
        + edge_penalty
        + vertical_band_penalty
        + scale_penalty * 0.35
    )


def _vertical_band_penalty(
    candidate: dict[str, int],
    original: dict[str, int],
    anchor_original: dict[str, int],
    anchor_target: dict[str, int],
    page_width: int,
) -> float:
    original_center_y = original["y"] + original["h"] / 2
    if not (anchor_original["y"] <= original_center_y <= anchor_original["y"] + anchor_original["h"]):
        return 0.0
    candidate_center_y = candidate["y"] + candidate["h"] / 2
    if anchor_target["y"] <= candidate_center_y <= anchor_target["y"] + anchor_target["h"]:
        return 0.0
    return page_width * 0.30


def _vertical_room_below(anchor: dict[str, int], placed: list[dict[str, int]], bottom_limit: int) -> int:
    anchor_bottom = anchor["y"] + anchor["h"]
    next_top = bottom_limit
    for box in placed:
        if box["y"] <= anchor_bottom:
            continue
        horizontal_overlap = _axis_overlap(
            anchor["x"],
            anchor["x"] + anchor["w"],
            box["x"],
            box["x"] + box["w"],
        )
        if horizontal_overlap <= 0:
            continue
        next_top = min(next_top, box["y"])
    return max(0, next_top - anchor_bottom)


def _relative_side(box: dict[str, int], anchor: dict[str, int]) -> str:
    center_x = box["x"] + box["w"] / 2
    center_y = box["y"] + box["h"] / 2
    anchor_left = anchor["x"]
    anchor_right = anchor["x"] + anchor["w"]
    anchor_top = anchor["y"]
    anchor_bottom = anchor["y"] + anchor["h"]
    if center_y >= anchor_bottom:
        return "below"
    if center_y <= anchor_top:
        return "above"
    if center_x >= anchor_right:
        return "right"
    if center_x <= anchor_left:
        return "left"
    return "overlap"


def _center_distance(first: dict[str, int], second: dict[str, int]) -> float:
    first_x = first["x"] + first["w"] / 2
    first_y = first["y"] + first["h"] / 2
    second_x = second["x"] + second["w"] / 2
    second_y = second["y"] + second["h"] / 2
    return abs(first_x - second_x) + abs(first_y - second_y)


def _avoid_visual_collisions(
    target: dict[str, int],
    placed: list[dict[str, int]],
    margin: int,
    page_width: int,
    bottom_limit: int,
    gap: int,
    *,
    allow_scale: bool,
) -> dict[str, int]:
    adjusted = dict(target)
    for _ in range(8):
        previous = next((item for item in placed if _overlap_ratio(adjusted, item) > 0.02), None)
        if previous is None:
            break
        right = previous["x"] + previous["w"] + gap // 2
        right_width = page_width - margin - right
        if allow_scale and right_width >= adjusted["w"] * 0.62:
            scale = min(1.0, right_width / max(1, adjusted["w"]))
            adjusted["x"] = right
            adjusted["w"] = max(1, int(adjusted["w"] * scale))
            adjusted["h"] = max(1, int(adjusted["h"] * scale))
            adjusted["y"] = _clamp(adjusted["y"], margin, bottom_limit - adjusted["h"])
            continue
        below = previous["y"] + previous["h"] + gap // 2
        if below + adjusted["h"] <= bottom_limit:
            adjusted["y"] = below
            continue
        above = previous["y"] - gap // 2 - adjusted["h"]
        if above >= margin:
            adjusted["y"] = above
            adjusted["x"] = min(
                max(adjusted["x"], previous["x"] + previous["w"] + gap // 2),
                page_width - margin - adjusted["w"],
            )
            continue
        left = previous["x"] - gap // 2 - adjusted["w"]
        if left >= margin:
            adjusted["x"] = left
            adjusted["y"] = _clamp(adjusted["y"], margin, bottom_limit - adjusted["h"])
            continue
        adjusted["y"] = _clamp(below, margin, bottom_limit - adjusted["h"])
    return adjusted


def _associate_visuals(
    text_candidates: list[dict[str, Any]],
    visuals: list[dict[str, Any]],
    page_width: int,
    page_height: int,
) -> dict[str, dict[str, Any]]:
    associations: dict[str, dict[str, Any]] = {}
    if not text_candidates:
        return associations
    for visual in visuals:
        best_score: float | None = None
        best_text: dict[str, Any] | None = None
        for text in text_candidates:
            score = _association_score(visual["bbox"], text["bbox"], page_width, page_height)
            if score is None:
                continue
            if best_score is None or score < best_score:
                best_score = score
                best_text = text
        if best_text is not None:
            associations[visual["id"]] = best_text
    return associations


def _semantic_associations(
    semantic_groups: list[dict[str, Any]],
    objects: list[dict[str, Any]],
    visuals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_id = {obj["id"]: obj for obj in objects}
    visual_ids = {obj["id"] for obj in visuals}
    associations: dict[str, dict[str, Any]] = {}
    for group in semantic_groups:
        anchor = by_id.get(str(group.get("anchor_id") or ""))
        if anchor is None:
            continue
        for visual_id in group.get("visual_ids", []):
            object_id = str(visual_id)
            if object_id in visual_ids:
                associations[object_id] = anchor
    return associations


def _association_score(
    visual: dict[str, int],
    text: dict[str, int],
    page_width: int,
    page_height: int,
) -> float | None:
    gap_x = _axis_gap(visual["x"], visual["x"] + visual["w"], text["x"], text["x"] + text["w"])
    gap_y = _axis_gap(visual["y"], visual["y"] + visual["h"], text["y"], text["y"] + text["h"])
    overlap_x = _axis_overlap(visual["x"], visual["x"] + visual["w"], text["x"], text["x"] + text["w"]) / max(1, min(visual["w"], text["w"]))
    overlap_y = _axis_overlap(visual["y"], visual["y"] + visual["h"], text["y"], text["y"] + text["h"]) / max(1, min(visual["h"], text["h"]))
    close_x = overlap_x >= 0.18 or gap_x <= page_width * 0.08
    close_y = overlap_y >= 0.08 or gap_y <= page_height * 0.14
    if not close_x or not close_y:
        return None
    visual_center_y = visual["y"] + visual["h"] / 2
    text_center_y = text["y"] + text["h"] / 2
    return gap_x + gap_y * 1.35 + abs(visual_center_y - text_center_y) * 0.15 - overlap_x * page_width * 0.04 - overlap_y * page_height * 0.04


def _is_visual(obj: dict[str, Any]) -> bool:
    obj_type = str(obj.get("type") or "")
    return not _has_text(obj) or obj_type in {"pic", "graphicFrame"}


def _preserve_geometry(obj: dict[str, Any]) -> bool:
    return str(obj.get("type") or "") == "graphicFrame"


def _would_overlap_stable(target: dict[str, int], stable: list[dict[str, Any]]) -> bool:
    target_area = _area(target)
    if not target_area:
        return False
    for item in stable:
        other = item["bbox"]
        smaller = min(target_area, _area(other))
        if smaller and _overlap_area(target, other) / smaller > 0.2:
            return True
    return False


def _is_small_visual(obj: dict[str, Any], page_width: int) -> bool:
    box = obj["bbox"]
    text = str(obj.get("text") or "").strip()
    return not text or box["w"] <= page_width * 0.18


def _reason(obj: dict[str, Any]) -> str:
    if _is_small_visual(obj, DEFAULT_PAGE["width"]):
        return "将浮动公式/图片移到清晰空白区，解除正文遮挡。"
    return "调整文本对象位置，降低页面重叠并保持原有内容。"


def _changed(original: dict[str, int], target: dict[str, int]) -> bool:
    return any(abs(int(original[key]) - int(target[key])) > 20000 for key in ("x", "y", "w", "h"))


def _objects(slide: dict[str, Any]) -> list[dict[str, Any]]:
    text_by_id = {str(item.get("id") or ""): item for item in slide.get("text_objects", [])}
    result: list[dict[str, Any]] = []
    for index, item in enumerate(slide.get("object_boxes", [])):
        box = _box_value(item)
        if not box:
            continue
        text_item = text_by_id.get(str(item.get("id") or ""))
        result.append(
            {
                "id": str(item.get("id") or index + 1),
                "name": str(item.get("name") or ""),
                "type": str(item.get("type") or ""),
                "text": str(item.get("text") or (text_item or {}).get("text") or ""),
                "bbox": {key: int(box[key]) for key in ("x", "y", "w", "h")},
                "z_order": int(item.get("z_order", index)),
            }
        )
    return result


def _box_record(item: dict[str, Any]) -> dict[str, Any]:
    box = _box_value(item) or {"x": 0, "y": 0, "w": 0, "h": 0}
    return {
        "id": str(item.get("id") or ""),
        "bbox": {key: int(box[key]) for key in ("x", "y", "w", "h")},
    }


def _box_value(item: dict[str, Any]) -> dict[str, Any] | None:
    box = item.get("bbox") or item
    if not all(key in box for key in ("x", "y", "w", "h")):
        return None
    if int(box.get("w", 0)) <= 0 or int(box.get("h", 0)) <= 0:
        return None
    return box


def _area(box: dict[str, Any]) -> int:
    return max(0, int(box.get("w", 0))) * max(0, int(box.get("h", 0)))


def _overlap_area(first: dict[str, Any], second: dict[str, Any]) -> int:
    left = max(int(first.get("x", 0)), int(second.get("x", 0)))
    top = max(int(first.get("y", 0)), int(second.get("y", 0)))
    right = min(int(first.get("x", 0)) + int(first.get("w", 0)), int(second.get("x", 0)) + int(second.get("w", 0)))
    bottom = min(int(first.get("y", 0)) + int(first.get("h", 0)), int(second.get("y", 0)) + int(second.get("h", 0)))
    return max(0, right - left) * max(0, bottom - top)


def _overlap_ratio(first: dict[str, int], second: dict[str, int]) -> float:
    smaller = min(_area(first), _area(second))
    if not smaller:
        return 0.0
    return _overlap_area(first, second) / smaller


def _axis_gap(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
    if first_end < second_start:
        return second_start - first_end
    if second_end < first_start:
        return first_start - second_end
    return 0


def _axis_overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
    return max(0, min(first_end, second_end) - max(first_start, second_start))


def _clamp(value: int, lower: int, upper: int) -> int:
    if upper < lower:
        return lower
    return max(lower, min(value, upper))
