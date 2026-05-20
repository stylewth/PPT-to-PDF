# Route Drift Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. It will decide whether each batch should run in parallel or serial subagent mode and will pass only task-local context to each subagent. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop route drift by replacing global page repacking with semantic-group local repair, so `guide.pdf` preserves PPT author intent while only fixing unreadable occlusion areas.

**Architecture:** Add a route contract and intent checks first, then split object reflow into grouping, local repair planning, intent scoring, visual verification, and report output. Existing `object_reflow_planner.py` should become an orchestrator instead of a global layout packer.

**Tech Stack:** Python stdlib, existing PPTX parser/analyzer, existing OOXML slide editor, LibreOffice conversion, PyMuPDF rendering for screenshot verification, existing `unittest` test suite.

---

## Non-Negotiable Contract

| Rule | Meaning |
|---|---|
| Local repair only | Do not repack the whole slide unless a whole-slide policy is explicitly approved later. |
| Author intent first | Preserve original text, formula, image relative relationships before chasing visual balance. |
| Stable objects stay stable | Objects not in severe overlap or animation coverage remain in place. |
| Groups move together | A related text/formula/image group may adjust internally, but should not scatter across the page. |
| Clear beats decorative | If relation cannot be preserved automatically, perform the smallest reliable move and report the limitation. |
| Screenshot decides | Unit tests and JSON metrics are necessary but not sufficient; `base.pdf` vs `guide.pdf` screenshot must pass. |

## Files

| File | Role |
|---|---|
| `docs/reflow_route_contract.md` | Project-level route contract and visual acceptance checklist. |
| `app/backend/reflow_groups.py` | New semantic grouping module: build local repair groups from overlap graph, animation coverage, bbox proximity, and text/visual roles. |
| `app/backend/object_reflow_planner.py` | Refactor into orchestration: choose candidates, call grouping, call local repair, output operations. Remove global left-column/right-column packing as default. |
| `app/backend/reflow_diagnostics.py` | Keep overlap graph; add small helper only if grouping needs explicit overlap edge lookup. |
| `app/backend/reflow_visual_check.py` | New deterministic checker for movement distance, group distance, right-column/left-column bias, overlap, and screenshot artifact paths. |
| `app/backend/converter.py` | Include visual check summary in output report after conversion. |
| `app/tests/test_v3_reflow_groups.py` | New tests for semantic grouping and author-intent preservation. |
| `app/tests/test_v3_object_reflow.py` | Replace brittle global layout expectations with local repair contract tests. |
| `app/tests/test_v3_reflow_visual_check.py` | New tests for route-drift metrics and screenshot check outputs. |
| `task_plan.md`, `findings.md`, `progress.md`, `lessons.md` | Keep route, findings, and user correction memory synchronized. |

## Phase 1: Route Contract And Guardrails

- [x] **Step 1: Create `docs/reflow_route_contract.md`**

Write the route contract in plain Chinese:

```markdown
# 重排路线契约

## 北极星
学习版 PDF 保留原 PPT 页面意图，只对遮挡、拥挤、动画终态不可读区域做局部微调。

## 红线
| 红线 | 判定 |
|---|---|
| 禁止全局左栏化 | 正文组不能被统一推到页面左侧形成新栏目。 |
| 禁止全局右栏化 | 图片/公式不能默认集中到右侧展示栏。 |
| 禁止语义组散开 | 同一段文字对应的图、公式、结论必须保持近邻关系。 |
| 禁止只看不重叠 | 不重叠但关系断裂也算失败。 |
| 禁止旧 job 验收 | 每次后端改动后必须重启服务并重新转换 `app/samples/test.pptx`。 |

## 每轮验收
1. 运行单测。
2. 重启 8765。
3. 转换 `app/samples/test.pptx`。
4. 渲染 `base.pdf` 和 `guide.pdf` 前两页截图。
5. 人眼检查：更清楚、更少移动、关系没断。
```

- [x] **Step 2: Add route-drift lessons**

Append to `lessons.md`:

```markdown
| 2026-05-17 | 后续重排必须先通过路线契约：局部修复、语义组不散、稳定对象不动、截图人工验收；几何不重叠不能单独算成功。 |
```

- [x] **Step 3: Record plan status**

Append to `task_plan.md`:

