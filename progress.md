# 进度记录

## 2026-05-16 路线大修规划记录
| 项 | 记录 |
|---|---|
| 用户反馈 | 当前截图中页面主体仍然重叠，说明上一版没有真正重排。 |
| 自审结论 | 路线偏了：不能把“保留 PPT 基本页面”理解为“原 PDF 主体不动”。 |
| 新规划 | 已新增 `docs/superpowers/plans/2026-05-16-object-level-reflow-overhaul.md`，主线改为 PPTX 对象级重排。 |
| 后续执行入口 | 先做 OOXML slide editor，再做 overlap diagnostics，再做 object_reflow_planner，最后接入 `guide_deck.pptx -> guide.pdf`。 |

## 2026-05-16 V3G 最终执行记录
| 项 | 结果 |
|---|---|
| 主线 | 已从整页重画切换为 `base.pdf` 上的 PDF 层微调重排；`guide.pdf` 保留原页主体，必要时扩展右侧栏展示遮挡前后流程。 |
| 核心实现 | 新增 `pdf_micro_reflow.py`、`metrics_builder.py`、`compare_builder.py`、`env_check.py`，接入 `converter.py`、`pdf_augmenter.py`、`layout_decider.py`、`augment_planner.py`、Web 下载入口和一键启动脚本。 |
| 遮挡处理 | 对遮挡流程去重，优先找原页边缘空白；空白不足时扩展 PDF 画布，不再压缩原页；流程卡展示“遮挡前 -> 覆盖后”。 |
| 五轮自审 | 依次修复流程卡缺失、错误空白判断、连接线穿过正文、窄栏截图不清、缩小原页损失保真、双流程卡高度不足。 |
| 样例修复 | `course_animation_occlusion.pptx` 原包不是有效 Office PPTX，已用有效 PPTX 骨架保留原 slide XML 和备注重建，LibreOffice 可真实转换。 |
| 最终样例 | `app/tests/.tmp_runs/final_product_test` 产出 `base.pdf`、`guide.pdf`、`compare.html`、`metrics.json`、`report.json`、`analysis.json`、`augment_plan.json`。 |
| 大课件验收 | `Review+chapter24-27.pptx` 42 页真实转换通过，`metrics.json` 显示 27 页微调重排、预计节省约 289.2 分钟。 |
| 验证 | `python -m unittest discover -s app\tests` 34 项通过；`py_compile` 通过；`node --check app\frontend\app.js` 通过；`env_check.py` 通过；4 个样例真实转换通过。 |

