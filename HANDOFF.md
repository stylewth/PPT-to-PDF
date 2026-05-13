# Slide2Study / PPT-to-PDF 项目交接

## 当前状态

| 项 | 状态 |
|---|---|
| 项目目录 | `赛道3` |
| Git 远程 | `https://github.com/stylewth/PPT-to-PDF.git` |
| 当前分支 | `main` |
| 最近提交 | `e42e6b4 Initial project snapshot` |
| 当前阶段 | V3D：原生 PPT 转 PDF + 动画导读增强 |
| 产品目标 | 把课程/培训 PPTX 转成适合阅读、批注、复习的 PDF |
| 当前主输出 | `base.pdf`、`guide.pdf`、`analysis.json`、`augment_plan.json`、`report.json`、`preview.html` |

当前路线已经从“扫描文字后重画 PPT”修正为“LibreOffice 原生保真转 PDF + 只在必要位置做动画导读增强”。`base.pdf` 永远作为原生对照保留；`guide.pdf` 在原生页面上做轻量提示，复杂页先写报告，不硬生成低价值导读页。

## 已完成内容

| 阶段 | 完成内容 |
|---|---|
| V0 静态 Demo | `赛道3/demo` 中有早期产品形态展示页面 |
| V2 真实解析链路 | 可解析 `.pptx` ZIP/OOXML，读取 slide、对象、备注、基础动画和遮挡风险 |
| V3A 原生转换 | 使用 LibreOffice `soffice` 生成 `base.pdf` |
| V3B 页面分析 | 输出 `analysis.json`，包含页面尺寸、动画步骤、拥挤度、复杂度、遮挡指标、策略提示 |
| V3C 动画导读 | 输出 `augment_plan.json` 和 `guide.pdf`，能追加导读页 |
| V3D 止损修复 | 复杂课件不再生成大量导读页；大面积绿色调试框已移除；单页最多 3 个锚点 |
| V3D 有用标注 | `inline_markers` 已有 `role/hint`，支持 `first_change`、`covered_content`、`key_result`；页内提示为“先出现 / 遮挡变化 / 关键结果”等短提示 |
| Web 工具 | `http://127.0.0.1:8765` 可上传 PPTX 并下载输出 |
| 回归测试 | 当前 `python -m unittest discover -s '赛道3/app/tests'` 为 21 个测试通过 |

## 运行命令

### 启动 Web

```powershell
python .\赛道3\app\backend\server.py
```

打开：

```text
http://127.0.0.1:8765
```

健康检查：

```powershell
Invoke-WebRequest -Uri 'http://127.0.0.1:8765/api/health' -UseBasicParsing
```

### 命令行转换

使用默认 LibreOffice 查找：

```powershell
python .\赛道3\app\backend\cli.py .\赛道3\app\samples\native_conversion_smoke.pptx .\赛道3\app\workspace\outputs\manual
```

显式指定 LibreOffice：

```powershell
python .\赛道3\app\backend\cli.py .\赛道3\app\samples\animation_guide_smoke.pptx .\赛道3\app\workspace\outputs\manual --soffice-path "C:\Program Files\LibreOffice\program\soffice.exe"
```

只生成分析、报告和预览，不生成 PDF：

```powershell
python .\赛道3\app\backend\cli.py .\path\to\deck.pptx .\赛道3\app\workspace\outputs\manual --no-pdf
```

### 测试与检查

```powershell
python -m unittest discover -s '赛道3/app/tests'
python -m py_compile '赛道3/app/backend/augment_planner.py' '赛道3/app/backend/pdf_augmenter.py' '赛道3/app/backend/slide_analyzer.py' '赛道3/app/backend/converter.py' '赛道3/app/backend/server.py'
node --check '赛道3/app/frontend/app.js'
```

### Git

```powershell
git status -sb
git log --oneline -3
git push
```

## 重要文件结构

