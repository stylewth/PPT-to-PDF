# PDF Micro Reflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. It will decide whether each batch should run in parallel or serial subagent mode and will pass only task-local context to each subagent. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V3G PDF micro-reflow so `guide.pdf` keeps the original PPT-converted page image and only performs local layout adjustments.

**Architecture:** Keep LibreOffice as the native rendering source for `base.pdf`. Add a PDF-level editor that reads `base.pdf`, maps PPTX object bboxes into PDF coordinates, scales the original page to create a note lane, and overlays concise sequence hints without redrawing the whole slide.

**Tech Stack:** Python stdlib, existing PPTX analysis pipeline, LibreOffice headless, PyMuPDF (`fitz`) as the primary PDF editing library.

---

## File Structure

| Path | Responsibility |
|---|---|
| `app/backend/pdf_micro_reflow.py` | New PDF-level editor: dependency check, coordinate mapping, page scaling, note-lane overlay, output `guide.pdf`. |
| `app/backend/augment_planner.py` | Replace full-page `reflow_replace` output with micro-reflow instructions. |
| `app/backend/layout_decider.py` | Keep strategy decision, but rename complex supported pages to `pdf_micro_reflow`. |
| `app/backend/pdf_augmenter.py` | Route micro-reflow plans to `pdf_micro_reflow.py`; keep PPTX overlay path for simple inline markers. |
| `app/backend/converter.py` | Keep output contract and report micro-reflow strategy in `report.json`. |
| `app/tests/test_v3_pdf_micro_reflow.py` | New tests for dependency failure, coordinate mapping, page count preservation, and overlay plan behavior. |
| `app/tests/test_v3_pdf_augmenter.py` | Update old full-page reflow assertions so they expect micro-reflow routing. |
| `app/README.md` | Update capability boundary: “PDF micro-reflow, not full object-level PDF editing.” |

## Task 1: Dependency Boundary

**Files:**
- Create: `app/tests/test_v3_pdf_micro_reflow.py`
- Create: `app/backend/pdf_micro_reflow.py`

- [ ] **Step 1: Write the failing dependency test**

```python
import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from pdf_micro_reflow import PdfMicroReflowError, require_pymupdf


class V3PdfMicroReflowTest(unittest.TestCase):
    def test_require_pymupdf_reports_missing_dependency(self):
        with self.assertRaisesRegex(PdfMicroReflowError, "PyMuPDF"):
            require_pymupdf(importer=lambda name: (_ for _ in ()).throw(ImportError(name)))
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow.V3PdfMicroReflowTest.test_require_pymupdf_reports_missing_dependency
```

Expected: fails because `pdf_micro_reflow` does not exist.

- [ ] **Step 3: Implement minimal dependency wrapper**

```python
from __future__ import annotations

from typing import Callable, Any


class PdfMicroReflowError(RuntimeError):
    pass


def require_pymupdf(importer: Callable[[str], Any] = __import__) -> Any:
    try:
        return importer("fitz")
    except ImportError as exc:
        raise PdfMicroReflowError("PyMuPDF is required for PDF micro-reflow. Install package: PyMuPDF.") from exc
```

