# AI Guide Reader UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a new branch, worktree, or commit unless the user explicitly approves it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement方案 A：以知识块解释为主、整页解释兜底，把 Web 改成直接围绕 `guide.pdf` 阅读、点选、生成、旁侧查看 AI 解释的产品界面。

**Architecture:** Keep `base.pdf` and `guide.pdf` as stable outputs. Render `guide.pdf` pages into preview images, map content-based knowledge blocks onto those page images, and let the frontend queue separate AI calls per block so every explanation stays tied to one original content area. Whole-page explanation is only used when block segmentation is unreliable or the user chooses page-level send for a fallback page.

**Tech Stack:** Python stdlib HTTP server, PyMuPDF, existing converter/knowledge block pipeline, vanilla JS/CSS frontend, OpenAI-compatible provider adapter, `unittest`, Browser verification for local Web UI.

---

## Final Behavior

| 区域 | 目标行为 |
|---|---|
| 顶栏 | 只保留 `Base PDF`、`Guide PDF`、`对比页`、`AI 解释版`；`AI 解释版` 在没有 `ai_guide.pdf` 前禁用但可见 |
| Preview | 默认展示生成后的 `guide.pdf` 预览，不再展示调试型对象列表作为主视图 |
| 知识块选择 | 在 `guide.pdf` 页图上显示可点选区域；勾选状态直接叠在页面上 |
| AI 解释 | 每个块单独请求、单独缓存、单独展示；解释显示在当前页右侧，并锚定到对应原文块 |
| 一页发送 | 对当前页所有可解释块逐个排队请求；不是把整页内容一次合并发给模型 |
| 整页兜底 | 当一页块划分不可靠时，显示一个 `whole_page` 块，只发送该页最小上下文 |
| 动画重复 | 动画只作为 `animation_refs` 证据挂到内容块上，不再因为 appear/fade 生成重复文本块 |

## Output Contracts

### `guide_preview_manifest.json`

```json
{
  "kind": "guide_preview",
  "version": "v5a",
  "pdf": "guide.pdf",
  "pages": [
    {
      "number": 1,
      "width_pt": 720.0,
      "height_pt": 405.0,
      "image": "guide_preview/page_001.png",
      "image_width": 1440,
      "image_height": 810
    }
  ]
}
```

### `knowledge_blocks.json` v5

```json
{
  "kind": "knowledge_blocks",
  "version": "v5a",
  "slides": [
    {
      "number": 1,
      "mode": "blocks",
      "fallback_reason": "",
      "blocks": [
        {
          "id": "s1_b1",
          "type": "text_concept",
          "title": "Electric potential energy",
          "texts": ["Like the gravitational force..."],
          "display_bbox": {"x": 0.12, "y": 0.31, "w": 0.43, "h": 0.18},
          "content_hash": "sha256:...",
          "source_refs": [
            {"kind": "slide_text", "slide": 1, "object_id": "shape7"}
          ],
          "animation_refs": [
            {"kind": "animation", "slide": 1, "object_id": "shape7", "effect": "appear"}
          ],
          "token_estimate": 154
        }
      ]
    }
  ]
}
```

兜底页使用：

```json
{
  "number": 3,
  "mode": "whole_page",
  "fallback_reason": "duplicate_animation_text",
  "blocks": [
    {
      "id": "s3_page",
      "type": "whole_page",
      "title": "第 3 页整页解释",
      "texts": ["页面内去重后的全部可读文字"],
      "display_bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
      "source_refs": [
        {"kind": "slide", "slide": 3, "object_id": "page"}
      ],
      "animation_refs": [],
      "token_estimate": 900
    }
  ]
}
```

## Files

| 文件 | 动作 | 职责 |
|---|---|---|
| `app/backend/guide_preview.py` | Create | 渲染 `guide.pdf` 为页图，写 `guide_preview_manifest.json` |
| `app/backend/converter.py` | Modify | 转换完成后生成 guide preview，并把 manifest URL 暴露给 Web |
| `app/backend/knowledge_blocks.py` | Modify | 从动画驱动块改为内容驱动块，动画变为证据引用 |
| `app/backend/ai_context.py` | Modify | 支持单块上下文和 `whole_page` 兜底页上下文 |
| `app/backend/server.py` | Modify | 转换响应增加 reader 所需 URL；保留单块 `/api/ai/explain`，新增页兜底接口 |
| `app/frontend/index.html` | Modify | 顶栏收敛、加入 reader 主体和右侧解释栏 |
| `app/frontend/styles.css` | Modify | 页面图、overlay、选中态、解释侧栏、队列状态 |
| `app/frontend/app.js` | Modify | 渲染 guide 页图、点击知识块、按块排队请求、当前页发送 |
| `app/tests/test_v5_guide_preview.py` | Create | guide preview manifest 和页图生成测试 |
| `app/tests/test_v5_knowledge_blocks_dedupe.py` | Create | 动画重复文本去重、整页兜底测试 |
| `app/tests/test_v5_ai_context.py` | Create | 单块/整页上下文边界测试 |
| `app/tests/test_v5_server_reader_payload.py` | Create | Web 响应契约测试 |

