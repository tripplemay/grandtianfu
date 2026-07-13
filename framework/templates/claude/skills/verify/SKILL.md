---
name: verify
description: 启动 Harness 状态机的验收阶段——以隔离 evaluator subagent 独立验收当前批次（无自评铁律的执行入口）。在 progress.json status 为 verifying / reverifying 时使用。
---

# /verify — 验收阶段入口（编排 Evaluator）

**你（主上下文）在本阶段只做编排，不做评估。** 按顺序执行：

1. **前置确认：** status 为 `verifying` / `reverifying`；所有 executor:generator 的 feature 已 completed 且已 push；CI 绿色
2. **启动隔离验收：** 以 `evaluator` subagent 类型（`.claude/agents/evaluator.md`）启动验收。prompt 只含：批次名、progress.json / features.json / spec 路径、[L2 是否已获用户授权]。**不得夹带实现过程叙述或质量定性描述**（harness-rules.md 铁律 12）
3. **规模判定：** completed features ≥4 条或验收维度多 → 按 `orchestration-patterns.md` §4 fan-out（每 feature 一个 evaluator subagent → FAIL/PARTIAL 对抗复核 → 机械汇总）；否则单个 evaluator subagent 全量验收
4. **结论原样落盘：** evaluator_feedback 按 subagent 返回**原样**写入 progress.json；报告确认已落 `docs/test-reports/`；不改写、不筛选、不软化任何 PASS/FAIL 判定
5. **状态流转：** 有 FAIL/PARTIAL → status 置 `fixing`，对应 feature 改回 pending，向用户汇报问题清单；全 PASS 且 signoff 已写入 → status 置 `done`
6. **推送证据：** `git status --short docs/test-reports/ docs/test-cases/` 确认测试产物全部入库后 commit + push
