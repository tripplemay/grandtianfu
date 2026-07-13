# Proposed Learnings Archive — v0.9.x

> 已闭环的提案归档。每条记录：原始提案、用户裁决、落地位置。

---

## [2026-04-19] Planner (Kimi) — 来源：BI1-F008 RLS empty-string GUC flaky

**类型：** 新坑（技术坑）

**原始提案：**
PostgreSQL RLS 策略用 `current_setting('app.xxx', true)::uuid` 直接 cast 存在 session 污染坑 —— GUC 被 SET LOCAL 触达过后返回 `''` 而非 NULL，空串 cast 抛 `invalid input syntax`，导致 RLS USING 谓词失败、`withPlatformAdmin` 绕过设计失效，表现为 Prisma 连接池复用下的随机 flaky。**所有 RLS 策略模板必须用 `NULLIF(current_setting(...), '')::uuid` 兜底**。

**用户裁决（2026-04-20）：** ✅ 采纳

**落地位置：** 新增 `framework/harness/database-patterns.md` §1（v0.9.1）

---

## [2026-04-19] Planner (Kimi) — 来源：BI1-F010 CI job acceptance 偏离

**类型：** 新规律（Planner 自律）

**原始提案：**
Planner 写 CI workflow job acceptance 时，必须先与**同批次的 helper/策略设计**交叉核对，避免 acceptance 文案与实现冲突。具体：如批次选 Testcontainers（测试代码自启容器），CI acceptance 就不应写 "service container"；两者互斥，混用会制造死代码 + 维护困惑。通用化表述：「Acceptance 文案必须与同批次 F00x helper/config spec 交叉核对一次再定稿」。

**用户裁决（2026-04-20）：** ✅ 采纳

**落地位置：** `framework/harness/pre-impl-adjudication.md` §9.1 Planner 写 spec 自检清单（v0.9.1）

---

## [2026-04-20] Planner (Kimi) — 来源：BI2 DB 命名坑

**类型：** 新规律（Planner 自律）

**原始提案：**
涉及数据库命名 / 角色名 / grant 对象的 spec 写作前，Planner 必须先扫一遍项目现存 `prisma/migrations/*/migration.sql`，提取 migration 里硬编码的 DB 名 / 角色名 / 权限对象名。spec 和 environment docs 的字面命名必须与 migration 硬编码**完全一致**；如冲突以 migration 为准（migration 已执行过就是事实，文档必须追随）。

**用户裁决（2026-04-20）：** ✅ 采纳

**落地位置：** `framework/harness/database-patterns.md` §2 "数据库命名 / 角色 / Grant 对象必须与 migration 硬编码一致"（v0.9.2）

---

## [2026-04-20] Planner (Kimi) — 来源：BI2-F002 PM2 zero-downtime 两轮证伪

**类型：** 新坑（技术坑 + Planner 自律）

**原始提案：**
PM2 cluster 的 zero-downtime reload **不是** "cluster mode + instances ≥ 2" 自动拥有的能力，必须同时满足 3 条：(1) worker 是 PM2 直接子进程；(2) app 主动 `process.send('ready')`；(3) `wait_ready: true` + 合理 `listen_timeout`。Next.js 生产 + PM2 cluster 唯一可靠路径 = custom `server.js` + `wait_ready`，不是可选优化。

**用户裁决（2026-04-20）：** ✅ 采纳

**落地位置：** 新增 `framework/harness/deploy-patterns.md` §1 "PM2 cluster zero-downtime reload 的 3 个必要条件"（v0.9.2）

---

## [2026-04-23] Planner (Kimi) — 来源：BI3-F005 签收漏 + BAux1 deploy 失败

**类型：** 新坑 + 签收流程补丁（合并 2 个关联 gap）

**原始提案：**

Gap 1：Reviewer 签收"VPS 上产出某 artifact"类 feature 时只核对"artifact 存在 VPS 上"，未核对"artifact 是否 in git"。BI3-F005 的 `scripts/cert-expiry-check.sh` 被 Generator 在 VPS 直接创建，签收 PASS 但脚本从未 commit。86 行代码活在 prod 单机，任何 re-deploy 都会丢。

Gap 2：Generator/Planner 在 VPS SSH 直接编辑 `src/middleware.ts` 加 debug log 诊断后未清理也未 commit 回本地。3 天后 `deploy-prod.sh` 跑 `git checkout` 时被 working tree 冲突阻塞。

规律总结：(1) Reviewer 签收类 "VPS 产出" feature 必须加 `git ls-files` 核对；(2) VPS ad-hoc 编辑完成必须 clean checkout 或 push 回 git；(3) deploy-prod.sh 应前置 `git status --porcelain` early fail。

**用户裁决（2026-04-23）：** ✅ 采纳（都做）

**落地位置：** `framework/harness/deploy-patterns.md` §2 "VPS working tree 卫生 + artifact in-git 强制"（v0.9.3）

**同步动作：**
- `scripts/deploy-prod.sh` 加 `git status --porcelain` 前置 check（留 BI2 spec 后续更新，本次 framework 只定规则不改 script）
- Reviewer 下次签收类似"VPS 产出" feature 时必须走新 checklist（§2.4）

---

## [2026-04-24] Planner — 来源：MVP-visual-fidelity-hotfix F001 越界事件

**类型：** 新坑 / 铁律补充

**原始提案：**
Generator 在 BM2 F005 完成后、F006 开工前未等 Planner 裁决就启动了 MVP-visual-fidelity-hotfix F001（公共组件库抽取），写了 pre-impl 审计但 §7 自裁决"全 A 无偏离方案；跨批次执行已用户授权"（实际用户未给此授权，Generator 误读了 Planner Phase 2 三点决议）。技术产出合理（7 文件代码质量良好），但流程两处违规：(a) 自裁决违反 `pre-impl-adjudication.md` §2.3；(b) 跨批次执行违反 hotfix spec §6 顺序约束。用户选 Option 3 接受产出 + 补流程补丁。

**用户裁决（2026-04-26）：** ✅ 采纳（B 套餐，含 framework v0.9.4 沉淀）

**落地位置：**
- `framework/harness/pre-impl-adjudication.md` §4.6 "Generator 自裁决"（含同 agent 豁免规则）
- `framework/harness/pre-impl-adjudication.md` §4.7 "Generator 跨批次启动"（含边界 + 判定原则）
- `harness-rules.md` §铁律第 10 条（features.json feature 号归属强制）
- CHANGELOG v0.9.4

**关联信号：** 同时记录 BM2 building 期间 role_assignments johnsong 同时担任 planner+generator 触发了 §4.6 §4.7 — 不升为新硬规则（harness §6 仍允许重叠）但保留警告。新 Planner（Kimi）2026-04-26 接手时把 planner 切回 Kimi 隔离。
