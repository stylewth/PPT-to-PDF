# 赛道3 Demo 开发计划

## 2026-05-16 大修路线重规划
| 项 | 新结论 |
|---|---|
| 偏差判定 | 上一版 V3G 把“保留原页面”误做成“原页面主体不动”，导致截图中的主体文字、公式、单位行仍然重叠。 |
| 新目标 | `guide.pdf` 必须让主体页面本身变清楚，而不是只在右侧栏解释遮挡。 |
| 新主线 | PPTX 对象级微调重排：解析 shape，移动/缩放/复制具体对象，生成 `guide_deck.pptx`，再由 LibreOffice 转成 `guide.pdf`。 |
| PDF 层定位 | PDF 层只做对比、指标、少量标注和视觉检查；不再承担主体重排。 |
| 第一验收样例 | `app/samples/test.pptx` 第 2 页：正文、公式、单位行必须分开，页面主体可读。 |
| 完整大修计划 | `docs/superpowers/plans/2026-05-16-object-level-reflow-overhaul.md`。 |

## 2026-05-16 V3G 已完成范围
| 模块 | 状态 | 产出 |
|---|---|---|
| PDF 微调重排 | 完成 | `app/backend/pdf_micro_reflow.py`，基于 PyMuPDF 复用原 PDF 局部区域，优先空白区，必要时扩展右侧栏。 |
| 遮挡流程表达 | 完成 | `augment_plan.json` 写入 `micro_reflow.occlusion_flows`，`guide.pdf` 中展示“遮挡前 -> 覆盖后”。 |
| 原生转换链路 | 完成 | LibreOffice 生成 `base.pdf`，PyMuPDF 生成 `guide.pdf`，保留原页主体。 |
| 对比和指标 | 完成 | `compare.html`、`metrics.json`、`report.json`，用于比赛展示普通 PDF 与学习版 PDF 差异和提效数据。 |
| 小白启动 | 完成 | `start.ps1`、`start.bat`、`env_check.py`、`app/README.md`。 |
| 比赛文档 | 完成 | `使用说明.md`、`路演脚本.md`、`比赛提交清单.md`、`docs/competition/README.md`。 |
| 样例验收 | 完成 | `test.pptx`、`animation_guide_smoke.pptx`、`course_animation_occlusion.pptx`、`native_conversion_smoke.pptx`、`Review+chapter24-27.pptx` 均完成真实转换验证。 |
| 下一阶段 | 预留 | V4 再接真实 AI 讲义解释，不影响当前比赛基础成品。 |

## 目标
开发一个“小白开箱即用”的演示型 PPT 转学习型 PDF Demo，面向大学课程课件和企业培训 PPT，展示系统如何把依赖讲师现场讲解的动态 PPT 重构为可阅读、可批注、可复习的学习型 PDF。

## 当前阶段
阶段 15：最终路线已锁定为“原生 `base.pdf` + PDF 层微调重排”。下一次正式执行时，先废弃上一版 `reflow_replace` 的整页重画路径，再让 `test.pptx` 在 `guide.pdf` 中保持原页面主体，局部让位、遮盖、裁剪复用和叠加动画顺序。

## 最终路线锁定
| 项 | 定法 |
|---|---|
| 产品目标 | 做一个面向课程课件和企业培训材料的本地 PPTX 转学习型 PDF 工具，参加小鹏 AI 公开赛赛道 3。 |
| 转换底座 | LibreOffice/Unoserver 只负责生成原生 `base.pdf`，保证基础画面和排版。 |
| 重排定义 | 不抽取内容重画页面；只在 `base.pdf` 画面基础上做 PDF 层局部微调，尤其要把被遮挡内容放到清晰位置并表达流程关系；放置位置优先使用原页空白，不固定塞进展开栏。 |
| 首版输入 | 只支持 `.pptx`。 |
| PDF 编辑 | 按需要引入 PyMuPDF；缺依赖时直接报错，不生成假结果。 |
| AI 接入 | 首版不接真实大模型 API；保留 AI 解释接口，路演中如实说明当前为 AI/VibeCoding 辅助构建的 Agent 工具。 |
| 交付形态 | 本地可运行项目、Web/CLI、`base.pdf`、`guide.pdf`、`compare.html`、使用说明、样例输出、提效数据、路演脚本。 |
| 自主执行 | 用户下令开始后，非破坏性开发、测试、调试、文档补齐连续完成；完成后自动做 5 轮自审优化。 |
| 停止条件 | 破坏性操作、不可逆操作、方向冲突、需要真实外部账号/API Key 时停下来确认。 |

完整执行计划见 `docs/superpowers/plans/2026-05-16-final-product-route.md`。后续如果历史章节与本节冲突，以本节为准。

## 阶段清单
| 阶段 | 状态 | 产出 |
|---|---|---|
| 1. 需求收敛 | complete | 明确定位为“课件可读化”，覆盖大学课程与企业培训 |
| 2. Demo 信息架构 | complete | 上传区、分析流程、问题识别、学习型 PDF 预览、导出 |
| 3. 静态前端实现 | complete | `赛道3/demo` 下的 HTML/CSS/JS |
| 4. 视觉与交互自检 | complete | 桌面截图检查，预览区可读 |
| 5. 本地验证 | complete | JS 语法检查通过，无头 Edge 成功渲染截图 |
| 6. V2 真实功能开发 | complete | `.pptx` 解析、基础动画理解、遮挡检测、HTML/PDF 输出、本地 Web |
| 7. 原生保真转换路线 | complete | 已生成 `赛道3/design_technical_route.md` 和 `赛道3/development_roadmap.md` |
| 8. V3A 原生 PDF 底座 | complete | LibreOffice 已跑通真实 `base.pdf` 转换，CLI 和 Web 上传均可生成结果 |
| 9. V3B 分析数据升级 | complete | 已输出 `analysis.json`，包含页面尺寸、动画步骤、拥挤指标和策略提示 |
| 10. V3C 动画导读基础版 | complete | 已输出 `guide.pdf` 和 `augment_plan.json`，动画页可追加导读说明页 |
| 11. V3D 原页同页增强小步 | complete | `guide.pdf` 的原生页已可叠加动画编号和局部高亮框；低拥挤动画页保持 1 页，复杂页先进入报告 |
| 12. V3D 复杂课件可读性修正 | complete | 止损热修、`layout_decider.py`、标注可放置性和导读页泛滥控制已完成 |
| 13. V3F 综合样例验收 | complete | `animation_guide_smoke.pptx`、`test.pptx`、`Review+chapter24-27.pptx` 真实转换通过，页数未膨胀，抽样页标注不遮挡正文 |
| 14. 动画识别扩展 | complete | 已支持 `blinds(horizontal)`、`wheel(1)` 和明确的 `ppt_x/ppt_y` 位置移动；无法确定语义的裸 `anim` 仍不硬猜 |
| 15. V3G PDF 微调重排 | in_progress | 纠偏：上一版 `reflow_replace` 属于抽取重画，不符合目标；下一步改为基于 `base.pdf` 的局部微调重排 |
| 16. 小白开箱即用封装 | pending | 补 LibreOffice 检测、启动脚本和更清晰的本地运行入口 |
| 17. 对比展示与提效指标 | pending | 输出 `compare.html`、`metrics.json` 和演示数据，让评委一眼看到普通 PDF 与学习版 PDF 的差异 |
| 18. 路演交付包 | pending | 固化样例、对比截图、使用说明、3 分钟演示脚本和能力边界 |
| 19. 全量回归和五轮自审 | pending | 单测、编译、前端检查、样例转换、PDF 渲染检查、路线/功能/视觉/赛题/交付五轮优化 |
| 20. AI 讲义解释版预留 | pending | 独立接口、关闭状态、引用来源和不足提示 |

