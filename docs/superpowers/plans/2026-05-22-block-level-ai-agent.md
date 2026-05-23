# Block-Level AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a new branch or worktree unless the user explicitly approves it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an optional block-level AI Agent that lets users click or select specific knowledge blocks in the Web UI, generate evidence-based explanations only for selected blocks, and merge approved explanations into a separate `ai_guide.pdf` in Phase 5.

**Architecture:** Keep the existing `base.pdf` and `guide.pdf` pipeline unchanged. Add a new block index layer from existing PPTX objects, analysis, reflow plan, media manifest, and render coordinates; the AI layer only consumes selected block evidence and never decides core object reflow. Web holds the API key only for the current local request, backend proxies model calls without writing the key, and outputs audited AI artifacts.

**Tech Stack:** Python stdlib HTTP server, existing PPTX/OOXML analysis modules, PyMuPDF render coordinates, frontend vanilla JS/CSS, provider-agnostic OpenAI-compatible HTTP calls.

---

## Core Principle

AI 不做整页泛讲解，也不直接改排版。主线是：

1. 规则生成知识块。
2. 用户在 Web 上点选知识块。
3. AI 只解释被选中的块。
4. 每条解释都带页码、块 ID、对象 ID、文本/备注/动画来源。
5. 用户确认后，才生成单独的 `ai_guide.pdf`。

## Output Contract

| 文件 | 作用 |
|---|---|
| `knowledge_blocks.json` | 每页知识块索引，包含类型、标题、bbox、来源对象、可点击区域 |
| `ai_explanations.json` | 单块或多块解释结果，全部带来源 |
| `ai_audit.json` | AI 输出校验结果、缺证据内容、token 用量、缓存命中 |
| `selected_blocks.json` | 用户选择要融入 PDF 的块和解释 |
| `ai_guide.pdf` | 可选 AI 融合版 PDF，不覆盖 `guide.pdf` |

## New Files

| 路径 | 职责 |
|---|---|
| `app/backend/knowledge_blocks.py` | 从 `presentation + analysis + augment_plan + media_manifest` 生成块 |
| `app/backend/ai_context.py` | 为选中块裁剪最小上下文，控制 token |
| `app/backend/ai_provider.py` | OpenAI-compatible 调用，API key 只来自请求，不落盘 |
| `app/backend/ai_explainer.py` | 组装 prompt、解析结构化 JSON、写缓存 |
| `app/backend/ai_audit.py` | 校验来源、拒绝无来源结论、统计 token 和风险 |
| `app/backend/ai_pdf_exporter.py` | 把确认后的解释生成 `ai_guide.pdf` |
| `app/tests/test_v4_knowledge_blocks.py` | 块划分测试 |
| `app/tests/test_v4_ai_context.py` | 上下文裁剪和 token 控制测试 |
| `app/tests/test_v4_ai_security.py` | API key 不落盘、不进缓存、不进日志测试 |
| `app/tests/test_v4_ai_explainer.py` | 模型调用、缓存、结构化输出测试 |
| `app/tests/test_v4_ai_pdf_exporter.py` | 选中解释融入 PDF 的布局和门禁测试 |

## Modified Files

| 路径 | 改动 |
|---|---|
| `app/backend/converter.py` | 转换后生成 `knowledge_blocks.json`，报告中暴露路径 |
| `app/backend/server.py` | 新增 AI 解释、组合解释、导出 AI PDF 接口 |
| `app/frontend/index.html` | 增加 API key 输入、模型配置、块级交互区 |
| `app/frontend/app.js` | 渲染知识块、选中块、调用 AI、缓存展示 |
| `app/frontend/styles.css` | 增加块框选、解释面板、选择篮样式 |
| `app/backend/compare_builder.py` | 比赛展示页增加 AI Agent 入口和 token 节省指标 |
| `app/backend/metrics_builder.py` | 增加块级解释节省估算 |
| `app/README.md`、`使用说明.md` | 补充 AI 可选能力、API key 安全边界 |

## Phase 1: Knowledge Block Index

- [x] **Step 1: Define block schema**

`knowledge_blocks.json` 顶层结构：

