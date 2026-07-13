// autonomous-mode.md 机件 #4「确定性 Gate Arbiter + Governor」。
// 由 /loop /autodrive 每次唤醒调用一次，跑「一个指令周期」。
// 安全关键逻辑（governor / classifyGate / budget）是纯函数，零模型判断。
// §8 契约：引擎不 flip status——本 workflow RETURN 决策，由耐久 /autodrive 层做 commit + 推进 + 重排。
// 约束：Workflow 内 Date 不可用 → 时间通过 args.now（ISO-8601 UTC 字符串）传入；过期硬判在 validate-autonomy-policy.sh。
// 依赖已装 subagent：agentType 'generator-restricted'（机件 #0）、'spec-lock-critic'（机件 #2），均在 .claude/agents/。

export const meta = {
  name: 'autodrive-gate-arbiter',
  description: 'One autonomous wake cycle: deterministic governor + gate classifier, dispatch one phase-step, return decision (never flips status)',
  phases: [{ title: 'Wake' }],
}

// ==================== 纯函数：安全关键，零模型判断 ====================

// 闸门分类：(from → to) → 'A' 可逆内环/同阶段继续 / 'B' →done / 'C' 不可逆
function classifyGate(fromStatus, toStatus) {
  if (toStatus === fromStatus) return 'A'          // 同阶段继续（如 building 下一 feature），非跨越
  if (toStatus === 'done') return 'B'
  const reversibleInner = new Set([
    'planning>building', 'planning>verifying',
    'building>verifying', 'verifying>fixing',
    'fixing>reverifying', 'reverifying>fixing',
  ])
  return reversibleInner.has(`${fromStatus}>${toStatus}`) ? 'A' : 'C'
}

// Governor：命中任一 halt_condition → 停。now 为 ISO 字符串（同格式 UTC 可字典序比较）。
function governor(state, policy, ledger, now) {
  const halts = []
  if (!policy || policy.enabled !== true) halts.push('policy_disabled')
  if (policy && policy.expires_at && now >= policy.expires_at) halts.push('policy_expired')
  if (policy && policy.batch_scope !== state.current_sprint) halts.push('scope_mismatch')
  const b = (policy && policy.budget) || {}
  if (ledger.tokens >= (b.max_tokens ?? Infinity)) halts.push('budget_breach:tokens')
  if (ledger.cost_usd >= (b.max_cost_usd ?? Infinity)) halts.push('budget_breach:cost')
  if (ledger.wake_n >= (b.max_wakes ?? Infinity)) halts.push('budget_breach:wakes')
  if (state.fix_rounds >= (b.max_fix_rounds ?? Infinity)) halts.push('max_fix_rounds')
  if ((ledger.same_feature_fail_streak ?? 0) >= 2) halts.push('no_progress')
  return { halt: halts.length > 0, reasons: halts }
}

// status → 下一动作（纯映射，不执行）
function decode(status) {
  return ({
    new: 'plan', planning: 'plan',
    building: 'build', fixing: 'build',
    verifying: 'verify', reverifying: 'verify',
    done: 'finish',
  })[status] || 'unknown'
}

const CRITIC_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['violation', 'detail'],
  properties: {
    violation: { type: 'boolean' },
    detail: { type: 'string' },
    offending_files: { type: 'array', items: { type: 'string' } },
    unmapped_tags: { type: 'array', items: { type: 'string' } },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false, required: ['verdicts', 'all_pass'],
  properties: {
    all_pass: { type: 'boolean' },
    verdicts: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['feature_id', 'result', 'evidence', 'steps_to_reproduce'],
      properties: {
        feature_id: { type: 'string' },
        result: { type: 'string', enum: ['PASS', 'PARTIAL', 'FAIL'] },
        evidence: { type: 'string', minLength: 1 },          // 机件 #3：证据非空
        steps_to_reproduce: { type: 'string', minLength: 1 },
      } } },
  },
}