## 2026-05-17 视觉对象分布修正
| 项 | 状态 | 结果 |
|---|---|---|
| 避免右栏化 | complete | 正文重排不再强行贴到页面 10% 左边，优先保留原正文组水平起点。 |
| 图文关系 | complete | 视觉对象先按关联正文生成局部候选，右侧、上方、下方、原相对位置均参与评分。 |
| 组内避让 | complete | 同组公式优先放置，图片随后避让，避免宽公式被图像挤压或相互遮挡。 |
| 样例验收 | complete | `test.pptx` 真实 Web 转换 `0406b9f8281c41188ca6cc99eea5b7b5`，两页 `guide.pdf` 不再统一右侧堆图。 |

## 2026-05-17 路线防偏重修计划
| 阶段 | 状态 | 目标 |
|---|---|---|
| 路线契约 | pending | 写入“局部语义组修复”硬约束，禁止全局左栏/右栏式重排。 |
| 语义分组 | pending | 先识别文字、公式、图片的对应组，再决定谁移动。 |
| 局部修复 | pending | 只在遮挡组附近找清晰位置，稳定对象默认不动。 |
| 意图指标 | pending | 新增右栏化、左栏化、移动距离、组间距离等防偏指标。 |
| 截图验收 | pending | 每次真实转换后对比 `base.pdf` 与 `guide.pdf`，截图不合格不算完成。 |
| 执行计划 | complete | 详细路线见 `docs/superpowers/plans/2026-05-17-route-drift-repair.md`。 |

## 2026-05-21 渲染门禁与公式根修计划
| 阶段 | 状态 | 目标 |
|---|---|---|
| 1. 渲染门禁 | in_progress | 新增基于最新 `guide.pdf` 截图的视觉回归检查，截图失败即失败，不能只靠 bbox。 |
| 2. 公式质量检测 | pending | 检测公式 fallback/渲染区域的墨迹触边、异常高密黑块、疑似裁切和叠字。 |
| 3. 公式修复链路 | pending | fallback 可用则重绘公式；fallback 本身异常则暴露为视觉失败，不再假修复。 |
| 4. 复杂页局部展开 | pending | 对第 35 页这类多对象冲突页做语义块展开，不继续单对象硬挪。 |
| 5. 最新样例验收 | pending | 重启 8765，转换 `test.pptx` 和 `Review+chapter24-27.pptx`，渲染问题页截图审查。 |

## 2026-05-25 Agent 式 AI PDF 编辑器路线
| 项 | 定法 |
|---|---|
| 路线目标 | 用户勾选讲解卡后，由 AI 作为“PDF 编辑代理”取舍内容、压缩短稿并建议融入方式；系统算法负责最终位置和视觉门禁。 |
| 输出边界 | 只生成或更新独立 `ai_guide.pdf`，不覆盖 `base.pdf` 和 `guide.pdf`。 |
| 核心链路 | 讲解卡选择 -> AI PDF 编辑 -> 来源/长度审计 -> 空白候选区评分 -> 页内短旁注或拓展页 -> 截图门禁 -> manifest。 |
| 内容策略 | PDF 只放重要补充解释，不归档完整 AI 讲解；每页默认 1-3 条，每条 40-120 字，总字数受硬限制。 |
| 排版策略 | 优先放入原页安全空白处；空白不足但内容重要时进入拓展页；低价值或重复原文的内容不导出。 |
| 防偏约束 | AI 不能自由给坐标；不能展示内部 `source_refs`；不能用长解释页掩盖原页排版问题；页内融入必须通过截图检查。 |
| 实施计划 | `docs/superpowers/plans/2026-05-25-agentic-ai-pdf-editor.md`。 |

## 关键约束
| 约束 | 决策 |
|---|---|
| 不捏造真实解析能力 | Demo 明确展示产品流程与结果形态，不宣称已完整解析任意 PPT |
| 用户友好 | 默认一键生成学习版 PDF，减少参数配置 |
| 贴合赛题 | 强调知识管理、协同办公、学习/培训效率提升 |
| 不创建分支/worktree | 当前目录直接开发 |

## Demo 范围
| 包含 | 不包含 |
|---|---|
| PPT 上传入口 | 后端文件解析服务 |
| 示例课件/培训材料分析流程 | 真正读取 PPT 动画 XML |
| 遮挡/动画/解释缺失问题展示 | 对任意 PPT 的严谨转换 |
| 学习型 PDF 页面预览 | 真实 PDF 二进制生成 |
| 浏览器打印导出 | 云端账号体系 |

## 下一步建议
| 优先级 | 任务 | 原因 |
|---|---|---|
| 1 | V3G PDF 微调重排 | 当前 `test.pptx` 已能识别动画；必须在保留原页面主体的基础上做空白优先放置、必要时让位、遮挡展开、裁剪搬移和流程关系表达 |
| 2 | 小白开箱即用封装 | 比赛演示不能依赖命令行，必须有一键启动和清晰错误提示 |
| 3 | `compare.html` 对比展示 | 比赛展示必须一眼看懂普通 PDF 和学习版 PDF 的差异 |
| 4 | 提效指标与 ROI 证明 | 赛题明确要求用数据证明节省时间、提升效率、减少错误 |
| 5 | 路演交付包 | 评委需要看到原 PPT、普通 PDF、学习型 PDF、对比页、问题报告和使用说明 |
| 6 | AI 讲义解释版预留 | 后续增强解释能力，但不能阻塞基础版稳定交付 |

