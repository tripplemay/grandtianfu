---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **decor-envelope-b1 ✅ done（首轮验收 PASS，2026-07-16）— 未部署**：第7步 auto_check 残余误报
  - 根因（本批查实，比立项时更深）：`perspective.py` 把**轴测压扁世界**(axon `WALL_H=1450`)的数字照抄进**实拍真实毫米世界**(层高 ~2700)。铁证：`_DEFAULT_HEIGHT_MM` 里 `wardrobe/bookshelf=2000 > 1450` 在压扁世界立不住 → 两表不同源
  - F001：allowed 上沿由「渲染顶+余量」**派生**（删双写表 `_WALL_BAND_ALLOWED_Z`），纯机制化重构，allowed mask 逐字节不变
  - F002：窗帘盒 `150..1450`(照抄轴测) → **落地帘 `0..2700`**（呼应 catalog `floor-length curtains`）
  - **裁决 #4**（building 期实测推翻 spec §2.2）：挂画盒 `1000..1400` 同样欠建模（模型实测画 ~750mm 的画，盒只 400mm）→ 只机制化派生、余量维持 100mm 不动、**不用容差掩盖** → 另立 `BL-wall-art-box-undermodeled`
  - 生产实物 `fc8823be` 重放：修前 `ok=False/0.95/3/96`（自证保真）→ 修后 **`ok=True/0.967/2/92`**；失明代价 allowed 52.5%→54.9%(+2.4pp)
  - 隔离验收 8 硬门全过（含阳性对照+失明门），evaluator 独立复核 handoff 数字全部一致，`can_deploy=True`
  - ⚠ **未部署**：分支 `decor-envelope-b1` 6 commit 未 push；**[L2] 未验**——「误报是否真消除」须用修后引导图重出一张 v7/r_live 图，**修完但未 [L2] 前不得写「误报已消除」**

## 已上线（近期，均已闭环）
- **calib-z-b1** ✅ 2026-07-15 `a73f92d`（标定 z 轴系统性取反；11/11 存量自愈已执行）
- **render-fix-b1** ✅ 2026-07-15 `d9c2b35` · **decor-b3-fix** ✅ 2026-07-14 `ac98c20`

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy → 状态/记忆文件随批次 PR 走，别单推
- **ruff 坑**：本机需 `python3 -m ruff`（裸 ruff 不在 PATH）；只用 `ruff check`，全仓基线 203 条既有噪声
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入；`git add -A` 会扫入脏文件
- **两个 z 世界**（decor-envelope-b1 沉淀）：perspective=真实毫米(层高2700) vs axon/scene=压扁dollhouse(1450)，**数字不得互借**

## 待办 / 遗留
- **decor-envelope-b1 待部署 + [L2]**（用户手动）；`BL-wall-art-box-undermodeled`(medium, 挂画盒欠建模, 须 [L2] 验)
- backlog：`BL-calib-min-3-anchors`(high) / `BL-input-gate-error-class`(medium) / `BL-decor-b2-L2-realphoto` / `BL-horizon-template-removal` 等
- framework **proposed-learnings 已清空待确认（本批 4 条 → v1.0.7）**：Planner「看着合理」不写成 spec 断言 / 等价重构以逐字节对照为判据 / 二手测量须带单位 / 验收 subagent 尽早分段落盘（两个 evaluator 均在收尾被 idle timeout 截断的机件教训）