```markdown
## 2026-05-17 路线防偏重修
| 阶段 | 状态 | 目标 |
|---|---|---|
| 路线契约 | pending | 把“局部语义组修复”写成硬约束。 |
| 语义分组 | pending | 先知道哪些图/公式/文字是一组，再决定谁移动。 |
| 局部修复 | pending | 只在遮挡组附近找位置，禁止整页重排。 |
| 视觉验收 | pending | 每次真实转换后截图对比，截图不合格不算完成。 |
```

## Phase 2: Semantic Grouping Before Layout

- [x] **Step 1: Write failing grouping tests**

Create `app/tests/test_v3_reflow_groups.py`:

```python
import unittest

from app.backend.reflow_groups import build_reflow_groups


class V3ReflowGroupsTest(unittest.TestCase):
    def test_groups_formula_with_covering_text_anchor(self):
        slide = {
            "size": {"width": 12192000, "height": 6858000},
            "object_boxes": [
                {"id": "body", "type": "sp", "text": "Capacitance explanation", "bbox": {"x": 2000000, "y": 2200000, "w": 6000000, "h": 1100000}},
                {"id": "formula", "type": "graphicFrame", "text": "", "bbox": {"x": 5100000, "y": 2300000, "w": 1200000, "h": 900000}},
                {"id": "title", "type": "sp", "text": "(2) Capacitance", "bbox": {"x": 4300000, "y": 1100000, "w": 3700000, "h": 520000}},
            ],
            "animation_steps": [
                {
                    "target_id": "formula",
                    "covered_objects": [
                        {"id": "body", "text": "Capacitance explanation", "bbox": {"x": 2000000, "y": 2200000, "w": 6000000, "h": 1100000}}
                    ],
                }
            ],
        }

        groups = build_reflow_groups(slide)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["anchor_id"], "body")
        self.assertEqual(groups[0]["visual_ids"], ["formula"])
        self.assertNotIn("title", groups[0]["member_ids"])

    def test_keeps_unrelated_visual_out_of_group(self):
        slide = {
            "size": {"width": 12192000, "height": 6858000},
            "object_boxes": [
                {"id": "body", "type": "sp", "text": "First paragraph", "bbox": {"x": 2000000, "y": 2000000, "w": 5000000, "h": 900000}},
                {"id": "cover", "type": "sp", "text": "Cover", "bbox": {"x": 2100000, "y": 2050000, "w": 4500000, "h": 700000}},
                {"id": "unrelated_pic", "type": "pic", "text": "", "bbox": {"x": 8200000, "y": 900000, "w": 2000000, "h": 1200000}},
            ],
            "animation_steps": [
                {"target_id": "cover", "covered_objects": [{"id": "body", "text": "First paragraph", "bbox": {"x": 2000000, "y": 2000000, "w": 5000000, "h": 900000}}]}
            ],
        }

        groups = build_reflow_groups(slide)

        self.assertEqual(groups[0]["member_ids"], ["body", "cover"])
        self.assertNotIn("unrelated_pic", groups[0]["member_ids"])
```

- [x] **Step 2: Implement `app/backend/reflow_groups.py`**

Implement only deterministic grouping:

```python
from __future__ import annotations

from typing import Any


VISUAL_TYPES = {"pic", "graphicFrame", "cxnSp"}


def build_reflow_groups(slide: dict[str, Any]) -> list[dict[str, Any]]:
    objects = _objects_by_id(slide)
    groups: dict[str, dict[str, Any]] = {}
    for step in slide.get("animation_steps", []):
        target_id = str(step.get("target_id") or "")
        target = objects.get(target_id)
        for covered in step.get("covered_objects", []):
            anchor_id = str(covered.get("id") or "")
            anchor = objects.get(anchor_id)
            if anchor is None:
                continue
            group = groups.setdefault(anchor_id, _new_group(anchor))
            if target is not None:
                _add_member(group, target)
    return list(groups.values())


def _new_group(anchor: dict[str, Any]) -> dict[str, Any]:
    return {
        "anchor_id": anchor["id"],
        "member_ids": [anchor["id"]],
        "text_ids": [anchor["id"]] if _has_text(anchor) else [],
        "visual_ids": [],
        "bbox": dict(anchor["bbox"]),
    }


def _add_member(group: dict[str, Any], obj: dict[str, Any]) -> None:
    object_id = obj["id"]
    if object_id in group["member_ids"]:
        return
    group["member_ids"].append(object_id)
    if _has_text(obj):
        group["text_ids"].append(object_id)
    if obj.get("type") in VISUAL_TYPES:
        group["visual_ids"].append(object_id)
    group["bbox"] = _union(group["bbox"], obj["bbox"])


def _objects_by_id(slide: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in slide.get("object_boxes", []):
        if not item.get("bbox"):
            continue
        result[str(item.get("id") or "")] = {
            "id": str(item.get("id") or ""),
            "type": item.get("type", ""),
            "text": item.get("text", ""),
            "bbox": {key: int(item["bbox"][key]) for key in ("x", "y", "w", "h")},
        }
    return result


def _has_text(obj: dict[str, Any]) -> bool:
    return bool(str(obj.get("text") or "").strip())


def _union(first: dict[str, int], second: dict[str, int]) -> dict[str, int]:
    left = min(first["x"], second["x"])
    top = min(first["y"], second["y"])
    right = max(first["x"] + first["w"], second["x"] + second["w"])
    bottom = max(first["y"] + first["h"], second["y"] + second["h"])
    return {"x": left, "y": top, "w": right - left, "h": bottom - top}
```