## 基础功能共识
| 功能 | 首版要做 | 暂不做 |
|---|---|---|
| 文件输入 | 上传 `.pptx`，校验文件结构 | `.ppt`、Keynote、网盘导入 |
| 页面解析 | 读取文本、图片、形状、备注、层级顺序 | 完整还原所有 Office 特效 |
| 动画解析 | 支持出现、淡入、擦除、路径外的基础顺序动画 | 复杂触发器、音视频、交互按钮 |
| 遮挡检测 | 基于对象边界框和层级判断最终态遮挡 | 用不透明规则硬猜用户意图 |
| 内容解释 | 只基于 PPT 文本、备注、页内关系生成解释 | 无依据扩写、编造知识点 |
| 输出结果 | 生成学习型 HTML 预览和 PDF | 多人协作、账号体系、云端素材库 |
| 问题报告 | 标出不支持动画、缺失字体、疑似遮挡 | 静默降级 |

## 代码开发路线
| 阶段 | 目标 | 主要模块 | 验收标准 |
|---|---|---|---|
| V0 演示原型 | 已完成产品形态展示 | 静态前端 Demo | 能展示上传、分析、预览、打印导出 |
| V1 真实解析闭环 | 真实 `.pptx` 输入到学习型 PDF 输出 | 上传接口、PPTX 解析器、讲义 JSON、PDF 渲染 | 一个测试 PPTX 可稳定输出 PDF， unsupported 明确报错 |
| V2 动画理解增强 | 把基础动画拆成学习步骤 | 动画时间线解析、遮挡检测、步骤重构 | 支持 3 类基础动画，能拆出步骤页 |
| V3 AI 解释生成 | 补足“只有重点没解释” | 证据抽取、解释生成、引用校验 | 每段解释能追溯到 PPT 文本/备注，否则标记需补充 |
| V4 路演增强 | 更像完整产品 | 示例库、转换对比、问题报告下载 | 评委能看到原 PPT、普通 PDF、学习型 PDF 对比 |

## 推荐目录结构
| 路径 | 用途 |
|---|---|
| `赛道3/demo` | 保留现有静态路演 Demo |
| `赛道3/app/frontend` | 后续真实 Web 前端 |
| `赛道3/app/backend` | 上传、解析、生成接口 |
| `赛道3/app/backend/pptx_parser` | PPTX OOXML 解析 |
| `赛道3/app/backend/study_builder` | 学习型讲义 JSON 重构 |
| `赛道3/app/backend/pdf_renderer` | HTML/PDF 渲染 |
| `赛道3/app/samples` | 可提交的样例 PPTX，不放敏感课件 |
| `赛道3/app/tests` | 解析器和转换闭环测试 |

## V1 最小真实功能
| 接口/页面 | 输入 | 输出 |
|---|---|---|
| 上传页面 | `.pptx` 文件 | 任务 ID |
| 解析接口 | 任务 ID | slide objects、notes、z-order、warnings |
| 讲义构建接口 | slide JSON | study document JSON |
| 预览页面 | study document JSON | 学习型讲义 HTML |
| 导出接口 | study document JSON | PDF 文件 |

## 技术路线建议
| 层 | 建议 | 原因 |
|---|---|---|
| 前端 | 保持工具界面，突出“原 PDF + 增补页”对比 | 用户关心排版是否保留，不关心解析细节 |
| 后端 | Python 服务编排转换流程 | 文件处理、任务状态、调用外部转换器更顺手 |
| 原生 PDF 底座 | LibreOffice headless；批量/服务化用 Unoserver | 保留 PPT 基本排版、图片、字体和母版，比自己重画稳 |
| PPTX 解析 | 继续解析 OOXML / python-pptx，只做诊断和定位 | 不承担渲染任务，避免版式失真 |
| PDF 增补 | PyMuPDF / pypdf / reportlab 组合 | 在原 PDF 前后插入讲义页、留白页、问题页，不破坏原页 |
| AI 模块 | 独立 `explanation_provider` 接口 | 没有模型 Key 时明确不可用，不写假解释 |

## 路线修正：原生保真优先
| 原路线问题 | 新路线 |
|---|---|
| 解析 PPT 文本后用 HTML 重画，图片、母版、图表、复杂排版会丢 | 先用 LibreOffice/Unoserver 原生转 PDF，保留普通 PPT 转 PDF 的基本效果 |
| 遮挡页被重构成讲义，但原页样貌丢了 | 原页保留，另插“展开页/解释页/批注页” |
| 每页都重排，用户感觉不像 PPT 转 PDF | 只对特殊页增补，其余页等同普通 PDF |
| 解析模块承担太多渲染职责 | 解析模块只输出风险报告和增补计划 |

## 新版本目标形态
| 输出页类型 | 内容 | 触发条件 |
|---|---|---|
| 原生页 | LibreOffice/Collabora 转出来的原始 PDF 页 | 每一页都保留 |
| 留白页 | 原生页旁边/下一页增加笔记空间 | 用户选择“批注版”或页内信息密度高 |
| 智能重排页 | 尽量还原原页面意思和视觉素材，在同页加入变化引导、解释、留白 | 有动画、遮挡、解释缺失或信息密度高 |
| 动画展开页 | 按变化量规划页数，不按每个动画机械加页 | 检测到中高复杂度动画、遮挡、逐步出现 |
| 解释页 | 摘出备注、标题、关键对象，生成短解释和复习提示 | PPT 有备注或页内文字足够 |
| 问题页 | 字体缺失、图片缺失、动画不支持、遮挡风险 | 转换/解析发现 warning |

## 用户可选输出模式
| 模式 | 名称 | 是否需要 AI API | 输出目标 | 首版优先级 |
|---|---|---|---|---|
| Mode A | 动画导读基础版 | 不需要 | 引导用户理解 PPT 在本页按什么顺序变化，少量标注、编号、箭头、变化提示 | 先做 |
| Mode B | AI 讲义解释版 | 需要或强烈建议 | 解释每页内容，并推理动画背后的讲解逻辑、知识结构和复习重点 | 后做 |

## Mode A：动画导读基础版
| 项 | 规则 |
|---|---|
| 输入依据 | PPTX 动画顺序、对象层级、对象文本、对象边界框、备注 |
| 输出内容 | 原生页或二次排版页 + 变化编号 + 阅读顺序 + 局部高亮 + 简短变化提示 |
| 文案来源 | 只使用 PPT 内已有文字和规则模板 |
| 不做内容推理 | 不解释“为什么这样讲”，只说明“先出现什么、后出现什么、哪里被覆盖” |
| AI 依赖 | 无 |
| 失败策略 | 无法识别动画时保留原生页并写入问题报告 |

