# render-relation-b1 — R1 关系约束闭环产品化（实拍出图主路径）

> 状态：**已 lock（用户 2026-07-23 批准，"批准，开工"）**。分支建议 `feat/render-relation-b1`（off main，calib-route-a1 合并后）→ PR → squash；绝不单推 `main`。
> 证据基座：`docs/test-reports/route-eval-real-render-2026-07-23.md`（三路线实测）+ `docs/test-reports/calib-route-a1-signoff-2026-07-23.md`（路线裁决）。
> 用户裁决（2026-07-23）：R1 转正为主路径；几何锁定退役备用；软参考保留为快速预览档。

## 1. 为什么立这批

实测结论（4 张生产真实空房照、统一 VLM 验收）：

- 放置约束命中率：R1 关系约束 **93%** > 几何锁定 86%（n=1 且入口断）> 软参考 **65%**；
- R1 **零标定、零轴测参考**：彻底绕开「单图恢复 7 自由度相机」这一病态前置——标定路线三批（b1-b3）+ 一路研究批（route-a1）已证明此路对人不可行、对机器未证可行；
- R1 round1（1 gen + 1 VLM）即达标，成本与软参考同量级。

本批把评测原型（沙箱 `scripts/r1.py`）产品化为 render-real 的**默认出图路径**。

## 2. 本批的性质

**产品化批次，改产品路径**（apps/api + apps/web + packages/floorplan_core 允许新增模块）。
前提已被评测验证，不重复研究。评测原型代码仅作设计参考，**不直接搬用**——产品化须过本仓工程标准（类型化错误、门禁、测试、byte-safe 纪律）。

## 3. 关键设计决策

### D1 约束编译器进 floorplan_core（纯 stdlib、确定性）
新模块 `floorplan_core/placement_brief.py`：geometry + scene 归一化家具 + openings → 结构化
**放置简报**（中文自然语言约束清单 + 视角→画面四至映射）。理由：
- 纯派生计算、无 AI 依赖，放引擎符合「单一真源」哲学，pytest 直接单测；
- 视角映射 `v0..v3 → 前/后/左/右墙` 与 `main._VIEW_FORWARDS` 同源（搬进引擎，main 改调它，消除双写）。

评测原型已验证的语义规则须保留：**orient=靠背墙**（非朝向）、**贴墙判定用边缘缝隙**（≤300mm）、
merge 组成员并集为作用域。

### D2 render-real 三档策略（`strategy` 参数）
`POST .../schemes/{id}/render-real` 增 `strategy`（默认 `relational`）：

| 档 | 内容 | 定位 |
|---|---|---|
| `relational`（默认） | 空房照单图 + 放置简报 prompt + VLM 关系验收 | 主路径（评测 93%） |
| `softref` | 现有轴测软参考路径（逐字保留） | 快速预览档（1 gen，无 VLM 成本） |
| `geometry_lock` | 现有彩盒几何锁定路径（逐字保留） | 备用（标定可信时仍可用） |

- `relational` 需要 `photo.room_id`（编译简报），缺 → 400（同 REAL_NOT_READY 语义）；
  `direction` 可选（缺则简报省略画面四至段，降级不阻断）。
- 已有 `backend` 参数语义不变（仅对 geometry_lock 生效）；软参考/几何锁定两路径**一行不改**。

### D3 VLM 关系验收复用 semantic_accept 基建，闭环策略「round1 + 按需重试 + 可回退」
- `semantic_accept.py` 扩展 `relation-check` 模式：约束清单逐条 pass/fail/uncertain + 背景保真分级
  （沿用评测原型 prompt，迭代于评测实测）；
- 闭环策略（评测发现「闭环非单调」的直接教训）：**round1 出图即验收；仅当存在 fail 约束时重试 1 次**
  （失败约束回写进修正 prompt）；**两轮取验收分高者交付**，允许 round1 回退；
