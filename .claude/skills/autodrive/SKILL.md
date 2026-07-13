---
name: autodrive
description: 自主开发心跳的单次唤醒入口——把 progress.json.status 当程序计数器，跑一个指令周期（取状态→派发单阶段步→机械回写→闸门检查→推进或硬停→自排下一次）。仅在已装机件 + 合法 autonomy-policy.json 存在时使用；配合 /loop 动态自排程。
---

<!-- autonomous-mode.md 的 Dispatcher 组件 + §4 控制流。
     本 skill 是耐久层：调 .claude/autonomous/gate-arbiter.workflow.js 拿决策，自己按下 commit/推进/重排键（§8：引擎不 flip status）。 -->

# /autodrive — 自主心跳单次唤醒（一个指令周期）

**你是耐久层，不是评估者。** 每次唤醒严格按序执行；任一步 fail-closed 就**硬停并停止排程**，不留半开状态。
完整设计见 `framework/harness/autonomous-mode.md`。**可逆内环先行；deploy/prod/spend 永远留人类闸门。**

## 步骤 0 —— 前置机件断言（机件在位 = 开车前置条件；缺一即 HARD_HALT）

开跑前逐项断言，**任一不满足 → 打印原因、`ScheduleWakeup(stop:true)`、STOP，不回写、不排下一次**：

1. `.claude/settings.json` 已合入 `.claude/autonomous/settings.autodrive.json` 的 deny-list（deploy/migrate/prod/花钱 MCP + policy 只读）
2. `bash .claude/autonomous/validate-autonomy-policy.sh autonomy-policy.json` 退出 0（策略合法、未过期、`auto_cross` 不含 C、`authorized_by=user`）
3. 受限 subagent 定义就位：`generator-restricted`（build/fix 用）+ `spec-lock critic`（写盘前用）
4. verdict 工件 schema 校验 hook 就位（机件 #3）

> 机制没装齐，护栏就是纸面——宁可不开车。

## 步骤 1 —— FETCH（取最新状态）
- `git pull --ff-only origin main`
- 从磁盘读 `progress.json` / `features.json` / `autonomy-policy.json`；组装 `state`（status、current_sprint、fix_rounds、features）、`ledger`（累计 tokens/cost/wake_n/same_feature_fail_streak）
- 取当前 UTC 时间字符串 `now`（供 gate-arbiter；Workflow 内 Date 不可用，须由本层注入）

## 步骤 2 —— LOCK（并发唤醒护栏，§9）
- 读 `progress.json.wake_in_progress`：若存在且未超时（`started_at` 在 stale 窗口内）→ 说明上一唤醒仍在跑，**本次立即返回，不重排**（避免双跑抢 push）
- 否则写入 `wake_in_progress = {wake_id, started_at: now}`，commit

## 步骤 3 —— IDEMPOTENCY（崩溃前跳）
- 若 status 隐含的步已反映在状态里（如"下一 pending feature"实际已 completed，说明上次 execute 后、writeback 前崩溃）→ 前跳，不重做该步

## 步骤 4 —— 派发一个指令周期（调 Gate Arbiter）
- 运行 `.claude/autonomous/gate-arbiter.workflow.js`，传 `args = { state, policy, ledger, now, diff }`（`diff` = 本批未提交 `git diff`，供 spec-lock critic）
- Arbiter 内部：纯函数 `governor` 判 halt → `decode` status → 会写盘前先跑 spec-lock critic → EXECUTE 单步（verify 派隔离 evaluator + PASS 抽样查证据；build 派 `generator-restricted`）
- Arbiter **返回决策**，不 flip status：`{ decision, gateClass, proposedNext, writeback, reasons }`

## 步骤 5 —— 按 decision 处置
| decision | 含义 | 动作 |
|---|---|---|
| `HALT` | governor/critic/未知态触发 | 记 halt 原因入 session_notes → 释放 lock → **PushNotification 通知用户** → `ScheduleWakeup(stop:true)` → STOP |
| `DONE_PENDING_USER` | 批次跑完，→done 是 Class B | 同上（批次完成通知），**不自动置 done**，等用户确认 |
| `HANDBACK` | Class B 需授权但 policy 未授权 | 同上，交用户确认跨闸门 |
| `ADVANCE` | Class A 可逆，或 Class B 且 policy.auto_cross 含 B | 进步骤 6 |

## 步骤 6 —— WRITEBACK（机械原样，§8 + 铁律 12）
- 每个已验/已实现 feature **立即**写 `features.json`（逐条，不等全量，抗中途崩溃）
- evaluator 的 `evaluator_feedback` **逐字**写入 `progress.json`；FAIL/PARTIAL feature 改回 pending
- **断言 verdict 工件**：`docs/test-reports/{BL-id}-verdict.json` 存在且每 feature `evidence`/`steps_to_reproduce` 非空
  - 缺失/空壳 → **重跑该 verify 步上限 1 次**；仍缺 → `evaluator_cannot_verify` 硬停 + 通知，**绝不静默无限重跑**
- 把 `proposedNext` 写入 `progress.json.status`（此处才是"按下阶段推进键"——由耐久层做，非引擎）

## 步骤 7 —— ACCOUNT（记账，铁律 6）
- 追加 `progress.json.autonomy_ledger` 条目：`{ wake_ts: now, status_before→after, gate_crossed, authorized_by_policy_version, tokens, cost, fix_round, verdict_ref }`
- 覆盖写 `session_notes['autodriver']`：本轮做了什么、跨了哪个闸门、下一步

## 步骤 8 —— COMMIT
- `git status --short docs/test-reports/ docs/test-cases/ .auto-memory/` 确认测试产物入库
- 清空 `wake_in_progress`（释放 lock）→ commit + `git push origin main`

## 步骤 9 —— RESCHEDULE 或 收尾
- 若步骤 5 已 HALT/DONE_PENDING_USER/HANDBACK → 已 stop，不到此步
- 否则 `ScheduleWakeup(delaySeconds = policy.wake_interval_s[当前阶段], prompt = "/autodrive", reason = "autodrive 下一唤醒：<阶段>")`
- 存活告警（§9）：若距上次成功唤醒 commit 超过预期窗口 → PushNotification（防心跳静默停摆）

---

## 不变量（任何唤醒都不得违反）
- **引擎不按阶段推进键**：status 的 flip 只在步骤 6 由本耐久层做，gate-arbiter 只返回 `proposedNext`
- **铁律 12**：派 evaluator 的 prompt 用固定模板，只插值 `{批次, spec/feature 路径, L2-flag}`，无实现叙述、无质量定性
- **Class C 在工具层被拒**：deploy/prod/spend 由 deny-list 拦，不依赖闸门分类器——闸门分类器只是兜底
- **每轮以 commit 结束**：唤醒之间 kill/压缩零丢失，下轮纯从磁盘状态恢复
- **fail-closed**：策略缺失/过期/非法、机件未装、工件校验不过 → 硬停 + 停排程，绝不降级放行
