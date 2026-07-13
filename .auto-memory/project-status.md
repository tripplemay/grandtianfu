---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **无进行中批次**（Triad harness v1.0.3 于 2026-07-13 接入本项目，试用中）
- 下一步：`/plan` 开启第一个需求批次

## 项目概况
- 阅天府 studio — 室内设计工作流 monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib 几何/渲染) + `apps/web`(Next.js15/Yarn1)
- 无仓库级 task runner；命令 ad hoc（见 CLAUDE.md）

## 关键约束（harness 相关）
- **push `main` = 部署生产** → harness 工作走 branch→PR→squash，**禁止自动 push main**
- **自主模式 /autodrive 禁止开启**（会误触生产）；已装但 inert
- 当前 backlog：`docs/backlog-核对-20260708.md`

## 已知（非阻塞）
- 接入前工作区有 6 个未提交改动（既有 WIP，harness 接入未触碰）
- harness 接入产物待用户 review 后单独提交（勿与 WIP 混提）

<!-- 覆盖写，≤30 行；只放 WHAT，不重复 progress.json 结构化数据 -->