- [ ] **Step 4: Run the test and verify GREEN**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow.V3PdfMicroReflowTest.test_require_pymupdf_reports_missing_dependency
```

Expected: OK.

## Task 2: Coordinate Mapping

**Files:**
- Modify: `app/tests/test_v3_pdf_micro_reflow.py`
- Modify: `app/backend/pdf_micro_reflow.py`

- [ ] **Step 1: Write the failing bbox mapping test**

Append this method to the existing `V3PdfMicroReflowTest` class, and extend the import line to include `map_emu_box_to_pdf`:

```python
def test_map_emu_box_to_pdf_scales_slide_coordinates_to_points(self):
    result = map_emu_box_to_pdf(
        {"x": 6096000, "y": 3429000, "w": 3048000, "h": 1714500},
        slide_size={"width": 12192000, "height": 6858000},
        page_rect=(0.0, 0.0, 960.0, 540.0),
    )

    self.assertEqual(result, (480.0, 270.0, 720.0, 405.0))
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow.V3PdfMicroReflowTest.test_map_emu_box_to_pdf_scales_slide_coordinates_to_points
```

Expected: FAIL because `map_emu_box_to_pdf` is missing.

- [ ] **Step 3: Implement mapping**

```python
def map_emu_box_to_pdf(
    bbox: dict[str, int],
    *,
    slide_size: dict[str, int],
    page_rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    page_x0, page_y0, page_x1, page_y1 = page_rect
    page_width = page_x1 - page_x0
    page_height = page_y1 - page_y0
    slide_width = max(int(slide_size.get("width", 1)), 1)
    slide_height = max(int(slide_size.get("height", 1)), 1)
    x0 = page_x0 + int(bbox.get("x", 0)) / slide_width * page_width
    y0 = page_y0 + int(bbox.get("y", 0)) / slide_height * page_height
    x1 = x0 + int(bbox.get("w", 0)) / slide_width * page_width
    y1 = y0 + int(bbox.get("h", 0)) / slide_height * page_height
    return (round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2))
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow
```

Expected: OK.

## Task 3: Micro-Reflow Plan Shape

**Files:**
- Modify: `app/tests/test_v3_layout_decider.py`
- Modify: `app/tests/test_v3_pdf_augmenter.py`
- Modify: `app/backend/layout_decider.py`
- Modify: `app/backend/augment_planner.py`

- [ ] **Step 1: Write failing strategy assertions**

Update complex supported page expectations:

```python
self.assertEqual(decide_slide_layout({...})["strategy"], "pdf_micro_reflow")
```

Update `test.pptx` plan assertions:

```python
self.assertEqual(plan["summary"]["micro_reflow_pages"], [1, 2])
self.assertEqual([slide["strategy"] for slide in plan["slides"]], ["pdf_micro_reflow", "pdf_micro_reflow"])
self.assertTrue(all(slide["micro_reflow"] for slide in plan["slides"]))
self.assertEqual(plan["summary"]["guide_page_count"], 0)
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m unittest app.tests.test_v3_layout_decider app.tests.test_v3_pdf_augmenter
```

Expected: FAIL because strategy is still `reflow_replace`.

- [ ] **Step 3: Implement minimal planner change**

In `layout_decider.py`, return `pdf_micro_reflow` for complex supported pages.

In `augment_planner.py`, replace `reflow_page` with:

```python
"micro_reflow": {
    "mode": "scale_with_note_lane",
    "note_lane": "right",
    "preserve_original_page_ratio": 0.86,
    "steps": [{"order": index + 1, "text": text} for index, text in enumerate(_guide_step_summaries(slide.get("animation_steps", []))[:4])],
}
```

Add summary:

```python
"micro_reflow_pages": [
    slide["source_slide"]
    for slide in slides
    if slide["strategy"] == "pdf_micro_reflow"
],
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
python -m unittest app.tests.test_v3_layout_decider app.tests.test_v3_pdf_augmenter
```

Expected: OK.

## Task 4: PDF Page Scaling And Note Lane

**Files:**
- Modify: `app/tests/test_v3_pdf_micro_reflow.py`
- Modify: `app/backend/pdf_micro_reflow.py`

- [ ] **Step 1: Write failing integration-style test with fake fitz**

Use a small fake API that records operations:

```python
def test_apply_micro_reflow_keeps_page_count_and_adds_note_lane(self):
    fake_fitz = FakeFitz(page_count=2, page_rect=(0.0, 0.0, 960.0, 540.0))
    plan = {
        "slides": [
            {"source_slide": 1, "strategy": "pdf_micro_reflow", "size": {"width": 12192000, "height": 6858000}, "micro_reflow": {"note_lane": "right", "steps": [{"order": 1, "text": "先出现：A"}]}},
            {"source_slide": 2, "strategy": "keep_native", "size": {"width": 12192000, "height": 6858000}},
        ]
    }

    apply_micro_reflow_pdf("base.pdf", "guide.pdf", plan, fitz_module=fake_fitz)

    self.assertEqual(fake_fitz.saved_path, "guide.pdf")
    self.assertEqual(fake_fitz.page_count, 2)
    self.assertTrue(fake_fitz.pages[0].show_pdf_page_calls)
    self.assertTrue(fake_fitz.pages[0].draw_rect_calls)
    self.assertTrue(fake_fitz.pages[0].insert_textbox_calls)
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow.V3PdfMicroReflowTest.test_apply_micro_reflow_keeps_page_count_and_adds_note_lane
```

Expected: FAIL because `apply_micro_reflow_pdf` is missing.

- [ ] **Step 3: Implement page processing**

Implement:

```python
def apply_micro_reflow_pdf(base_pdf_path, output_pdf_path, plan, *, fitz_module=None):
    fitz = fitz_module or require_pymupdf()
    doc = fitz.open(str(base_pdf_path))
    for slide in plan.get("slides", []):
        if slide.get("strategy") != "pdf_micro_reflow":
            continue
        page_index = int(slide.get("source_slide", 0)) - 1
        if page_index < 0 or page_index >= len(doc):
            continue
        page = doc[page_index]
        rect = page.rect
        width = rect.width
        height = rect.height
        content_rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + width * 0.84, rect.y1)
        lane_rect = fitz.Rect(rect.x0 + width * 0.85, rect.y0, rect.x1, rect.y1)
        page.show_pdf_page(content_rect, doc, page_index)
        page.draw_rect(lane_rect, color=(0.88, 0.92, 0.90), fill=(0.96, 0.98, 0.97), width=0.5)
        _insert_step_text(page, lane_rect, slide.get("micro_reflow", {}).get("steps", []), fitz)
    doc.save(str(output_pdf_path))
    doc.close()
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_micro_reflow
```

Expected: OK.

## Task 5: Wire Into Existing Conversion

**Files:**
- Modify: `app/backend/pdf_augmenter.py`
- Modify: `app/tests/test_v3_pdf_augmenter.py`

- [ ] **Step 1: Write failing routing test**

Add:

```python
def test_generate_guide_pdf_uses_micro_reflow_for_micro_reflow_plan(self):
    calls = []
    def fake_apply(base_pdf_path, guide_pdf_path, plan):
        calls.append((str(base_pdf_path), str(guide_pdf_path), plan["summary"]["micro_reflow_pages"]))
        Path(guide_pdf_path).write_bytes(b"%PDF-1.7\n%micro reflow\n")

    result = generate_guide_pdf(
        pptx_path,
        output_dir,
        plan,
        base_pdf_path=base_pdf,
        micro_reflow_runner=fake_apply,
    )

    self.assertEqual(calls[0][2], [1])
    self.assertTrue(Path(result["guide_pdf_path"]).exists())