```json
{
  "kind": "knowledge_blocks",
  "version": "v4a",
  "source": {"name": "deck.pptx", "slide_count": 10},
  "slides": [
    {
      "number": 1,
      "title": "第一页标题",
      "blocks": [
        {
          "id": "s1_b1",
          "type": "formula_group",
          "title": "电容公式",
          "summary": "由公式和相邻说明组成",
          "source_bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
          "display_bbox": {"x": 0, "y": 0, "w": 1, "h": 1},
          "object_ids": ["shape7", "shape8"],
          "texts": ["C = q / U"],
          "animation_steps": [2],
          "source_refs": [
            {"kind": "slide_text", "slide": 1, "object_id": "shape7"}
          ],
          "token_estimate": 120
        }
      ]
    }
  ]
}
```

- [x] **Step 2: Write failing tests for block generation**

| 场景 | 期望 |
|---|---|
| 标题 + 三段正文 | 生成 3 个正文知识块，不把标题当解释块 |
| 正文 + 邻近公式 | 生成 `formula_group`，公式和说明绑定 |
| GIF 媒体 | 生成 `media_timeline`，绑定 `media_manifest` |
| 电路图/流程图碎片 | 生成一个 `diagram_group`，不拆成大量小块 |
| 动画遮挡关系 | 生成 `animation_flow`，包含覆盖前后对象 |

Run:

```powershell
python -m unittest app.tests.test_v4_knowledge_blocks
```

Expected: 初始失败，因为 `knowledge_blocks.py` 不存在。

- [x] **Step 3: Implement conservative block grouping**

| 优先级 | 规则 |
|---|---|
| 1 | 动画覆盖关系形成 `animation_flow` |
| 2 | 媒体对象形成 `media_timeline` |
| 3 | 公式 + 最近说明文本形成 `formula_group` |
| 4 | 大图/图表 + 标题/说明形成 `diagram_group` |
| 5 | 普通正文按垂直邻近和项目符号形成 `text_concept` |
| 6 | 大量小图元且缺少长文本锚点时合并为 `diagram_group` |

- [x] **Step 4: Integrate converter output**

`convert_pptx` 完成 `analysis`、`plan`、`media_manifest` 后写出 `knowledge_blocks.json`，并在 `report.json.outputs` 和 Web 响应中加入下载 URL。

## Phase 2: Web Block Interaction

- [x] **Step 1: Render block list first**

MVP 不强依赖 PDF 坐标点击，先在 Web 右侧按页展示块列表。

| UI 元素 | 行为 |
|---|---|
| 页码 tabs | 切换当前页 |
| 块列表 | 显示标题、类型、token 估算 |
| 复选框 | 加入选择篮 |
| 解释按钮 | 单块解释 |
| 组合讲解按钮 | 多块合并解释 |

- [ ] **Step 2: Add optional visual overlay**

后续增强用 `display_bbox` 映射到页面截图，支持点击页面区域选择块。截图只用于 Web 交互，不影响 PDF 主链路。

- [x] **Step 3: Add API key panel**

| 字段 | 规则 |
|---|---|
| API Key | `password` 输入框，只保存在浏览器内存变量 |
| Base URL | 可选，默认使用 OpenAI-compatible 地址 |
| Model | 可选，默认由配置给出 |
| Clear | 清空内存中的 key |

禁止写入 `localStorage`、URL、日志、JSON 输出。

## Phase 3: AI Explanation Agent

- [x] **Step 1: Context builder**

`build_ai_context(blocks, mode)` 只放入选中块文本、同页标题、少量相邻块标题、相关备注摘录、相关动画步骤、相关媒体 manifest。默认单块上下文控制在 1500 中文字符内。

- [x] **Step 2: Prompt output schema**

AI 必须返回 JSON：

```json
{
  "block_id": "s1_b1",
  "short_explanation": "一句话解释",
  "detail": "较详细解释",
  "key_points": ["要点1", "要点2"],
  "common_misunderstanding": ["易错点"],
  "review_questions": ["问题1"],
  "source_refs": [
    {"kind": "slide_text", "slide": 1, "object_id": "shape7"}
  ],
  "missing_context": [],
  "confidence": "medium"
}
```

