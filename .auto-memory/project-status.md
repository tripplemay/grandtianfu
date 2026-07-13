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

## 待办 / 遗留
- **PR #81 开着待用户 squash-merge**（整条 chore/harness-onboarding = 本批+harness 采纳+WIP）：CI pytest+smoke 全绿；gitleaks continue-on-error 不阻断。**squash-merge = 部署生产**(F001-F005 上线)，时机由用户定；合并后 `curl https://design.vpanel.cc/api/health` 验活。.bak 已入 .gitignore
- 合并后：future 工作从 main 切分支（main 将带 harness）
- **ruff 格式坑**：本机 ruff 0.15.20 与仓库基线不一致 + ruff.toml 缺 known-first-party + CI 不跑 ruff → `ruff format .`会全文件重排；编辑 Python 手工匹配风格、只用 `ruff check` 查真错（可选根治：加 known-first-party）

<!-- 覆盖写，≤30 行；只放 WHAT，不重复 progress.json 结构化数据 -->
