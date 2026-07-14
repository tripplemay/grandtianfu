# decor-b3-fix 验收报告（verifying, 首轮）— 2026-07-14

> 批次：`decor-b3-fix` ｜ 阶段：verifying（fix_rounds=0，首轮）
> Evaluator：隔离 fresh-context subagent（署名 local/evaluator-subagent）
> 验收对象：features.json F001「轴测校验豁免贴墙软装（NOSHADOW_TYPES）落位三项 ERROR，与 D13 内缩豁免对齐」
> 结论：**PASS（1/1）→ status 置 done**

---

## 1. 验收方法（独立取证，不依赖实现叙述）

- 读取 `git diff main...HEAD`（merge-base=2dd6b5d）实物，逐行审查 `packages/floorplan_core/floorplan_core/scene.py` 与 `packages/floorplan_core/tests/test_decor.py`
- 通读 `_validate_items`（scene.py:660-756）全文 + D13 归一化区（scene.py:535-560）+ `catalog.NOSHADOW_TYPES` 真实成员
- 运行两套 pytest（floorplan_core 154 + api 320），逐条核查 skip / golden 快照实跑与否
- **自建独立对抗脚本** `scratchpad/eval_adversarial.py`（不复用 generator 测试断言），10/10 PASS
- ruff `check` + py_compile 兜底

---

## 2. 改动范围核实

| 文件 | 类别 | 说明 |
|---|---|---|
| `packages/floorplan_core/floorplan_core/scene.py` | **产品代码（唯一）** | 4 处改动全部落在 `def _validate_items`（diff hunk @670/@712/@723/@743），均在 660-756 区间内 |
| `packages/floorplan_core/tests/test_decor.py` | 测试 | +2 回归用例 |
| `features.json` / `progress.json` | 状态机 | 非产品代码 |

- **D13 归一化区（scene.py:535-560）逐字节未动** → acceptance (5)/point-5 成立：修复只碰校验层，未触 build_scene D13 内缩或其他链路。
- 改动本体：`wall_hugging = isinstance(it.get("t"), str) and it.get("t") in _catalog.NOSHADOW_TYPES`；三处落位 level 判定由 `code_prefix == "AXON"` / `normalizable` 收紧为 `... and not wall_hugging`。

`NOSHADOW_TYPES` 实测成员 = `{'curtain', 'wall_art'}`（仅两类，豁免面极窄；tv/mirror/wardrobe/sofa/rug/plant/floor_lamp 均不在内）。

---

## 3. 逐条 acceptance 判定

### 根因修复：贴墙软装 AXON 三项落位降 WARN，validation.ok 恢复 True — **PASS**

独立对抗 T1（真实 build_scene 管线，wall_art+curtain 紧贴左墙 dx=0）：
```
T1 贴墙软装 build_scene ok==True        ok=True errors=[]
T1 三项落位无 ERROR                      axon placement ERROR=[]
   触发的 AXON codes 及 level: [('WARN','AXON_WALL_THICKNESS_COLLISION'),
                                ('WARN','AXON_CENTER_OUTSIDE_ROOM'),
                                ('WARN','AXON_OUTSIDE_ROOM_BBOX')]
```
三项落位检查确实触发但降为 WARN，validation.ok=True，出图入口（main.py 1839/2377/2708）不再被阻断。generator 回归用例 `test_wall_hugging_decor_does_not_block_ai_render` 亦 PASSED。用户报的误判（户型 v7/胡桃石韵轻奢「场景校验未通过，已阻断 AI 出图」）已消除。

### (a) 豁免类型限定，非 noshadow 件 AXON 三项仍 ERROR — **PASS**

独立对抗 T3（`validate_scene`→`_validate_items` 校验层直注入，同一越界几何 x=rx-4 嵌墙 4px）：
```
T3 noshadow  wall_art  → 落位检查全 WARN   [WARN AXON_OUTSIDE_ROOM_BBOX, WARN AXON_WALL_THICKNESS_COLLISION]
T3 noshadow  curtain   → 落位检查全 WARN   [WARN ...]
T3 非noshadow mirror   → AXON ERROR        [ERROR AXON_OUTSIDE_ROOM_BBOX, ERROR AXON_WALL_THICKNESS_COLLISION]
T3 非noshadow tv       → AXON ERROR        [ERROR ...]
T3 非noshadow wardrobe → AXON ERROR        [ERROR ...]
T3 非noshadow sofa     → AXON ERROR        [ERROR ...]
```
证明 AXON 硬门**未被整体关掉** —— 同几何下仅 curtain/wall_art 降级，其余全类型保持 ERROR。逻辑层亦字节等价：非 noshadow 件 `wall_hugging=False` → `not wall_hugging=True` → `(code_prefix=="AXON" and True) ≡ (code_prefix=="AXON")`，与 main 逐布尔相同。generator 回归用例 `test_wall_hugging_exemption_is_type_scoped` PASSED。