- [x] **Step 3: Provider call**

| 接口 | 功能 |
|---|---|
| `POST /api/ai/explain` | 单块解释 |
| `POST /api/ai/compose` | 多块组合解释 |
| `POST /api/ai/export-guide` | 生成 `ai_guide.pdf` |

API key 通过请求 header 或 body 传给本地后端；后端不落盘，不写日志，不返回给前端。

- [x] **Step 4: Cache**

缓存 key：

```text
sha256(model + mode + block_content_hash + prompt_version)
```

缓存值只保存解释结果和用量，不保存 API key。

## Phase 4: Audit And Cost Control

- [x] **Step 1: Source audit**

| 问题 | 处理 |
|---|---|
| 没有 `source_refs` | 标记失败，不展示为可融入 PDF |
| 引用了不存在的对象 ID | 标记失败 |
| 生成了来源之外的事实性扩写 | 放入 `missing_context` 或提示需补充 |
| JSON 不合法 | 直接报错，不静默修复 |

- [x] **Step 2: Token metrics**

`metrics.json` 增加：

| 字段 | 含义 |
|---|---|
| `ai_block_count` | 可解释块数量 |
| `ai_selected_block_count` | 用户选择解释数量 |
| `estimated_full_slide_tokens` | 整页解释估算 token |
| `estimated_block_tokens` | 块级解释估算 token |
| `estimated_token_saved_ratio` | token 节省比例 |

## Phase 5: AI Guide PDF Export

- [ ] **Step 1: Keep base outputs stable**

不覆盖 `base.pdf` 和 `guide.pdf`，新增 `ai_guide.pdf`。

- [ ] **Step 2: Layout strategy**

| 内容长度 | 放置方式 |
|---|---|
| 1-3 句短解释 | 原页空白区旁注 |
| 多块组合解释 | 页尾或右侧解释区 |
| 长讲解/题目 | 紧邻原页后插入 AI 讲解页 |
| 空间不足 | 不硬塞，转为讲解页 |

- [ ] **Step 3: Visual gate**

导出后必须跑：

```powershell
python -m unittest app.tests.test_v4_ai_pdf_exporter
python app\tests\render_sample_reflow_check.py
```

验收：原页内容不被 AI 文本遮挡；每段解释有块编号或页码；截图通过渲染检查；`guide.pdf` 不变，新增 `ai_guide.pdf`。

## Phase 6: Competition Packaging

- [ ] **Step 1: Demo flow**

1. 上传 PPTX。
2. 生成 `base.pdf` 和 `guide.pdf`。
3. 打开 Web 块列表。
4. 点选一个公式块生成解释。
5. 多选公式 + 图生成组合讲解。
6. 导出 `ai_guide.pdf`。
7. 展示 token 节省和可追溯来源。

- [ ] **Step 2: Docs**

| 内容 | 写法 |
|---|---|
| API key | 只在本地当前请求使用，不保存 |
| AI 能力 | 解释选中块，不保证补全外部知识 |
| 无 key | 基础版仍完整可用，AI 按钮不可用 |
| 输出 | `ai_guide.pdf` 是可选增强，不替代 `guide.pdf` |

## Recommended MVP

| 顺序 | 任务 | 原因 |
|---|---|---|
| 1 | `knowledge_blocks.json` | 没有块，后面都是空中楼阁 |
| 2 | Web 块列表 + 选择篮 | 先证明交互闭环 |
| 3 | 单块 AI 解释 + key 不落盘 | 先控制成本和安全 |
| 4 | 多块组合讲解 + 缓存 | 形成比赛亮点 |

`ai_guide.pdf` 放第二轮，等 Web 交互和解释质量稳定后再做。

## Risks

| 风险 | 拦截 |
|---|---|
| 块划分过碎 | 小图元合并门禁，复用现有图元碎片化经验 |
| AI 编造 | 来源校验，不合格不允许融入 PDF |
| token 失控 | 默认只传选中块，上下文硬上限 |
| key 泄露 | 不写文件、不进日志、不进缓存、不进 URL |
| PDF 被挤坏 | 单独 `ai_guide.pdf`，渲染截图门禁 |
