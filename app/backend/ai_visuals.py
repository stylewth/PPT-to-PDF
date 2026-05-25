from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


def build_page_visual_inputs(output_dir: str | Path, page_number: int, *, include_images: bool) -> list[dict[str, str]]:
    if not include_images:
        return []
    page = _find_preview_page(output_dir, page_number)
    image_path = _preview_image_path(output_dir, page)
    return [{"label": f"guide page {page_number}", "data_url": _image_data_url(image_path)}]


def build_block_visual_inputs(
    output_dir: str | Path,
    page_number: int,
    block: dict[str, Any],
    *,
    include_images: bool,
) -> list[dict[str, str]]:
    if not include_images:
        return []
    page = _find_preview_page(output_dir, page_number)
    image_path = _preview_image_path(output_dir, page)
    bbox = block.get("display_bbox") or {}
    if not _valid_bbox(bbox):
        return [{"label": f"guide page {page_number}", "data_url": _image_data_url(image_path)}]

    with Image.open(image_path) as image:
        width, height = image.size
        crop_box = (
            max(0, int(float(bbox["x"]) * width)),
            max(0, int(float(bbox["y"]) * height)),
            min(width, int((float(bbox["x"]) + float(bbox["w"])) * width)),
            min(height, int((float(bbox["y"]) + float(bbox["h"])) * height)),
        )
        cropped = image.crop(crop_box)
        buffer = BytesIO()
        cropped.save(buffer, format="PNG")
    return [
        {
            "label": f"guide page {page_number} block {block.get('id')}",
            "data_url": f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}",
        }
    ]


def _find_preview_page(output_dir: str | Path, page_number: int) -> dict[str, Any]:
    manifest_path = Path(output_dir) / "guide_preview_manifest.json"
    if not manifest_path.exists():
        raise ValueError("Guide preview images for this job were not found.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for page in manifest.get("pages", []) or []:
        if int(page.get("number") or 0) == int(page_number):
            return page
    raise ValueError(f"Guide preview image for page {page_number} was not found.")


def _preview_image_path(output_dir: str | Path, page: dict[str, Any]) -> Path:
    image_path = Path(output_dir) / str(page.get("image") or "")
    if not image_path.exists():
        raise ValueError(f"Guide preview image was not found: {image_path.name}")
    return image_path


def _image_data_url(path: Path) -> str:
    data = path.read_bytes()
    return f"data:image/png;base64,{base64.b64encode(data).decode('ascii')}"


def _valid_bbox(bbox: dict[str, Any]) -> bool:
    try:
        x = float(bbox.get("x"))
        y = float(bbox.get("y"))
        w = float(bbox.get("w"))
        h = float(bbox.get("h"))
    except (TypeError, ValueError):
        return False
    return x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= 1.001 and y + h <= 1.001
