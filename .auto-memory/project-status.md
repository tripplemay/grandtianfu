---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **decor-b1 ✅ DONE**（2026-07-13）：软装配饰引擎+编辑器基座 9/9 全 PASS（fix_rounds=0）
  - 独立件 wall_art(挂画)/curtain(窗帘) 进目录走全链路（m_from_spec 悬空画框+vplane/半透长幔）
  - 附着件 DECOR_ATTACH(抱枕/床品/台灯/花瓶/摆件) 挂宿主顶面 mount_z（对齐实际模型顶面 D12）
  - 换件 decor 双端透传(D11) / 第7步隔离兜底(D10) / golden 字节零回归
  - 三域 fan-out 隔离 evaluator 验收 + signoff（docs/test-reports/decor-b1-*）
  - **未 push main**：分支 feat/decor-b1，合并/PR/部署时机待用户定（push main=部署生产）
- 下一步：与用户确认下一批次（decor-b2 / backlog / 新需求）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy；状态/记忆文件应随批次 PR 一起走
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 编辑 Python 手工匹配风格，只用 `ruff check` 查真错

## 待办 / 遗留
- backlog：BL-decor-b2(high, AI 配饰+第7步实拍接入) / BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) / BL-tv-mirror-wall-clearance(low) + docs/backlog-核对-20260708(30 项)
- proposed-learnings 待用户确认：decor-b1 一条(词表类 feature 拆分完整性约束) + 上轮 harness-fit P2-1~P2-5