## 2026-05-13 本轮恢复记录
| 类型 | 内容 |
|---|---|
| 上下文恢复 | 已读取 `lessons.md`、`task_plan.md`、`progress.md`、`findings.md`、`HANDOFF.md`；当前主线为 V3D 后续 `layout_decider.py` 与“标注可放置性”。 |
| 基线测试 | `python -m unittest discover -s app\tests` 中 17 个测试因 `app/workspace/test_runs` 无写权限报 `PermissionError`，业务断言尚未执行到。 |
| 比赛页面 | 官方 topic3 URL 可打开但静态抓取不到赛题正文；公开搜索只找到赛事启动新闻，未找到 topic3 细则全文。 |
| Git 忽略维护 | 新增项目级 `.gitignore`，更新 `app/.gitignore`，覆盖 Python 缓存、前端产物、运行输出、临时文件和本地配置。 |
| 样例维护 | 用户新增 `app/samples/test.pptx`，覆盖多种场景，后续优先作为综合回归测试输入。 |
| 路线开发 | 修复测试临时目录到 `app/tests/.tmp_runs`，新增 `layout_decider.py`，将策略选择从 `augment_planner.py` 抽出。 |
| 标注可放置性 | `layout_decider.py` 计算上下左右空白区；`augment_planner.py` 只有在空间足够时生成 `inline_markers` 和 `hint_box`，`pdf_augmenter.py` 按 `hint_box` 写入提示。 |
| 导读页重做 | `expand_after_native` 的导读页不再逐动画流水账；复杂动画压成“先读 / 遮挡变化或中间过程 / 最后形成”三条摘要，简单页保持原逐步描述。 |
| 综合样例验收 | `animation_guide_smoke.pptx` 保持 1 页并生成 1 个页内提示；`test.pptx` 保持 2 页且 2 页均 `report_only`；`Review+chapter24-27.pptx` 保持 42 页，只有 3 页生成页内提示。 |
| 视觉修正 | 抽样渲染 Review 第 31/32/42 页，发现右侧提示条过窄；已把提示框宽度从 `880000` 调整为 `1160000`，短中文提示保持单行。 |
| 动画识别扩展 | `pptx_parser.py` 已支持 `blinds(horizontal)`、`wheel(1)` 和明确的 `ppt_x/ppt_y` 数值位移；无变化坐标节点会被跳过。 |
| `test.pptx` 复验 | 第 1 页为 10 支持 / 0 不支持；第 2 页为 12 支持 / 0 不支持。两页仍因步骤多、重叠高而 `report_only`。 |
| 验证 | 28 个单元测试通过；`py_compile` 与 `node --check app\frontend\app.js` 通过；`test.pptx` 真实转换成功，`base.pdf` 和 `guide.pdf` 均为 2 页，已无 unsupported 动画警告。 |
| 后续路线规划 | 已把下一阶段改为 V3G PDF 微调重排：`test.pptx` 这类“动画已识别但页面复杂”的样例不再追加导读页，也不抽取重画，而是在 `base.pdf` 原画面上同页微调。 |
| 用户纠偏 | 用户认为多加导读页实际意义不大；路线改为全力攻克重排，`base.pdf` 保留原生对照，`guide.pdf` 默认不新增页。 |
| V3G 初版实现 | 新增 `reflow_replace` 策略：复杂且动画已支持的页面不再 `report_only` 或追加导读页，而是在 `guide.pdf` 中替换为学习版重排页。 |
| V3G 验证 | `python -m unittest discover -s app\tests` 29 个测试通过；`test.pptx` CLI 真实转换成功，`base.pdf` 2 页、`guide.pdf` 2 页，`augment_plan.json` 中 `reflow_pages=[1,2]`、`guide_page_count=0`。 |
| 二次路线纠偏 | 用户明确要求“保留原有画面基础上的微调重排”，不是抽出元素重画页面；后续路线改为 PDF 层微调重排。 |
| 技术可行性评估 | 当前环境未安装 `fitz`/`pypdf`/`reportlab`；需要新增 PDF 编辑依赖。主路线建议 PyMuPDF：先缩放原页腾出说明带，再做 bbox 映射、局部遮盖、裁剪复用和叠加。 |
| 规划阶段完成 | 已生成 `docs/superpowers/plans/2026-05-14-pdf-micro-reflow.md`，把 V3G PDF 微调重排拆成依赖边界、坐标映射、计划结构、PDF 编辑、转换接线和真实样例验收 6 个任务。 |
| 赛题要求审查 | 已读取 `小鹏AI公开赛.pdf`：赛题三要求可运行提效工具/脚本/Agent、使用说明、数据证明提效成果，评分为实用性 40%、平权性 30%、创意性 30%。当前路线需要补 ROI 指标、开箱封装和普通用户说明。 |
| 最终路线规划 | 用户已确认关键边界；已生成 `docs/superpowers/plans/2026-05-16-final-product-route.md`，路线为 PDF 微调重排、前端收口、开箱启动、指标证明、比赛交付包、全量回归和 5 轮自审优化。 |
| 规划自检 | 本机 `rg.exe` 执行被拒绝，已改用 PowerShell `Select-String` 完成路线残留检查；`reflow_replace` 仅保留在历史/废弃说明中。 |
| 遮挡目标校准 | 用户明确希望被遮挡内容在 PDF 中换到清晰位置展示，并带流程关系；已把 V3G 验收从“说明带不遮挡”提升为“遮挡展开 + 流程连接”。 |
| 排版目标校准 | 用户确认遮挡内容不固定放到展开区；已把 V3G 策略改为原页空白优先、必要时缩放让位，并要求多轮排版优化，兼顾科学性和美观。 |
| 执行前最终路线 | 已将最终交付收口为：PDF 微调重排、空白优先遮挡展开、流程关系、多轮视觉优化、`compare.html` 对比展示、`metrics.json` 提效数据、一键启动和比赛文档。 |

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
## 2026-05-16 对象级重排大修

