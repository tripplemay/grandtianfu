---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **ops-cleanup-b1 ✅ DONE + 已部署生产**（2026-07-13，harness 接入后首批）：运维长尾+死控件清理 6/6 PASS
  - F001 rsvg 可诊断降级(503) / F002 缩略图 kind 入 modes 注册表 / F004 project_lock 改 flock
  - F003 real-render 角标中文房名 / F005 comingSoon 死代码 / F006 编辑器升级文档状态列回填
  - 快车道 fan-out 三域隔离验收 + signoff（docs/test-reports/ops-cleanup-b1-*）
  - PR #81 squash-merge → main `3e1fa2c`；deploy 成功；prod health `ok:true version=3e1fa2c` ✅
  - **harness v1.0.3 已随本批采纳上 main**（不再是试用）
- 下一步：与用户确认下一批次（从 backlog / 新需求）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开（已装 inert）
- backlog：`backlog.json`（BL-horizon-template-removal medium / BL-useviewport-hook-deps low）+ `docs/backlog-核对-20260708.md`(30 项)

## 待办 / 遗留
- future 工作从 main 切分支（main 已带 harness）；backlog：BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) + docs/backlog-核对-20260708(30 项)
- **⚠ deploy.yml 无 paths-ignore**（harness-rules 声称有=不实）→ **任何 push main 都触发 build+deploy**，连 progress.json/.auto-memory/docs 也会触发无谓部署。故 harness 状态/记忆文件**不宜单独 push main**，应随批次 PR 一起走；可选修：给 deploy.yml 加 paths-ignore
- **ruff 格式坑**：本机 ruff 0.15.20 与仓库基线不一致 + ruff.toml 缺 known-first-party + CI 不跑 ruff → `ruff format .`会全文件重排；编辑 Python 手工匹配风格、只用 `ruff check` 查真错（可选根治：加 known-first-party）
- 本条记忆更新在**本地 main 未 push**（避免无谓部署），随下一批次 PR 上库

<!-- 覆盖写，≤30 行；只放 WHAT，不重复 progress.json 结构化数据 -->