## Task 1: Lock Reader Output Contract

**Files:**
- Create: `app/tests/test_v5_server_reader_payload.py`
- Modify: `app/backend/server.py`
- Modify: `app/backend/converter.py`

- [ ] **Step 1: Write failing response contract test**

```python
import unittest


class ReaderPayloadContractTest(unittest.TestCase):
    def test_convert_response_exposes_reader_assets(self):
        response = {
            "outputs": {
                "base_pdf_url": "/outputs/job/base.pdf",
                "guide_pdf_url": "/outputs/job/guide.pdf",
                "guide_preview_manifest_url": "/outputs/job/guide_preview_manifest.json",
                "knowledge_blocks_url": "/outputs/job/knowledge_blocks.json",
                "ai_guide_pdf_url": None,
            }
        }
        outputs = response["outputs"]
        self.assertTrue(outputs["guide_pdf_url"].endswith("guide.pdf"))
        self.assertTrue(outputs["guide_preview_manifest_url"].endswith("guide_preview_manifest.json"))
        self.assertTrue(outputs["knowledge_blocks_url"].endswith("knowledge_blocks.json"))
        self.assertIsNone(outputs["ai_guide_pdf_url"])
```

- [ ] **Step 2: Run contract test**

Run:

```powershell
python -m unittest app.tests.test_v5_server_reader_payload -v
```

Expected: FAIL until real conversion response exposes `guide_preview_manifest_url` and `ai_guide_pdf_url`.

- [ ] **Step 3: Add response fields**

`converter.py` returns output paths for `guide_preview_manifest.json`; `server.py` maps them to URLs under the existing output serving route. `ai_guide_pdf_url` is `null` until the file exists.

- [ ] **Step 4: Re-run contract test**

Run:

```powershell
python -m unittest app.tests.test_v5_server_reader_payload -v
```

Expected: PASS.

## Task 2: Generate Guide Preview Assets

**Files:**
- Create: `app/backend/guide_preview.py`
- Create: `app/tests/test_v5_guide_preview.py`
- Modify: `app/backend/converter.py`

- [ ] **Step 1: Write failing manifest test**

```python
import json
import tempfile
import unittest
from pathlib import Path

import fitz

from app.backend.guide_preview import build_guide_preview


class GuidePreviewTest(unittest.TestCase):
    def test_build_guide_preview_writes_manifest_and_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pdf_path = root / "guide.pdf"
            doc = fitz.open()
            doc.new_page(width=720, height=405)
            doc.save(pdf_path)
            doc.close()

            manifest_path = build_guide_preview(pdf_path, root)

            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], "v5a")
            self.assertEqual(len(data["pages"]), 1)
            self.assertTrue((root / data["pages"][0]["image"]).exists())
            self.assertEqual(data["pages"][0]["width_pt"], 720)
            self.assertEqual(data["pages"][0]["height_pt"], 405)
```

- [ ] **Step 2: Run preview test**

Run:

```powershell
python -m unittest app.tests.test_v5_guide_preview -v
```

Expected: FAIL because `guide_preview.py` does not exist.

- [ ] **Step 3: Implement `build_guide_preview`**

Function signature:

```python
from pathlib import Path


def build_guide_preview(pdf_path: Path, output_dir: Path, zoom: float = 2.0) -> Path:
    """Render guide.pdf pages to PNG files and return manifest path."""
```

Rules:

| 规则 | 实现 |
|---|---|
| 输出目录 | `output_dir / "guide_preview"` |
| 页图命名 | `page_001.png`, `page_002.png` |
| 坐标基准 | manifest 同时写 PDF point 尺寸和 PNG pixel 尺寸 |
| 失败方式 | PDF 不存在或渲染失败直接抛错，不吞掉 |

- [ ] **Step 4: Integrate converter**

`convert_pptx` 在 `guide.pdf` 已生成后调用 `build_guide_preview(guide_pdf_path, output_dir)`，并写入 `report.json.outputs.guide_preview_manifest`.

- [ ] **Step 5: Re-run preview test**

Run:

```powershell
python -m unittest app.tests.test_v5_guide_preview -v
```