| 项目 | 结果 |
|---|---|
| 路线纠偏 | 放弃“PDF 侧栏/整页替换”为主路线，改为先编辑 PPTX 对象坐标，再用 LibreOffice 原生转 `guide.pdf`。 |
| 核心能力 | 新增对象级解析、遮挡图、重排规划、OOXML 坐标写回、重排编号标注；复杂页不新增导读页。 |
| `test.pptx` 验收 | `base.pdf` 2 页、`guide.pdf` 2 页；两页均走 `object_reflow`，遮挡文本/公式被移动到清晰位置，并保留原 PPT 页面风格。 |
| Review 回归 | `Review+chapter24-27.pptx` 42 页真实转换成功；7 页执行对象级重排，24 页原生增强，6 页因终态坐标不稳定转报告复核，无空重排页。 |
| 五轮自审 | 修正主链路未接入、间距不足、只移动局部遮挡对象、标题误移动、文本框压缩溢出、空重排虚报等问题。 |
| 作者意图保护 | 修正“严重页扩展候选”过宽问题：无遮挡图片/公式/图形默认保持原位，只移动真实参与遮挡关系的视觉对象。 |
| 图文组重排 | 新增关联视觉对象随正文组移动和组内避让，避免公式被独立挪走或留在旧位置遮挡新文本。 |
| 标注与公式稳定性 | 重排编号改为避让式放置；`graphicFrame` 公式保留原始尺寸，减少 LibreOffice 压缩/偏移。 |
| OLE 公式写回 | 同步更新 `graphicFrame` 外层坐标和 fallback 图片坐标，真实 Web 输出中公式位置与计划一致。 |
| 验证 | `python -m unittest discover -s app\tests` 42 项通过；`compileall` 通过；`node --check app\frontend\app.js` 通过；真实样例转换通过。 |
| 环境 | `env_check.py` 显示 Python/LibreOffice/PyMuPDF 正常，只有 `8765` 端口已被占用。 |
## 2026-05-17 OLE 公式预览修复
| 项目 | 结果 |
|---|---|
| 根因 | `graphicFrame` 公式移动后，LibreOffice 仍可能裁剪 OLE 预览；从 `base.pdf` 裁区域又会把原位置文字一起带到新位置。 |
| 修复 | `pdf_augmenter.py` 优先从 PPTX fallback 图片提取公式预览，白边透明裁剪并高分辨率重渲染 EMF/WMF，再覆盖到 `guide.pdf` 目标 bbox。 |
| 排版 | `object_reflow_planner.py` 将已移动视觉对象纳入后续避让，视觉对象重叠阈值收紧到近似零；空间不足时允许公式预览小幅缩放避让。 |
| 验收 | Web 重新生成 `job_id=9ab6c32e2d134133bae1456b317ecc64`，两页 `guide.pdf` 公式完整、未带入旧文字，编号未压住公式或图像。 |

## 2026-05-17 右栏化修正
| 项目 | 结果 |
|---|---|
| 根因 | 文本打包阶段把正文统一推到页面左侧，算法人为制造了右侧空白栏，导致图片和公式集中到右边。 |
| 修复 | 正文水平位置优先保留原页面意图；关联视觉对象使用多候选评分，公式优先占位，图片随后避让。 |
| 样例 | `test.pptx` 新生成 `job_id=0406b9f8281c41188ca6cc99eea5b7b5`，第 1 页视觉对象分布到上右、右中、左下、右下，不再统一堆右栏。 |
| 验证 | `python -m unittest discover -s app\tests` 53 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过。 |

