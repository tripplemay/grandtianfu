# progress.json 自主模式字段（草案）

> autonomous-mode.md 机件 #5 的状态字段（**不**在 `progress.init.json` 默认铺入）。
> 自主模式开启时把下面的 `autonomy` 命名空间块合并进项目 progress.json；关闭自主时整块删除即可，
> 不污染基础状态机字段。**遵循「每条信息只存一处」：这里只放自主运行的过程状态，不重复 status/features。**

## 合并进 progress.json 的块

```json
{
  "autonomy": {
    "status": "running",
    "policy_version": "2026-07-12T00:00:00Z",
    "wake_in_progress": null,
    "last_halt": null,
    "ledger": []
  }
}
```

## 字段语义

| 字段 | 含义 | 写者 |
|---|---|---|
| `autonomy.status` | `running` \| `halted` \| `done_pending_user`——自主运行总闸 | /autodrive |
| `autonomy.policy_version` | 授权本次运行的 `autonomy-policy.json` 的 `expires_at`（版本戳），记账用 | /autodrive |
| `autonomy.wake_in_progress` | 并发锁（§9）：`{wake_id, started_at}` 或 `null`；非空且未超时 = 上一唤醒仍在跑，新唤醒立即返回 | /autodrive |
| `autonomy.last_halt` | 最近一次停机：`{condition, at, detail}` 或 `null` | /autodrive |
| `autonomy.ledger` | 追加型记账（机件 #5），每唤醒一条（见下） | /autodrive |

### ledger 条目
```json
{ "wake_ts": "ISO", "status_before": "building", "status_after": "verifying",
  "gate_crossed": "A", "tokens": 12345, "cost_usd": 0.42, "fix_round": 0,
  "verdict_ref": "docs/test-reports/BL-XXX-verdict.json" }
```

### halt_conditions 枚举（`last_halt.condition` 取值）
`policy_disabled` · `policy_expired` · `scope_mismatch` · `budget_breach:{tokens|cost|wakes}` ·
`max_fix_rounds` · `no_progress` · `spec_lock_required` · `scope_drift` · `feature_blocked` ·
`evaluator_cannot_verify` · `debias_conflict` · `ci_red` · `worktree_conflict` · `batch_complete`

## 派生（不另存字段）
- **`spec_locked`**（gate-arbiter plan 分支用）= `!!docs.spec && features.length > 0`，
  由 /autodrive **每唤醒即时计算**注入 `state.spec_locked`，**不**在 progress.json 另存——
  避免与既有 `docs.spec` 重复状态（框架「每条信息只存一处」铁律）。