Expected: PASS.

## Task 3: Make Blocks Content-Based And De-Duplicated

**Files:**
- Create: `app/tests/test_v5_knowledge_blocks_dedupe.py`
- Modify: `app/backend/knowledge_blocks.py`

- [ ] **Step 1: Write failing duplicate-animation test**

```python
import unittest

from app.backend.knowledge_blocks import merge_animation_duplicates


class KnowledgeBlockDedupeTest(unittest.TestCase):
    def test_same_text_with_multiple_animation_effects_becomes_one_block(self):
        blocks = [
            {
                "id": "s1_a1",
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "display_bbox": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.1},
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "shape3", "effect": "appear"}],
            },
            {
                "id": "s1_a2",
                "type": "animation_flow",
                "texts": ["Like the gravitational force"],
                "display_bbox": {"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.1},
                "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape3"}],
                "animation_refs": [{"kind": "animation", "slide": 1, "object_id": "shape3", "effect": "fade"}],
            },
        ]

        merged = merge_animation_duplicates(blocks)

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["type"], "text_concept")
        self.assertEqual(len(merged[0]["animation_refs"]), 2)
```

- [ ] **Step 2: Write failing whole-page fallback test**

```python
import unittest

from app.backend.knowledge_blocks import should_use_whole_page_fallback


class WholePageFallbackTest(unittest.TestCase):
    def test_duplicate_heavy_page_uses_whole_page_fallback(self):
        page_blocks = [
            {"texts": ["same text"], "content_hash": "a"} for _ in range(6)
        ]
        self.assertTrue(
            should_use_whole_page_fallback(page_blocks, duplicate_ratio=0.66, block_count=6)
        )
```

- [ ] **Step 3: Run dedupe tests**

Run:

```powershell
python -m unittest app.tests.test_v5_knowledge_blocks_dedupe -v
```

Expected: FAIL until helper functions exist and are wired into block generation.

- [ ] **Step 4: Implement content identity**

Each generated block gets:

| 字段 | 来源 |
|---|---|
| `content_hash` | normalized text + normalized image/media object ids + rounded bbox |
| `animation_refs` | existing animation evidence for same object/text |
| `type` | content semantic type, not animation effect type |

Normalized text rules:

```text
strip -> collapse whitespace -> lowercase -> remove repeated punctuation-only gaps
```

- [ ] **Step 5: Implement fallback threshold**

Use whole-page mode when either condition is true:

| 条件 | 阈值 |
|---|---|
| duplicate content ratio | `>= 0.5` and block count `>= 5` |
| all blocks are animation-only evidence | block count `>= 3` |

The fallback creates exactly one `whole_page` block with de-duplicated page text and all valid page source refs.

- [ ] **Step 6: Re-run dedupe tests**

Run:

```powershell
python -m unittest app.tests.test_v5_knowledge_blocks_dedupe -v
```

Expected: PASS.

## Task 4: Support Block And Whole-Page AI Context

**Files:**
- Create: `app/tests/test_v5_ai_context.py`
- Modify: `app/backend/ai_context.py`
- Modify: `app/backend/server.py`

- [ ] **Step 1: Write failing context tests**

```python
import unittest

from app.backend.ai_context import build_single_block_context, build_whole_page_context


class AiContextV5Test(unittest.TestCase):
    def test_single_block_context_contains_only_selected_block_text(self):
        block = {
            "id": "s1_b1",
            "texts": ["selected concept"],
            "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "shape1"}],
            "animation_refs": [],
        }
        context = build_single_block_context(block, page_title="Title")
        self.assertIn("selected concept", context["evidence_text"])
        self.assertNotIn("unselected concept", context["evidence_text"])

    def test_whole_page_context_uses_deduped_text(self):
        page = {
            "number": 1,
            "blocks": [
                {"texts": ["A"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "a"}]},
                {"texts": ["A"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "b"}]},
                {"texts": ["B"], "source_refs": [{"kind": "slide_text", "slide": 1, "object_id": "c"}]},
            ],
        }
        context = build_whole_page_context(page)
        self.assertEqual(context["evidence_text"].count("A"), 1)
        self.assertIn("B", context["evidence_text"])
```

- [ ] **Step 2: Run context tests**

Run:

```powershell
python -m unittest app.tests.test_v5_ai_context -v
```

Expected: FAIL until v5 context functions exist.

- [ ] **Step 3: Implement context builders**

Rules:

| Context | 输入 | 输出边界 |
|---|---|---|
| single block | one block + page title | only selected block evidence + source refs + animation refs |
| whole page | one slide entry | de-duplicated page text + page-level source refs |