### (b) RAW 路径不变（本就 WARN）— **PASS**

RAW 路径 `code_prefix=="RAW"`，落位判定首项 `code_prefix=="AXON"` 恒 False → WARN，`wall_hugging` 项不改变结果；RAW 墙碰撞在 scene.py:823-824 后处理强制 WARN。逐布尔字节等价，行为不变。

### (c) AXON_HEIGHT_EXCEEDS_WALL 安全项未被豁免 — **PASS**

代码审查：height 检查（scene.py:679-693）位于 `wall_hugging` 定义之后但 level 判定仍为 `"ERROR" if code_prefix == "AXON" else "WARN"`，**无 `wall_hugging` 守卫**。独立对抗 T4（wall_art/curtain + 超高 z=2400 > max_furniture_height_mm=1400，位置合法以隔离高度项）：
```
T4 贴墙 wall_art 超高 → HEIGHT_EXCEEDS_WALL 仍 ERROR   [ERROR AXON_HEIGHT_EXCEEDS_WALL] ok=False
T4 贴墙 curtain  超高 → HEIGHT_EXCEEDS_WALL 仍 ERROR   [ERROR AXON_HEIGHT_EXCEEDS_WALL] ok=False
```
高度超墙对贴墙件依旧硬阻断，未被误纳入豁免。point-4 成立。

### (d) golden 字节不受影响 — **PASS**

- `test_render_snapshot.py::test_render_string_matches_baseline_byte_for_byte[平面布置图.svg]` 与 `[D户型-空壳底图.svg]` 均 **PASSED（非 skip）**——本机 `rsvg-convert` 存在（/opt/homebrew/bin/rsvg-convert），快照测试真实执行并逐字节匹配基线。
- `test_d_data_has_no_decor_types` PASSED（D 默认方案不含 decor 类型，豁免路径在 golden 场景不触达）。

### 回归 / 无回归 — **PASS**

```
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q      → 154 passed（152→154，+2 回归）
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q             → 320 passed
```
两套合计 474 passed，**0 skip / 0 fail**（`-rs` 确认无 skip）。ruff `All checks passed!` + py_compile OK。

---

## 4. 独立发现 / 备注

- **T2 信息项（非 pass/fail 门）：** 可归一化非-noshadow 件（如超大 sofa 5000×3000）走 build_scene 会被 D13 内缩自愈（`axon-size-clamp dw=-4716 dh=-2776` 夹回房内，ok=True）——这是既有 D13 设计行为，非本批次引入，也非缺陷。正因自愈会掩盖校验门是否工作，类型限定的决定性反证在 `_validate_items` 校验层（T3 直注入）而非端到端管线做。已在报告中如实标注，不影响判定。
- **L2 真实 AI 出图未执行且非本 bug 必需：** 该 bug 的阻断点在 AI 调用**之前**的场景校验（validation.ok=False → sceneBlocked），T1 已证 validation.ok 在真实 build_scene 恢复 True，即修复点完全 L1 可验证。下游真实出图属独立链路，无 AI keys（环境限制）+ 未部署 staging（push main=部署生产，本批未 push）。标 [L2] 未执行，非阻断。

---

## 5. 判定汇总

| 维度 | 结果 |
|---|---|
| 根因修复（贴墙软装不阻断出图） | PASS |
| (a) 类型限定 / 硬门未整体关闭 | PASS |
| (b) RAW 路径字节不变 | PASS |
| (c) HEIGHT_EXCEEDS_WALL 安全项保持 | PASS |
| (d) golden 字节安全 | PASS |
| 回归 / 无回归（474 tests, 0 skip） | PASS |
| 改动范围（仅校验层，D13 未动） | PASS |

**F001：PASS。pass=1 / partial=0 / fail=0。status → done。**