## Mode B：AI 讲义解释版
| 项 | 规则 |
|---|---|
| 输入依据 | Mode A 的结构化结果 + PPT 文字 + 备注 + 可选课程/培训背景 |
| 输出内容 | 页面解释、动画意图推理、复习提示、概念关系、可能的讲解逻辑 |
| 文案来源 | AI 生成，但必须标注依据来源；无依据处标“推测”或“需确认” |
| AI 依赖 | 建议接入 AI API，否则只能做规则模板，效果不足 |
| 失败策略 | AI 不可用时降级为 Mode A，不生成推理性内容 |

## 动画页页数预算规则
| 动画变化量 | 学习版处理 | 页数 |
|---|---|---|
| 无动画或仅装饰变化 | 保留原生页，只加很轻的提示或不处理 | 1 页 |
| 细小变化：少量文字/图标出现，画面主体不变 | 同一页内加编号、变化提示条、局部高亮，不新增展开页 | 1 页 |
| 中等变化：多个知识点逐步出现，但同属一个逻辑组 | 同一页二次排版，保留主要图片/图表，右侧或底部加入步骤说明 | 1 页 |
| 较大变化：多个逻辑组、遮挡明显、最终态看不懂过程 | 默认替换为 1 页融合重排页，`base.pdf` 保留原貌 | 1 页 |
| 很大变化：一页承担多个推导/流程/案例 | 先报告为需人工确认；不默认追加导读页，不机械拆页 | 1 页或人工确认后拆页 |

## 同页增强表现方式
| 引导方式 | 用途 |
|---|---|
| 变化编号 | 标出这页从 1 到 N 发生了什么 |
| 变化提示条 | 用短句解释新增/消失/覆盖的内容 |
| 局部放大框 | 对被遮挡或细小变化区域做放大说明 |
| 半透明幽灵层 | 显示之前被盖住的对象轮廓 |
| 阅读顺序线 | 用箭头或序号提示先看哪里、后看哪里 |
| 侧边说明栏 | 在不破坏主图的情况下增加解释文字 |
| 底部笔记区 | 给学生/员工留批注空间 |

## Study PDF 映射原则
| 原 PPT 页 | 学习版 PDF 页 |
|---|---|
| 简单页 | 1 页，尽量接近原生转换 |
| 动画细小页 | 1 页，在原画面基础上轻量标注 |
| 动画中等页 | 1 页，允许重排空间但保留核心图片/图表 |
| 动画复杂页 | 默认 1 页 PDF 微调重排，保留原画面主体，优先利用原页空白放置遮挡展开内容，必要时再让位 |
| 无法可靠处理页 | 保留原生页，并追加问题说明 |

## 推荐开源组件
| 组件 | 用途 | 判断 |
|---|---|---|
| LibreOffice headless | 单文件 PPT/PPTX 原生转 PDF | 首选底座，本机需安装 LibreOffice |
| Unoserver | 常驻 LibreOffice 转换服务 | 批量转换/比赛服务端更稳，优先于已归档的 unoconv |
| Collabora Online | 容器化/服务化文档转换 | 更重，但更接近生产级转换服务 |
| python-pptx / OOXML 直读 | 读取 shape tree、备注、对象顺序 | 适合诊断，不适合作为渲染器 |
| Apache POI XSLF | Java 生态的 PPTX 对象解析 | 可选，不建议当前 Python 项目切 Java |
| PPspliT | 动画拆页思路参考 | 适合借鉴，不作为核心依赖；它依赖 PowerPoint/VBA |
| PyMuPDF / pypdf / reportlab | PDF 插页、合并、批注区、问题报告 | 后续实现“原 PDF + 增补页”的关键 |

## 新开发阶段
| 阶段 | 目标 | 验收标准 |
|---|---|---|
| V3A 原生 PDF 底座 | 接入 LibreOffice headless 转换 | 上传样例 PPTX 后生成与普通 PPT 转 PDF 接近的 base.pdf |
| V3B 动画导读基础版 | 实现 Mode A，不依赖 AI API | 输出能标注动画顺序、变化提示、遮挡风险 |
| V3C PDF 增补器 | 生成同页增强/少量拆页/留白页 | 页数按变化量预算，不机械逐动画拆页 |
| V3D 输出模式选择 | 用户选择标准版、批注版、动画导读版、AI 讲义版 | AI 讲义版未配置 API 时明确不可用 |
| V3E AI 讲义解释版 | 接入 AI API 生成解释和推理 | 每段解释可追溯来源，推测内容明确标记 |
| V3F 回归测试 | 用真实课件样本验证排版保留 | 至少 3 个不同风格 PPTX 输出可读，无静默失败 |

## 下一步具体改造顺序
| 顺序 | 任务 | 文件影响 |
|---|---|---|
| 1 | 新增 `native_converter.py`，查找 LibreOffice/Unoserver 并生成 `base.pdf` | `赛道3/app/backend/native_converter.py` |
| 2 | 新增 `pdf_augmenter.py`，把 `base.pdf` 和增补页合并 | `赛道3/app/backend/pdf_augmenter.py` |
| 3 | 改 `converter.py`：输出 `base.pdf`、`study.pdf`、`report.json` | `赛道3/app/backend/converter.py` |
| 4 | 改前端：显示输出模式选择和“原生 PDF / 动画导读 PDF / 问题报告”下载入口 | `赛道3/app/frontend/*` |
| 5 | 保留现有 OOXML 解析模块，但从“渲染源”降级为“诊断源” | `pptx_parser.py`、`study_builder.py` |
| 6 | 加测试：确保原生页数量不变，增补页只追加不替换 | `赛道3/app/tests/*` |

## V3 代码开发路线已定

| 阶段 | 先后关系 | 关键产出 |
|---|---|---|
| V3A | 必须先做 | `base.pdf` 原生保真转换 |
| V3B | 第二步 | `analysis.json` 页面分析、动画顺序、拥挤指标 |
| V3C | 第三步 | `guide.pdf` 动画导读基础版 |
| V3D | 第四步 | 同页增强、融合重排、拆页决策 |
| V3F | 已完成 | 3 类真实样例验证 |
| V3G | 当前下一步 | PDF 微调重排 |
| V3H | 之后 | 前端结果解释和下载体验 |
| V3I | 之后 | 小白开箱即用封装 |
| V3J | 之后 | 对比展示与提效指标 |
| V3K | 之后 | 路演交付包 |
| V4 | 最后 | AI 讲义解释版 |