- [x] **Step 3: Run grouping tests**

Run:

```powershell
python -m unittest app.tests.test_v3_reflow_groups
```

Expected: `OK`.

## Phase 3: Replace Global Packing With Local Repair

- [x] **Step 1: Write local repair tests in `app/tests/test_v3_object_reflow.py`**

Add tests that fail on the current implementation:

```python
def test_test_sample_does_not_push_charge_diagram_to_left_margin(self):
    sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
    slide = analyze_presentation(parse_pptx(sample))["slides"][0]
    plan = plan_object_reflow(slide)
    after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}
    before = {str(item["id"]): item["bbox"] for item in slide["object_boxes"]}

    self.assertGreater(after["4"]["x"], before["21"]["x"] - 800000)
    self.assertLess(abs(after["4"]["y"] - before["4"]["y"]), 1200000)


def test_test_sample_preserves_visual_group_proximity(self):
    sample = Path(__file__).resolve().parents[1] / "samples" / "test.pptx"
    slide = analyze_presentation(parse_pptx(sample))["slides"][0]
    plan = plan_object_reflow(slide)
    after = {item["id"]: item["bbox"] for item in simulate_operations(slide["object_boxes"], plan["operations"])}

    paragraph = after["21"]
    diagram = after["4"]
    formula = after["23"]

    self.assertLess(_center_distance(diagram, paragraph), 4800000)
    self.assertLess(_center_distance(formula, paragraph), 5200000)
```

- [x] **Step 2: Add helper `_center_distance` in tests if missing**

```python
def _center_distance(first: dict[str, int], second: dict[str, int]) -> float:
    return abs(first["x"] + first["w"] / 2 - second["x"] - second["w"] / 2) + abs(
        first["y"] + first["h"] / 2 - second["y"] - second["h"] / 2
    )
```

- [x] **Step 3: Modify `object_reflow_planner.py` orchestration**

Change policy:

| Current | New |
|---|---|
| Collect all candidate text, pack into a column | Build repair groups first |
| Pack loose visuals into right column | Loose visuals stay in place unless directly overlapping |
| Associated visuals chase moved text | Group repair chooses smallest internal move |

Implementation target:

```python
from reflow_groups import build_reflow_groups


def _pack_candidates(...):
    groups = build_reflow_groups({"object_boxes": candidates + stable, "animation_steps": ...})
    if groups:
        return _repair_groups(groups, candidates, stable, page_width, page_height)
    return _repair_direct_overlaps(candidates, stable, page_width, page_height)
```

Do not keep `_pack_text_candidates` as default for complex pages. Keep it only behind an explicit fallback name such as `_legacy_global_pack_candidates`, and do not call it for `test.pptx`.

- [x] **Step 4: Implement local repair rules**

Inside `object_reflow_planner.py`, implement:

```python
def _repair_group(group, by_id, stable, page_width, page_height):
    # 1. Prefer moving the front visual that causes occlusion.
    # 2. Candidate positions are near original bbox: below, above, right, left, slight offset.
    # 3. Reject candidates that overlap stable objects or move too far from anchor.
    # 4. If no visual candidate works, move the minimum text object inside group.
```

Acceptance:

