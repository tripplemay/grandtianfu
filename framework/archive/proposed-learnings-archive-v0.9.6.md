# Framework 提案暂存区 — v0.9.6 归档

> 本文件归档 v0.9.5 → v0.9.6 闭环的 8 条 proposed-learnings。
> 来源批次：BIx-mvp-polish-pass（2026-05-02）+ BL-025-asset-library（2026-05-02 → 2026-05-03）。
> 处理方式：8 条全部按 Planner 预判落地。
> 归档日期：2026-05-03（Planner johnsong）。
> 详见 framework/CHANGELOG.md v0.9.6 条目。

---
---

## [2026-05-02] Reviewer — 来源：BIx F005 L1 测试

**类型：** 新坑

**内容：** WSL2 跨 Windows fs `/mnt/c/...` 全代码 fast-glob 在默认 vitest 5000ms 超时下偶发 fail（B7b guard test `no-hardcoded-coming-soon-without-issue.test.ts`）。CI 在 Linux 容器跑无此问题，本机 dev 看似 flaky 实为 fs 慢。

**建议写入：** `vitest.config.ts` 给 `tests/unit/no-hardcoded-*` glob 加 `testTimeout: 60_000`；或 `framework/harness/evaluator.md` §测试分层补充段（"WSL2 fs 跨边界场景的 vitest timeout 调优"）

**状态：** 待确认

---

## [2026-05-02] Reviewer — 来源：BIx F005 acceptance §6 O3

**类型：** 模板修订

**内容：** `@next/bundle-analyzer` 不在 devDeps 时 spec §F005 acceptance "实测初始 JS 减 ≥ 200KB gzipped" 无法证证 → 数字层 acceptance 无证据。本质：perf 类 acceptance 必须自带"工具+输出物" checklist，否则验证无从落地。

**建议写入：** `framework/harness/planner.md` §perf 类 acceptance 模板补丁 — perf feature spec 必须含两段："开工前 npm install --save-dev <tool>" + "本工具 in devDeps + ANALYZE=true 报告快照 in `docs/test-reports/`"

**状态：** 待确认

---

## [2026-05-02] Reviewer — 来源：BIx 验收决策

**类型：** 新规律

**内容：** 首轮 verifying PASS（fix_rounds=0）的判据 — 当 acceptance 全部代码层 + L1/L2 全 PASS + soft-watch 项均有兜底（如 7-day follow-up agent / Planner 已声明的 acceptance soft-watch），可直接切 done，无需走 fixing/reverifying。**关键前置：所有 soft-watch 必须在 progress.json / spec 中有明文兜底机制**（不能"反正有问题再说"）。

**建议写入：** `framework/harness/evaluator.md` §verdict 决策矩阵 — 加 row "首轮 PASS 的硬条件：全代码层 PASS + soft-watch 有明文兜底"

**状态：** 待确认

---

## [2026-05-02] Planner — 来源：commit 3da4248 误打包 Generator P3

**类型：** 新坑 + 铁律补充

**内容：** 多角色同工作树并行时，`git add <specific-file>` 不能阻止其他已 staged 内容混入 commit；Planner docs-only commit 误把 Generator F004-P3 在制 9 文件一并打包推 main，违反铁律 #10 commit-tag 一致性。Revert + 重做 (commit 006ac35 + 3150136) 恢复，但留下 audit trail noise。

**根因：** `git commit` 默认提交 staged 索引中**全部内容**，无视 -- pathspec 后的限制（pathspec 仅限制 git add 输入，commit 时索引已成既定）。Cross-agent 同工作树时 Generator 可能已用 `git add` 把自己的文件 stage 但未 commit，Planner 误以为自己只 add 自己的文件就只 commit 自己的文件。

**建议写入：** `harness-rules.md` 新铁律 #12 — "docs-only commit 前必须先 `git diff --cached --name-only` 检查 staged 索引，confirm 无 cross-agent WIP 已 staged 才 commit。如有 → 先 stash 或先让对方 commit 自己的内容。" + 配套 `framework/templates/pre-commit-hook.sh` 加守门（检测 commit-tag prefix 与 staged 文件路径一致性，如 `docs/*` tag 必为 `docs(`，`src/*` tag 必为 `feat|fix|refactor`）。

**状态：** 待确认

---

## [2026-05-02] Planner — 来源：BL-025 spec drafting 自审

**类型：** 模板修订（强约束化）

**内容：** UI Fidelity Guardrail (`framework/harness/ui-fidelity-guardrail.md` §2) 已规定所有 UI 类 feature spec 必须含 4 段（§2.1 原型路径 + §2.2 必用公共组件清单 + §2.3 不得简化清单 + §2.4 visual baseline 硬要求），但 Planner（我）起草 BL-025 spec 时**漏写 3/4**（仅写了 §2.1），导致用户主动 challenge "新页面会严格按框架/还原规范实现 + 抽公共组件 + 不手写吗?"。这是已有规范但 Planner 自检 checklist 缺失的典型 case。

