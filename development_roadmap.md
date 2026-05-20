# 代码开发路线

## 总原则

| 原则 | 定法 |
|---|---|
| 原生保真优先 | `base.pdf` 由 LibreOffice/Unoserver 生成，不再用 HTML 重画原 PPT |
| 解析只做诊断 | PPTX 解析器读取对象、动画、备注、层级，用于生成重排计划，不承担原生渲染 |
| 动画融入页面 | `guide.pdf` 以 `base.pdf` 为画面来源，通过 PDF 微调重排、空白优先放置、遮挡展开、流程关系线和少量锚点表达动画变化 |
| 不伪造能力 | 不支持项写入 `report.json`，转换失败直接报错 |
| 小白可用 | 开发期保留 Web 服务，交付期做双击启动和样例包 |

## 目标输出

| 文件 | 说明 |
|---|---|
| `base.pdf` | 原生保真转换结果 |
| `guide.pdf` | 学习版 PDF：保留原 PDF 画面主体，在复杂页做 PDF 层微调重排，让遮挡内容清晰可见并呈现流程关系，不依赖 AI |
| `compare.html` | 比赛展示页：并排呈现普通 PDF 与学习版 PDF，突出遮挡展开、流程关系和提效数据 |
| `report.json` | 转换、动画、遮挡、拥挤、不支持项报告 |
| `preview.html` | 本地网页预览，方便调试和比赛展示 |

## 阶段 1：V3A 原生 PDF 底座

| 项 | 内容 |
|---|---|
| 目标 | `.pptx` 稳定生成 `base.pdf` |
| 新增模块 | `native_converter.py` |
| 改动模块 | `converter.py`、`server.py`、前端下载入口、测试 |
| 核心逻辑 | 查找 LibreOffice `soffice`；调用 headless 转换；输出明确错误 |
| 验收 | 样例 PPTX 能生成 `base.pdf`；页数非 0；失败时不生成假 PDF |

当前状态：LibreOffice 原生转换已跑通，`base.pdf` 和 `guide.pdf` 均可生成。

## 阶段 2：V3B 分析数据升级

| 项 | 内容 |
|---|---|
| 目标 | 输出稳定的 `analysis.json` |
| 新增模块 | `slide_analyzer.py` |
| 改动模块 | `pptx_parser.py`、`study_builder.py` |
| 核心逻辑 | 统一页面尺寸、对象面积、重叠率、文本密度、动画目标、备注、不支持项 |
| 验收 | 每页都有 `complexity`、`crowding`、`animation_steps`、`warnings` |

本阶段不改 PDF 视觉，只把后面导读和重排需要的数据算准。

## 阶段 3：V3C 动画导读基础版

| 项 | 内容 |
|---|---|
| 目标 | 生成 `guide.pdf`，能表达动画顺序和页面变化 |
| 新增模块 | `augment_planner.py`、`pdf_augmenter.py` |
| 改动模块 | `converter.py`、HTML 预览 |
| 核心逻辑 | 根据分析结果生成 `augment_plan.json`；对简单页叠加编号/高亮/提示；复杂页先进入报告，等待重排 |
| 验收 | 不机械按动画数量拆页；细小变化保持 1 页；遮挡页能看到被盖住内容的导读表达 |

首版先做“原生增强页 + PDF 微调重排”，重排限定在可定位矩形区域、空白区放置、必要让位、局部遮盖和裁剪复用，避免假装能完整编辑任意 PPT/PDF 语义对象。

## 阶段 4：V3D 拥挤判断和重排决策

| 项 | 内容 |
|---|---|
| 目标 | 自动判断同页增强、融合重排、少量拆页 |
| 新增模块 | `layout_decider.py` |
| 改动模块 | `augment_planner.py`、`pdf_augmenter.py` |
| 核心指标 | 对象覆盖率、重叠率、空白率、文本密度、动画目标数量、标注可放置性 |
| 验收 | 同一套样例能稳定输出三类策略；极复杂页进入报告，不硬做 |

这是核心攻关阶段。判断算法必须可解释，每个策略都要能在 `report.json` 里说明触发原因。

当前小步已完成：`augment_plan.json` 会输出 `inline_markers`，`guide.pdf` 的原生页会叠加动画编号和局部高亮框；低拥挤动画页保持 1 页，复杂/拥挤页先 `report_only`。下一步不再追加导读页，也不抽取重画，改做 PDF 层微调重排。

## 阶段 5：V3G PDF 微调重排

| 项 | 内容 |
|---|---|
| 目标 | 在保留原 PDF 画面主体的基础上，对复杂动画页做局部微调重排 |
| 改动模块 | `layout_decider.py`、`augment_planner.py`、新增 `pdf_micro_reflow.py`、测试 |
| 核心逻辑 | 以 `base.pdf` 原页为底，按 PPTX bbox 映射到 PDF 坐标；优先把遮挡前后的局部区域放到原页空白处，空白不足时再缩放让位或使用展开区，并叠加编号、箭头或关系线 |
| 验收 | `test.pptx` 的 `guide.pdf` 仍为 2 页，每页保留原画面主体，被遮挡内容可独立看清，流程关系明确，布局科学、美观，不追加导读页，不整页抽取重画 |

