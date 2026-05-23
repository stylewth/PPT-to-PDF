from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from augment_planner import build_augment_plan
from compare_builder import write_compare_html
from html_renderer import write_study_html
from knowledge_blocks import build_knowledge_blocks, write_knowledge_blocks
from media_processor import process_presentation_media
from metrics_builder import build_metrics, write_metrics
from native_converter import convert_pptx_to_pdf
from object_reflow_planner import simulate_operations
from pdf_augmenter import generate_guide_pdf
from pptx_parser import parse_pptx
from render_visual_check import check_rendered_pdf
from reflow_visual_check import check_reflow_intent
from slide_analyzer import analyze_presentation, summarize_analysis
from study_builder import build_study_document


def convert_pptx(
    pptx_path: str | Path,
    output_dir: str | Path,
    *,
    render_pdf: bool = True,
    soffice_path: str | Path | None = None,
    command_runner=None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    presentation = parse_pptx(pptx_path)
    document = build_study_document(presentation)
    analysis = analyze_presentation(presentation)

    report_path = output / "report.json"
    analysis_path = output / "analysis.json"
    metrics_path = output / "metrics.json"
    compare_html_path = output / "compare.html"
    preview_html_path = output / "preview.html"
    media_manifest_path = output / "media_manifest.json"
    knowledge_blocks_path = output / "knowledge_blocks.json"

    warnings = [
        warning
        for slide in document["slides"]
        for warning in slide.get("warnings", [])
    ]

    plan = build_augment_plan(analysis)
    media_manifest = process_presentation_media(pptx_path, presentation, output)
    knowledge_blocks = build_knowledge_blocks(presentation, analysis, plan, media_manifest)
    write_knowledge_blocks(knowledge_blocks_path, knowledge_blocks)
    base_pdf_path = None
    guide_pdf_path = None
    augment_plan_path = output / "augment_plan.json"
    if render_pdf:
        base_pdf_path = convert_pptx_to_pdf(
            pptx_path,
            output,
            soffice_path=soffice_path,
            command_runner=command_runner,
        )
        guide_outputs = generate_guide_pdf(
            pptx_path,
            output,
            plan,
            base_pdf_path=base_pdf_path,
            media_manifest=media_manifest,
            soffice_path=soffice_path,
            command_runner=command_runner,
        )
        guide_pdf_path = guide_outputs.get("guide_pdf_path")
        augment_plan_path = guide_outputs["augment_plan_path"]
    else:
        augment_plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    write_study_html(document, preview_html_path)
    analysis_path.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    metrics = build_metrics(
        analysis,
        plan,
        knowledge_blocks=knowledge_blocks,
        runtime_seconds=time.perf_counter() - started_at,
    )
    write_metrics(metrics_path, metrics)
    reflow_intent_check = _build_reflow_intent_check(plan)
    render_visual_check = _build_render_visual_check(guide_pdf_path, output, plan)

    report = {
        "kind": "conversion_report",
        "version": "v3g",
        "source": document["source"],
        "outputs": {
            "base_pdf": "base.pdf" if base_pdf_path else None,
            "guide_pdf": "guide.pdf" if guide_pdf_path else None,
            "compare_html": "compare.html" if base_pdf_path and guide_pdf_path else None,
            "analysis_json": "analysis.json",
            "augment_plan_json": "augment_plan.json",
            "metrics_json": "metrics.json",
            "media_manifest_json": "media_manifest.json",
            "knowledge_blocks_json": "knowledge_blocks.json",
            "preview_html": "preview.html",
            "report": "report.json",
        },
        "summary": summarize_analysis(analysis),
        "media": media_manifest,
        "reflow_intent_check": reflow_intent_check,
        "render_visual_check": render_visual_check,
        "warnings": warnings,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if base_pdf_path and guide_pdf_path:
        write_compare_html(
            compare_html_path,
            source=document["source"],
            plan=plan,
            metrics=metrics,
            report=report,
        )

    return {
        "status": "ok",
        "source": document["source"],
        "base_pdf_path": str(base_pdf_path) if base_pdf_path else None,
        "guide_pdf_path": str(guide_pdf_path) if guide_pdf_path else None,
        "compare_html_path": str(compare_html_path) if base_pdf_path and guide_pdf_path else None,
        "analysis_path": str(analysis_path),
        "augment_plan_path": str(augment_plan_path),
        "metrics_path": str(metrics_path),
        "media_manifest_path": str(media_manifest_path),
        "knowledge_blocks_path": str(knowledge_blocks_path),
        "report_path": str(report_path),
        "preview_html_path": str(preview_html_path),
        "warnings": warnings,
    }


def _build_reflow_intent_check(plan: dict[str, Any]) -> dict[str, Any]:
    slide_checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    for slide in plan.get("slides", []):
        reflow = slide.get("object_reflow") or {}
        operations = reflow.get("operations") or []
        if not operations:
            continue
        before_boxes = slide.get("object_boxes") or []
        after_boxes = simulate_operations(before_boxes, operations)
        check = check_reflow_intent(
            before_boxes,
            after_boxes,
            operations,
            slide.get("size") or {},
        )
        slide_number = slide.get("source_slide")
        slide_checks.append({"slide": slide_number, **check})
        warnings.extend(f"第 {slide_number} 页：{warning}" for warning in check.get("warnings", []))
    return {
        "passed": not warnings,
        "warnings": warnings,
        "slides": slide_checks,
    }


def _build_render_visual_check(guide_pdf_path: str | Path | None, output: Path, plan: dict[str, Any]) -> dict[str, Any] | None:
    if not guide_pdf_path:
        return None
    return check_rendered_pdf(
        guide_pdf_path,
        pages=_render_check_pages(plan),
        formula_regions=_render_formula_regions(plan),
        screenshot_dir=output / "render_visual_check",
        scale=1.2,
    )


def _render_check_pages(plan: dict[str, Any]) -> list[int]:
    pages: set[int] = set()
    for slide in plan.get("slides", []):
        slide_number = int(slide.get("source_slide") or 0)
        if slide_number <= 0:
            continue
        if (slide.get("object_reflow") or {}).get("operations"):
            pages.add(slide_number)
            continue
        if any(str(obj.get("type") or "") == "graphicFrame" for obj in slide.get("object_boxes", [])):
            pages.add(slide_number)
    return sorted(pages)


def _render_formula_regions(plan: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    regions: dict[int, list[dict[str, Any]]] = {}
    for slide in plan.get("slides", []):
        slide_number = int(slide.get("source_slide") or 0)
        if slide_number <= 0:
            continue
        size = slide.get("size") or {}
        target_by_id = {
            str(operation.get("id") or ""): operation.get("to") or {}
            for operation in ((slide.get("object_reflow") or {}).get("operations") or [])
            if str(operation.get("object_type") or "") == "graphicFrame"
        }
        for obj in slide.get("object_boxes", []):
            if str(obj.get("type") or "") != "graphicFrame":
                continue
            bbox = dict(target_by_id.get(str(obj.get("id") or "")) or obj.get("bbox") or {})
            if not all(key in bbox for key in ("x", "y", "w", "h")):
                continue
            bbox = _compact_render_box(bbox, size, slide.get("page_compact"))
            regions.setdefault(slide_number, []).append(
                {
                    "id": str(obj.get("id") or ""),
                    "bbox": bbox,
                    "slide_size": size,
                }
            )
    return regions


def _compact_render_box(
    bbox: dict[str, Any],
    slide_size: dict[str, Any],
    page_compact: dict[str, Any] | None,
) -> dict[str, int]:
    if not page_compact:
        return {key: int(bbox[key]) for key in ("x", "y", "w", "h")}
    scale = max(0.88, min(0.98, float(page_compact.get("scale") or 0.94)))
    width = max(int(slide_size.get("width") or 12192000), 1)
    height = max(int(slide_size.get("height") or 6858000), 1)
    dx = (width - width * scale) / 2
    dy = (height - height * scale) / 2
    return {
        "x": int(dx + int(bbox["x"]) * scale),
        "y": int(dy + int(bbox["y"]) * scale),
        "w": int(int(bbox["w"]) * scale),
        "h": int(int(bbox["h"]) * scale),
    }