详细路线见 `赛道3/development_roadmap.md`。当前硬前提已经从“原生转换能否跑通”转为“复杂动画页如何在保留原 PDF 画面的基础上微调得更可读”。

## 2026-05-14 后续路线

| 阶段 | 目标 | 关键文件 | 验收标准 |
|---|---|---|---|
| V3G PDF 微调重排 | 对 `unsupported_animation_count=0`、步骤多、重叠高的复杂动画页，以 `base.pdf` 原页为底做同页微调 | `layout_decider.py`、`augment_planner.py`、`pdf_micro_reflow.py`、`test_v3_pdf_micro_reflow.py` | `test.pptx` 的 `guide.pdf` 仍为 2 页；原画面主体保留；被遮挡内容在清晰位置可见；流程关系明确；布局科学、美观，不追加导读页 |
| V3H 前端输出解释 | Web 页面展示为什么某页增强、为什么某页只报告，下载区更清晰 | `server.py`、`frontend/app.js`、`frontend/index.html`、`frontend/styles.css` | 上传后能看到 `base.pdf`、`guide.pdf`、`report.json`、`analysis.json`；错误和策略原因中文直说 |
| V3I 开箱封装 | 非技术用户双击启动，自动检查 LibreOffice | `start.ps1`、`start.bat`、`app/backend/env_check.py`、`app/README.md` | 缺 LibreOffice 时给安装/路径提示；已安装时自动打开本地网页 |
| V3J 对比展示与提效指标 | 用可视对比和数据证明工具价值 | `compare.html`、`metrics.json`、`report.json`、`使用说明.md`、演示样例输出 | 展示普通 PDF vs 学习版 PDF 差异、人工处理 vs 工具处理的时间节省、识别问题数、可复用成本 |
| V3K 路演交付 | 准备比赛演示材料和固定样例输出 | `demo/`、`samples/`、`docs/` 或根目录演示说明 | 3 分钟内演示：上传 PPTX -> 生成 base/guide/report/metrics -> 展示复杂页导读价值 |
| V4 AI 解释版 | 可选接入 AI，把页面内容解释和动画意图生成到独立输出 | `explanation_provider.py`、`ai_notes_builder.py`、前端模式开关 | 无 API 时入口不可用且说明原因；有 API 时解释必须引用 PPT 文本/备注来源 |

## V3G 执行细则

| 规则 | 定法 |
|---|---|
| 触发条件 | `unsupported_animation_count == 0`，动画步骤超过 5，且页面高重叠或高拥挤 |
| 输出方式 | 以 `base.pdf` 原页为底，`guide.pdf` 同页微调；不整页重画、不追加导读页 |
| 重排方式 | 先识别原页可用空白区，把遮挡前后的局部区域裁剪复用到清晰位置；空白不足时再缩放原页腾出侧边/底部展开区；用编号、箭头或关系线表达流程 |
| 禁止事项 | 不抽取文字重画整页；不承诺任意 PDF 语义对象可精确移动；不能可靠定位就写入报告 |
| 首个验收样例 | `app/samples/test.pptx`，目标是 `base.pdf` 2 页、`guide.pdf` 2 页；每页保留原画面主体面积不低于 85%；遮挡内容可独立看清且能看出先后关系 |

## 2026-05-14 二次纠偏：PDF 微调重排路线

| 层级 | 方案 | 结论 |
|---|---|---|
| 原生底座 | LibreOffice/Unoserver 生成 `base.pdf` | 继续保留，作为所有微调的画面来源 |
| PDF 主编辑 | PyMuPDF | 主攻：支持打开页面、绘制遮盖/文本/形状、复用页面裁剪区域、输出新 PDF |
| PDF 备选 | pypdf + reportlab | 可做覆盖层和页面合并，但局部编辑弱于 PyMuPDF |
| 坐标映射 | PPTX EMU 坐标 -> PDF points | 可行，需用 slide 宽高和 PDF page rect 建立线性映射 |
| 微调策略 | 空白优先放置、原页缩放让位、局部遮盖、局部复制、遮挡展开、流程箭头/关系线叠加 | 符合“保留原画面基础上的微调重排” |
| 不做 | 全量重画 PPT、从 PDF 反推高层对象、任意对象级精确搬移 | 技术风险高，容易伪造能力 |

## V3G 新开发顺序

| 顺序 | 任务 | 验收 |
|---|---|---|
| 1 | 新增 PDF 依赖检查，优先 PyMuPDF | 缺依赖时直接报错，不生成假重排 |
| 2 | 新增 `pdf_micro_reflow.py` | 输入 `base.pdf` + `augment_plan.json`，输出同页数 `guide.pdf` |
| 3 | 实现空白优先的放置决策 | 优先把遮挡展开内容放在原页空白处，放不下才缩放让位 |
| 4 | 实现 PPTX bbox 到 PDF 坐标映射 | `test.pptx` 的动画目标区域能映射到 PDF 上的正确矩形 |
| 5 | 实现局部遮盖、裁剪搬移和流程连接 | 被遮挡区域可在原页空白区或必要展开区独立看清，并能看出覆盖前后关系 |
| 6 | 实现页面裁剪复用 | 可把原 PDF 局部区域复制到旁注/放大框/流程节点，保持视觉来源 |
| 7 | 多轮视觉回归 `test.pptx` 和 Review 样例 | 页数不膨胀，原画面主体保留，复杂页可读性提升；至少反复调整布局到不遮挡、连线清晰、边距统一、视觉协调 |

## 路线取舍

| 不优先 | 原因 |
|---|---|
| 继续泛化更多动画类型 | `test.pptx` 已无 unsupported 动画；当前主要矛盾不是识别，而是复杂页在原画面上的微调表达 |
| 直接做 AI | 基础版还没把复杂动画路径稳定表达出来，AI 会掩盖结构问题 |
| 追加导读页 | 用户已明确认为多加导读页实际意义低；后续默认不新增页，改做 PDF 同页微调 |
| 泛化到任意 PPT 的完美重排 | 范围过大，先用 `test.pptx` 做有限规则闭环，再扩展样例 |
| 打包安装器 | 可放在一键启动脚本之后，不先做重型安装包 |

