# Slide2Study V3G

## 目标
将真实 `.pptx` 原生转换为 `base.pdf`，同时输出学习版 `guide.pdf`、`compare.html`、`analysis.json`、`augment_plan.json`、`metrics.json` 和问题报告。当前路线为 V3G PDF 微调重排：`guide.pdf` 必须以 `base.pdf` 原页面为画面来源，优先利用原页空白放置被遮挡内容，空白不足时才缩放让位，并用编号、箭头或关系线表达流程。

## 一键启动
```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

或：
```bat
start.bat
```

## 启动 Web
```powershell
python .\app\backend\server.py
```

打开：
```text
http://127.0.0.1:8765
```

## 可用样例
| 文件 | 用途 |
|---|---|
| `samples/native_conversion_smoke.pptx` | 原生转换验收样例，可生成 `base.pdf` |
| `samples/animation_guide_smoke.pptx` | 简单动画轻增强验收样例 |
| `samples/course_animation_occlusion.pptx` | 早期解析器单测样例，结构极简，不用于 LibreOffice 原生转换验收 |
| `samples/test.pptx` | 综合回归样例，覆盖多种场景，V3G 优先用于复杂页重排验收 |

## 命令行转换
```powershell
python .\app\backend\cli.py .\app\samples\native_conversion_smoke.pptx .\app\workspace\outputs\manual
```

指定 LibreOffice 路径：
```powershell
python .\app\backend\cli.py .\path\to\deck.pptx .\app\workspace\outputs\manual --soffice-path "C:\Program Files\LibreOffice\program\soffice.exe"
```

只生成报告和预览：
```powershell
python .\app\backend\cli.py .\path\to\deck.pptx .\app\workspace\outputs\manual --no-pdf
```

## 输出文件
| 文件 | 用途 |
|---|---|
| `base.pdf` | LibreOffice 原生转换结果，对照组 |
| `guide.pdf` | 学习版 PDF，保留原画面并做 PDF 层微调 |
| `compare.html` | 比赛展示页，并排对比普通 PDF 和学习版 PDF |
| `analysis.json` | 页面对象、动画、遮挡、拥挤度分析 |
| `augment_plan.json` | 重排和遮挡展开计划 |
| `metrics.json` | 运行耗时、问题数、人工整理时间估算 |
| `report.json` | 能力边界和问题报告 |
| `preview.html` | 结构化预览 |

## V3G 支持范围
| 能力 | 状态 |
|---|---|
| `.pptx` 结构校验 | 支持 |
| 文本、图片、形状对象读取 | 支持基础对象 |
| 备注读取 | 支持 notesSlide |
| 基础动画顺序 | 支持 fade、wipe、appear、blinds、wheel in/out、明确的 x/y 位置移动 |
| 遮挡检测 | 支持基于边界框和层级的检测 |
| `analysis.json` | 支持页面尺寸、覆盖率、重叠率、空白率、文本密度、拥挤度、策略提示 |
| `augment_plan.json` | 支持动画导读计划、页数预算、策略原因、遮挡展开和空白优先放置 |
| 原生 `base.pdf` 导出 | 依赖本机 LibreOffice `soffice` |
| 学习版 `guide.pdf` | 低拥挤动画页轻标注；复杂支持动画页走 PDF 微调重排；默认不追加旁白式导读页 |
| `compare.html` / `metrics.json` | 支持 |

## 边界
不支持 `.ppt`、Keynote、复杂触发器、音视频、路径动画和交互按钮。遇到不支持动画会写入问题报告，不静默降级。
