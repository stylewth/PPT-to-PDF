from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from augment_planner import build_augment_plan
from compare_builder import write_compare_html
from guide_preview import build_guide_preview
from html_renderer import write_study_html
from knowledge_blocks import build_knowledge_blocks, write_knowledge_blocks
from media_processor import process_presentation_media
from metrics_builder import build_metrics, write_metrics
from native_converter import convert_pptx_to_pdf
from object_reflow_planner import simulate_operations
from pdf_augmenter import generate_guide_pdf
from pptx_parser import parse_pptx
from render_visual_check import check_rendered_pdf, check_rendered_preview_images
from reflow_visual_check import check_reflow_intent
from slide_analyzer import analyze_presentation, summarize_analysis
from study_builder import build_study_document


ProgressCallback = Callable[[dict[str, Any]], None]

_conversion_cache: dict[str, dict[str, Any]] = {}
_CACHE_VERSION = 1


def _cache_file_path() -> Path:
    import tempfile
    return Path(tempfile.gettempdir()) / "slide2study_conv_cache.json"


def _load_disk_cache() -> dict[str, dict[str, Any]]:
    path = _cache_file_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("_version") == _CACHE_VERSION:
                return {k: v for k, v in raw.items() if k != "_version"}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_disk_cache(data: dict[str, dict[str, Any]]) -> None:
    try:
        payload = dict(data)
        payload["_version"] = _CACHE_VERSION
        _cache_file_path().write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def convert_pptx(
    pptx_path: str | Path,
    output_dir: str | Path,
    *,
    render_pdf: bool = True,
    soffice_path: str | Path | None = None,
    command_runner=None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    source = Path(pptx_path)
    source_hash = _file_sha256(source)
    disk_cache = _load_disk_cache() if not _conversion_cache else {}
    cached = _conversion_cache.get(source_hash) or disk_cache.get(source_hash)
    if cached:
        cached_base = cached.get("base_pdf_path")
        cached_guide = cached.get("guide_pdf_path")
        if cached_base and Path(cached_base).exists() and cached_guide and Path(cached_guide).exists():
            output = Path(output_dir)
            output.mkdir(parents=True, exist_ok=True)
            import shutil
            new_base = output / "base.pdf"
            new_guide = output / "guide.pdf"
            shutil.copyfile(cached_base, new_base)
            shutil.copyfile(cached_guide, new_guide)
            result = dict(cached)
            result["base_pdf_path"] = str(new_base)
            result["guide_pdf_path"] = str(new_guide)
            for key in ("analysis_path", "augment_plan_path", "metrics_path", "media_manifest_path",
                        "knowledge_blocks_path", "report_path", "preview_html_path", "compare_html_path",
                        "guide_preview_manifest_path"):
                if result.get(key):
                    src = Path(result[key])
                    if src.exists():
                        dst = output / src.name
                        shutil.copyfile(src, dst)
                        result[key] = str(dst)
            cached_preview_manifest = cached.get("guide_preview_manifest_path")
            if cached_preview_manifest:
                manifest_src = Path(cached_preview_manifest)
                preview_dir = manifest_src.parent / "guide_preview"
                if preview_dir.is_dir():
                    dst_preview_dir = output / "guide_preview"
                    if dst_preview_dir.exists():
                        shutil.rmtree(dst_preview_dir, ignore_errors=True)
                    shutil.copytree(preview_dir, dst_preview_dir)
            _emit_progress(progress, 100, "复用缓存结果", "cached", 100)
            return result

    started_at = time.perf_counter()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    _t = started_at
    _timings: dict[str, float] = {}

    def _tick(label: str) -> None:
        nonlocal _t
        now = time.perf_counter()
        _timings[label] = round(now - _t, 3)
        _t = now

    _emit_progress(progress, 8, "解析 PPTX", "parse", 18)
    presentation = parse_pptx(pptx_path)
    document = build_study_document(presentation)
    _tick("parse_pptx")

    _emit_progress(progress, 18, "分析课件结构", "analysis", 35)
    analysis = analyze_presentation(presentation)
    _tick("analyze")

    report_path = output / "report.json"
    analysis_path = output / "analysis.json"
    metrics_path = output / "metrics.json"
    compare_html_path = output / "compare.html"
    preview_html_path = output / "preview.html"
    media_manifest_path = output / "media_manifest.json"
    knowledge_blocks_path = output / "knowledge_blocks.json"
    guide_preview_manifest_path = None

    warnings = [
        warning
        for slide in document["slides"]
        for warning in slide.get("warnings", [])
    ]

    _emit_progress(progress, 35, "生成导读计划", "plan", 45)
    plan = build_augment_plan(analysis)
    media_manifest = process_presentation_media(pptx_path, presentation, output)
    knowledge_blocks = build_knowledge_blocks(presentation, analysis, plan, media_manifest)
    write_knowledge_blocks(knowledge_blocks_path, knowledge_blocks)
    _tick("plan_and_media")
    base_pdf_path = None
    guide_pdf_path = None
    augment_plan_path = output / "augment_plan.json"
    if render_pdf:
        _emit_progress(progress, 58, "LibreOffice 生成 base.pdf", "base_pdf_native", 64)
        base_pdf_path = convert_pptx_to_pdf(
            pptx_path,
            output,
            soffice_path=soffice_path,
            command_runner=command_runner,
            progress=progress,
        )
        _tick("base_pdf_native")
        _emit_progress(progress, 64, "准备 guide 输出", "guide_deck_build", 70)
        guide_outputs = generate_guide_pdf(
            pptx_path,
            output,
            plan,
            base_pdf_path=base_pdf_path,
            media_manifest=media_manifest,
            soffice_path=soffice_path,
            command_runner=command_runner,
            progress=progress,
        )
        _tick("guide_pdf_total")
        guide_pdf_path = guide_outputs.get("guide_pdf_path")
        augment_plan_path = guide_outputs["augment_plan_path"]
        if guide_pdf_path:
            _emit_progress(progress, 82, "生成 guide 预览", "guide_preview", 86)
            guide_preview_manifest_path = build_guide_preview(guide_pdf_path, output)
            _tick("guide_preview")
    else:
        _emit_progress(progress, 82, "写入导读计划", "augment_plan", 90)
        augment_plan_path.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    _emit_progress(progress, 86, "渲染质量自检", "render_check", 90)
    reflow_intent_check = _build_reflow_intent_check(plan)
    render_visual_check = _build_render_visual_check(
        guide_pdf_path,
        output,
        plan,
        guide_preview_manifest_path=guide_preview_manifest_path,
    )
    _tick("render_check")

    _emit_progress(progress, 90, "写入报告和指标", "report", 98)
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

    report = {
        "kind": "conversion_report",
        "version": "v3g",
        "source": document["source"],
        "outputs": {
            "base_pdf": "base.pdf" if base_pdf_path else None,
            "guide_pdf": "guide.pdf" if guide_pdf_path else None,
            "guide_preview_manifest": "guide_preview_manifest.json" if guide_preview_manifest_path else None,
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

    _tick("report_write")
    _emit_progress(progress, 98, "整理转换结果", "finalize", 100)
    _timings["total"] = round(time.perf_counter() - started_at, 3)
    timings_path = output / "_timings.json"
    timings_path.write_text(json.dumps(_timings, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {
        "status": "ok",
        "source": document["source"],
        "base_pdf_path": str(base_pdf_path) if base_pdf_path else None,
        "guide_pdf_path": str(guide_pdf_path) if guide_pdf_path else None,
        "guide_preview_manifest_path": str(guide_preview_manifest_path) if guide_preview_manifest_path else None,
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
    _conversion_cache[source_hash] = result
    all_cached = _load_disk_cache()
    all_cached[source_hash] = result
    _save_disk_cache(all_cached)
    return result


def _emit_progress(
    progress: ProgressCallback | None,
    percent: int,
    message: str,
    stage: str,
    next_percent: int | None = None,
) -> None:
    if progress is None:
        return
    event: dict[str, Any] = {
        "percent": percent,
        "message": message,
        "stage": stage,
    }
    if next_percent is not None:
        event["next_percent"] = next_percent
    progress(event)


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


def _build_render_visual_check(
    guide_pdf_path: str | Path | None,
    output: Path,
    plan: dict[str, Any],
    *,
    guide_preview_manifest_path: str | Path | None = None,
) -> dict[str, Any] | None:
    if not guide_pdf_path:
        return None
    pages = _render_check_pages(plan)
    formula_regions = _render_formula_regions(plan)
    if guide_preview_manifest_path and Path(guide_preview_manifest_path).exists():
        return check_rendered_preview_images(
            guide_preview_manifest_path,
            pages=pages,
            formula_regions=formula_regions,
            screenshot_dir=output / "render_visual_check",
            scale=1.2,
        )
    return check_rendered_pdf(
        guide_pdf_path,
        pages=pages,
        formula_regions=formula_regions,
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
        elif slide.get("page_compact"):
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



def _file_sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()