**建议写入：** `framework/harness/planner.md` 加 spec 起草前 mandatory self-check checklist — UI 类 feature spec 必须 grep 自身确认含全 4 段（机器可自动 lint）；如缺则不能交付。同时 ui-fidelity-guardrail.md §2 顶部加 "**严格强制 — Planner spec 起草自检 checklist + Reviewer L1 受理前 checklist**"。

**状态：** 待确认

---

## [2026-05-02] Planner — 来源：prod 字符方框 bug → hotfix bb637a1

**类型：** 新坑 + 模板修订

**内容：** BIx F005-B Material Symbols self-host 子集脚本 `scripts/regenerate-material-symbols-subset.sh` 仅 3 个 grep pattern（`>name<` / 跨行 span / `icon: "name"`）覆盖代码中 icon name 引用，**漏 5 类动态范式**：
1. JSX prop `icon="name"`（5 处）
2. JSX 三元 `{cond ? "a" : "b"}`（6 处）
3. 对象值 key !== `icon`（如 `flat: "trending_flat"`，2 处）
4. 数组元素跨行（如 `ACTIVITY_ICONS = ["auto_fix_high", ...]`，4 处）
5. 函数 return / `??` fallback（如 `?? "history"`，2 处）

**总漏 19 icon**，prod 用户在 dashboard / discovery / crm / roi / database / knowledge-base 各页都看到字符方框（`TRENDING_FLAT` / `bookmark_added` / etc）。Hotfix 加 manifest 文件 + Pattern 4，BL-025 F009 加 Pattern 6/7 + CI 守门 test + PR template checklist。

**根因：** 静态 grep 永不可能 100% 兜住所有动态 case；spec §F005 acceptance "100+ 处 material-symbols-outlined 全渲染无字符方框" 是抽样验证，未跑全 callsite L2 烟测。

**建议写入：**
1. 新建 `framework/harness/material-symbols-pattern.md` 沉淀 5 类漏范式 + manifest 维护方式 + regenerate-when + CI 守门模式（独立框架文件，跨项目可复用）
2. `framework/harness/evaluator.md` §L2 烟测加 row："含字体子集（Material Symbols / etc）的 perf feature 必须 spot check ≥ 5 个 dynamic callsite，不能只看 grep 出的 baseline icons"
3. `framework/templates/pre-commit-hook.sh` 加守门：检测 `manifest 文件 vs grep + 实际 import` 一致性

**状态：** 待确认

---

## [2026-05-03] Generator — 来源：BL-025 F004 CI flaky `kol-profile.test.ts`

**类型：** 新坑

**内容：** Server actions 用 `void logAudit({...})` fire-and-forget 模式（不 await）让业务路径少一次 round-trip，但 integration test 在 action 返回后立即查 audit_log 会偶发 race（CI 高并发下成立，本地 dev 不易复现）。F003/F004 两轮跨同 commit 一次 PASS 一次 FAIL 验证为 flake，rerun 全绿。
case 在 `src/app/[locale]/(app)/kols/[id]/actions.ts:83`（`void logAudit`）+ `tests/integration/kol-profile.test.ts:127`（`expect(audits).toHaveLength(1)`）。

**建议写入：** 两选一：
- `framework/harness/evaluator.md` §回归测试稳定性 — "fire-and-forget audit pattern 测试约束：要么 action 内部 await logAudit，要么测试用 `vi.waitFor(() => expect(audits)...)` 配合 50-100ms retry 上限"
- `framework/harness/code-review.md`（如有）补一条 — server action 选 `void logAudit` vs `await logAudit` 的取舍：业务热路径优先 void，但凡 integration test 需要观察 audit_log 必须 await 或加 vi.waitFor

**状态：** 待确认

---

## [2026-05-03] Generator (johnsong) — 来源：BL-025-F001 staging deploy 失败

**类型：** 新坑（已修，沉淀防再发）

**内容：** `NODE_ENV=production` + `npm ci` 在本 VM 上不跑 package.json 的 `postinstall: prisma generate`，导致 `node_modules/.prisma/client/` 缺席 → `next build` 阶段 `tsc` 解析 `import { PrismaClient } from "@prisma/client"` 失败（`@prisma/client/index.d.ts` 只 `export * from .prisma/client/default`，无生成的 client 等于无 PrismaClient 类型）。
本批次 BL-025 schema 加了 `Asset` model + 3 enum，`src/lib/assets/*` 必引 PrismaClient → 第一次撞到此坑（之前批次 schema 改动小，旧 `.prisma/client/` 仍能 satisfy build typecheck）。
本批次 hotfix 已落：`infrastructure/deploy-staging.sh` 和 `scripts/deploy-prod.sh` 均补 `npx prisma generate` 显式步骤（npm ci 之后、prisma migrate deploy 之前）。

**建议写入：** `framework/harness/deploy-patterns.md` §3 完整链 checklist 补一项："npm ci 之后必须 explicit `npx prisma generate`，不能依赖 postinstall hook（NODE_ENV=production 行为不可信）"。

**状态：** 待确认

---
