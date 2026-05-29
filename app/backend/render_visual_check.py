from __future__ import annotations

import json
import shutil
from io import BytesIO
from pathlib import Path
from typing import Any


def check_rendered_pdf(
    pdf_path: str | Path,
    *,
    pages: list[int] | None = None,
    formula_regions: dict[int, list[dict[str, Any]]] | None = None,
    screenshot_dir: str | Path | None = None,
    scale: float = 1.2,
) -> dict[str, Any]:
    import fitz
    from PIL import Image

    pdf = Path(pdf_path)
    output = Path(screenshot_dir) if screenshot_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf)
    try:
        page_numbers = list(range(1, len(doc) + 1)) if pages is None else pages
        checks: list[dict[str, Any]] = []
        warnings: list[str] = []
        for page_number in page_numbers:
            if page_number < 1 or page_number > len(doc):
                continue
            pix = doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
            if output:
                image.save(output / f"page_{page_number:02d}.png")
            page_regions = _page_formula_regions(
                formula_regions or {},
                page_number,
                image.size,
            )
            page_check = check_rendered_image(
                image,
                page_number=page_number,
                formula_regions=page_regions,
            )
            checks.append(page_check)
            warnings.extend(f"第 {page_number} 页：{warning}" for warning in page_check["warnings"])
    finally:
        doc.close()

    return {
        "passed": not warnings,
        "warnings": warnings,
        "pages": checks,
        "screenshot_dir": str(output) if output else None,
    }


def check_rendered_preview_images(
    preview_manifest_path: str | Path,
    *,
    pages: list[int] | None = None,
    formula_regions: dict[int, list[dict[str, Any]]] | None = None,
    screenshot_dir: str | Path | None = None,
    scale: float | None = None,
) -> dict[str, Any]:
    from PIL import Image

    manifest_path = Path(preview_manifest_path)
    output = Path(screenshot_dir) if screenshot_dir else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    wanted = None if pages is None else set(pages)
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for page in manifest.get("pages", []) or []:
        page_number = int(page.get("number") or 0)
        if page_number <= 0:
            continue
        if wanted is not None and page_number not in wanted:
            continue
        image_path = root / str(page.get("image") or "")
        if not image_path.exists():
            raise FileNotFoundError(f"Guide preview image was not found: {image_path.name}")
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
            image = _resize_preview_for_check(image, page, scale)
            if output:
                target = output / f"page_{page_number:02d}.png"
                if image_path.suffix.lower() == ".png" and image.size == opened.size:
                    shutil.copyfile(image_path, target)
                else:
                    image.save(target)
            page_regions = _page_formula_regions(
                formula_regions or {},
                page_number,
                image.size,
            )
            page_check = check_rendered_image(
                image,
                page_number=page_number,
                formula_regions=page_regions,
            )
        checks.append(page_check)
        warnings.extend(f"第 {page_number} 页：{warning}" for warning in page_check["warnings"])
    return {
        "passed": not warnings,
        "warnings": warnings,
        "pages": checks,
        "screenshot_dir": str(output) if output else None,
    }


def _resize_preview_for_check(image: Any, page: dict[str, Any], scale: float | None) -> Any:
    if not scale or scale <= 0:
        return image
    width_pt = float(page.get("width_pt") or 0)
    height_pt = float(page.get("height_pt") or 0)
    if width_pt <= 0 or height_pt <= 0:
        return image
    target_size = (
        max(1, int(round(width_pt * scale))),
        max(1, int(round(height_pt * scale))),
    )
    if image.size == target_size:
        return image
    return image.resize(target_size)