// 机件 #6 去偏：主 evaluator 档位按 wake_n 确定性轮换（Workflow 内无 Math.random）；
// 第二 evaluator 取"下一档"，永远与主档位不同 → 打破相关模型盲点。档位表为可调旋钮。
const EVAL_TIERS = [{ model: 'opus', effort: 'high' }, { model: 'sonnet', effort: 'high' }]

// spec-lock 稽核（机件 #2）：在会写盘的 build/fix 步后、推进前跑；critic 自行 git diff，不需传入。
async function specLockCritic(batchScope) {
  const c = await agent(
    `你是 spec-lock 稽核员，稽核 batch_scope=${batchScope}。自行 git show HEAD / git diff HEAD~1 取本次改动，`
    + `对照 features.json 判断是否越 scope 或 commit tag 不映射真实 feature id（铁律 10；`
    + `用 pre-impl-adjudication.md §4.6/§4.7 anti-patterns 为清单）。拿不准判 VIOLATION。`,
    { label: 'critic:spec-lock', phase: 'Wake', effort: 'low', agentType: 'spec-lock-critic', schema: CRITIC_SCHEMA })
  return c
}

// ==================== 一个唤醒周期 ====================
phase('Wake')
const { state, policy, ledger, now } = args

// 1. GOVERN（纯函数）— 任一 halt 条件命中即停，不回写
const gov = governor(state, policy, ledger, now)
if (gov.halt) return { decision: 'HALT', reasons: gov.reasons, writeback: null }

// 2. DECODE
const action = decode(state.status)
if (action === 'unknown') return { decision: 'HALT', reasons: ['undecodable_status:' + state.status] }
if (action === 'finish') return { decision: 'DONE_PENDING_USER', reasons: ['batch_complete'] }

// 3. EXECUTE 单步
let stepResult = null
let proposedNext = null

