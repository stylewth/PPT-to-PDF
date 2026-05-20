from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "app"
BACKEND = APP_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from converter import convert_pptx  # noqa: E402


def main() -> int:
    sample = APP_ROOT / "samples" / "test.pptx"
    run_dir = APP_ROOT / "tests" / ".tmp_runs" / "reflow_visual_check" / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=False)

    result = convert_pptx(sample, run_dir, render_pdf=True)
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    for name in ("base", "guide"):
        pdf_path = run_dir / f"{name}.pdf"
        _render_pdf(pdf_path, run_dir, name)

    print(f"output={run_dir.resolve()}")
    print(json.dumps(report.get("reflow_intent_check", {}), ensure_ascii=False, indent=2))
    return 0


def _render_pdf(pdf_path: Path, output_dir: Path, stem: str) -> None:
    doc = fitz.open(pdf_path)
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False)
        pix.save(output_dir / f"{stem}_page_{index}.png")


if __name__ == "__main__":
    raise SystemExit(main())
