from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def render_study_html(document: dict[str, Any]) -> str:
    title = html.escape(document["source"].get("name") or "学习型 PDF")
    slides = "\n".join(_render_slide(slide) for slide in document["slides"])
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} · 学习型 PDF</title>
  <style>{_css()}</style>
</head>
<body>
  <main>
    <header class="doc-header">
      <p>Slide2Study V3A Preview</p>
      <h1>{title} · 学习型 PDF</h1>
      <span>{document["source"].get("slide_count", 0)} pages</span>
    </header>
    {slides}
  </main>
</body>
</html>
"""


def write_study_html(document: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_study_html(document), encoding="utf-8")
    return path


def _render_slide(slide: dict[str, Any]) -> str:
    warnings = "".join(_render_warning(warning) for warning in slide["warnings"])
    steps = "".join(_render_step(step) for step in slide["steps"])
    objects = "".join(_render_object(obj) for obj in slide["original_objects"] if obj.get("text"))
    explanation = html.escape(slide["explanation"])
    title = html.escape(slide["title"])
    return f"""
    <section class="page">
      <div class="page-grid">
        <section class="original">
          <div class="page-meta">第 {slide["number"]} 页 · 原始对象</div>
          <h2>{title}</h2>
          <div class="object-list">{objects}</div>
          <div class="warnings">{warnings}</div>
        </section>
        <section class="study">
          <div class="page-meta">学习路径</div>
          <h2>{title}</h2>
          <ol class="steps">{steps}</ol>
          <div class="explanation">
            <strong>复习解释</strong>
            <p>{explanation}</p>
          </div>
          <div class="notes">
            <div></div><div></div><div></div><div></div><div></div>
          </div>
        </section>
      </div>
    </section>
"""


def _render_object(obj: dict[str, Any]) -> str:
    text = html.escape(obj.get("text", ""))
    return f"<div class=\"object-item\"><span>z{obj.get('z_order', 0)}</span>{text}</div>"


def _render_warning(warning: dict[str, str]) -> str:
    code = html.escape(warning["code"])
    message = html.escape(warning["message"])
    return f"<div class=\"warning\"><code>{code}</code>{message}</div>"


def _render_step(step: dict[str, Any]) -> str:
    summary = html.escape(step["summary"])
    target = html.escape(step["target_text"])
    animation = html.escape(step["animation"])
    return f"<li><span>{animation}</span><strong>{target}</strong><p>{summary}</p></li>"


def _css() -> str:
    return """
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #f7f8f4;
  color: #17201b;
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
}
main { max-width: 1180px; margin: 0 auto; padding: 28px; }
.doc-header { display: flex; align-items: end; justify-content: space-between; gap: 20px; border-bottom: 1px solid #d8dfda; padding-bottom: 16px; margin-bottom: 18px; }
.doc-header p { margin: 0; color: #237a57; font-size: 12px; font-weight: 800; text-transform: uppercase; }
.doc-header h1 { flex: 1; margin: 0; font-size: 28px; }
.doc-header span { color: #66746d; }
.page { min-height: 860px; margin: 0 0 20px; padding: 22px; background: #fff; border: 1px solid #d8dfda; border-radius: 8px; page-break-after: always; }
.page-grid { display: grid; grid-template-columns: 0.92fr 1.08fr; gap: 22px; }
.page-meta { color: #66746d; font-size: 13px; margin-bottom: 10px; }
h2 { margin: 0 0 14px; font-size: 22px; }
.object-list { display: grid; gap: 10px; margin-bottom: 16px; }
.object-item { display: grid; grid-template-columns: 42px 1fr; gap: 10px; align-items: center; min-height: 42px; padding: 9px 10px; border: 1px solid #d8dfda; border-radius: 6px; background: #f7f8f4; }
.object-item span { color: #237a57; font-weight: 800; }
.warnings { display: grid; gap: 8px; }
.warning { padding: 9px 10px; border-radius: 6px; background: #fbecd5; color: #693b00; font-size: 13px; }
.warning code { margin-right: 8px; font-weight: 800; }
.steps { display: grid; gap: 14px; margin: 0; padding-left: 24px; }
.steps li { padding-left: 4px; }
.steps span { display: inline-block; min-width: 54px; margin-right: 8px; color: #fff; background: #237a57; border-radius: 999px; padding: 2px 8px; font-size: 12px; text-align: center; }
.steps strong { font-size: 16px; }
.steps p { margin: 6px 0 0; color: #17201b; line-height: 1.65; }
.explanation { margin-top: 22px; padding: 14px 0; border-top: 1px solid #d8dfda; border-bottom: 1px solid #d8dfda; }
.explanation p { line-height: 1.75; }
.notes { display: grid; gap: 16px; margin-top: 24px; }
.notes div { height: 1px; background: #d8dfda; }
@media print {
  body { background: #fff; }
  main { max-width: none; padding: 0; }
  .doc-header { display: none; }
  .page { min-height: 96vh; border: 0; border-radius: 0; margin: 0; }
}
"""