if (action === 'plan') {
  // 自主模式不自撰 spec（scope 漂移最危险处）——spec-lock 是人类闸门。
  // 仅当已有 locked spec + numbered features + status=planning 时，机械跨到 building/verifying；否则 HALT 交人类。
  const specLocked = state.spec_locked === true   // 由 /autodrive 从 docs/specs + progress.json.docs.spec 判定注入
  if (state.status === 'planning' && specLocked && (state.features || []).length > 0) {
    const allEval = state.features.every(f => f.executor === 'evaluator')
    proposedNext = allEval ? 'verifying' : 'building'
  } else {
    return { decision: 'HALT', reasons: ['spec_lock_required'],
      detail: '自主模式不自撰 spec；请人类先 /plan 锁定 spec 与 features.json 再启动。' }
  }

} else if (action === 'build') {
  // 派受限 generator subagent 实现/修复一个 pending 的 executor:generator feature（跑在 deny-list 下）。
  const pending = (state.features || []).filter(f => f.executor === 'generator' && f.status === 'pending')
  if (pending.length === 0) {
    proposedNext = 'verifying'                     // 所有 generator feature 完成 → 跨到验收
  } else {
    const t = pending[0]
    stepResult = await agent(
      `实现 feature ${t.id}${t.title ? '（' + t.title + '）' : ''}。读 docs/specs 对应段与 acceptance；`
      + `只做本 feature、越界即停；本地自测通过后以 feat(${state.current_sprint}-${t.id}): 独立 commit。`
      + `禁止任何 deploy/生产/花钱动作（deny-list 已强制）。bug 修复须同 commit 补回归测试。`,
      { label: `build:${t.id}`, phase: 'Wake', agentType: 'generator-restricted',
        schema: { type: 'object', additionalProperties: false, required: ['feature_id', 'result', 'files_touched'],
          properties: {
            feature_id: { type: 'string' },
            result: { type: 'string', enum: ['completed', 'blocked'] },
            files_touched: { type: 'array', items: { type: 'string' } },
            blocked_reason: { type: 'string' },
          } } })
    if (!stepResult || stepResult.result === 'blocked') {
      return { decision: 'HALT', reasons: ['feature_blocked:' + t.id],
        detail: (stepResult && stepResult.blocked_reason) || 'generator 返回空/受阻', writeback: stepResult }
    }
    // 机件 #2：完成后、推进前跑 spec-lock 稽核；越界即 HALT 交人类裁决（不自动 revert）。
    const critic = await specLockCritic(state.current_sprint)
    if (critic && critic.violation) {
      return { decision: 'HALT', reasons: ['scope_drift'], detail: critic.detail, writeback: stepResult }
    }
    proposedNext = 'building'                       // 本 feature 完成 → 继续 building，下一 feature 交下一唤醒
  }

} else if (action === 'verify') {
  // 隔离 evaluator（≥4/多维 → fan-out）。对 FAIL/PARTIAL 证伪；对 PASS 抽样查证据（机件 #3）。
  // 机件 #6：主档位按 wake_n 轮换。
  const w = ledger.wake_n ?? 0
  const primaryTier = EVAL_TIERS[w % EVAL_TIERS.length]
  const secondTier = EVAL_TIERS[(w + 1) % EVAL_TIERS.length]

  stepResult = await agent(
    `以隔离 evaluator 验收 batch=${state.current_sprint}。prompt 只含 {spec/feature 路径, L2-flag}，`
    + `无任何实现叙述（铁律 12）。对 FAIL/PARTIAL 证伪已知环境误报；对 PASS 抽样核对 `
    + `steps_to_reproduce + evidence 非空，无证据的 PASS 一律降级 PARTIAL。`,
    { label: 'verify:evaluator', phase: 'Wake', agentType: 'general-purpose',
      model: primaryTier.model, effort: primaryTier.effort, schema: VERDICT_SCHEMA })

  // 机件 #6：每批抽一个 feature 跑第二独立 evaluator（不同档位、fresh context），与主判定对比。
  // 抽样确定性（wake_n % n，无 Math.random）；分歧 → debias_conflict 硬停交人类，防相关盲点整夜传播。
  const feats = state.features || []
  if (stepResult && feats.length) {
    const s = feats[w % feats.length]
    const primary = (stepResult.verdicts || []).find(v => v.feature_id === s.id)
    const second = await agent(
      `你是第二独立 evaluator（去偏抽检）。只验 feature ${s.id}：读 spec/acceptance + 实测，`
      + `独立给 PASS/PARTIAL/FAIL。prompt 无实现叙述、无第一 evaluator 的结论（铁律 12）。`,
      { label: `verify:debias:${s.id}`, phase: 'Wake', agentType: 'general-purpose',
        model: secondTier.model, effort: secondTier.effort,
        schema: { type: 'object', additionalProperties: false, required: ['feature_id', 'result'],
          properties: { feature_id: { type: 'string' }, result: { type: 'string', enum: ['PASS', 'PARTIAL', 'FAIL'] } } } })
    if (second && primary && second.result !== primary.result) {
      return { decision: 'HALT', reasons: ['debias_conflict'], writeback: stepResult,
        detail: `去偏抽检分歧 @${s.id}：主 ${primary.result}（${primaryTier.model}）vs 第二 ${second.result}（${secondTier.model}）——交人类裁决` }
    }
  }
  proposedNext = stepResult && stepResult.all_pass ? 'done' : 'fixing'
}

// 4. 分类结果闸门 + 组装返回。真正的 commit/status flip/reschedule 由耐久 /autodrive 层执行（§8）。
const gateClass = proposedNext ? classifyGate(state.status, proposedNext) : 'A'
const allowed = gateClass === 'A' || (gateClass === 'B' && (policy.auto_cross || []).includes('B'))

return {
  decision: allowed ? 'ADVANCE' : (gateClass === 'C' ? 'HALT' : 'HANDBACK'),
  gateClass,
  proposedNext,          // 目标 status，交 /autodrive 层落盘
  writeback: stepResult, // evaluator_feedback 等由 /autodrive 层原样写 progress.json/features.json（铁律 12）
  reasons: allowed ? [] : [`gate_${gateClass}_requires_user`],
}