## 第一轮开发顺序
| 顺序 | 任务 | 结果 |
|---|---|---|
| 1 | 建立 `赛道3/app` 项目骨架 | 前后端目录、README、测试入口 |
| 2 | 实现 PPTX 文件校验和解包 | 拒绝非 PPTX，列出 slide XML |
| 3 | 解析每页文本、备注、对象层级 | 输出稳定 JSON |
| 4 | 基于现有 demo 模板生成学习型 HTML | 真实数据替换示例数据 |
| 5 | 接入浏览器 PDF 导出 | 得到真实 PDF 文件 |
| 6 | 加 1 个样例 PPTX 和测试 | 转换闭环可重复验证 |

## V2 已落地产物
| 模块 | 路径 | 说明 |
|---|---|---|
| PPTX 解析 | `赛道3/app/backend/pptx_parser.py` | 校验 `.pptx`，解析 slide XML、对象、备注、基础动画 |
| 讲义构建 | `赛道3/app/backend/study_builder.py` | 生成步骤、解释、遮挡 warning |
| HTML 渲染 | `赛道3/app/backend/html_renderer.py` | 输出学习型讲义页面 |
| PDF 渲染 | `赛道3/app/backend/pdf_renderer.py` | 调用本机 Edge/Chrome 打印 PDF |
| 转换编排 | `赛道3/app/backend/converter.py` | PPTX 到 JSON/HTML/PDF |
| 本地 Web | `赛道3/app/backend/server.py`、`赛道3/app/frontend` | 上传 `.pptx` 并下载结果 |
| CLI | `赛道3/app/backend/cli.py` | 命令行转换 |
| 测试 | `赛道3/app/tests/test_v2_pipeline.py` | 解析、重构、渲染、上传解析、转换闭环 |
| 样例 | `赛道3/app/samples/course_animation_occlusion.pptx` | 最小动画遮挡样例 |

## V2 验证记录
| 验证 | 结果 |
|---|---|
| 单元测试 | `python -m unittest discover -s '赛道3/app/tests'` 通过，6 个测试 |
| Python 编译 | `py_compile` 通过 |
| 前端 JS 语法 | `node --check '赛道3/app/frontend/app.js'` 通过 |
| CLI 端到端 | 样例 PPTX 成功输出 `study.json`、`study.html`、`study.pdf` |
| Web 健康检查 | `http://127.0.0.1:8765/api/health` 返回 200 |
| Web 上传转换 | `/api/convert` 成功返回 HTML/PDF/JSON URL |
| 页面截图 | `赛道3/app/workspace/v2_home.png` 成功生成 |
## 2026-05-16 当前路线状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| V3G 对象级微调重排 | 已落地 | `guide_deck.pptx` 先移动/缩放 PPTX 对象，再由 LibreOffice 转 `guide.pdf`。 |
| 遮挡诊断 | 已落地 | `reflow_diagnostics.py` 生成遮挡边，结合动画覆盖关系和几何重叠。 |
| 重排规划 | 已落地 | `object_reflow_planner.py` 按正文区/图片区排布，保留标题，避免空重排。 |
| 作者意图保护 | 已修正 | 无遮挡关系的图片/公式/图形默认不动，避免把整页视觉元素统一搬到右侧。 |
| 图文对应关系 | 已修正 | 相关公式/图片绑定到最近正文组，就近移动并组内避让，避免破坏原本讲解关系。 |
| 编号和公式稳定性 | 已修正 | 重排编号避让对象外侧；公式对象默认只平移不缩放。 |
| OLE 公式写回 | 已修正 | `graphicFrame` 外层与 fallback 内层坐标同步更新，LibreOffice 输出不再显示旧位置。 |
| OOXML 写回 | 已落地 | `ooxml_slide_editor.py` 直接编辑 shape 坐标和尺寸，并加流程编号。 |
| 样例验收 | 已完成 | `test.pptx`、`Review+chapter24-27.pptx` 均完成真实转换和截图抽查。 |
| 下一步 | 待做 | 清理历史 PDF 微重排表述，优化 `compare.html` 展示文案，准备比赛提交包和演示脚本。 |
## 2026-05-17 当前阶段补充
| 阶段 | 状态 | 说明 |
|---|---|---|
| OLE 公式稳定性 | 已修复 | 学习版 PDF 不再直接依赖 LibreOffice 对移动后 OLE 公式的渲染结果，改为 PPTX fallback 预览图覆盖。 |
| 图文组内避让 | 已修复 | 公式、图片、编号均进入占位避让；已移动图像会影响后续公式落位，避免新遮挡。 |
| 样例验收 | 已完成 | `sample/test.pptx` 真实 Web 输出已复核，最新 job 为 `9ab6c32e2d134133bae1456b317ecc64`。 |
| 下一步 | 待做 | 继续扩大样例集，针对更多 PPTX 里的公式类型、SmartArt、组合形状和矢量图做回归。 |
## 2026-05-17 路线防偏重修执行结果
| 阶段 | 状态 | 结果 |
|---|---|---|
| 路线契约 | complete | 已新增 `docs/reflow_route_contract.md`，明确局部修复、语义组不散、稳定对象不动、截图验收。 |
| 语义分组 | complete | 已新增 `app/backend/reflow_groups.py`，用动画覆盖关系建立正文、公式、图片的局部修复组。 |
| 局部修复 | complete | `object_reflow_planner.py` 已取消复杂页默认正文左栏化/图片右栏化，改为只移动遮挡关系里的对象并靠近语义锚点落位。 |
| 意图指标 | complete | `report.json` 已写入 `reflow_intent_check`，检查右栏化、左栏化和过大位移。 |
| 截图验收 | complete | 已新增 `app/tests/render_sample_reflow_check.py`，真实转换 `test.pptx` 并渲染 `base.pdf`/`guide.pdf` 前两页截图。 |
| 旧路线清理 | complete | 已移除旧 `legacy_pack_*` 包装函数，代码主线只保留局部文本修复和局部视觉修复，避免回退到全局分栏路线。 |

## 2026-05-18 局部重排关系线收口
| 阶段 | 状态 | 结果 |
|---|---|---|
| 漂移指标 | complete | `reflow_visual_check` 区分无锚点漂移和有锚点让位；`max_unexplained_move_ratio` 才触发移动过大告警。 |
| 关系线 | complete | `pdf_augmenter.py` 的重排关系线改为对象外缘到外缘连接，避免中心连线穿过正文。 |
| 单对象右移 | complete | 单个有语义锚点的公式右移不再计为系统性右栏化，`right_column_bias` 只描述多个视觉对象集中右移。 |
| 样例验收 | complete | `test.pptx` 新输出 `app/tests/.tmp_runs/reflow_visual_check/0d60abfdfcf9444288e5c415403d4289/`，两页 `reflow_intent_check.passed=true` 且 warnings 为空。 |
| 箭头安全距 | complete | 关系线端点新增目标外侧安全距离，避免 PowerPoint/PDF 箭头三角压住公式或图像。 |