Do not include API key in context, cache key, audit file, or logs.

- [ ] **Step 4: Add page fallback endpoint**

Add `POST /api/ai/explain-page` for `whole_page` blocks only. If the page mode is `blocks`, frontend should call `/api/ai/explain` once per block instead of this endpoint.

- [ ] **Step 5: Re-run context tests**

Run:

```powershell
python -m unittest app.tests.test_v5_ai_context -v
```

Expected: PASS.

## Task 5: Rebuild Top Bar And Reader Layout

**Files:**
- Modify: `app/frontend/index.html`
- Modify: `app/frontend/styles.css`
- Modify: `app/frontend/app.js`

- [ ] **Step 1: Replace top bar actions**

Top bar visible actions:

| Label | Enabled condition |
|---|---|
| `Base PDF` | `base_pdf_url` exists |
| `Guide PDF` | `guide_pdf_url` exists |
| `对比页` | `compare_url` exists |
| `AI 解释版` | `ai_guide_pdf_url` exists; otherwise disabled |

Move debug/report/media/knowledge downloads into a collapsed details area below the reader.

- [ ] **Step 2: Build reader shell**

Main layout:

```text
┌──────────────────────────────────────────────┐
│ Top bar: Base / Guide / 对比页 / AI 解释版    │
├─────────────────────────────┬────────────────┤
│ guide page preview + blocks │ current page AI │
│ page tabs / zoom / send page│ explanations    │
└─────────────────────────────┴────────────────┘
```

- [ ] **Step 3: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 6: Render Guide Preview With Selectable Overlays

**Files:**
- Modify: `app/frontend/app.js`
- Modify: `app/frontend/styles.css`

- [ ] **Step 1: Load manifest and blocks together**

Frontend state:

```js
const readerState = {
  pages: [],
  blocksByPage: new Map(),
  currentPage: 1,
  selectedBlockIds: new Set(),
  explanationsByBlockId: new Map(),
  queue: [],
  running: false
};
```

- [ ] **Step 2: Map normalized bbox to overlay CSS**

```js
function bboxToStyle(bbox) {
  return {
    left: `${bbox.x * 100}%`,
    top: `${bbox.y * 100}%`,
    width: `${bbox.w * 100}%`,
    height: `${bbox.h * 100}%`
  };
}
```

- [ ] **Step 3: Add click behavior**

Clicking an overlay toggles `selectedBlockIds`. The overlay shows selected state directly on the page; the side panel updates to the same block.

- [ ] **Step 4: Guard invalid bbox**

If any bbox has `x/y/w/h` outside `[0, 1]` or non-positive width/height, show that block in the side panel as non-clickable and record a console warning with block id. Do not silently stretch it to the whole page.

- [ ] **Step 5: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 7: Queue One AI Request Per Block

**Files:**
- Modify: `app/frontend/app.js`
- Modify: `app/frontend/styles.css`

- [ ] **Step 1: Implement queue function**

```js
function enqueueBlockExplanation(blockId) {
  if (readerState.explanationsByBlockId.has(blockId)) return;
  if (readerState.queue.some((item) => item.blockId === blockId)) return;
  readerState.queue.push({ blockId, status: "pending" });
  runExplanationQueue();
}
```

- [ ] **Step 2: Implement serial runner**

```js
async function runExplanationQueue() {
  if (readerState.running) return;
  readerState.running = true;
  try {
    while (readerState.queue.length > 0) {
      const item = readerState.queue.shift();
      await explainSingleBlock(item.blockId);
    }
  } finally {
    readerState.running = false;
    renderReader();
  }
}
```

Concurrency is `1` for the first implementation. This keeps mapping and provider errors easy to see.

- [ ] **Step 3: Keep existing `/api/ai/explain` single-block**

The request body contains exactly one `block_id`. Do not call `/api/ai/compose` for the page send path.

- [ ] **Step 4: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 8: Add Current-Page Send

**Files:**
- Modify: `app/frontend/app.js`
- Modify: `app/frontend/index.html`
- Modify: `app/frontend/styles.css`

- [ ] **Step 1: Add button**

Button label: `发送本页`.

Enabled when:

| Condition | Result |
|---|---|
| API key missing | disabled with inline message `请先填写 API Key` |
| current page has block mode | enabled, queues all current page blocks |
| current page has whole_page mode | enabled, calls page fallback endpoint |

- [ ] **Step 2: Implement page send behavior**

```js
function sendCurrentPage() {
  const page = getCurrentReaderPage();
  if (!page) return;
  if (page.mode === "whole_page") {
    enqueueWholePageExplanation(page.number);
    return;
  }
  page.blocks.forEach((block) => enqueueBlockExplanation(block.id));
}
```

