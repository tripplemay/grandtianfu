---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **decor-b2 ✅ DONE**（2026-07-13）：AI 配饰生成+第7步实拍接入 7/7 全 PASS（fix_rounds=0，首轮）
  - furnish AI 出 decor 清单(attach 挂谁/standalone 放哪房，不出坐标) + layout.place_decor_standalone 确定性落位
  - 第7步完整接入: _box_polys 加 z0 逐件派生(挂画 1000-1400 墙面带) + annotate 放行 + prompt 锚定 + acceptance allowed 抬顶 z1500
  - **头号项(审查#3)对抗过**: allowed 真覆盖挂画墙面区(0未覆盖+21px顶余量), structure 不误判, byte-safe(sofa逐字节), NOSHADOW红线未改
  - [L2] 第7步真实出图未执行(AI keys 未设=环境限制, spec 授权降级 SVG/mask 目检) → backlog BL-decor-b2-L2-realphoto
  - 三域 fan-out 隔离 evaluator(python/web/render)+signoff（docs/test-reports/decor-b2-*）
  - **未 push main**：分支 feat/decor-b2(stacked off feat/decor-b1)，合并/PR/部署时机待用户定（push main=部署生产）
- **decor-b1 ✅ DONE**（2026-07-13）：软装配饰引擎+编辑器基座 9/9 全 PASS
- 下一步：与用户确认下一批次（decor-b1/b2 PR 合并部署 / backlog / 新需求）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy；状态/记忆文件应随批次 PR 一起走
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 编辑 Python 手工匹配风格，只用 `ruff check` 查真错

## 待办 / 遗留
- backlog：BL-decor-b2(high, AI 配饰+第7步实拍接入) / BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) / BL-tv-mirror-wall-clearance(low) + docs/backlog-核对-20260708(30 项)
- proposed-learnings 待用户确认：decor-b1 一条(词表类 feature 拆分完整性约束) + 上轮 harness-fit P2-1~P2-5