## 2026-05-18 GIF/视频媒体处理阶段
| 阶段 | 状态 | 目标 |
|---|---|---|
| 媒体识别 | complete | 从 PPTX slide 关系和 `a:blip` 中识别 GIF/视频素材，绑定到原始对象 bbox。 |
| GIF 可读化 | complete | 导出原始 GIF，抽取关键帧，生成 `media_manifest.json`、poster 和关键帧 strip。 |
| PDF 原位替换 | complete | 在 `guide.pdf` 原 GIF bbox 内用关键帧宫格替换封面图，不移动无关图文，不做全局右栏堆放。 |
| Web 输出 | complete | 下载区暴露媒体清单和导出素材，让评委能追溯原始动态内容。 |
| 真实样例验收 | complete | 使用用户已加入 GIF 的 `app/samples/test.pptx` 转换并截图审查。 |

## 2026-05-18 GIF/视频媒体处理执行结果
| 项目 | 结果 |
|---|---|
| GIF 识别 | `test.pptx` 第 3 页 `ppt/media/image6.gif` 被识别为动态媒体，保留原图位置。 |
| 媒体导出 | 输出 `media_manifest.json`、原始 GIF、poster、6 帧关键帧 strip。 |
| PDF 表达 | `guide.pdf` 第 3 页在原 GIF 区域直接替换为 6 张关键帧宫格，标题不动，不额外占底部空白。 |
| 视频边界 | 已识别并导出视频/音频原文件；关键帧摘要留给后续 ffmpeg 接入，不伪造视频帧。 |
| 验证 | `python -m unittest discover -s app\tests` 76 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过。 |

## 2026-05-19 GIF 宫格自适应放大
| 项目 | 结果 |
|---|---|
| 目标 | 小 GIF 不再被原始图片尺寸限制导致关键帧过小。 |
| 策略 | 原 bbox 作为语义锚点，宫格可向周边空白扩展；扩展必须包含原 bbox，且避让同页 `occupied_boxes`。 |
| 回退 | 无安全空白时退回原 bbox，不硬挤压标题、正文或其它图形。 |
| 验收 | `test.pptx` 当前 4 页、2 个 GIF；第 4 页小 GIF 宫格已放大，第 3 页大 GIF 不被无意义放大。 |
| 验证 | `python -m unittest discover -s app\tests` 77 项通过；`python -m compileall app\backend` 通过；`node --check app\frontend\app.js` 通过。 |

## 2026-05-20 项目瘦身与旧路线清理
| 阶段 | 状态 | 边界 |
|---|---|---|
| tracked 生成物清理 | complete | 删除已纳入 git 的 `.pyc/__pycache__` 文件；`.gitignore` 已覆盖，源码与测试不依赖。 |
| 旧 HTML 打印 PDF 路线 | complete | 删除无引用的 `app/backend/pdf_renderer.py`；当前主线继续由 LibreOffice 生成 `base.pdf`，再生成 `guide.pdf`。 |
| 追加导读页旧分支 | complete | 删除 `expand_after_native`、新幻灯片追加、整页重画 `reflow_page` 等旧代码；保留输出中的 `guide_pages: []` 和 `guide_page_count=0` 用于验收。 |
| 暂不删除项 | pending | `demo/`、历史规划文档、`pdf_micro_reflow.py`、核心样例 PPTX 仍和比赛展示/历史路线/回归有关，未经确认不删。 |
| 验收 | complete | 单测 81 项、后端编译、前端 JS 语法检查通过；已重启 8765 并真实转换 `app/samples/test.pptx`。 |

## 2026-05-21 渲染门禁与公式修复执行结果
| 阶段 | 状态 | 结果 |
|---|---|---|
| 渲染门禁 | complete | `report.json` 写入 `render_visual_check`，并输出重点页截图目录。 |
| 公式修复链路 | complete | 移动公式按 fallback 预览等比绘制；稳定公式只在最终渲染检测失败时修复。 |
| 错误重排拦截 | complete | 对象重排新增质量门禁，重排不能降低真实重叠时不落地。 |
| 空间不足缩放 | complete | 重排失败且页底拥挤时采用整页轻微缩放，保留原页面关系。 |
| 最新验收 | complete | `test.pptx` 与 `Review+chapter24-27.pptx` 最新转换的渲染门禁均通过。 |
| 后续 | pending | 继续扩大真实课件样本，针对仍可能存在的非黄色公式、组合图形和 SmartArt 做视觉门禁补充。 |

## 2026-05-21 追加收口
| 阶段 | 状态 | 结果 |
|---|---|---|
| 组合公式解析 | complete | 组合内 `graphicFrame` 可解析、可移动，Review 第 4 页公式与相关图形不再互挡。 |
| 行内公式保护 | complete | Review 第 22 页带制表占位的公式保持原位，不再被重排拆散。 |
| fallback 可用性 | complete | 稳定公式只在预览图可用时覆盖，Review 第 28 页恢复正常公式显示。 |
| 渲染门禁校准 | complete | 公式拥挤检测保留真实叠压识别，同时放过正常分式横线。 |
| 最新验收 | complete | `test=027b583b047646b68e882e9483b85593`，`review=589f1b6da5984629907ea69494666f61`，两者 `render_visual_check.passed=true`。 |

## 2026-05-22 残留排版问题收口
| 阶段 | 状态 | 结果 |
|---|---|---|
| 第 36 页电阻错乱定位 | complete | 根因是对象级重排拆散电路图小图元，不是公式或 PDF 渲染问题。 |
| 图元碎片化门禁 | complete | 大量小图元移动且缺少长文本锚点时拒绝落地，Review 第 36 页不再对象重排。 |
| 第 23 页短条件拆行定位 | complete | 根因是短数学条件文本框被 LibreOffice 自动换行。 |
| 单行数学文本保护 | complete | 对短比较式文本设置不换行，并在安全空隙内扩宽文本框。 |
| 回归测试 | complete | 新增 Review 第 36 页电路图不重排、Review 第 23 页短数学文本不换行、稳定公式可用预览修复测试。 |
| 最新验收 | complete | `test=a03c2c3d9d8149809e936ea33b80c898`，`review=5ee2eb6737df49ae993921331840564d`；完整 `render_visual_check.passed=true`，已查看第 23/36 页截图。 |
## 2026-05-22 V4 块级 AI Agent 规划
| 阶段 | 状态 | 目标 |
|---|---|---|
| V4A 知识块索引 | complete | 已生成 `knowledge_blocks.json`，支持正文、公式组、图示组、媒体时间线、动画流程等块 |
| V4B Web 块级交互 | complete | Web 已按页展示知识块，支持单块解释按钮和多选组合讲解 |
| V4C AI 解释 Agent | complete | 已接入 `/api/ai/explain` 与 `/api/ai/compose`；API key 只在当前请求使用，不写输出 |
| V4D 来源审计与缓存 | complete | AI 结果必须带合法来源；缓存解释结果和用量，不缓存 key |
| V4E AI 融合 PDF | complete | 已支持把已生成的块级解释导出为独立 `ai_guide.pdf`，不覆盖 `base.pdf` 和 `guide.pdf` |
| V4F 比赛包装 | pending | 在 `compare.html` 展示块级解释、token 节省、可追溯来源和可选 AI PDF |

