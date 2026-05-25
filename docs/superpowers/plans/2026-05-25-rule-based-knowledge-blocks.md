# Rule-Based Knowledge Blocks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a new branch or worktree unless the user explicitly approves it. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Web knowledge blocks less fragmented, reliably selectable, retryable after AI errors, and able to render AI-returned LaTeX in the browser.

**Architecture:** Keep AI out of block grouping. `knowledge_blocks.py` uses deterministic rules: stricter title detection, title-to-content attachment, dense diagram/formula grouping before formula splitting, and fallback whole-page only when grouping is unreliable. The frontend keeps the right-side list as the reliable selector, adds colored overlays and overlap-hit candidate selection, retries failed block requests, and asks MathJax to typeset LaTeX safely from text nodes.

**Tech Stack:** Python stdlib/unittest, existing PPTX analysis schema, vanilla JS/CSS, MathJax browser runtime.

---

## File Map

| 文件 | 职责 |
|---|---|
| `app/backend/knowledge_blocks.py` | 规则分组、标题识别、密集图示/公式整组聚合 |
| `app/tests/test_v4_knowledge_blocks.py` | 锁住第 3 页空块、标题绑定、图示/公式不碎裂 |
| `app/frontend/app.js` | 彩色 overlay、重叠候选选择、AI 失败重试、LaTeX typeset |
| `app/frontend/styles.css` | 彩色框、候选浮层、错误重试按钮、公式样式 |
| `app/frontend/index.html` | 加载 MathJax 配置和脚本 |
| `app/tests/test_v5_frontend_reader.py` | 锁住前端交互与 LaTeX typeset 行为 |
| `task_plan.md` / `progress.md` / `findings.md` | 本轮规划、进度和根因记录 |
| `lessons.md` | 记录用户指出的分块和交互问题，避免回归 |

## Tasks

### Task 1: 后端规则分组

- [x] 写失败测试：唯一大文本框不能被当标题跳过。
- [x] 写失败测试：标题文本要并入首个内容块，不单独成为块。
- [x] 写失败测试：电路图/公式/短标签密集页合并为一个 `diagram_group`。
- [x] 实现更严格的标题判断：必须顶部、短高度、非长正文。
- [x] 在公式拆分前加入密集图示整组规则。
- [x] 把真实标题对象并入首个内容块。
- [x] 跑 `python -m unittest app.tests.test_v4_knowledge_blocks app.tests.test_v5_knowledge_blocks_dedupe`。

### Task 2: 前端选择与失败重试

- [x] 写失败测试：重叠点击返回候选按钮，而不是只能点最上层。
- [x] 写失败测试：块解释失败后解释卡片保留重试按钮。
- [x] 实现块色板，overlay 和右侧列表颜色一致。
- [x] 实现重叠候选浮层，候选按钮可切换对应块。
- [x] 实现错误卡片重试按钮，不清空当前选择。
- [x] 跑 `python -m unittest app.tests.test_v5_frontend_reader`。

### Task 3: LaTeX 网页可视化

- [x] 写失败测试：`appendExplanationContent` 后调用 MathJax typeset。
- [x] 在 `index.html` 加 MathJax 配置和脚本。
- [x] `appendExplanationContent` 仍用 `textContent` 写入，最后调用 `typesetMath(parent)`，避免把 AI 文本当 HTML 注入。
- [x] 跑 `node --check app/frontend/app.js`。

### Task 4: 真实样例验收

- [x] 跑后端和前端定向测试。
- [x] 跑 `python -m compileall app\backend`。
- [x] 用 `Review+chapter24-27.pptx` 重新转换，检查第 3、12、13 页 `knowledge_blocks.json`。
- [x] 如影响 Web 服务，重启 8765。
- [x] 渲染最新 `guide.pdf` 截图检查，不能只看几何指标。
