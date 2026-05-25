from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz


def build_guide_preview(pdf_path: str | Path, output_dir: str | Path, zoom: float = 2.0) -> Path:
    pdf = Path(pdf_path)
    output = Path(output_dir)
    if not pdf.exists():
        raise FileNotFoundError(f"Guide PDF not found: {pdf}")
    if zoom <= 0:
        raise ValueError("zoom must be positive.")

    preview_dir = output / "guide_preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, Any]] = []
    doc = fitz.open(pdf)
    try:
        matrix = fitz.Matrix(zoom, zoom)
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image_relative = Path("guide_preview") / f"page_{page_index + 1:03d}.png"
            image_path = output / image_relative
            pixmap.save(image_path)
            pages.append(
                {
                    "number": page_index + 1,
                    "width_pt": float(page.rect.width),
                    "height_pt": float(page.rect.height),
                    "image": image_relative.as_posix(),
                    "image_width": int(pixmap.width),
                    "image_height": int(pixmap.height),
                }
            )
    finally:
        doc.close()

    manifest = {
        "kind": "guide_preview",
        "version": "v5a",
        "pdf": pdf.name,
        "pages": pages,
    }
    manifest_path = output / "guide_preview_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
