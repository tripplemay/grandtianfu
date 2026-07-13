---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **ops-cleanup-b1 ✅ DONE**（2026-07-13，harness 接入后首批）：运维长尾+前端死控件清理 6/6 PASS
  - F001 rsvg 可诊断降级(503) / F002 缩略图 kind 入 modes 注册表 / F004 project_lock 改 flock
  - F003 real-render 角标中文房名 / F005 comingSoon 死代码 / F006 编辑器升级文档状态列回填
  - 快车道 fan-out 三域隔离验收 + signoff（docs/test-reports/ops-cleanup-b1-*）
- 下一步：与用户确认下一批次 + **合并/上线时机**（见遗留）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开（已装 inert）
- backlog：`backlog.json`（BL-horizon-template-removal medium / BL-useviewport-hook-deps low）+ `docs/backlog-核对-20260708.md`(30 项)

## 遗留（非阻塞）
- **分支 `chore/harness-onboarding` 未 push**：本批 6+2 commits + harness 接入(5762587) + 接入前 WIP(CLAUDE.md/AI链路续接/.bak/新审查文档) 全在本地；合并策略待用户定（harness 是否随本批上 main / WIP 单独处理）
- **ruff 格式坑**：本机 ruff 0.15.20 与仓库格式基线不一致 + ruff.toml 缺 known-first-party + CI 不跑 ruff → `ruff format .`会全文件重排；编辑 Python 手工匹配风格、只用 `ruff check` 查真错

<!-- 覆盖写，≤30 行；只放 WHAT，不重复 progress.json 结构化数据 -->
