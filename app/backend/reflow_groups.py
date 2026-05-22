from __future__ import annotations

from typing import Any


VISUAL_TYPES = {"pic", "graphicFrame", "cxnSp"}


def build_reflow_groups(slide: dict[str, Any]) -> list[dict[str, Any]]:
    objects = _objects_by_id(slide)
    groups: dict[str, dict[str, Any]] = {}
    for step in slide.get("animation_steps", []):
        target_id = str(step.get("target_id") or "")
        target = objects.get(target_id)
        for covered in step.get("covered_objects", []):
            anchor_id = str(covered.get("id") or "")
            anchor = objects.get(anchor_id)
            if anchor is None:
                continue
            group = groups.setdefault(anchor_id, _new_group(anchor))
            if target is not None:
                _add_member(group, target)
    _attach_nearby_grouped_visuals(groups, objects)
    return list(groups.values())


def _new_group(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_id": anchor["id"],
        "member_ids": [anchor["id"]],
        "text_ids": [anchor["id"]] if _has_text(anchor) else [],
        "visual_ids": [],
        "bbox": dict(anchor["bbox"]),
    }


def _add_member(group: dict[str, Any], obj: dict[str, Any]) -> None:
    object_id = obj["id"]
    if object_id in group["member_ids"]:
        return
    group["member_ids"].append(object_id)
    if _has_text(obj):
        group["text_ids"].append(object_id)
    if obj.get("type") in VISUAL_TYPES:
        group["visual_ids"].append(object_id)
    group["bbox"] = _union(group["bbox"], obj["bbox"])


def _objects_by_id(slide: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in slide.get("object_boxes", []):
        bbox = item.get("bbox")
        if not bbox:
            continue
        object_id = str(item.get("id") or "")
        if not object_id:
            continue
        result[object_id] = {
            "id": object_id,
            "type": item.get("type", ""),
            "text": item.get("text", ""),
            "bbox": {key: int(bbox[key]) for key in ("x", "y", "w", "h")},
            "in_group": bool(item.get("in_group")),
        }
    return result


def _attach_nearby_grouped_visuals(groups: dict[str, dict[str, Any]], objects: dict[str, dict[str, Any]]) -> None:
    if not groups:
        return
    for group in groups.values():
        changed = True
        while changed:
            changed = False
            members = [objects[item_id] for item_id in group["member_ids"] if item_id in objects]
            visual_members = [item for item in members if item.get("type") in VISUAL_TYPES]
            if not visual_members:
                break
            for obj in objects.values():
                if obj["id"] in group["member_ids"]:
                    continue
                if not obj.get("in_group") or obj.get("type") not in VISUAL_TYPES:
                    continue
                if any(_visually_adjacent(obj["bbox"], member["bbox"]) for member in visual_members):
                    _add_member(group, obj)
                    changed = True


def _visually_adjacent(first: dict[str, int], second: dict[str, int]) -> bool:
    gap_x = _axis_gap(first["x"], first["x"] + first["w"], second["x"], second["x"] + second["w"])
    gap_y = _axis_gap(first["y"], first["y"] + first["h"], second["y"], second["y"] + second["h"])
    overlap_x = _axis_overlap(first["x"], first["x"] + first["w"], second["x"], second["x"] + second["w"])
    overlap_y = _axis_overlap(first["y"], first["y"] + first["h"], second["y"], second["y"] + second["h"])
    close_x = overlap_x > 0 or gap_x <= max(first["w"], second["w"]) * 0.25
    close_y = overlap_y > 0 or gap_y <= max(first["h"], second["h"]) * 0.45
    return close_x and close_y


def _has_text(obj: dict[str, Any]) -> bool:
    return bool(str(obj.get("text") or "").strip())


def _union(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    left = min(first["x"], second["x"])
    top = min(first["y"], second["y"])
    right = max(first["x"] + first["w"], second["x"] + second["w"])
    bottom = max(first["y"] + first["h"], second["y"] + second["h"])
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}


def _axis_gap(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
    if first_end < second_start:
        return second_start - first_end
    if second_end < first_start:
        return first_start - second_end
    return 0


def _axis_overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> int:
    return max(0, min(first_end, second_end) - max(first_start, second_start))
