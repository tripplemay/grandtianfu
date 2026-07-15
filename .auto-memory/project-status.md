---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **calib-z-b1 ✅ 已签收 PASS（fix_rounds=2）→ 待合并部署 + 生产迁移**（2026-07-15）：标定世界 z 轴符号系统性取反
  - 根因（合成真值控制实验证明）：世界系 (X=东,Y=南,Z=上) 是**左手系**(East×South=Down)，相机系是右手系 → 物理正确的 R 必然 **det=−1**；而 `z=+cross(x,y)` 强制 det=+1 → x/y 拟合正确时 **z 列系统性取反**（喂真值相机 C_z=+1500 → 返回 −1500）
  - 加之两条打分约束只用**地面**锚点（11/11 锚点 z 全为 0 → z 列恒乘 0）→ 2 锚点时两候选 err **精确平局**(1e-13~1e-16) → z 方向由**浮点噪声抛硬币**（铁证：同输入换机器重算即得相反 z，**三方独立复现**）
  - 生产**11 条**（非原 spec 说的 5 条 —— 漏掉整个 v7 = 在用 baseline）：7 条相机解在地板下方 + 4 条 z 朝上但**平面被水平镜像**（det=+1 下二者同一事件）
  - 修法：`z=-cross`(det=−1) + `C_z>0` 硬门 + 无解 raise，**两处缺一不可**（只加门 = 原 spec D1 → 实测破坏生产）
  - F001 ✅ PASS（Evaluator 加跑 300 组随机场景：修后 300/300 还原真值、0 误 raise；修前 300/300 恰为 z 镜像）
  - F002：**11 条全量自愈**（fix-round 1 曾排除 1537e → fix-round 2 撤销：两位 Evaluator 独立推翻排除前提，方向已定论）
  - ⚠ **下游误报未消除**：20/111 → 9/96，仍 ok:false。**口径铁律：不得写"已消除"**；判定须用**修后**引导图重出一张 = [L2]
  - spec 已三轮订正（D1/D2/D4 + §2.1/§2.3/§2.4/§2.5）；审计 `docs/specs/calib-z-b1-F001-z-axis-audit.md`
  - **生产未写入任何字节**；顺序铁律：**先部署代码再跑迁移**（反了会被重新标定写回带病值）
- **render-fix-b1 ✅ 已上线生产**（2026-07-15，`d9c2b35`）：第7步引导图退化致家具落位错
  - F001 curtain 盒越相机平面→投影炸开糊死全画幅（近平面裁剪修复）；F002 调色板撞色扩 14 色；F003 引导图健全性门禁
  - **[L2] 未验**：真实 AI 出图 → ⏳ 待用户重新生成一张 v7 实拍图目检（原始报障的验证闭环）
- **decor-b3-fix ✅ 已上线生产**（2026-07-14，`ac98c20`）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 只用 `ruff check` 查真错（providers.py/main.py 的 I001、tests/ 的 22 条均为既有噪声）
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入
- **git add -A 坑**（calib-z-b1 实证）：会扫入工作区既有脏文件 → 推送前必查 `git status --short data/projects/`

## 待办 / 遗留
- calib-z-b1：**待你合并 PR（=部署）→ 生产 dry-run 核对 → `--apply`**（用户已授权范围=全量 11 条）；顺序不可反
- backlog：BL-calib-min-3-anchors(high, 精度) / BL-input-gate-error-class(medium) / BL-decor-b2-L2-realphoto / BL-horizon-template-removal 等
- stash@{0}「本地测试残留 renders.json」= **用户待决事项**（曾被无声丢弃，已恢复）
