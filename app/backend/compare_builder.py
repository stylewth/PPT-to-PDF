from __future__ import annotations

import html
from pathlib import Path
from typing import Any


def write_compare_html(
    output_path: str | Path,
    *,
    source: dict[str, Any],
    plan: dict[str, Any],
    metrics: dict[str, Any],
    report: dict[str, Any],
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_compare_html(source=source, plan=plan, metrics=metrics, report=report), encoding="utf-8")
    return output


def render_compare_html(
    *,
    source: dict[str, Any],
    plan: dict[str, Any],
    metrics: dict[str, Any],
    report: dict[str, Any],
) -> str:
    title = html.escape(str(source.get("name") or "转换结果"))
    micro_pages = plan.get("summary", {}).get("micro_reflow_pages", [])
    warnings = report.get("warnings", [])
    warning_items = "".join(
        f"<li><code>{html.escape(str(item.get('code', 'warning')))}</code>{html.escape(str(item.get('message', '')))}</li>"
        for item in warnings[:8]
    ) or "<li>未发现需要人工优先处理的问题。</li>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} · Slide2Study 对比</title>
  <style>{_css()}</style>
</head>
<body>
  <main>
    <header>
      <p>Slide2Study · PPT 讲解还原 Agent</p>
      <h1>{title}</h1>
      <span>{int(source.get('slide_count') or 0)} 页课件 · 遮挡展开 {len(micro_pages)} 页 · 预计节省 {metrics.get('estimated_saved_minutes', 0)} 分钟</span>
    </header>
    <section class="compare">
      <article>
        <h2>普通 PDF</h2>
        <embed src="base.pdf" type="application/pdf" />
      </article>
      <article>
        <h2>学习版 PDF</h2>
        <embed src="guide.pdf" type="application/pdf" />
      </article>
    </section>
    <section class="facts">
      <article>
        <h2>遮挡展开与流程关系</h2>
        <p>学习版 PDF 保留原页面画面，优先利用原页空白区展示被遮挡内容；空白不足时才缩放让位，并用编号、箭头或关系线表达讲解流程。</p>
        <p>本次进入 PDF 微调重排的页面：{html.escape(', '.join(str(page) for page in micro_pages) or '无')}</p>
      </article>
      <article>
        <h2>提效数据</h2>
        <dl>
          <div><dt>运行耗时</dt><dd>{metrics.get('runtime_seconds', 0)} 秒</dd></div>
          <div><dt>动画页</dt><dd>{metrics.get('animated_page_count', 0)} 页</dd></div>
          <div><dt>问题数</dt><dd>{metrics.get('warning_count', 0)} 个</dd></div>
          <div><dt>预计节省</dt><dd>{metrics.get('estimated_saved_minutes', 0)} 分钟</dd></div>
        </dl>
      </article>
      <article>
        <h2>问题报告</h2>
        <ul>{warning_items}</ul>
      </article>
    </section>
  </main>
</body>
</html>
"""


def _css() -> str:
    return """
* { box-sizing: border-box; }
body { margin: 0; color: #17201b; background: #f7f8f4; font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; letter-spacing: 0; }
main { min-height: 100vh; padding: 24px; }
header { display: flex; align-items: end; justify-content: space-between; gap: 18px; padding-bottom: 16px; border-bottom: 1px solid #d8dfda; }
header p { margin: 0 0 6px; color: #237a57; font-size: 12px; font-weight: 800; }
h1, h2 { margin: 0; }
h1 { font-size: 28px; }
header span { color: #66746d; font-weight: 700; }
.compare { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-top: 18px; min-height: 620px; }
article { min-width: 0; background: #fff; border: 1px solid #d8dfda; border-radius: 8px; padding: 14px; }
.compare article { display: flex; flex-direction: column; }
h2 { font-size: 18px; margin-bottom: 12px; }
embed { width: 100%; min-height: 560px; flex: 1; border: 1px solid #edf1ed; background: #fff; }
.facts { display: grid; grid-template-columns: 1.15fr 0.85fr 1fr; gap: 18px; margin-top: 18px; }
p, li { line-height: 1.7; color: #29342f; }
dl { display: grid; gap: 10px; margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px solid #edf1ed; padding-bottom: 8px; }
dt { color: #66746d; }
dd { margin: 0; font-weight: 900; color: #237a57; }
code { margin-right: 8px; color: #7a4a12; font-weight: 800; }
@media (max-width: 1000px) { header, .compare, .facts { display: flex; flex-direction: column; align-items: stretch; } embed { min-height: 420px; } }
"""