```

- [ ] **Step 2: Run and verify RED**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_augmenter.V3PdfAugmenterTest.test_generate_guide_pdf_uses_micro_reflow_for_micro_reflow_plan
```

Expected: FAIL because `generate_guide_pdf` does not accept `micro_reflow_runner`.

- [ ] **Step 3: Implement routing**

In `pdf_augmenter.py`:

```python
from pdf_micro_reflow import apply_micro_reflow_pdf

def _has_micro_reflow(plan):
    return any(slide.get("strategy") == "pdf_micro_reflow" for slide in plan.get("slides", []))
```

Before writing guide PPTX:

```python
if _has_micro_reflow(plan):
    runner = micro_reflow_runner or apply_micro_reflow_pdf
    runner(base_pdf_path, guide_pdf_path, plan)
    return {"augment_plan_path": plan_path, "guide_pdf_path": guide_pdf_path}
```

- [ ] **Step 4: Run and verify GREEN**

Run:

```powershell
python -m unittest app.tests.test_v3_pdf_augmenter
```

Expected: OK.

## Task 6: Real `test.pptx` Verification

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run all tests**

```powershell
python -m unittest discover -s app\tests
```

Expected: all tests OK.

- [ ] **Step 2: Compile key backend files**

```powershell
$env:PYTHONPYCACHEPREFIX=(Resolve-Path -LiteralPath 'app\tests\.tmp_runs').Path + '\pycache'
python -m py_compile app\backend\pdf_micro_reflow.py app\backend\pdf_augmenter.py app\backend\augment_planner.py app\backend\layout_decider.py app\backend\converter.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Convert `test.pptx`**

```powershell
python app\backend\cli.py app\samples\test.pptx app\tests\.tmp_runs\pdf_micro_reflow_test
```

Expected:
- `base.pdf` exists
- `guide.pdf` exists
- both PDFs have 2 pages
- `augment_plan.json` has `micro_reflow_pages: [1, 2]`
- `guide_page_count: 0`

- [ ] **Step 4: Render guide pages for visual QA**

```powershell
$out='app\tests\.tmp_runs\pdf_micro_reflow_pages'
if (Test-Path -LiteralPath $out) { Remove-Item -LiteralPath $out -Recurse -Force }
New-Item -ItemType Directory -Path $out | Out-Null
pdftoppm -png -r 120 'app\tests\.tmp_runs\pdf_micro_reflow_test\guide.pdf' (Join-Path $out 'page')
Get-ChildItem -LiteralPath $out | Select-Object FullName,Length
```

Expected: two PNG files. Inspect them: original slide content should remain visible, with a right-side note lane.

- [ ] **Step 5: Record results**

Update `progress.md` with command results. Update `findings.md` if visual QA shows overlap, unreadable text, or page content loss.

## Self-Review Checklist

| Check | Status |
|---|---|
| Spec coverage | Covers dependency, mapping, planning, PDF editing, routing, and real sample verification |
| Placeholder scan | No placeholder tokens |
| Type consistency | Uses `pdf_micro_reflow`, `micro_reflow_pages`, `micro_reflow`, and `apply_micro_reflow_pdf` consistently |
| Scope control | Does not promise arbitrary PDF object-level editing |
| TDD | Every production behavior starts with a failing test |