def check_rendered_image(
    image: Any,
    *,
    page_number: int | None = None,
    formula_regions: list[dict[str, int]] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    warnings.extend(_formula_background_warnings(image, formula_regions=formula_regions))
    warnings.extend(_dense_ink_warnings(image))
    return {
        "page": page_number,
        "passed": not warnings,
        "warnings": warnings,
    }


def _page_formula_regions(
    formula_regions: dict[int, list[dict[str, Any]]],
    page_number: int,
    image_size: tuple[int, int],
) -> list[dict[str, int]]:
    page_regions = formula_regions.get(page_number) or []
    result: list[dict[str, int]] = []
    width, height = image_size
    for region in page_regions:
        bbox = region.get("bbox") or {}
        slide_size = region.get("slide_size") or {}
        slide_width = max(float(slide_size.get("width") or 12192000), 1.0)
        slide_height = max(float(slide_size.get("height") or 6858000), 1.0)
        x0 = int(float(bbox.get("x", 0)) / slide_width * width)
        y0 = int(float(bbox.get("y", 0)) / slide_height * height)
        x1 = int((float(bbox.get("x", 0)) + float(bbox.get("w", 0))) / slide_width * width)
        y1 = int((float(bbox.get("y", 0)) + float(bbox.get("h", 0))) / slide_height * height)
        x0 = max(0, min(width - 1, x0))
        y0 = max(0, min(height - 1, y0))
        x1 = max(x0 + 1, min(width, x1))
        y1 = max(y0 + 1, min(height, y1))
        result.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return result


def _formula_background_warnings(image: Any, *, formula_regions: list[dict[str, int]] | None = None) -> list[str]:
    if formula_regions is not None:
        warnings: list[str] = []
        for region in formula_regions:
            warnings.extend(_formula_region_warnings(image, region))
        return warnings

    width, height = image.size
    pixels = image.load()
    visited = bytearray(width * height)
    warnings: list[str] = []
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or not _is_formula_background(pixels[x, y]):
                continue
            component = _collect_component(pixels, visited, width, height, x, y)
            if component["area"] < 140:
                continue
            warning = _formula_edge_warning(pixels, component)
            if warning:
                warnings.append(warning)
    return warnings


def _formula_region_warnings(image: Any, region: dict[str, int]) -> list[str]:
    x0, y0, x1, y1 = region["x0"], region["y0"], region["x1"], region["y1"]
    if x1 - x0 < 18 or y1 - y0 < 12:
        return []
    crop = image.crop((x0, y0, x1, y1))
    warnings = _formula_background_warnings(crop) if _background_ratio(crop) >= 0.05 else []
    crowding = _formula_ink_crowding_warning(crop)
    if crowding:
        warnings.append(crowding)
    return warnings


def _background_ratio(image: Any) -> float:
    width, height = image.size
    if width <= 0 or height <= 0:
        return 0.0
    pixels = image.load()
    background = 0
    for y in range(height):
        for x in range(width):
            if _is_formula_background(pixels[x, y]):
                background += 1
    return background / (width * height)


def _collect_component(pixels: Any, visited: bytearray, width: int, height: int, x: int, y: int) -> dict[str, int]:
    stack = [(x, y)]
    left = right = x
    top = bottom = y
    area = 0
    while stack:
        cx, cy = stack.pop()
        if cx < 0 or cy < 0 or cx >= width or cy >= height:
            continue
        index = cy * width + cx
        if visited[index] or not _is_formula_area_pixel(pixels[cx, cy]):
            continue
        visited[index] = 1
        area += 1
        left = min(left, cx)
        right = max(right, cx)
        top = min(top, cy)
        bottom = max(bottom, cy)
        stack.extend(((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)))
    return {"x0": left, "y0": top, "x1": right, "y1": bottom, "area": area}


def _formula_edge_warning(pixels: Any, box: dict[str, int]) -> str | None:
    x0, y0, x1, y1 = box["x0"], box["y0"], box["x1"], box["y1"]
    width = x1 - x0 + 1
    height = y1 - y0 + 1
    if width < 18 or height < 12:
        return None
    edge = max(2, min(6, width // 18, height // 8))
    sides = {
        "左侧": (
            [(x, y) for x in range(x0, min(x0 + edge, x1 + 1)) for y in range(y0, y1 + 1)],
            [(x0, y) for y in range(y0, y1 + 1)],
        ),
        "右侧": (
            [(x, y) for x in range(max(x1 - edge + 1, x0), x1 + 1) for y in range(y0, y1 + 1)],
            [(x1, y) for y in range(y0, y1 + 1)],
        ),
        "上侧": (
            [(x, y) for y in range(y0, min(y0 + edge, y1 + 1)) for x in range(x0, x1 + 1)],
            [(x, y0) for x in range(x0, x1 + 1)],
        ),
        "下侧": (
            [(x, y) for y in range(max(y1 - edge + 1, y0), y1 + 1) for x in range(x0, x1 + 1)],
            [(x, y1) for x in range(x0, x1 + 1)],
        ),
    }
    for side, (coords, border_coords) in sides.items():
        if not coords or not border_coords:
            continue
        ink = sum(1 for x, y in coords if _is_ink(pixels[x, y]))
        border_ink = sum(1 for x, y in border_coords if _is_ink(pixels[x, y]))
        if ink / len(coords) > 0.18 and border_ink / len(border_coords) > 0.08:
            return f"公式/高亮区域墨迹贴近{side}边界，疑似裁切或遮挡"
    return None


def _dense_ink_warnings(image: Any) -> list[str]:
    width, height = image.size
    tile = 28
    pixels = list(image.getdata())
    size = len(pixels)

    ink_mask = bytearray(size)
    ink_cls = bytearray(size)
    bg_mask = bytearray(size)

    for i, (r, g, b) in enumerate(pixels):
        if r < 80 and g < 80 and b < 80:
            ink_mask[i] = 1
            ink_cls[i] = 1
        elif b > 120 and r < 120 and g < 160:
            ink_mask[i] = 1
            ink_cls[i] = 2
        elif r > 140 and g < 90 and b < 90:
            ink_mask[i] = 1
            ink_cls[i] = 3
        if (r > 215 and g > 175 and b < 150) or (g > 210 and r < 230 and b < 230) or (g > 210 and b > 210 and r < 245):
            bg_mask[i] = 1

    h_diff = bytearray(size)
    v_diff = bytearray(size)
    for y in range(height):
        row_start = y * width
        for x in range(width - 1):
            i = row_start + x
            if ink_mask[i] != ink_mask[i + 1] or (ink_mask[i] and ink_cls[i] != ink_cls[i + 1]):
                h_diff[i] = 1
    for y in range(height - 1):
        row_start = y * width
        next_row = row_start + width
        for x in range(width):
            i = row_start + x
            if ink_mask[i] != ink_mask[i + width] or (ink_mask[i] and ink_cls[i] != ink_cls[i + width]):
                v_diff[i] = 1

    for y0 in range(int(height * 0.12), height - tile + 1, tile):
        for x0 in range(0, width - tile + 1, tile):
            ink_count = 0
            colored_count = 0
            classes: set[int] = set()
            transitions = 0
            for dy in range(tile):
                row_start = (y0 + dy) * width + x0
                row_end = row_start + tile
                ink_count += sum(ink_mask[row_start:row_end])
                colored_count += sum(bg_mask[row_start:row_end])
                transitions += sum(h_diff[row_start:row_end - 1])
                for dx in range(tile):
                    cls = ink_cls[row_start + dx]
                    if cls:
                        classes.add(cls)
            for dy in range(tile - 1):
                row_start = (y0 + dy) * width + x0
                transitions += sum(v_diff[row_start:row_start + tile])

            area = tile * tile
            if ink_count / area > 0.58 and colored_count / area < 0.20 and len(classes) >= 2 and transitions / area > 0.35:
                return ["局部墨迹密度异常，疑似文字/公式叠压"]
    return []


def _formula_ink_crowding_warning(image: Any) -> str | None:
    width, height = image.size
    if width < 60 or height < 24:
        return None
    pixels = list(image.getdata())
    row_ink = [0] * height
    col_ink = [0] * width
    ink = 0
    formula_background = 0
    for i, (r, g, b) in enumerate(pixels):
        y = i // width
        x = i % width
        if (r > 215 and g > 175 and b < 150) or (g > 210 and r < 230 and b < 230) or (g > 210 and b > 210 and r < 245):
            formula_background += 1
        if not ((r < 80 and g < 80 and b < 80) or (b > 120 and r < 120 and g < 160) or (r > 140 and g < 90 and b < 90)):
            continue
        ink += 1
        row_ink[y] += 1
        col_ink[x] += 1
    area = width * height
    ink_ratio = ink / area
    if ink_ratio <= 0.12:
        return None
    background_ratio = formula_background / area
    if background_ratio > 0.25 and ink_ratio < 0.18:
        return None
    dense_rows = sum(1 for count in row_ink if count / width > 0.22)
    very_dense_rows = sum(1 for count in row_ink if count / width > 0.34)
    dense_columns = sum(1 for count in col_ink if count / height > 0.34)
    max_row_ratio = max(row_ink, default=0) / width
    if background_ratio > 0.65 and very_dense_rows <= 1:
        return None
    if max_row_ratio > 0.38 and very_dense_rows >= 3 and dense_columns >= 1:
        return "公式墨迹拥挤，疑似公式被压缩或叠压"
    if max_row_ratio > 0.32 and dense_rows >= max(6, height // 8) and dense_columns >= 2:
        return "公式墨迹拥挤，疑似公式被压缩或叠压"
    return None


def _is_formula_background(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    yellow = r > 215 and g > 175 and b < 150
    green = g > 210 and r < 230 and b < 230
    cyan = g > 210 and b > 210 and r < 245
    return yellow or green or cyan


def _is_formula_area_pixel(rgb: tuple[int, int, int]) -> bool:
    return _is_formula_background(rgb) or _is_ink(rgb)


def _is_ink(rgb: tuple[int, int, int]) -> bool:
    r, g, b = rgb
    dark = r < 80 and g < 80 and b < 80
    blue = b > 120 and r < 120 and g < 160
    red = r > 140 and g < 90 and b < 90
    return dark or blue or red


def _ink_class(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    if r > 140 and g < 90 and b < 90:
        return "red"
    if b > 120 and r < 120 and g < 160:
        return "blue"
    return "dark"
