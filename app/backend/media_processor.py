from __future__ import annotations

import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any


DYNAMIC_MEDIA_KINDS = {"gif", "video", "audio"}
MAX_GIF_STRIP_FRAMES = 6
MAX_STRIP_FRAME_SIZE = (240, 135)


def process_presentation_media(
    pptx_path: str | Path,
    presentation: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "media_manifest.json"
    media_dir = output / "media"
    preview_dir = media_dir / "previews"
    media_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, Any]] = []
    with zipfile.ZipFile(pptx_path, "r") as package:
        for slide in presentation.get("slides", []):
            for obj in slide.get("objects", []):
                media = obj.get("media") or {}
                kind = media.get("kind")
                if kind not in DYNAMIC_MEDIA_KINDS:
                    continue
                items.append(_process_media_object(package, output, media_dir, preview_dir, slide, obj, media))

    manifest = {
        "kind": "media_manifest",
        "version": "v1",
        "page": presentation.get("page") or {},
        "summary": _summary(items),
        "items": items,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _process_media_object(
    package: zipfile.ZipFile,
    output: Path,
    media_dir: Path,
    preview_dir: Path,
    slide: dict[str, Any],
    obj: dict[str, Any],
    media: dict[str, Any],
) -> dict[str, Any]:
    media_path = str(media.get("path") or "")
    if not media_path:
        raise ValueError(f"Media object {obj.get('id')} has no package path.")
    try:
        data = package.read(media_path)
    except KeyError as exc:
        raise ValueError(f"Media file not found in PPTX package: {media_path}") from exc

    slide_number = int(slide.get("number") or 0)
    object_id = str(obj.get("id") or "media")
    original_name = Path(media_path).name
    stem = _safe_stem(f"slide{slide_number}_obj{object_id}_{Path(original_name).stem}")
    extension = str(media.get("extension") or Path(media_path).suffix).lower()
    export_path = media_dir / f"{stem}{extension}"
    export_path.write_bytes(data)

    item = {
        "slide_number": slide_number,
        "object_id": object_id,
        "object_name": obj.get("name", ""),
        "kind": media.get("kind", ""),
        "extension": extension,
        "source_path": media_path,
        "export_path": _relative(output, export_path),
        "bbox": obj.get("bbox"),
        "occupied_boxes": _slide_occupied_boxes(slide, obj),
        "status": "exported",
    }
    if media.get("kind") == "gif":
        item["preview"] = _write_gif_preview(data, preview_dir, stem, output)
        item["status"] = "ok"
    elif media.get("kind") == "video":
        item["status"] = "exported_original_only"
        item["note"] = "视频已导出原文件；关键帧摘要将在 ffmpeg 接入后生成。"
    elif media.get("kind") == "audio":
        item["status"] = "exported_original_only"
        item["note"] = "音频已导出原文件；转写摘要不在当前阶段生成。"
    return item


def _write_gif_preview(data: bytes, preview_dir: Path, stem: str, output: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageDraw, ImageSequence
    except ImportError as exc:
        raise RuntimeError("Pillow is required to process GIF media.") from exc

    with Image.open(BytesIO(data)) as image:
        frames = [frame.convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if not frames:
            raise ValueError("GIF media has no readable frames.")
        durations = [
            int(getattr(frame, "info", {}).get("duration", image.info.get("duration", 0)) or 0)
            for frame in ImageSequence.Iterator(image)
        ]
        frame_count = len(frames)
        sampled = _sample_indices(frame_count, MAX_GIF_STRIP_FRAMES)

        poster_path = preview_dir / f"{stem}_poster.png"
        strip_path = preview_dir / f"{stem}_strip.png"
        grid_path = preview_dir / f"{stem}_grid.png"
        frames[0].save(poster_path, format="PNG")

        thumbs = [_thumbnail(frames[index]) for index in sampled]
        frame_entries = _write_labeled_keyframes(thumbs, sampled, preview_dir, stem, output)
        grid = _keyframe_grid(thumbs, sampled)
        grid.save(grid_path, format="PNG")

        gap = 10
        pad = 12
        label_h = 22
        strip_w = sum(image.width for image in thumbs) + gap * (len(thumbs) - 1) + pad * 2
        strip_h = max(image.height for image in thumbs) + label_h + pad * 2
        strip = Image.new("RGBA", (strip_w, strip_h), (255, 255, 255, 255))
        draw = ImageDraw.Draw(strip)
        x = pad
        for frame_index, thumb in zip(sampled, thumbs):
            strip.alpha_composite(thumb, (x, pad + label_h))
            draw.rectangle(
                (x, pad + label_h, x + thumb.width - 1, pad + label_h + thumb.height - 1),
                outline=(35, 122, 87, 255),
                width=2,
            )
            draw.text((x, pad), f"F{frame_index + 1}", fill=(23, 50, 77, 255))
            x += thumb.width + gap
        strip.save(strip_path, format="PNG")

    return {
        "poster_path": _relative(output, poster_path),
        "strip_path": _relative(output, strip_path),
        "grid_path": _relative(output, grid_path),
        "frame_count": frame_count,
        "duration_ms": sum(durations),
        "sampled_frame_indices": sampled,
        "frames": frame_entries,
        "strip_width": strip.width,
        "strip_height": strip.height,
        "grid_width": grid.width,
        "grid_height": grid.height,
    }


def _write_labeled_keyframes(
    thumbs: list[Any],
    sampled: list[int],
    preview_dir: Path,
    stem: str,
    output: Path,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for order, (frame_index, thumb) in enumerate(zip(sampled, thumbs), start=1):
        cell = _keyframe_cell(thumb, frame_index)
        frame_path = preview_dir / f"{stem}_frame{order:02d}.png"
        cell.save(frame_path, format="PNG")
        entries.append(
            {
                "path": _relative(output, frame_path),
                "frame_index": frame_index,
                "width": cell.width,
                "height": cell.height,
            }
        )
    return entries


def _keyframe_cell(thumb: Any, frame_index: int) -> Any:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to process GIF media.") from exc

    label_h = 20
    cell = Image.new("RGBA", (thumb.width, thumb.height + label_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(cell)
    label_w = max(22, 10 + len(str(frame_index + 1)) * 7)
    draw.rounded_rectangle((0, 0, label_w, 14), radius=4, fill=(35, 122, 87, 255))
    draw.text((5, 2), str(frame_index + 1), fill=(255, 255, 255, 255))
    cell.alpha_composite(thumb, (0, label_h))
    draw.rectangle((0, label_h, thumb.width - 1, thumb.height + label_h - 1), outline=(35, 122, 87, 255), width=2)
    return cell


def _keyframe_grid(thumbs: list[Any], sampled: list[int]) -> Any:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to process GIF media.") from exc

    count = len(thumbs)
    cols = 2 if count <= 4 else 3
    rows = (count + cols - 1) // cols
    cell_w = max(image.width for image in thumbs)
    cell_h = max(image.height for image in thumbs)
    gap = 10
    pad = 12
    label_h = 20
    grid_w = cols * cell_w + (cols - 1) * gap + pad * 2
    grid_h = rows * (cell_h + label_h) + (rows - 1) * gap + pad * 2
    grid = Image.new("RGBA", (grid_w, grid_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(grid)
    for index, (frame_index, thumb) in enumerate(zip(sampled, thumbs)):
        col = index % cols
        row = index // cols
        x = pad + col * (cell_w + gap)
        y = pad + row * (cell_h + label_h + gap)
        label_box = (x, y, x + 28, y + 14)
        draw.rounded_rectangle(label_box, radius=4, fill=(35, 122, 87, 255))
        draw.text((x + 5, y + 2), f"{frame_index + 1}", fill=(255, 255, 255, 255))
        image_x = x + (cell_w - thumb.width) // 2
        image_y = y + label_h + (cell_h - thumb.height) // 2
        grid.alpha_composite(thumb, (image_x, image_y))
        draw.rectangle(
            (x, y + label_h, x + cell_w - 1, y + label_h + cell_h - 1),
            outline=(35, 122, 87, 255),
            width=2,
        )
    return grid


def _thumbnail(image: Any) -> Any:
    thumb = image.copy()
    thumb.thumbnail(MAX_STRIP_FRAME_SIZE)
    return thumb


def _sample_indices(frame_count: int, max_frames: int) -> list[int]:
    if frame_count <= max_frames:
        return list(range(frame_count))
    return sorted({round(index * (frame_count - 1) / (max_frames - 1)) for index in range(max_frames)})


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "media_count": len(items),
        "gif_count": sum(1 for item in items if item.get("kind") == "gif"),
        "video_count": sum(1 for item in items if item.get("kind") == "video"),
        "audio_count": sum(1 for item in items if item.get("kind") == "audio"),
    }


def _slide_occupied_boxes(slide: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    target_id = str(target.get("id") or "")
    boxes: list[dict[str, Any]] = []
    for obj in slide.get("objects", []):
        if str(obj.get("id") or "") == target_id:
            continue
        bbox = obj.get("bbox")
        if not _valid_box(bbox):
            continue
        boxes.append(
            {
                "id": str(obj.get("id") or ""),
                "name": obj.get("name", ""),
                "type": obj.get("type", ""),
                "text": obj.get("text", ""),
                "bbox": bbox,
            }
        )
    return boxes


def _valid_box(box: Any) -> bool:
    if not isinstance(box, dict):
        return False
    return all(key in box for key in ("x", "y", "w", "h")) and int(box.get("w") or 0) > 0 and int(box.get("h") or 0) > 0


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned or "media"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
