from __future__ import annotations

from typing import Any


SIGNIFICANT_OVERLAP = 0.15


def build_overlap_graph(slide: dict[str, Any]) -> dict[str, Any]:
    objects = _objects(slide)
    edges_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for front_index, front in enumerate(objects):
        for back in objects[:front_index]:
            edge = _edge(front, back, ["geometric_overlap"])
            if edge:
                edges_by_key[(edge["front_id"], edge["back_id"])] = edge

    for step in slide.get("animation_steps", []):
        target = _object_by_id(objects, str(step.get("target_id") or ""))
        if target is None:
            target = _object_from_step(step)
        for covered in step.get("covered_objects", []):
            back = _object_by_id(objects, str(covered.get("id") or "")) or _object_from_covered(covered)
            edge = _edge(target, back, ["animation_occlusion"])
            if not edge:
                continue
            key = (edge["front_id"], edge["back_id"])
            if key in edges_by_key:
                reasons = set(edges_by_key[key]["reasons"])
                reasons.update(edge["reasons"])
                edges_by_key[key]["reasons"] = sorted(reasons)
            else:
                edges_by_key[key] = edge

    edges = sorted(
        edges_by_key.values(),
        key=lambda edge: (-edge["severity"], -edge["overlap_ratio"], edge["front_id"], edge["back_id"]),
    )
    return {
        "overlap_edges": edges,
        "max_overlap_ratio": max((edge["overlap_ratio"] for edge in edges), default=0),
        "severe_overlap_count": sum(1 for edge in edges if edge["severity"] >= 0.35),
    }


def _objects(slide: dict[str, Any]) -> list[dict[str, Any]]:
    text_by_id = {str(item.get("id") or ""): item for item in slide.get("text_objects", [])}
    objects: list[dict[str, Any]] = []
    for index, item in enumerate(slide.get("object_boxes", [])):
        bbox = item.get("bbox") or item
        if not _valid_box(bbox):
            continue
        text_item = text_by_id.get(str(item.get("id") or ""))
        objects.append(
            {
                "id": str(item.get("id") or index + 1),
                "text": str(item.get("text") or (text_item or {}).get("text") or ""),
                "bbox": {key: int(bbox[key]) for key in ("x", "y", "w", "h")},
                "z_order": int(item.get("z_order", index)),
                "type": item.get("type", ""),
                "name": item.get("name", ""),
            }
        )
    objects.sort(key=lambda obj: obj["z_order"])
    return objects


def _object_by_id(objects: list[dict[str, Any]], object_id: str) -> dict[str, Any] | None:
    return next((obj for obj in objects if obj["id"] == object_id), None)


def _object_from_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(step.get("target_id") or ""),
        "text": str(step.get("target_text") or ""),
        "bbox": step.get("bbox") or {"x": 0, "y": 0, "w": 0, "h": 0},
        "z_order": 999,
        "type": "",
        "name": "",
    }


def _object_from_covered(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or ""),
        "text": str(item.get("text") or ""),
        "bbox": item.get("bbox") or {"x": 0, "y": 0, "w": 0, "h": 0},
        "z_order": 0,
        "type": "",
        "name": "",
    }


def _edge(front: dict[str, Any], back: dict[str, Any], reasons: list[str]) -> dict[str, Any] | None:
    front_box = front.get("bbox") or {}
    back_box = back.get("bbox") or {}
    overlap = _overlap_area(front_box, back_box)
    smaller = min(_area(front_box), _area(back_box))
    if not smaller:
        return None
    ratio = overlap / smaller
    if ratio < SIGNIFICANT_OVERLAP and "animation_occlusion" not in reasons:
        return None
    severity = ratio + (0.2 if front.get("text") and back.get("text") else 0) + (0.18 if "animation_occlusion" in reasons else 0)
    return {
        "front_id": str(front.get("id") or ""),
        "back_id": str(back.get("id") or ""),
        "front_text": str(front.get("text") or ""),
        "back_text": str(back.get("text") or ""),
        "front_bbox": front_box,
        "back_bbox": back_box,
        "overlap_area": overlap,
        "overlap_ratio": ratio,
        "severity": round(severity, 4),
        "reasons": reasons,
    }


def _valid_box(box: dict[str, Any]) -> bool:
    return all(key in box for key in ("x", "y", "w", "h")) and int(box.get("w", 0)) > 0 and int(box.get("h", 0)) > 0


def _area(box: dict[str, Any]) -> int:
    return max(0, int(box.get("w", 0))) * max(0, int(box.get("h", 0)))


def _overlap_area(first: dict[str, Any], second: dict[str, Any]) -> int:
    left = max(int(first.get("x", 0)), int(second.get("x", 0)))
    top = max(int(first.get("y", 0)), int(second.get("y", 0)))
    right = min(int(first.get("x", 0)) + int(first.get("w", 0)), int(second.get("x", 0)) + int(second.get("w", 0)))
    bottom = min(int(first.get("y", 0)) + int(first.get("h", 0)), int(second.get("y", 0)) + int(second.get("h", 0)))
    return max(0, right - left) * max(0, bottom - top)
