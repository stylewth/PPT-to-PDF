# 进度记录

## 2026-05-13 本轮恢复记录
| 类型 | 内容 |
|---|---|
| 上下文恢复 | 已读取 `lessons.md`、`task_plan.md`、`progress.md`、`findings.md`、`HANDOFF.md`；当前主线为 V3D 后续 `layout_decider.py` 与“标注可放置性”。 |
| 基线测试 | `python -m unittest discover -s app\tests` 中 17 个测试因 `app/workspace/test_runs` 无写权限报 `PermissionError`，业务断言尚未执行到。 |
| 比赛页面 | 官方 topic3 URL 可打开但静态抓取不到赛题正文；公开搜索只找到赛事启动新闻，未找到 topic3 细则全文。 |
| Git 忽略维护 | 新增项目级 `.gitignore`，更新 `app/.gitignore`，覆盖 Python 缓存、前端产物、运行输出、临时文件和本地配置。 |

## 2026-05-11
| 时间 | 进展 |
|---|---|
| 当前会话 | 创建规划文件，准备开发 `赛道3/demo` 静态交互 Demo |
| 当前会话 | 完成 `赛道3/demo/index.html`、`styles.css`、`app.js`、`README.md` |
| 当前会话 | 完成无头 Edge 截图验证，截图位于 `赛道3/demo/screenshot.png` |
| 当前会话 | 补充基础功能共识、代码开发路线、V1 最小真实功能和推荐目录结构 |
| 当前会话 | 用户要求直接做到 V2，开始按 TDD 开发真实 `.pptx` 解析与基础动画理解链路 |
| 当前会话 | Python `tempfile.TemporaryDirectory` 在当前 Windows 环境创建出权限异常目录，已改用 `workspace/test_runs` 普通目录；旧异常目录删除被系统拒绝，后续检查需避开 |
| 当前会话 | 完成 V2 后端：PPTX 解析、学习型讲义构建、HTML 渲染、PDF 渲染、转换编排、CLI、本地 Web 服务 |
| 当前会话 | 完成 V2 前端：上传 `.pptx`、查看状态、展示问题报告、预览/下载 HTML/PDF/JSON |
| 当前会话 | 生成样例 `赛道3/app/samples/course_animation_occlusion.pptx` 和端到端输出 `赛道3/app/workspace/outputs/sample` |
| 当前会话 | 本地服务已启动，健康检查 `http://127.0.0.1:8765/api/health` 返回 200 |
| 当前会话 | 用户指出 V2 过于文本扫描，确认路线改为“原生保真 PDF + 智能增补页” |
| 当前会话 | 已调研 LibreOffice、Unoserver、Collabora Online、python-pptx、Apache POI、PPspliT，并写入 `task_plan.md` / `findings.md` |
| 当前会话 | 用户补充动画页不能机械逐动画加页，已加入“页数预算”和“同页增强”规则 |
| 当前会话 | 用户确认允许 study.pdf 二次排版，并决定输出分为“动画导读基础版”和“AI 讲义解释版”；首版先做不依赖 AI 的基础版 |
| 当前会话 | 第 1 项产品定义确认；补充动画导读必须融入 PDF 页面本身 |
| 当前会话 | 第 2 项用户和使用场景确认 |
| 当前会话 | 第 3 项输入文件范围确认：首版只支持 `.pptx` |
| 当前会话 | 第 4 项输出文件类型确认：`base.pdf`、`guide.pdf`、`report.json`、`preview.html` |
| 当前会话 | 第 5 项输出模式确认：批注版暂不做，重点做标准版和动画导读版 |
| 当前会话 | 第 6 项动画融入策略确认：融合重排是核心攻关点，需要保持原意不变且排版协调易懂 |
| 当前会话 | 第 7 项同页增强和融合重排视觉规则确认 |
| 当前会话 | 第 8 项二次排版触发条件确认；拥挤判断被标记为算法关键 |
| 当前会话 | 第 9 项新增页规则确认 |
| 当前会话 | 第 10 项 AI 接入边界确认 |
| 当前会话 | 第 11 项技术架构确认，并补充最终需要小白开箱即用封装 |
| 当前会话 | 第 12 项不支持边界确认：首版简化，后续预留音视频/复杂动画/交互动画理解性还原 |
| 当前会话 | 第 13 项开发阶段和验收标准确认，并生成 `赛道3/design_technical_route.md` |
| 2026-05-12 | 生成 `赛道3/development_roadmap.md`，把 V3 代码开发路线拆成 V3A-V3F，并明确 V3A 需要 LibreOffice/Unoserver |
| 2026-05-12 | 读取文件时发现旧 `tmp_tests_plain` 下仍有拒绝访问目录，后续扫描和测试继续避开该遗留目录 |
| 2026-05-12 | 开始 V3A：新增 `native_converter.py`，实现 LibreOffice `soffice` 查找、headless 转 PDF、`base.pdf` 输出和明确错误 |
| 2026-05-12 | 改造 `converter.py` 输出 V3A 包：`base.pdf`、`report.json`、`preview.html`，`guide.pdf` 留到 V3C |
| 2026-05-12 | 改造 Web/CLI 字段：前端下载 `base.pdf`/报告/预览，CLI 支持 `--soffice-path` |
| 2026-05-12 | 修复隐藏后台服务 stdout 不可用导致退出的问题，服务已在 `http://127.0.0.1:8765` 启动 |
| 2026-05-12 | V3A 验证：9 个单元测试通过，JS 语法检查通过，py_compile 通过；真实 PDF 路径因本机缺 LibreOffice 明确失败 |
| 2026-05-12 | 用户安装 LibreOffice 后，使用真实 PPTX 样例跑通 CLI 原生转换，生成 `base.pdf` 30404 字节，PDF 头为 `%PDF-1.7` |
| 2026-05-12 | 跑通 Web 上传接口：返回 200，生成 `base.pdf`、`report.json`、`preview.html`，服务健康检查仍为 200 |
| 2026-05-12 | 新增 `赛道3/app/samples/native_conversion_smoke.pptx` 作为 V3A 原生转换验收样例 |
| 2026-05-12 | 完成 V3B：新增 `slide_analyzer.py`，输出 `analysis.json`，包含页面尺寸、动画步骤、拥挤度、复杂度和策略提示 |
| 2026-05-12 | `converter.py` 报告版本升级为 `v3b`，`report.json` 增加摘要并引用 `analysis.json` |
| 2026-05-12 | Web 返回新增 `analysis_url`，前端下载区新增“分析”入口 |
| 2026-05-12 | 完成 V3C：新增 `augment_planner.py` 和 `pdf_augmenter.py`，输出 `augment_plan.json` 和 `guide.pdf` |
| 2026-05-12 | 新增 `samples/animation_guide_smoke.pptx`，真实验证 `guide.pdf` 生成 2 页，包含 1 页导读页 |
| 2026-05-12 | 修复 PPTX 导读包生成问题：不再用 ElementTree 重写关键 XML 命名空间，改为最小字符串插入 |
| 2026-05-12 | 性能排查发现动画解析不到 0.01 秒，主要耗时是两次 LibreOffice 转换各约 6.7 秒；前端进度文案已改为真实阶段 |
| 2026-05-12 | 修复 guide 动画导读页排版：新增结构化版式测试，导读页改为标题栏、步骤卡片和底部提示区；真实生成 `guide.pdf` 为 2 页、50204 字节 |
| 2026-05-12 | 完成 V3D 同页增强小步：`augment_plan.json` 新增 `inline_markers`，`guide_deck.pptx` 原页写入 `Guide Highlight` 和 `Guide Inline Marker`，真实样例生成 `guide.pdf` 为 50986 字节 |
| 2026-05-12 | 本地服务已重启到 V3D，`http://127.0.0.1:8765/api/health` 返回 200；沙箱内启动后台进程会被回收，持久服务改用沙箱外 `pythonw` 启动 |
| 2026-05-12 | Web 上传接口用 `animation_guide_smoke.pptx` 验证通过，返回 200，job `ab350b649f664ef096663cca8165d802` 生成 `base.pdf` 30404 字节和 `guide.pdf` 50986 字节 |
| 2026-05-13 | 完成 V3D 页数预算修正：低拥挤动画页不再追加导读页，`animation_guide_smoke.pptx` 的 `page_budget=1`、`guide_pages=0`，真实 `guide.pdf` 为 31260 字节 |
| 2026-05-13 | Web 上传接口复验通过，job `f307f643cbeb4b19a4a642675aff525f` 返回 200，生成 `base.pdf` 30404 字节和 `guide.pdf` 31260 字节 |
| 2026-05-13 | 检查用户提供的 `赛道3/guide测试.pdf`：源 `Review+chapter24-27.pptx` 为 42 页，输出 PDF 为 75 页；绿色框遮挡内容、导读页文本溢出，确认为 V3D 当前必须修的问题 |
| 2026-05-13 | 生成 `赛道3/v3d_repair_route.md`，将修复路线定为：止损热修、有用标注、导读页重做、拥挤判断重构、Review 样例验收 |
| 2026-05-13 | 完成 V3D 止损热修：新增 Review 样例回归测试，复杂页进入 `report_only`，单页锚点最多 3 个，默认移除大面积绿色框 |
| 2026-05-13 | Review 样例真实转换通过：`base.pdf` 42 页，`guide.pdf` 42 页，`augment_plan.json` 中 `guide_page_count=0`、`report_only_count=33`、`max_markers=3` |
| 2026-05-13 | 推进 V3D 有用标注：`inline_markers` 增加 `role/hint`，动画对象若按 z-order 覆盖已有对象会标为 `covered_content`，原生页编号旁加入短提示条 |

## 待记录
| 类型 | 内容 |
|---|---|
| 修改文件 | `task_plan.md`、`findings.md`、`progress.md`、`赛道3/demo/*`、`赛道3/app/*` |
| 验证结果 | V2 单元测试 6 个通过；CLI 生成 JSON/HTML/PDF；Web 健康检查和上传转换通过 |
| 遇到的问题 | `tempfile` 权限异常、沙箱内 Edge PDF 失败、`Start-Process` 环境冲突；均已改路线处理 |