```powershell
python -m unittest app.tests.test_v3_object_reflow
```

Expected: all tests pass, and old right-column/left-margin behavior is gone.

## Phase 4: Route-Drift Metrics

- [x] **Step 1: Create `app/backend/reflow_visual_check.py`**

Expose:

```python
def check_reflow_intent(before_boxes, after_boxes, operations, page_size):
    return {
        "right_column_bias": ...,
        "left_column_bias": ...,
        "max_move_ratio": ...,
        "group_distance_warnings": [...],
        "passed": ...
    }
```

Rules:

| Metric | Fail Condition |
|---|---|
| right_column_bias | More than 60% moved visuals have center x beyond page 70%. |
| left_column_bias | More than 60% moved text objects have center x before page 35%. |
| max_move_ratio | Any non-cover object moves more than 35% page width without group reason. |
| group_distance | Related formula/image center distance from anchor exceeds 45% page width. |
| stable_motion | Objects outside repair group have operations. |

- [x] **Step 2: Add tests**

Create `app/tests/test_v3_reflow_visual_check.py` with one passing local-repair sample and one failing artificial right-column sample.

- [x] **Step 3: Include check in conversion report**

Modify `converter.py` so `report.json` includes:

```json
"reflow_intent_check": {
  "passed": true,
  "warnings": []
}
```

## Phase 5: Real Screenshot Verification Loop

- [x] **Step 1: Add script `app/tests/render_sample_reflow_check.py`**

Script behavior:

1. Convert `app/samples/test.pptx`.
2. Render `base.pdf` and `guide.pdf` page 1 and 2 to PNG.
3. Save to `app/tests/.tmp_runs/reflow_visual_check/<job_id>/`.
4. Print file paths and route-drift check summary.

- [x] **Step 2: Manual visual checklist**

For page 1:

| Check | Must Pass |
|---|---|
| Title | Stays centered and unchanged. |
| First paragraph | More readable than base and not forced into left column. |
| Top diagram | Still near top paragraph. |
| Yellow formula | Near first paragraph or local blank, not floating as a separate poster. |
| Lower charge diagram | Near lower paragraph, not left-margin isolated. |
| Green formula | Near lower paragraph and readable. |
| Sequence marks | Do not cover object details; show relation or group order. |

For page 2:

| Check | Must Pass |
|---|---|
| Formula | Clear, not clipped, and not above title unless it was originally a title-level object. |
| Text | No new wrapping collisions. |
| Units | Remain readable and aligned. |

## Phase 6: Clean Up Old Route Drift

- [ ] **Step 1: Rename legacy functions**

In `object_reflow_planner.py`, rename old global packers:

| Old | New |
|---|---|
| `_pack_text_candidates` | `_legacy_pack_text_column` |
| `_pack_loose_visuals` | `_legacy_pack_visual_right_column` |

Do this only after local repair is passing, so future readers cannot accidentally treat legacy column packing as the main algorithm.

- [x] **Step 2: Update docs**

Update:

| File | Change |
|---|---|
| `task_plan.md` | Mark route-drift repair phases complete as they land. |
| `findings.md` | Record every route drift found by screenshot. |
| `progress.md` | Record job id, screenshots, test commands. |
| `lessons.md` | Add any new failure pattern immediately. |

## Stop Conditions

| Condition | Action |
|---|---|
| Local repair cannot keep semantic group together | Stop and report limitation; do not fall back to global scatter layout. |
| A visual object must move more than 35% page width | Prefer keeping it near original and adding a small callout; if still unreadable, report as manual review. |
| Screenshot is worse than base page | Revert that algorithm step and narrow the repair scope. |
| Tests pass but screenshot fails | Screenshot wins. Add a failing route-intent test before continuing. |

## Final Acceptance

| Item | Command / Evidence |
|---|---|
| Unit tests | `python -m unittest discover -s app\tests` passes. |
| Compile | `python -m compileall app\backend` passes. |
| Frontend | `node --check app\frontend\app.js` passes. |
| Real conversion | `app/samples/test.pptx` generates `base.pdf`, `guide.pdf`, `compare.html`, `report.json`. |
| Screenshot | Page 1 and 2 screenshots stored under `app/tests/.tmp_runs/reflow_visual_check/<job_id>/`. |
| Human route review | The learning PDF is clearer than ordinary PDF and does not look like a scattered reconstruction. |
