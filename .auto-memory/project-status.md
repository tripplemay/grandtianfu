---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **decor-envelope-b1 — planning 中**（用户 2026-07-15 选定 `BL-decor-allowed-envelope`）：第7步 auto_check 残余误报
  - 根因**已从标定转移到验收容差/建模侧**，且**差一块过门**：坏块 20/111（修前）→ 9/96（只修代码）→ **3/96**（代码+数据全修，score 0.95）；判据 `struct_ok = tiles_bad < _NEW_EDGE_TILES_MIN(=3)`
  - 3 块经逐块归因**全是家具本身**：2 块挂画（新边缘在 allowed 包络 8~12px 内 = 画框上沿略高于 `_WALL_BAND_ALLOWED_Z['wall_art']=1500mm` 封顶）+ 1 块窗帘（>32px = **建模缺口**：盒 `z0=150`/`h=1450` vs 该面是全落地窗、模型画的帘子从天花垂到地面 ~2700mm）
  - 代价：误报触发重试（该张 attempts=2）⇒ 每次实拍出图烧 2 倍 AI 预算 + 给用户假的「未通过」标记
  - 边界：窗帘 `z0=150/h=1450` 是 decor-b2 为对齐轴测 SPECS 画框所定 → 改动须同时核对 axon 渲染与 golden
  - **口径铁律（沿用 calib-z-b1）**：本条修完并用**修后引导图**重出一张验证前，**不得写「误报已消除」**

## 已上线（近期，均已闭环）
- **calib-z-b1** ✅ 2026-07-15 `a73f92d`：标定世界 z 轴系统性取反（左手系 `(东,南,上)` 里用 `+cross` 强制 `det=+1` → z 列系统性取反；2 锚点下 err 精确平局 → 浮点噪声抛硬币）。修法 `z=-cross`(det=−1) + `C_z>0` 硬门 + 无解 raise，**两处缺一不可**。11/11 存量自愈已执行（`.bak` 单步回退可用）。**[L2] 已闭环**（生产 render `fc8823be` 目检：餐桌落位正确、挂画回墙面）
- **render-fix-b1** ✅ 2026-07-15 `d9c2b35`（引导图退化致落位错）· **decor-b3-fix** ✅ 2026-07-14 `ac98c20`

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy（纯文档也不例外）→ 状态/记忆文件随批次 PR 走，别单推
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 只用 `ruff check` 查真错（全仓基线 203 条既有噪声）
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入
- **git add -A 坑**（calib-z-b1 实证）：会扫入工作区既有脏文件 → 推送前必查 `git status --short data/projects/`

## 待办 / 遗留
- backlog：`BL-calib-min-3-anchors`(high, 标定精度：1537e err 仍 ~124px；方向问题已解决) / `BL-input-gate-error-class`(medium) / `BL-decor-b2-L2-realphoto` / `BL-horizon-template-removal` 等
- framework proposed-learnings **已清空待确认队列**：calib-z-b1 的 7 条 → v1.0.5；render-fix-b1 的 6 条 → **v1.0.6**（用户 2026-07-15 确认）。剩余「确认待办」项均为 harness 机件改动，用户裁决留单独一轮机件重构做
- ~~stash@{0}「本地测试残留 renders.json」~~ → **用户 2026-07-15 裁决丢弃销案**（内容仅 2 条本地 dev 出图记录；仓库 `data/projects` 只是种子快照，生产真源在 deploysvr 且内容不同）。原 commit `740e4a8` 若未 gc 仍可 `git show` 取回