```text
赛道3/
  HANDOFF.md                    # 当前交接文档
  design_technical_route.md      # 技术路线与产品决策
  development_roadmap.md         # V3A-V3F 开发路线
  v3d_repair_route.md            # 复杂课件可读性修复路线
  demo/                          # 早期静态演示页
  app/
    README.md                    # 运行说明和能力边界
    .gitignore                   # 忽略 workspace / 临时测试目录
    backend/
      server.py                  # 本地 Web 服务
      cli.py                     # 命令行入口
      converter.py               # 转换编排
      native_converter.py        # LibreOffice 原生 PDF 转换
      pptx_parser.py             # PPTX OOXML 解析
      slide_analyzer.py          # 页面分析、拥挤度、遮挡识别
      augment_planner.py         # 增强计划、页数预算、marker 语义
      pdf_augmenter.py           # 写入增强 PPTX 并转成 guide.pdf
      html_renderer.py           # preview.html
      study_builder.py           # 早期 V2 学习文档结构
      pdf_renderer.py            # 早期 HTML/PDF 渲染
    frontend/
      index.html
      styles.css
      app.js
    samples/
      native_conversion_smoke.pptx
      animation_guide_smoke.pptx
      course_animation_occlusion.pptx
      Review+chapter24-27.pptx
    tests/
      test_v2_pipeline.py
      test_v3_native_converter.py
      test_v3_slide_analyzer.py
      test_v3_pdf_augmenter.py
    workspace/                   # 运行输出，已忽略，不提交
```

## 样例文件用途

| 文件 | 用途 |
|---|---|
| `native_conversion_smoke.pptx` | 原生转换最小验收样例 |
| `animation_guide_smoke.pptx` | 简单动画页，验证低拥挤页保持 1 页并加入页内提示 |
| `course_animation_occlusion.pptx` | 早期极简解析/遮挡单测样例 |
| `Review+chapter24-27.pptx` | 真实复杂课件样例，用于验证复杂页预算、`report_only`、不生成无意义导读页 |

## 注意事项

| 注意项 | 说明 |
|---|---|
| LibreOffice 依赖 | 真实 PDF 转换依赖本机 `soffice`，当前常用路径是 `C:\Program Files\LibreOffice\program\soffice.exe` |
| 速度瓶颈 | 动画解析很快，主要耗时在 LibreOffice 转 PDF；一次 `base.pdf` 和一次 `guide.pdf` 转换可能各需数秒 |
| 输出目录 | `赛道3/app/workspace/` 已忽略，里面是上传文件、输出 PDF、日志、临时截图，不应提交 |
| 复杂页策略 | 当前宁可写入 `report_only`，也不要硬生成排版混乱的导读页 |
| 标注原则 | 单页最多 3 个锚点；不能恢复大面积绿色框；提示必须少打扰、语义明确 |
| 编码 | 新文件保持 UTF-8，无 BOM |
| 沙箱问题 | `tmp_tests_plain` 里曾有拒绝访问目录，扫描全项目时避免直接遍历运行输出/临时目录 |
| 服务启动 | Codex 沙箱内后台进程可能被回收，长期预览可用 `pythonw` 启动服务 |
| Git 状态 | 当前仓库已推送到 GitHub；新增文件需要另行 `git add/commit/push` |

## 当前能力边界

| 支持 | 暂不支持 |
|---|---|
| `.pptx` | `.ppt`、Keynote、加密文件 |
| 文本、形状、图片等基础对象读取 | 完整 Office 特效还原 |
| notesSlide 备注读取 | 宏、交互按钮、复杂触发器 |
| `fade`、`wipe`、`appear` 基础动画 | 路径动画、音视频、复杂点击触发 |
| 基于 bbox 和 z-order 的遮挡检测 | 语义级完美理解所有遮挡意图 |
| 原生 `base.pdf` | 不安装 LibreOffice 时的真实 PDF 输出 |
| 基础动画导读 `guide.pdf` | 完整融合重排、AI 讲义解释 |

## 后续任务

| 顺序 | 任务 | 目标 |
|---|---|---|
| 1 | 抽出 `layout_decider.py` | 把 `keep_native` / `native_enhance` / `report_only` / `expand_after_native` 的策略判断从 `augment_planner.py` 拆出，便于解释和测试 |
| 2 | 标注可放置性 | 计算上下左右空白区，判断提示条能不能放；没空间就不硬塞 |
| 3 | 导读页重做 | 只给必要页加导读页；按语义组摘要，不逐动画流水账；防止文本溢出 |
| 4 | Review 样例视觉验收 | 用 `Review+chapter24-27.pptx` 持续验证页数、标注遮挡、报告质量 |
| 5 | 小白开箱即用封装 | 增加 LibreOffice 检测、路径配置提示、启动脚本或简易安装包 |
| 6 | AI 解释版预留 | 后续独立接入 AI API，生成每页内容解释和动画讲解逻辑；基础版不依赖 AI |
| 7 | 更多样例集 | 后续再设计少量高质量 PPT 测试样例，但不要为了样例扩大生产逻辑的标注数量 |

## 推荐继续方式

下一步优先做 `layout_decider.py` 和“标注可放置性”。这是解决重排难点的入口：先让系统知道哪里能放提示、哪里不能放，再谈融合重排和导读页重做。
