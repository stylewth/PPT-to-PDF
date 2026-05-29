# AI Notes Integration Route

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` if this plan is executed later. Current repository rules forbid creating a new branch or worktree without explicit user approval.

**Goal:** Turn AI explanations into page-local study notes, not separate explanation pages.

**Architecture:** `base.pdf` remains the untouched comparison file. `guide.pdf` remains the non-AI learning baseline. `ai_guide.pdf` becomes an annotated-note version of `guide.pdf`: each AI note is anchored to a selected block and rendered on the same logical page as margin notes, callouts, underlines, highlights, or compact note strips. Adding a separate explanation page is not the default route and should only happen in an explicit long-form appendix mode later.

**Tech Stack:** Python backend, PyMuPDF, existing `knowledge_blocks.json`, existing AI explanation/editor pipeline, frontend reader in `app/frontend/app.js`, PDF screenshot gates.

---

## Route Reset

| Item | Decision |
|---|---|
| Product metaphor | Like taking notes on a PDF: highlight, underline, arrows, short margin notes, formula reminders, and local callouts. |
| Default page count | `ai_guide.pdf` should keep the same page count as `guide.pdf` by default. |
| Forbidden default | Do not append an "AI Explanation - Page N" page as the normal result. |
| AI role | Condense explanation cards into note-sized text and note intent. |
| System role | Decide safe page-local placement, draw notes, and reject or ask for shorter notes if no safe layout exists. |
| User role | Select which blocks enter the AI note layer. User selection is the inclusion decision. |
| AI content source | The default AI PDF route uses the previous selected-block mode only. Whole-page explanations remain a Web reading aid unless a later explicit whole-page note mode is designed. |

## Target Visual Language

| Note Type | Use Case | Visual Form |
|---|---|---|
| `highlight_label` | A key term needs a one-line meaning. | Soft highlighter behind original term plus tiny nearby label. |
| `margin_note` | A block needs a short explanation. | Side or bottom handwritten-style note box, linked to the block. |
| `formula_note` | A formula needs meaning, unit, or condition. | Arrow to formula, compact explanation, optional unit reminder. |
| `process_arrow` | Animation or reasoning order matters. | Thin arrow and numbered step text near related objects. |
| `mistake_hint` | Common confusion or exam reminder. | Small red/blue note, max one sentence. |
| `summary_strip` | A dense page needs one summary. | Bottom strip inside or around the page, not a separate page. |

## Placement Policy

| Priority | Strategy | Rule |
|---|---|---|
| 1 | Existing blank area | Use true blank space near the selected block first. |
| 2 | Existing page margin | Use side, top, or bottom margin if it does not cover original content. |
| 3 | Expanded same-page canvas | Enlarge the PDF page canvas to add notebook margin while keeping the original page visible and unchanged. This is still the same logical page, not a new explanation page. |
| 4 | Condense note | If no safe space exists, shorten the note and try again. |
| 5 | Reject with visible reason | If still unsafe, do not silently append a new page; tell the user which selected note could not be placed. |

## Content Budget

| Scope | Budget |
|---|---|
| Per note | 12-45 Chinese chars preferred; hard max 80 chars unless explicitly using summary strip. |
| Per selected block | 1 note by default; at most 2 when formula + misconception are both useful. |
| Per page | 1-5 notes depending on blank space, not a fixed count. |
| Long explanation | Stays in Web reader, not in PDF note layer. |

## Data Contract

| Field | Meaning |
|---|---|
| `target_kind` | `block` or `page`. |
| `target_id` | Knowledge block id or `page_<number>`. |
| `prompt_profile` | Study/training/simple role that generated the explanation. |
| `note_type` | One of the visual note types above. |
| `note_text` | User-facing short note. No internal source refs. |
| `anchor_refs` | Internal source refs used only for audit. |
| `anchor_bbox` | Display bbox from `knowledge_blocks.json` / guide preview coordinates. |
| `style_intent` | `blue_note`, `red_hint`, `yellow_highlight`, `gray_formula`, etc. |
| `priority` | Used only when space is limited; user selection still means inclusion should be attempted. |

## Implementation Phases

| Phase | Goal | Main Files |
|---|---|---|
| M1 Route switch | Disable default appended explanation pages for AI notes. | `app/backend/ai_pdf_exporter.py`, tests |
| M2 Note contract | Replace `extension_panel/drop` centered thinking with anchored note objects. | `app/backend/ai_pdf_editor.py`, `app/tests/test_v6_ai_pdf_editor.py` |
| M3 Same-page layout | Score blank/margin/expanded-canvas placements around anchors. | new `app/backend/ai_note_layout.py`, exporter tests |
| M4 Note renderer | Draw highlighter, note boxes, arrows, underlines, and summary strips. | `app/backend/ai_pdf_exporter.py` |
| M5 Frontend preview | Let users see which selected blocks will become notes before export. | `app/frontend/app.js`, `app/frontend/styles.css` |
| M6 Visual gate | Render touched pages and fail on overlap, clipped text, or unreadable notes. | `app/backend/render_visual_check.py`, tests |

## Acceptance Gates

| Gate | Pass Condition |
|---|---|
| Page count | Default AI note export keeps `ai_guide.pdf` page count equal to `guide.pdf`. |
| Locality | Every AI note is visually attached to its selected block or page area. |
| Legibility | Original PPT text/formulas/images remain readable; AI note text is not clipped. |
| Note feel | Output resembles annotated study notes, not a report page or card list. |
| Source safety | No `slide_text@...` or JSON source refs appear in the user-facing PDF. |
| Failure behavior | If a selected note cannot be safely placed, export reports it; it does not hide failure by appending a generic explanation page. |

## First Concrete Slice

| Step | Test First |
|---|---|
| Replace appended explanation page fallback with expanded same-page canvas for one selected block. | A test exports one selected note on a dense page and asserts `ai_guide.pdf` page count equals `guide.pdf` page count. |
| Add anchored note manifest fields. | A test asserts manifest records `note_type`, `anchor_bbox`, and `placement_rect`. |
| Render one margin note and connector. | A screenshot/geometry test asserts note rect does not overlap protected bboxes. |
| Keep long text out of PDF. | A test asserts full `detail` stays out and only `note_text`/short snippet is rendered. |

## Non-Goals

| Non-Goal | Reason |
|---|---|
| Full lecture transcript in PDF | Breaks the notebook metaphor and crowds the page. |
| AI choosing final coordinates | Unsafe; deterministic layout must own geometry. |
| Hiding failed placement by appending pages | This recreates the current wrong route. |
| Modifying `guide.pdf` in place | `guide.pdf` is the stable baseline; AI output remains separate as `ai_guide.pdf`. |
