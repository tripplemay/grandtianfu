# decor-b3-fix Signoff 2026-07-14

> 状态：**签收通过**（progress.json status verifying → done，fix_rounds=0 首轮 PASS）
> 触发：修复贴墙软装（wall_art/curtain）在轴测场景校验中被误判 AXON ERROR 硬阻断 AI 出图的 bug
> Evaluator：隔离 fresh-context subagent（local/evaluator-subagent）
> 详细逐条证据见 `docs/test-reports/decor-b3-fix-verifying-2026-07-14.md`

---

## 变更背景

用户报：户型 v7 / 胡桃石韵轻奢 生成轴测图提示「场景校验未通过，已阻断 AI 出图：轴侧家具 wall_art 超出房间 r_live 边界 / 与墙体厚度相交；curtain 与墙体厚度相交」，但编辑器无任何报错。

根因：decor-b1 D13（scene.py:547）让 `NOSHADOW_TYPES`（挂画/窗帘）豁免 inner-clearance 内缩（它们本该贴墙），但 `_validate_items`（scene.py:660-756）走 AXON 路径时无对应豁免，把「正确贴墙」的件判为 `AXON_OUTSIDE_ROOM_BBOX` / `AXON_WALL_THICKNESS_COLLISION` / `AXON_CENTER_OUTSIDE_ROOM` = ERROR → `validation.ok=False` → 三处出图入口（main.py 1839/2377/2708）全阻断；编辑器（useFurnitureEditor.ts:877）过滤 `AXON_` 前缀，故用户在编辑器无感。

---

## 变更功能清单

### F001：轴测校验豁免贴墙软装（NOSHADOW_TYPES）落位三项 ERROR，与 D13 内缩豁免对齐

**Executor：** generator

**文件：**
- `packages/floorplan_core/floorplan_core/scene.py`（修改，唯一产品代码，4 处，全部在 `_validate_items`）
- `packages/floorplan_core/tests/test_decor.py`（新增 2 回归用例）

**改动：** 在 `_validate_items` 计算 `wall_hugging = isinstance(it.get("t"), str) and it.get("t") in _catalog.NOSHADOW_TYPES`；对 AXON 路径的越界/穿墙/中心越界三项落位检查，level 判定加 `and not wall_hugging`，使贴墙软装降为 WARN（与 D13 完全对齐），不硬阻断出图。

**验收标准与结果：**
- 贴墙 wall_art/curtain 经 build_scene → `validation.ok==True`，三项以 WARN 出现 — **PASS**（独立对抗 T1）
- 非 noshadow 件（tv/mirror/wardrobe/sofa）同越界几何仍 AXON ERROR，硬门未整体关闭 — **PASS**（独立对抗 T3）
- RAW 路径不变（本就 WARN）— **PASS**（逻辑字节等价）
- `AXON_HEIGHT_EXCEEDS_WALL` 安全项不在豁免范围，仍 ERROR — **PASS**（独立对抗 T4）
- golden 字节不受影响 — **PASS**（byte-for-byte 快照实跑通过 + test_d_data_has_no_decor_types）

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| build_scene D13 内缩归一化（scene.py:535-560） | 逐字节未动，diff hunk 全部落在 `_validate_items`（660-756） |
| 前端 useFurnitureEditor.ts:877 | 无需改，AXON 过滤逻辑不变，修复后这些码本就是 WARN |
| RAW 校验路径 | code_prefix!="AXON" → WARN 恒成立，行为字节不变 |
| 非 NOSHADOW_TYPES 全类型 AXON 行为 | `not wall_hugging=True` 使布尔式与 main 逐字等价 |

---

## 预期影响

| 项目 | 改动前 | 改动后 |
|---|---|---|
| 贴墙 wall_art/curtain 生成轴测图 | validation.ok=False，出图被阻断 | validation.ok=True，正常出图（三项降 WARN） |
| tv/mirror/wardrobe/sofa 越界/穿墙 | AXON ERROR 阻断 | AXON ERROR 阻断（不变） |
| 贴墙件高度超墙 | AXON_HEIGHT_EXCEEDS_WALL ERROR | ERROR（不变，安全项未豁免） |
| golden 渲染快照 | 基线 | 逐字节不变 |
| floorplan_core 测试数 | 152 | 154（+2 回归） |

---

## 类型检查 / CI

```
ruff check scene.py test_decor.py            → All checks passed!
py_compile scene.py test_decor.py            → OK（无语法错误）
pytest packages/floorplan_core/tests -q      → 154 passed（0 skip / 0 fail）
pytest apps/api/tests -q                      → 320 passed（0 skip / 0 fail）
render snapshot byte-for-byte                 → PASSED（rsvg-convert 存在，真实执行非 skip）
```
CI（GitHub Actions）：本批未 push main（push=部署生产），CI/部署由用户在合并 PR 时手动触发。

---

## L2 实测记录

| 项 | 证据 |
|---|---|
| Staging git_sha == main HEAD | N/A — 本批未部署 staging（push main=部署生产，未 push） |
| 端到端流验证 | 修复点在 AI 调用**之前**的场景校验门（validation.ok），T1 已在真实 build_scene 证 ok 恢复 True，修复完全 L1 可验证 |
| 真实 AI 出图 | **[L2] 未执行** — 无 AI keys（环境限制）+ 未部署 staging；属修复点下游独立链路，非本 bug 必需，不阻断签收 |

---

## Ops 副作用记录

本批次无数据库 ops（文件存储，纯校验层逻辑改动）。

---

## Soft-watch

无。修复自包含、L1 完全可验证，无 deferred / 未闭环项。

---

## 签收结论

**F001 PASS（pass=1 / partial=0 / fail=0）。首轮 verifying 即通过（fix_rounds=0），status 置 done。**
