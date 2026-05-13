# Slide2Study V3D

## 目标
将真实 `.pptx` 原生转换为 `base.pdf`，同时输出带动画导读增强的 `guide.pdf`、`analysis.json`、`augment_plan.json`、问题报告和本地预览。当前已完成 V3D 止损热修：细小动画只在原生页加入编号锚点，不额外加页；复杂或不支持动画页先进入报告，不硬生成低价值导读页。

## 启动 Web
```powershell
python .\赛道3\app\backend\server.py
```

打开：
```text
http://127.0.0.1:8765
```

## 可用样例
| 文件 | 用途 |
|---|---|
| `samples/native_conversion_smoke.pptx` | 原生转换验收样例，可生成 `base.pdf` |
| `samples/animation_guide_smoke.pptx` | 动画导读验收样例，可生成含导读页的 `guide.pdf` |
| `samples/course_animation_occlusion.pptx` | 早期解析器单测样例，结构极简，不用于 LibreOffice 原生转换验收 |

## 命令行转换
```powershell
python .\赛道3\app\backend\cli.py .\赛道3\app\samples\native_conversion_smoke.pptx .\赛道3\app\workspace\outputs\manual
```

指定 LibreOffice 路径：
```powershell
python .\赛道3\app\backend\cli.py .\path\to\deck.pptx .\赛道3\app\workspace\outputs\manual --soffice-path "C:\Program Files\LibreOffice\program\soffice.exe"
```

只生成报告和预览：
```powershell
python .\赛道3\app\backend\cli.py .\path\to\deck.pptx .\赛道3\app\workspace\outputs\manual --no-pdf
```

## V3D 支持范围
| 能力 | 状态 |
|---|---|
| `.pptx` 结构校验 | 支持 |
| 文本、图片、形状对象读取 | 支持基础对象 |
| 备注读取 | 支持 notesSlide |
| 基础动画顺序 | 支持 fade、wipe、appear |
| 遮挡检测 | 支持基于边界框和层级的检测 |
| `analysis.json` | 支持页面尺寸、覆盖率、重叠率、空白率、文本密度、拥挤度、策略提示 |
| `augment_plan.json` | 支持动画导读计划、页数预算、策略原因、原页行内标记坐标 |
| 原生 `base.pdf` 导出 | 依赖本机 LibreOffice `soffice` |
| 动画导读 `guide.pdf` | 低拥挤动画页保持 1 页并叠加编号锚点；复杂页先 `report_only`，避免导读页泛滥 |
| `preview.html` | 支持 |

## 边界
不支持 `.ppt`、Keynote、复杂触发器、音视频、路径动画和交互按钮。遇到不支持动画会写入问题报告，不静默降级。
