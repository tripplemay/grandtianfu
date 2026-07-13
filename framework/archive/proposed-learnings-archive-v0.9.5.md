# Framework 提案暂存区

> Generator 和 Evaluator 在工作中发现值得沉淀的经验时，追加到本文件。
> Planner 在 done 阶段读取本文件，逐条提交给用户确认。
> 确认后由 Planner 正式写入 `framework/` 对应文件，并在 `CHANGELOG.md` 追加记录，最后从本文件移除已确认条目。
> 已闭环条目归档到 `framework/archive/proposed-learnings-archive-vX.Y.md`。

---

## [2026-05-01] Planner johnsong — 来源：B5 7 轮 fixing + MVP-internal-demo-prep 3 轮 fixing 累积经验

下列 12 条候选由 Planner 在 MVP-internal-demo-prep done 阶段统一提交。每条标 [#x] 编号方便用户裁决。

---

### [#1] staging deploy runbook 必含 `prisma migrate deploy`

**类型：** 模板修订
**来源：** B5 fixing-2（commit cfd9c1e；Reviewer L2 FAIL 根因 = staging DB 缺 F001 migration → P2022 ColumnNotFound on `kol.channel_created_at`）

**内容：** 任何批次涉及 prisma schema 变更（新 migration 文件）时，staging deploy 步骤必须显式列「`npx prisma migrate deploy`」一步；否则代码部署后跑 production query 立刻 P2022。`git pull → npm ci → prisma migrate deploy → build → pm2 reload` 是缺一不可的链。

**建议写入：** `framework/harness/deploy-patterns.md` §3「Staging/Prod deploy 完整链 checklist」（新增 §3）

**状态：** 待确认

---

### [#2] staging deploy runbook 必含「数据回填 / enrich / seed」步骤

**类型：** 模板修订
**来源：** B5 fixing-3（staging F002 enrich 历史从未跑 → 5/5 抽样 KOL banner/age/videoCount 全空）；MVP fixing-2（staging seed 漏 KolCampaign rows + KOL.email → C-10 outreach 不可用）

**内容：** 当批次代码包含「数据填充脚本」（enrich / seed extension）时，staging deploy 步骤必须显式列脚本跑动 + 抽样验证。F001/F002 commit 验脚本本身 OK，但「staging 真实跑通」是独立 gate，runbook 漏 = 必踩。

**建议写入：** 同 #1 §3 同位置，作为 #1 的连带条款

**状态：** 待确认

---

### [#3] PM2 6.0.14 `env_file` 不可靠 → 必须 `pm2 delete` + sourced-shell start

**类型：** 新坑
**来源：** B5 fixing-4（staging /proc/<pid>/environ 无 AIGCGATEWAY_KOL_TOPIC_ACTION_ID 即便 .env.staging 已加；`pm2 reload --update-env` 不重读 env_file）

**内容：** PM2 6.0.14 在多次 reload + restart 后不再触发 `env_file` 重读 —— 初次部署的 shell 环境变量被 PM2 daemon 锁定为快照。新增 env var 后必须：

```bash
pm2 delete <app>           # 而不是 reload
set -a && source .env.<env> && set +a   # shell 显式注入
pm2 start ecosystem.config.js --only <app>
```

`ecosystem.config.js` 里的 `env_file:` 字段给人「PM2 会管」的错觉，实际不可靠。

**建议写入：** `framework/harness/deploy-patterns.md` §1（扩展 PM2 zero-downtime reload 段，加 anti-pattern 子节）

**状态：** 待确认

---

### [#4] aigcgateway action 输出 shape + variables 契约会漂移

**类型：** 新规律
**来源：** B5 fixing-5（实际返回裸 JSON 数组而代码期望 `{keywords: [...]}`）；MVP fixing-3（customize action 'variables' contract drift）

**内容：** aigcgateway Action 的 output shape 和 variables 契约不可仅信 spec 文档 —— 实际 prod 端可能裸数组、可能包装对象、可能 fenced markdown。**新 action 集成必须先 `curl POST /v1/actions/run` 看真 response 再写 parser**。Parser 设计原则：兼容 `Array.isArray(parsed) ? parsed : parsed?.keywords` 双 shape；后续 action 升级也不破。

**建议写入：** 新文件 `framework/harness/ai-action-contract.md` §1「Action 集成开工前必跑 dry-run + parser 双 shape 兼容」

**状态：** 待确认

---

### [#5] aigcgateway 调用 timeout 需 ≥10s（不能用 5s 默认）

**类型：** 新坑
**来源：** B5 fixing-6（日文 KOL 6 个标题 prompt token ≈606 → 5s timeout 偶发踩；实际 1s 即返回 8 keywords，但 P95 远超 5s）

**内容：** 多字节语言（中/日/韩）+ 重 token 内容下，aigcgateway action P95 latency 可能 5-10s。代码 timeout 5s 会偶发 fail → cache 不写入 → 永远 empty state。**默认 timeout 设 10s 起步**；CJK / 长文本 prompt 设 15s；超时 fallback 必须有用户感知（loading/retry CTA），不可 silent 写空 cache。

**建议写入：** 新文件 `framework/harness/ai-action-contract.md` §2「Timeout 起步 10s + CJK 15s + fallback 不可 silent」

**状态：** 待确认

---

### [#6] `chore(state)` commits 不触发 staging deploy + Reviewer 严收紧 SHA 对齐 → 死循环

**类型：** 新坑
**来源：** B5 fixing-7（reverifying-6 staging /api/health=ee45543 vs HEAD=e493ab4 mismatch；e493ab4 仅是 chore commit progress.json 改动，但 Reviewer 卡 SHA 对齐 → 必须再跑一次 staging deploy 同步 SHA → 又生 fixing-7 chore commit → 又 mismatch... 死循环风险）；MVP fixing-2（同样 SHA mismatch）

**内容：** `chore(state)` / `chore(planner)` / `test(...)` 类 commits 不变更产品代码，paths-ignore 配置使其不触发 staging deploy（合理）；但 Reviewer 严收紧 SHA 对齐会判 FAIL。**Planner 在 verifying 切换前必须确保 staging /api/health.git_sha = main HEAD（不论 HEAD 是否是 chore commit）**。两种解：(a) chore commit 后 Planner 自己 SSH 跑 staging redeploy 同步 SHA；(b) Reviewer 签收规则容许 chore-only 差异（白名单 SHA-1...SHA-2 范围内仅 paths-ignore matched 的差异 = 等价部署）。

**建议写入：** `framework/harness/deploy-patterns.md` §3 末尾 + `framework/harness/evaluator.md`「SHA 对齐严收紧的边界」段

**状态：** 待确认

---

### [#7] Spec 必须列「数据准备步骤」满足 ≥X 条完整数据条件（避免抽样污染）

**类型：** 模板修订
**来源：** B5 fixing-3（staging 96% youtube KOL 缺 channelId → Reviewer 抽样的 5 个全在污染池里 → FAIL 在 spec 没覆盖的地方）；MVP fixing-2（seed 数据虽然有 5 个 Product，但 KolCampaign rows 没建、KOL.email 没填，C-10 测试场景全空）

**内容：** Spec 起草时不能假设「seed 数据 = 测试可用」。Planner 必须显式列：「Reviewer 验收前提：staging/prod tenant 必须满足以下数据条件：(a) ≥X 条 fully-enriched KOL / (b) ≥Y 个 product-linked + KOL-emailed Campaign / 等」+ Planner 提供白名单 ID 给 Reviewer 抽样（避免随机抽到污染样本）。

**建议写入：** `framework/harness/planner.md` §"Spec 起草必含「数据准备步骤」" 新段 + `framework/harness/pre-impl-adjudication.md` 模板补充

**状态：** 待确认

---

### [#8] alpha tag 依赖（如 `@visx/wordcloud@4.0.1-alpha.0`）types 漂移 → ambient .d.ts shim 兜底

**类型：** 新坑
**来源：** B5 fixing-1（CI typecheck pass on f8fca4b 但本地 typecheck FAIL on TopicCloudCanvas.tsx — Cannot find module @visx/wordcloud + implicit any。原因：alpha-tag install drift — npm install/ci 跨循环 .d.ts 不稳定）

**内容：** 引入 alpha / beta / rc tag 依赖时，必须同时建 `src/types/<package>.d.ts` ambient shim 镜像 upstream surface（Wordcloud / BaseDatum / etc）。upstream types 加载时本地 shim 是 no-op override；upstream types 漂移时 shim 兜底。Generator 开工 spec § dependencies 段必须 explicit 标注 alpha/beta tag + 要求 shim。

**建议写入：** `framework/harness/generator.md`「Alpha/Beta/RC 依赖必须 ambient shim」新段 + spec 模板 (`framework/templates/spec-template.md` 如有) deps 段示例

**状态：** 待确认

---

### [#9] Prisma 7 Json 列输入需 `as Prisma.InputJsonValue` cast

**类型：** 新规律
**来源：** B5 F004 recent-videos.ts:140 + F006 topic-cloud.ts:211（同一坑 — `Record<string, unknown>` 不被 Prisma JSON column 接受 TS2322）

**内容：** `tx.kol.update({ data: { metadata: someObj } })` 当 `someObj` 是 `Record<string, unknown>` 或 `unknown` 时 TS 拒绝，需 `as Prisma.InputJsonValue` cast 或者把 `mergeMetadata` 函数返回类型直接收紧到 `Prisma.InputJsonValue`（推荐后者，避免每个调用点 cast）。**任何写 JSONB 列的 lib 函数返回类型应是 `Prisma.InputJsonValue` 而非 `Record<string, unknown>`。**

**建议写入：** `framework/harness/database-patterns.md` 新增「§ Prisma JSON 列写入类型」段

**状态：** 待确认

---

### [#10] `update-visual-baselines` workflow GITHUB_TOKEN push 不触发下游 CI

**类型：** 新坑
**来源：** B5 F006 visual baseline regen 多次（commits 68eaca4 + 6ded637 baseline 重生 + 14ea522 / 172c2df / 5b2f622 retrigger commits）

**内容：** GitHub Actions workflow 用 GITHUB_TOKEN 推 commit（如 `update-visual-baselines.yml`）默认不触发下游 workflow（GitHub 防 infinite loop policy）。Visual baseline 重生后 CI 不会自动跑 visual regression 验证 → 必须手动跟一个 real-content commit 触发（empty commit 也不行，paths-ignore matches 全部时 CI skip）。

**建议写入：** `framework/harness/deploy-patterns.md` §4「Visual baseline regen 注意事项」新段

**状态：** 待确认

---

### [#11] `progress.json` 写入后必须 JSON 解析校验 + pre-commit hook

**类型：** 铁律补充
**来源：** MVP commit b44b79d（Generator 推上去的 progress.json session_notes 块缺一个 `}` 导致 `python json.load` 失败；状态机字段读写如靠 jq/json-parse 即挂；2026-05-01 Planner SSH 通畅 commit 时顺手发现并修）

**内容：** 状态机文件（`progress.json` / `features.json` / `backlog.json`）写入后，commit 前必须跑 `python3 -c "import json; json.load(open('<file>'))"` 验证；建议 `.git/hooks/pre-commit` 加自动校验，挂钩失败拒提交。harness rule §铁律 增补一条「状态机 JSON 文件 commit 前 parse 校验」。

**建议写入：** `framework/harness/harness-rules.md` §铁律新增第 11 条 + `framework/templates/pre-commit-hook.sh` 新建（如已有 templates/ 目录）

**状态：** 待确认

---

### [#12] Smoke checklist 起草后 Planner 必须 grep 实际代码验证 elements 存在性

**类型：** 模板修订
**来源：** MVP fixing-1（C-03 /database 三卡 Reviewer 报「Market Intel/Campaign Timing/Budget Benchmark 缺失」但实际三卡名是「AI Intelligence/Coverage Gap/Engagement」 — checklist 文本陈旧 vs 代码现状）

**内容：** Planner 起草 prod L2 smoke checklist 时，每条 UI 元素描述（"X 卡可见" / "Y 按钮存在"）必须 grep 实际代码 / 跑实际页面验证一遍 —— 不可凭 spec 描述写。Reviewer 若按 stale checklist 验收，要么误标 FAIL 浪费 fixing 轮，要么误标 PASS 漏掉真 bug。

**建议写入：** `framework/harness/planner.md` §"Verifying 前 checklist 起草" 新段 + `framework/harness/evaluator.md` "checklist 文本陈旧时直接 update 而非标 FAIL" 段

**状态：** 待确认

---

> 用户裁决格式建议：每条贴 `[#x] ✅ 写入` / `[#x] ❌ 不写` / `[#x] ✅ 但改写入位置：<path>` / `[#x] ⚠️ 修订内容：<注>`