详细执行计划见 `docs/superpowers/plans/2026-05-22-block-level-ai-agent.md`。

## 2026-05-23 V5 AI 阅读器 UI 重构计划
| 阶段 | 状态 | 目标 |
|---|---|---|
| V5A Guide 预览主视图 | complete | Web Preview 默认展示 `guide.pdf` 页图，并生成 `guide_preview_manifest.json` |
| V5B 内容驱动知识块 | complete | 知识块按文字/图/媒体内容去重，动画只作为 `animation_refs` 证据，不再重复生成相同块 |
| V5C 页图 Overlay 选择 | complete | 用户直接在 guide 页图上点选知识块，选中态可视化显示 |
| V5D 单块 AI 队列 | complete | 每个块单独请求 AI；“发送本页”逐块排队，不做整页合并 prompt |
| V5E 整页兜底 | complete | 分块不可靠时生成唯一 `whole_page` 块，支持页级最小上下文解释 |
| V5F 侧栏锚定解释 | complete | AI 解释显示在当前页右侧并对应原文块，不再堆到页面底部 |
| V5G AI 解释版预留 | complete | 顶栏 `AI 解释版` 在 `ai_guide.pdf` 生成后启用，不覆盖 `guide.pdf` |

详细执行计划见 `docs/superpowers/plans/2026-05-23-ai-guide-reader-ui.md`。

## 2026-05-24 V5H 简单 AI PDF 导出
| 阶段 | 状态 | 目标 |
|---|---|---|
| 后端导出器 | complete | 复制 `guide.pdf`，在有解释的源页后插入 AI 解释页，输出 `ai_guide.pdf` 与 `ai_guide_manifest.json` |
| Web 导出接口 | complete | `/api/ai/export-guide` 只接收 `job_id` 和已生成解释，不接收 API key |
| 前端按钮 | complete | AI 解释生成后启用“生成 AI PDF”，成功后顶部 `AI 解释版` 下载入口变为可用 |
| 后续排版路线 | complete | 已写入 `docs/superpowers/plans/2026-05-24-ai-pdf-layout-route.md` |

## 2026-05-24 V5I 多角色整页视觉 AI
| 阶段 | 状态 | 目标 |
|---|---|---|
| Prompt 角色 | complete | 支持学习讲义版、工作培训版、简单解释版三种角色，前端可选，后端进入缓存键 |
| 视觉输入 | complete | AI 可接收 `guide.pdf` 渲染后的整页图或块裁剪图，不直接解析原始 PPT 图片 |
| 整页解释 | complete | “发送本页”改为一次整体解释请求，避免逐块排队造成整页语义割裂 |
| 块级解释 | complete | 单块解释仍保持单块请求，并可附带对应块的 guide 裁剪图 |
| AI PDF 导出 | complete | 页级解释和块级解释都可进入 `ai_guide.pdf`，导出前继续做来源审计 |
| 验证收口 | complete | 全量测试、重启 8765、真实样例转换和本地 provider 冒烟均已通过 |

## 2026-05-25 V5J 规则分组与 Web 交互收口
| 阶段 | 状态 | 目标 |
|---|---|---|
| 规则分组 | complete | 不接 AI 语义分组；修复唯一大文本框被当标题跳过、标题单独成块、公式/电路图/短标签过碎 |
| Overlay 交互 | complete | 不同块用不同颜色；重叠命中时展示候选，不再只能点最上层 |
| AI 失败重试 | complete | AI 报错后保留当前块和重试入口，用户可换模型/关闭图片后再次发起 |
| LaTeX 展示 | complete | AI 返回的 LaTeX 在 Web 中用 MathJax 可视化，仍保持文本安全写入 |
| 验收 | complete | 定向单测、全量测试、前端语法、Review 样例转换、关键页截图检查均完成 |

详细执行计划见 `docs/superpowers/plans/2026-05-25-rule-based-knowledge-blocks.md`。

## 2026-05-25 V5K 用户测试问题收口
| 阶段 | 状态 | 目标 |
|---|---|---|
| 问题报告去噪 | complete | Web 主界面移除长问题报告，内部 report/debug 输出保留给定位 |
| 动画证据绑定 | complete | 动画不再生成抢占内容的独立块，只挂到相关内容块的 `animation_refs` |
| AI 错误提示 | complete | 非 JSON 模型响应不再裸露 `Expecting value`，改为可操作中文错误 |
| 公式渲染约束 | complete | prompt 要求公式使用 MathJax 定界符，并升级 prompt 版本避开旧缓存 |
| 验收 | complete | 全量测试、重启服务、Review 样例重新转换和关键页截图检查完成 |

## 2026-05-25 V5L 用户二测问题收口
| 阶段 | 状态 | 目标 |
|---|---|---|
| 非 JSON 讲解展示 | complete | 模型返回普通文本时不再中断，按低置信纯文本解释展示并保留来源 |
| 目录页框选修正 | complete | 连续编号目录页 overlay 框覆盖实际渲染文字，不漏第 5 条 |
| 多角色重讲 | complete | 同一块按 `prompt_profile` 保存多份解释，卡片提供其它角色再讲入口 |
| 验收 | complete | 全量测试、重启服务、Review 样例重新转换和关键页检查完成 |

## 2026-05-25 V5M 整页解释版本切换
| 阶段 | 状态 | 目标 |
|---|---|---|
| 整页多角色重讲 | complete | 整页解释按 `page_number + prompt_profile` 保存多份解释，整页卡片提供其它角色再讲/查看入口 |
| 验收 | complete | `python -m unittest discover app\tests` 172 项、前端语法和 diff 空白检查通过 |
