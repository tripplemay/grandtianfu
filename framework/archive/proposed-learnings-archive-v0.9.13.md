# Proposed Learnings Archive — v0.9.13

> 归档日期：2026-05-06
> 来源批次：BL-024-ghost-controls-cleanup（B4 ghost-controls 实装 + F006 retroactive hotfix）
> 闭环情况：2 条 learnings 全部 Accept（用户决议）+ 落 framework，CHANGELOG v0.9.13 已记录。

---

## [2026-05-06] Generator Kimi（BL-024 F006 retroactive hotfix 起源）+ Planner johnsong 实战 Q2 ops 实地核查 — v0.9.13 #1：spec acceptance 改 deploy-script 时同 commit 必须改对应 yml workflow

**类型：** 新规律（铁律级别 — 与 v0.9.12 §deploy-patterns.md §5 互动延伸）

**内容：** BL-034 F001 spec acceptance 已 done @ dbbfbb3（deploy-prod.sh 加 ALTER ROLE 段 line 71-81）但漏了同 commit 改 .github/workflows/deploy-prod.yml script 块加 `set -a; source .env.production; set +a` 桥接 → GH Actions Run 时 KOLMATRIX_APP_PASSWORD env var 不会 export 到 shell 环境 → ALTER ROLE 段 silent skip → prod kolmatrix_app 角色实际仍用 init migration 字面 'kolmatrix_app' 弱密码（CRIT-1 fix 未在 prod 生效 1+ 周）。

Planner johnsong 在 BL-024 prod redeploy ops 准备阶段（2026-05-05 23:00）实地核查发现 — deploy-prod.sh 注释明示但 yml 实装漏。BL-024 F006 retroactive hotfix（commit eacbbbb）补 yml 桥接。

**根因：** spec 起草时 Planner / Generator 对「deploy 链」的端到端理解仅停在 deploy-script 层，未明确「shell env 来源 = yml 桥接」这一上下游关系。

**建议写入：** `framework/harness/deploy-patterns.md §5` 后追加 §5.1「spec acceptance 改 deploy-script 时同 commit 必须改对应 yml workflow」：含 Planner spec lock checklist + Generator 实装 checklist + Reviewer L2 deploy log warning 抓取强制 + BL-034 F001 → BL-024 F006 实战反面案例。

**状态：** ✅ Accept + 落档（v0.9.13 — 用户 2026-05-06 决议）。`deploy-patterns.md §5.1` 含 4 步修订规则 + grep checklist + Reviewer 强制段 + BL-034 F001 反面案例。CHANGELOG v0.9.13 已记录。

---

## [2026-05-06] Planner johnsong（BL-024 Q2 ops + BL-035 F013 同源痛点）— v0.9.13 #2：mcp__aigc-gateway create_action_version schema 应暴露 max_tokens 字段

**类型：** 模板修订（mcp tool schema 扩展提案 — 跨项目）

**内容：** Planner Q2 ops（2026-05-05 23:30）执行 BL-035 F013 aigcgateway 服务端协调时发现 `mcp__aigc-gateway create_action_version` schema 仅含 messages / variables / changelog / set_active，完全无 max_tokens 字段暴露。`mcp__aigc-gateway update_action` 也仅含 name / description / model。`get_action_detail` 返回 activeVersion 但不含 maxTokens。导致 v0.9.11 §ai-action-contract.md §4 max_tokens 矩阵 dogfood 无法通过 mcp 完整自动化，必须用户登录 aigcgateway Dashboard UI 手工设。

**影响：** prod-mvp-readiness audit + BL-035 F013 / BL-024 Q2 ops 都需要这个能力做完整 dogfood 自动化；本项目 6 个 Action max_tokens 推 Soft-watch 已是历史第二次（BL-035 + BL-024 两个 batch 共 12 次推延 max_tokens 设到 UI）。

**建议写入：**
1. 跨项目 issue（aigcgateway 项目独立项目，非 KOLMatrix 范围）：mcp 工具 `create_action_version` + `update_action` 应暴露 `max_tokens` 字段；同时 `get_action_detail` 返回应含 `activeVersion.maxTokens` 以便 dogfood 验证「目标值已设」
2. 短期 KOLMatrix 端：在 `framework/harness/ai-action-contract.md §4` 加 §4.7「mcp 自动化可达性」注解明示 max_tokens 部分必须列入 user 手工待办 + Soft-watch 兜底

**状态：** ✅ Accept + 落档（v0.9.13 — 用户 2026-05-06 决议）。`ai-action-contract.md §4.7` 含 mcp 字段范围矩阵 + 短期 KOLMatrix 端 spec 注解 + 长期跨项目 issue 3 项 + 清理触发条件 + 12 次推延实战数据。CHANGELOG v0.9.13 已记录。