- [ ] **Step 3: Render per-block progress**

For each block on the current page show one of:

| Status | UI |
|---|---|
| idle | `解释` button |
| pending | `排队中` |
| running | `生成中` |
| done | `已生成` |
| error | provider or audit error text |

- [ ] **Step 4: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 9: Move Explanations To The Side Of The Original Content

**Files:**
- Modify: `app/frontend/app.js`
- Modify: `app/frontend/styles.css`

- [ ] **Step 1: Remove bottom mega-list as primary UI**

The main explanation renderer filters by current page and sorts by block visual position. Existing historical results can stay in debug details, not below the whole preview.

- [ ] **Step 2: Render anchored side cards**

Each card title uses block title and a small source tag:

```text
第 1 页 · s1_b3
```

Each card shows:

| Field | Display |
|---|---|
| `short_explanation` | always visible |
| `key_points` | bullet list |
| `common_misunderstanding` | collapsed if empty |
| `review_questions` | collapsed if empty |
| `source_refs` | compact source chips |

- [ ] **Step 3: Sync click selection**

Clicking an overlay scrolls the right side card into view if it exists. Clicking a side card highlights the corresponding overlay.

- [ ] **Step 4: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 10: Reserve AI Guide Version Without Polluting Guide

**Files:**
- Modify: `app/frontend/app.js`
- Modify: `app/frontend/index.html`
- Modify: `app/frontend/styles.css`
- Modify: `app/backend/server.py`

- [ ] **Step 1: Disable AI guide action until file exists**

When `ai_guide_pdf_url` is missing, the top bar shows `AI 解释版` as disabled and does not create a broken link.

- [ ] **Step 2: Switch preview source when AI guide exists**

When `ai_guide_pdf_url` exists, clicking `AI 解释版` switches the reader PDF target to AI guide preview assets. If preview assets for AI guide do not exist, show a clear message that the AI guide file exists but preview images need generation.

- [ ] **Step 3: Keep `guide.pdf` unchanged**

No AI explanation writes into `guide.pdf`. All AI PDF work goes to separate `ai_guide.pdf`.

- [ ] **Step 4: Run frontend syntax check**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

## Task 11: Full Verification

**Files:**
- No new files; run commands and inspect outputs.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
python -m unittest app.tests.test_v5_guide_preview app.tests.test_v5_knowledge_blocks_dedupe app.tests.test_v5_ai_context app.tests.test_v5_server_reader_payload -v
```

Expected: PASS.

- [ ] **Step 2: Run existing regression tests**

Run:

```powershell
python -m unittest discover app\tests
```

Expected: PASS.

- [ ] **Step 3: Compile backend**

Run:

```powershell
python -m compileall app\backend
```

Expected: PASS.

- [ ] **Step 4: Check frontend syntax**

Run:

```powershell
node --check app\frontend\app.js
```

Expected: PASS.

- [ ] **Step 5: Restart 8765 and reconvert sample**

Run:

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
Start-Process -WindowStyle Hidden powershell -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-Command','Set-Location -LiteralPath "D:\学业\比赛\小鹏\赛道3"; python app\backend\server.py'
curl.exe -s -F "deck=@app/samples/test.pptx" http://127.0.0.1:8765/api/convert
```

Expected: response includes `guide_preview_manifest_url`, `knowledge_blocks_url`, and `guide_pdf_url`.

- [ ] **Step 6: Browser verification**

Use Browser on `http://127.0.0.1:8765`:

| Check | Expected |
|---|---|
| Top bar | only `Base PDF`、`Guide PDF`、`对比页`、`AI 解释版` |
| Preview | guide page image is visible |
| Overlay | blocks are clickable and selectable |
| Page send | queues one request per block |
| Side panel | generated explanations appear beside current page content |
| Console | no `items.forEach is not a function` or bbox rendering errors |

Do not call a real provider during automated verification unless the user explicitly provides a key for this run.

## Review Gate

Before marking complete, review these points:

| Check | Must be true |
|---|---|
| 比赛路线 | UI 仍服务 `guide.pdf` 学习版，不把项目变成普通聊天工具 |
| 成本控制 | 当前页发送仍是逐块请求，不是整页合并 prompt |
| 来源追踪 | 每条解释保留合法 `source_refs` |
| 安全 | API key 不进入 URL、localStorage、日志、缓存、报告文件 |
| 视觉 | 页面 overlay 不遮挡正文阅读；解释侧栏不压缩 PDF 预览到不可读 |
| 输出隔离 | `base.pdf`、`guide.pdf` 不被 AI 文本覆盖 |