这是当前最高优先级。继续泛化动画类型收益已经降低，因为 `test.pptx` 已无 unsupported 动画，主要矛盾是复杂页如何在原画面上被微调得更可读。

当前小步需要废弃：`reflow_replace` 虽然页数正确，但属于重画页面，不符合“保留原画面基础上的微调重排”。下一步切到 PDF 层微调。

## 阶段 6：V3H 前端结果解释

| 项 | 内容 |
|---|---|
| 目标 | 非技术用户可完成上传、转换、预览、下载 |
| 改动模块 | `frontend/index.html`、`frontend/styles.css`、`frontend/app.js`、`server.py` |
| 核心逻辑 | 输出模式选择；状态进度；`base.pdf`/`guide.pdf`/`report.json`/`analysis.json` 下载；策略原因和错误直说 |
| 验收 | 浏览器打开后拖入 PPTX 即可生成结果，用户能看懂为什么某页增强、某页只报告 |

开发期继续使用本地 Web 服务；比赛展示期再补双击启动脚本和样例包。

## 阶段 7：V3I 开箱即用封装

| 项 | 内容 |
|---|---|
| 目标 | 非技术用户双击启动本地工具 |
| 新增模块 | `start.ps1`、`start.bat`、`app/backend/env_check.py` |
| 核心逻辑 | 检查 Python、LibreOffice、端口占用；启动服务；打开浏览器 |
| 验收 | 缺 LibreOffice 时给出清晰安装/路径提示；已安装时一键打开本地网页 |

## 阶段 8：V3J 路演交付

在交付前先生成 `compare.html`：左侧展示 `base.pdf` 关键页，右侧展示 `guide.pdf` 对应页，下方列出遮挡展开点、动画流程关系和 `metrics.json` 的提效数据。它是比赛讲解的主入口，不替代 PDF 文件本身。

| 样例 | 要覆盖的问题 |
|---|---|
| 大学课程课件 | 分步骤公式/概念出现、备注不足 |
| 企业培训材料 | 流程图逐步出现、信息密集 |
| 图文密集课件 | 图片保真、局部遮挡、标注空间不足 |

验收标准：三类样例都能生成 `base.pdf`、`guide.pdf`、`report.json`，并且不出现静默失败。路演材料要能在 3 分钟内讲清“普通 PDF 保真 + 学习型 PDF 重排”的差异。

## 阶段 9：V4 AI 讲义解释版

| 项 | 内容 |
|---|---|
| 目标 | 在基础版稳定后，生成页面解释、动画意图和复习提示 |
| 新增模块 | `explanation_provider.py`、`ai_notes_builder.py` |
| 核心逻辑 | AI 只基于 PPT 文本、备注和 Mode A 结构化结果生成；每段标注依据来源 |
| 验收 | 无 API 时入口不可用且说明原因；有 API 时不编造无来源知识点 |

## 首轮开发任务拆分

| 顺序 | 任务 | 文件 |
|---|---|---|
| 1 | 写 `native_converter.py`，只负责原生转 PDF | `赛道3/app/backend/native_converter.py` |
| 2 | 改编排输出结构，从 `study.*` 切到 `base.pdf`/`guide.pdf`/`report.json` | `赛道3/app/backend/converter.py` |
| 3 | 改服务返回字段和下载链接 | `赛道3/app/backend/server.py`、`赛道3/app/frontend/app.js` |
| 4 | 补 V3A 测试：无 LibreOffice 时明确失败，有 LibreOffice 时生成 `base.pdf` | `赛道3/app/tests/test_v3_native_converter.py` |
| 5 | 再做 `analysis.json`，把旧 `study_builder` 逐步降为导读计划输入 | `slide_analyzer.py`、`study_builder.py` |
| 6 | 最后做 `guide.pdf` 增强，不提前碰复杂重排 | `augment_planner.py`、`pdf_augmenter.py` |

## 当前不做

| 不做 | 原因 |
|---|---|
| AI 讲义解释 | 基础版先不依赖 API |
| `.ppt` 老格式 | 会引入额外转换链路 |
| 音视频转写 | 不影响首版核心演示 |
| 复杂路径动画还原 | 首版只检测并报告 |
| 完美重排任意 PPT | 范围过大，先做可解释规则和有限样例 |

## 立即下一步

| 选择 | 动作 |
|---|---|
| 推荐 | 接入 PyMuPDF，开发 V3G PDF 微调重排 |
| 备选 | 若 PyMuPDF 安装受限，先用 pypdf + reportlab 做覆盖层验证 |

不要继续抽取重画页面；后续所有复杂页重排都要以 `base.pdf` 原页画面为底。
