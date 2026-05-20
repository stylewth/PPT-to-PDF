# 样例输出索引

| 样例 | 输出目录 | 说明 |
|---|---|---|
| 用户综合样例 `test.pptx` | `app/tests/.tmp_runs/final_product_test` | 最终视觉验收样例，含 `base.pdf`、`guide.pdf`、`compare.html`、`metrics.json`。 |
| 42 页 Review 课件 | `app/tests/.tmp_runs/acceptance3_review_chapter24_27` | 大课件验收样例，42 页真实转换通过，27 页触发 PDF 微调重排。 |
| 动画烟测 | `app/tests/.tmp_runs/acceptance2_animation_guide_smoke` | 单页基础动画链路验收。 |
| 遮挡动画烟测 | `app/tests/.tmp_runs/acceptance2_course_animation_occlusion` | 单页遮挡关系验收。 |
| 原生转换烟测 | `app/tests/.tmp_runs/acceptance2_native_conversion_smoke` | LibreOffice 原生转换基础验收。 |

最终参赛展示优先打开：

1. `app/tests/.tmp_runs/final_product_test/compare.html`
2. `app/tests/.tmp_runs/final_product_test/guide.pdf`
3. `app/tests/.tmp_runs/final_product_test/metrics.json`
4. `app/tests/.tmp_runs/acceptance3_review_chapter24_27/metrics.json`
