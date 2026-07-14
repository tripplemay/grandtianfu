---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **decor-b3-fix ✅ DONE**（2026-07-14）：贴墙软装轴测校验误判修复，F001 首轮 verifying 即 PASS（fix_rounds=0）
  - 用户报：户型 v7/胡桃石韵轻奢 生成轴测图被"场景校验未通过"阻断（wall_art/curtain 越界/穿墙 ERROR），但编辑器无错
  - 根因：decor-b1 D13 让 NOSHADOW_TYPES 豁免 build_scene 内缩归一化，但 `_validate_items` 的 AXON 路径无对应豁免 → 贴墙件被判 AXON_越界/穿墙/中心越界 ERROR → validation.ok=False 阻断；编辑器 useFurnitureEditor.ts:877 过滤 AXON_ 故用户无感
  - 修复：`_validate_items` 加 wall_hugging 判据，AXON 三项落位检查对贴墙件降 WARN（与 D13 对齐）。类型限定（tv/mirror/wardrobe 仍 ERROR）+ HEIGHT 安全项不豁免，独立对抗证实
  - 仅碰 scene.py:_validate_items(4 处) + test_decor.py(+2 回归)；474 tests(154+320) 0 skip 0 fail；golden 快照 byte-for-byte 实跑通过
  - **✅ 已上线生产**（2026-07-14）：squash-merge main（`ac98c20`）→ CI 部署成功，`/api/health` ok:true/readonly:false；户型 v7/胡桃石韵轻奢现可正常出轴测图
- **decor-b1(#82)/decor-b2(#83) 已 squash-merge 进 main**（早于 07-14）
- **framework v1.0.4 沉淀 8 条**已并入 main（`11bed56`，docs 部署跟进）
- 下一步：与用户确认下一批次（backlog / 新需求 / harness 机件重构轮）

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；/autodrive 禁开
- **⚠ deploy.yml 无 paths-ignore** → 任何 push main 都触发 build+deploy；状态/记忆文件应随批次 PR 一起走
- **ruff 格式坑**：本机 ruff 与仓库基线不一致 → 编辑 Python 手工匹配风格，只用 `ruff check` 查真错

## 待办 / 遗留
- backlog：BL-decor-b2-L2-realphoto(high) / BL-horizon-template-removal(medium) / BL-useviewport-hook-deps(low) / BL-tv-mirror-wall-clearance(low) + docs/backlog-核对-20260708(30 项)
- proposed-learnings：v1.0.4 已沉淀 8 条(引擎域 2 + harness-fit 6)；机件改动 3 条(P0-3/P1-2/P2-4)裁决为待办，留单独一轮 harness 机件重构；P0-1/P0-2 部分落地
