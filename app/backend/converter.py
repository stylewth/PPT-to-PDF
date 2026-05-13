from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from augment_planner import build_augment_plan
from html_renderer import write_study_html
from native_converter import convert_pptx_to_pdf
from pdf_augmenter import generate_guide_pdf
from pptx_parser import parse_pptx
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
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    presentation = parse_pptx(pptx_path)
    document = build_study_document(presentation)
    analysis = analyze_presentation(presentation)

    report_path = output / "report.json"
    analysis_path = output / "analysis.json"
    preview_html_path = output / "preview.html"

    warnings = [
        warning
        for slide in document["slides"]
        for warning in slide.get("warnings", [])
    ]

    plan = build_augment_plan(analysis)
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

    report = {
        "kind": "conversion_report",
        "version": "v3d",
        "source": document["source"],
        "outputs": {
            "base_pdf": "base.pdf" if base_pdf_path else None,
            "guide_pdf": "guide.pdf" if guide_pdf_path else None,
            "analysis_json": "analysis.json",
            "augment_plan_json": "augment_plan.json",
            "preview_html": "preview.html",
            "report": "report.json",
        },
        "summary": summarize_analysis(analysis),
        "warnings": warnings,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "source": document["source"],
        "base_pdf_path": str(base_pdf_path) if base_pdf_path else None,
        "guide_pdf_path": str(guide_pdf_path) if guide_pdf_path else None,
        "analysis_path": str(analysis_path),
        "augment_plan_path": str(augment_plan_path),
        "report_path": str(report_path),
        "preview_html_path": str(preview_html_path),
        "warnings": warnings,
    }