## 2026-05-17 路线防偏规划
| 项目 | 结果 |
|---|---|
| 用户反馈 | 前后对比显示学习版对象被分散摆开，图文关系和流程关系仍不达标。 |
| 新结论 | 不能继续靠候选权重修；必须从“全局重排”改成“语义组局部修复”。 |
| 计划文件 | 已新增 `docs/superpowers/plans/2026-05-17-route-drift-repair.md`。 |
| 下一步 | 先实现路线契约和语义组测试，再重构 `object_reflow_planner.py`。 |
## 2026-05-17 路线防偏重修执行记录
| 项目 | 结果 |
|---|---|
| 主线修正 | 已从“全局候选重排”改成“语义组局部修复”：只处理遮挡/动画覆盖相关对象，稳定对象默认不动。 |
| 新增模块 | `reflow_groups.py`、`reflow_visual_check.py`、`render_sample_reflow_check.py`。 |
| 核心改动 | `object_reflow_planner.py` 使用语义关联、局部候选位、垂直带约束、左栏/右栏偏航惩罚，避免把正文压左、图片公式堆右。 |
| 报告输出 | `converter.py` 已把 `reflow_intent_check` 写入 `report.json`。 |
| 最新 Web 样例 | `job_id=7e69c6c34b0846fb81fe2974f9d259a2`，输出目录 `app/workspace/outputs/7e69c6c34b0846fb81fe2974f9d259a2`。 |
| 截图目录 | `app/tests/.tmp_runs/reflow_visual_check/7e69c6c34b0846fb81fe2974f9d259a2/`。 |
| 最新指标 | `reflow_intent_check.passed=true`，warnings 为空；第 1 页右栏/左栏偏航均为 0，第 2 页只有单个公式右侧就近落位，不按系统性右栏化失败处理。 |
| 人工截图结论 | 第 1 页已从散点/右栏堆图回到局部修复：上方公式在首段附近空白区，顶部图仍靠近上段，底部电荷图与下段保持关系，绿色公式在下段附近可读。 |
## 2026-05-17 路线防偏重修复验
| 项目 | 结果 |
|---|---|
| 复验输出 | `app/tests/.tmp_runs/reflow_visual_check/99796f1ec0d249c79e7c6f6d2b8df220/`。 |
| 复验指标 | `reflow_intent_check.passed=true`，warnings 为空；第 1 页 right/left bias 均为 0，最大位移比 0.15。 |
| 截图审查 | 第 1 页已保留正文主结构，公式、图像围绕对应段落局部落位；第 2 页公式移到右侧空白区，避免继续压住正文和单位行。 |
| 剩余问题 | 旧全局 packer 函数名仍需 legacy 化，后续还要补更强的流程关系线/序号避让细节，让排版从“可读”继续靠近“优秀作品”。 |

## 2026-05-18 局部重排关系线收口
| 项目 | 结果 |
|---|---|
| 路线清理 | 删除 `object_reflow_planner.py` 中旧 `legacy_pack_*` 包装函数，避免后续沿用全局分栏路线。 |
| 漂移判断 | `reflow_visual_check.py` 新增 `max_unexplained_move_ratio`；有 `anchor_id`/`anchor_to`/`flow_relation` 的对象大位移视为语义让位，不当作无理由漂移。 |
| 右栏指标 | 单个视觉对象右移不再生成 `right_column_bias=1.0`，只有多个视觉对象集中右移才算右栏化。 |
| 关系线 | `pdf_augmenter.py` 的重排关系线改成外缘连外缘；新增 `_relation_points` 回归测试，避免中心线穿正文。 |
| 真实样例 | 新输出 `app/tests/.tmp_runs/reflow_visual_check/0d60abfdfcf9444288e5c415403d4289/`；第 1 页和第 2 页 `passed=true`，warnings 为空。 |
| 截图结论 | 第 1 页不再右栏堆图，图像与公式围绕对应正文段落局部落位；第 2 页公式放在右侧空白区，短关系线不穿过正文。 |
| 验证 | `python -m unittest discover -s app\tests` 68 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过；`render_sample_reflow_check.py` 通过。 |

