---
name: project-status
description: 项目当前状态快照（覆盖写，≤30 行）— 当前批次、计划、决策、遗留问题
type: project
---
## 当前批次
- **render-note-b1 ✅ done + 已上线（2026-07-16，PR#86 `8e645e4`）**：效果图唯一标识显示 + 单条可编辑备注（仅实拍页 real-render）；生产 health `ok:true/readonly:false/8e645e4`，api+web 容器 tag 对齐；待用户浏览器 L2 走查（显示id+复制+备注刷新持久）
  - F001 后端 comment 字段（镜像 `set_render_status` 加锁账本 + PATCH 偏更新，status⊥comment 零回归）/ F002 前端类型+客户端 / F003 短id+复制 / F004 备注 UI
  - 备注落生产 `renders.json`（GET 自动透出）→ agent 下轮读用户对每张图的意见做针对性修改
  - 验收：4/4 PASS 0 blocking；api pytest 373 + floorplan_core 154 全绿 0 skip；tsc/lint 绿；data/projects 净空。报告 `docs/test-reports/render-note-b1-verifying-2026-07-16.md`
  - non-blocking：RenderIdChip 手写 button（无同类组件，可辩护，建议后续抽 IdChip）；main.py 1 条既有 ruff I001（pre-existing）
  - 部署链路已验证成功（deploy run 29561027514 success 6m47s）；本条记忆本地记账，未单推 main（避免无谓重新部署，随下次改动搭车）

## 已上线（近期，均已闭环）
- **decor-envelope-b1** ✅ 2026-07-16 `d6d6506`(PR#85)：第7步 auto_check 残余误报——F001 allowed 上沿派生（删双写表）+ F002 窗帘落地帘 `0..2700`（删照抄轴测压扁世界的 `150..1450`）
  - evaluator 首轮 8 硬门 PASS（阳性对照+失明门）→ 部署（api:d6d6506，17:48 UTC）→ **[L2] 已确认**：重出 render f4dab9 `ok=True/0.967`，落地帘缺陷画面上消除
  - 残留 2~3 挂画坏块（3/92 边际，构图敏感）= 挂画盒同样欠建模 → `BL-wall-art-box-undermodeled`(medium，须 [L2] 改盒验)，非回归
- **calib-z-b1** ✅ 2026-07-15 `a73f92d` · **render-fix-b1** ✅ `d9c2b35` · **decor-b3-fix** ✅ `ac98c20`

## 项目概况
- 阅天府 studio monorepo：`apps/api`(FastAPI/Py3.9) + `packages/floorplan_core`(纯 stdlib) + `apps/web`(Next15/Yarn1)

## 关键约束
- **push `main` = 部署生产** → branch→PR→squash，**禁止自动 push main**；⚠ `deploy.yml` 无 paths-ignore，纯文档也触发 → 状态/记忆文件随批次 PR 走
- **ruff 坑**：本机 `python3 -m ruff`（裸 ruff 不在 PATH）；只用 `ruff check`，基线 203 条既有噪声
- **测试红线**：`data/projects/` 是 git-tracked 种子快照，测试绝不可写入；`git add -A` 会扫入脏文件
- **两个 z 世界**：perspective=真实毫米(层高2700) vs axon/scene=压扁dollhouse(1450)，数字不得互借

## 待办 / 遗留
- `BL-wall-art-box-undermodeled`(medium，挂画盒欠建模，须 [L2] 验) / `BL-calib-min-3-anchors`(high) / `BL-input-gate-error-class`(medium) 等
- **framework proposed-learnings**：decor-envelope-b1 学习项已落地 v1.0.7（用户 2026-07-16 已确认）；仅余 2026-07-12 harness-fit 两条零头待落（harness-rules 呼应条 + verify SKILL.md Patch B），与产品功能无关，随时可处理