- 成本闸：relational 每单最多 2 gen + 2 VLM，重试独立预算预扣（沿用 `_budget` 机制），
  VLM tokens 走 `on_usage` 计量；
- 验收结果（逐条状态 + 背景评级）写入 render 记录，前端可展示——用户看得见「哪条没做到」。

### D4 评测暴露的编译器缺陷随 F001 修复
1. **merge 组可见性污染**：兄弟房家具须标注「可能画外」或按绑定房过滤（评测：书房衣柜被要求
   画在画外墙上，两轮均 fail）；
2. **模板按实际数量生成**：床头柜关系模板不得硬写「两个」（书房方案仅 1 个）；
3. **超能力约束软化**：「整面悬挂窗帘」→「沿窗墙布置窗帘」（编辑模型做不到整面）；
4. 地毯文案泛化（已在原型修过：不再写死「沙发/茶几活动区」）。

### D5 背景保真不在本批
mask 级编辑是独立批次（`backlog.json BL-render-mask-edit`）。本批只如实记录背景重绘程度
（验收的背景分级进 render 记录），不做 prompt 之外的锁背景承诺——gpt-image-2 整图重生成，
prompt 锁不住（评测 §4），不得过度承诺。

## 4. Features

| ID | 一句话 | executor |
|---|---|---|
| F001 | `floorplan_core/placement_brief.py` 约束编译器（含 D4 缺陷修复 + 单测） | generator |
| F002 | render-real `strategy=relational` 路径接入（同步段/异步段/记录） | generator |
| F003 | semantic_accept `relation-check` 模式 + 闭环策略（D3） | generator |
| F004 | 前端 real-render 页：三档选择 + 简报预览 + 验收结果展示 | generator |
| F005 | 隔离验收：命中率/成本/回归四维复测 + b3 F007-F010 补验 | evaluator |

## 5. 验收总则（F005）

1. **放置命中率复测**：≥4 张真实空房照（可复用评测样本集），relational 档统一 VLM 核对
   命中率 ≥ 软参考档（同照片同方案对照），且不低于评测基线 93% 的量级（允许 VLM 噪声 ±10%）。
2. **回归零侵入**：软参考/几何锁定路径字节级不动（既有测试全绿即证）；floorplan_core 新增模块
   对既有渲染零字节影响（byte-safe 纪律：新增文件、不改既有函数）。
3. **成本可观测**：relational 每单 gen/VLM 调用数进 render 记录与 budget 监控。
4. **b3 F007-F010 补验**（当时用户 L2 驱动当场修复、未经隔离验收）：随本批 F005 一并复验。
5. 红线：新模块纯 stdlib；不动既有渲染路径；不写 `data/projects/`（e2e/测试用沙箱）；
   不把背景保真写进本批承诺（D5）；pytest 双套件 + 前端 build/lint 绿。

## 6. 开工前调查清单（lock 前完成）

- F001：原型 `r1.py` 语义规则逐条核对（orient/贴墙缝/merge 作用域/视角映射），确认无评测期临时简化；
  `main._VIEW_FORWARDS` 与 `_VIEW_FACING_ZH` 双写消除方案。
- F002：`strategy` 参数与现有 `backend`/`allow_unlabeled`/`allow_layout_issues` 参数的交互矩阵；
  relational 档的 renders.json 记录 schema（向后兼容）。
- F003：semantic_accept 现有调用点与 relation-check 的并存方式；VLM 失败时降级策略（跳过验收直交付？记 degraded）。
- F004：real-render 页 1417 行的现状，三档 UI 的最小侵入接入点。

## 7. 本批不做什么

- 不做 mask 级背景锁定（BL-render-mask-edit 独立批次）；
- 不动软参考/几何锁定路径（D2 逐字保留）；
- 不做标定路线的任何改动（已退役备用；route-a1 增强项见 BL-route-a1-enhancements）；
- 不做 VLM 预标定/自动视角推断等增强（评测未验证，另议）。
