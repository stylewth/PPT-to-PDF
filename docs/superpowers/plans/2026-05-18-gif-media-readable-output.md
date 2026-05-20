# GIF Media Readable Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect GIF media in PPTX, export the original asset, generate readable keyframe previews, and make the learning PDF/report expose the motion instead of silently flattening it to one frame.

**Architecture:** Extend the existing PPTX parser with media relationship metadata, add a focused media processor for asset export and GIF keyframe generation, then replace the original GIF bbox in `guide.pdf` with a keyframe grid. Keep the current reflow route intact: stable non-media objects do not move.

**Tech Stack:** Python standard library ZIP/XML, Pillow for GIF frames, PyMuPDF for PDF overlay, current `converter.py`/`pdf_augmenter.py` pipeline.

---

### Task 1: Parse PPTX Media References

**Files:**
- Modify: `app/backend/pptx_parser.py`
- Test: `app/tests/test_v3_media_processor.py`

- [x] Write a failing test that builds a tiny PPTX with one GIF relationship and asserts the parsed picture object includes `media.kind == "gif"`, `media.path`, `media.rel_id`, and its bbox.
- [x] Run `python -m unittest app.tests.test_v3_media_processor.MediaProcessorTest.test_parse_pptx_marks_gif_picture_media` and confirm it fails because media metadata is missing.
- [x] Pass slide relationships into `_parse_objects`, resolve `a:blip r:embed`, and attach normalized media metadata to `pic` objects.
- [x] Re-run the focused test and confirm it passes.

### Task 2: Export GIF And Generate Keyframe Strip

**Files:**
- Create: `app/backend/media_processor.py`
- Modify: `app/requirements.txt`
- Test: `app/tests/test_v3_media_processor.py`

- [x] Write failing tests for `process_presentation_media`: original GIF is copied to `media/`, poster and strip PNG are written under `media/previews/`, frame count/duration/sample indexes are recorded in `media_manifest.json`.
- [x] Run the focused test and confirm it fails because `media_processor.py` does not exist.
- [x] Implement GIF frame extraction with Pillow; if Pillow is unavailable, raise a clear error instead of pretending success.
- [x] Re-run focused tests and confirm they pass.

### Task 3: Integrate Media Manifest Into Conversion Outputs

**Files:**
- Modify: `app/backend/converter.py`
- Modify: `app/backend/server.py`
- Modify: `app/frontend/app.js`
- Test: `app/tests/test_v3_media_processor.py`

- [x] Write a failing converter test that checks `report.json.outputs.media_manifest_json`, `result["media_manifest_path"]`, and `/outputs/<job>/media_manifest.json` are exposed.
- [x] Implement `process_presentation_media` call after analysis and before report writing.
- [x] Add the manifest link to Web response and frontend download list.
- [x] Re-run focused tests.

### Task 4: Replace GIF Box With Keyframes In Guide PDF

**Files:**
- Modify: `app/backend/pdf_augmenter.py`
- Test: `app/tests/test_v3_media_processor.py`

- [x] Write a failing PDF test that creates a one-page PDF plus a GIF manifest and asserts colored keyframe pixels replace the source GIF bbox.
- [x] Implement `overlay_media_summaries(...)` using PyMuPDF and generated grid PNGs.
- [x] Call it after `guide.pdf` generation so it works for both native copy and object-reflow guide PDFs.
- [x] Add a regression test so the replacement stays inside the source bbox and does not cover the slide title.
- [x] Re-run focused tests.

### Task 5: Real Sample Verification

**Files:**
- Use: `app/samples/test.pptx`

- [x] Run `python -m unittest app.tests.test_v3_media_processor`.
- [x] Run `python -m unittest discover -s app\tests`.
- [x] Run `python -m compileall app\backend`.
- [x] Run `node --check app\frontend\app.js`.
- [x] Convert `app/samples/test.pptx` with PDF output.
- [x] Render/check the GIF slide screenshot and ensure `guide.pdf` replaces the original GIF area with keyframes, with no global right-column packing.