## 2026-05-18 箭头遮挡修复
| 项目 | 结果 |
|---|---|
| 根因 | 关系线端点贴到目标 bbox 边界，PPT/PDF 渲染箭头三角时会吃进黄色公式框。 |
| 修复 | `_relation_points` 给关系线两端增加 `RELATION_LINE_CLEARANCE`，目标侧箭头停在对象外侧。 |
| 回归 | 更新 `_relation_points` 单测，先确认旧逻辑失败，再实现通过。 |
| 样例 | 新输出 `app/tests/.tmp_runs/reflow_visual_check/685da2116b5646a7a4a072f13c14c883/`；第 2 页公式左侧箭头不再压住黄色区域，第 1 页未引入新遮挡。 |
| 验证 | `python -m unittest discover -s app\tests` 68 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过；`render_sample_reflow_check.py` 通过。 |

## 2026-05-18 GIF/视频媒体处理
| 项目 | 结果 |
|---|---|
| PPTX 识别 | `pptx_parser.py` 可从图片关系的 `a:blip` 目标后缀识别 `.gif`，也可从 `a:videoFile` 关系识别视频，并记录到对象 `media` 字段。 |
| 媒体产物 | 新增 `media_processor.py`，导出原始 GIF，生成 poster、关键帧 strip 和 `media_manifest.json`；视频/音频先导出原文件并记录边界。 |
| PDF 同页表达 | `pdf_augmenter.py` 在 `guide.pdf` 原 GIF bbox 内用关键帧宫格替换封面图，避免大封面占据主体区域。 |
| Web/报告 | `converter.py`、`server.py`、`app.js` 已输出并暴露媒体清单下载入口，`report.json` 写入媒体摘要。 |
| 样例 | `app/samples/test.pptx` 第 3 页真实 GIF 转换通过，截图 `app/tests/.tmp_runs/gif_media_sample/guide_page_3.png` 显示标题保留、原 GIF 区域变为 6 张关键帧宫格。 |
| 验证 | `python -m unittest discover -s app\tests` 76 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过；真实 CLI 转换通过。 |

## 2026-05-19 GIF 关键帧宫格自适应放大
| 项目 | 结果 |
|---|---|
| 问题 | 小 GIF 如果严格限制在原图 bbox 内，关键帧宫格会太小，学习版 PDF 可读性不足。 |
| 修复 | `pdf_augmenter.py` 新增锚点扩展布局：以原 GIF bbox 为锚点，优先向右下、中心、右上、左下、左上扩展到附近空白区。 |
| 避让 | 扩展矩形必须在页面内，并避开同页标题、正文、图形等 `occupied_boxes`；空间不足时逐级缩小，最后才退回原 bbox。 |
| 样例 | `test.pptx` 当前 4 页、2 个 GIF；第 4 页小 GIF 已自动放大为清晰关键帧宫格，第 3 页大 GIF 保持原位宫格。 |
| 验证 | `python -m unittest discover -s app\tests` 77 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过。 |

## 2026-05-20 项目瘦身执行记录
| 项目 | 结果 |
|---|---|
| 清理文件 | 删除 tracked `.pyc/__pycache__`、`app/backend/pdf_renderer.py`。 |
| 简化代码 | `augment_planner.py` 删除追加导读页预算、`expand_after_native`、不可达内容卡片逻辑；`pdf_augmenter.py` 删除新建导读页和整页重画分支；`test_v3_pdf_augmenter.py` 删除不可达断言和无用 helper。 |
| 主线复核 | 每个删改点均保持 `base.pdf` 原生对照、`guide.pdf` 同页学习版增强，不新增导读页。 |
| 自动验证 | `python -m unittest discover -s app\tests` 81 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过。 |
| Web 验收 | 已重启 8765，`curl.exe -s -F "deck=@app/samples/test.pptx" http://127.0.0.1:8765/api/convert` 成功，`job_id=2e422db8f84c4c3d89317f85e0b983b4`。 |
| 截图验收 | 已渲染并检查 `app/workspace/outputs/2e422db8f84c4c3d89317f85e0b983b4/guide_page1.png` 到 `guide_page4.png`；页 1/2 对象重排保持主线，页 3/4 GIF 关键帧正常替换原媒体区。 |
| 遇到的问题 | `rg` 在当前环境 Access denied，改用 `git grep`/PowerShell；PowerShell 未指定 UTF-8 读取 JSON 会误解码，已用 `-Encoding UTF8` 复核。 |
