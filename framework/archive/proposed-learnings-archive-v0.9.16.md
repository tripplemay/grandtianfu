# Proposed Learnings Archive — v0.9.16

> 归档日期：2026-05-08
> 来源批次：BL-052-dashboard-trend-edge-polish verifying P5 裁决（pre-commit-hook flaky test 范围正交）
> 闭环情况：1 条 learning Accept（用户 5/8 决议）+ 落 framework，CHANGELOG v0.9.16 已记录。

---

## [2026-05-08] Planner johnsong（BL-052 verifying P5 裁决）— v0.9.16：acceptance 边界 vs 全套测试基线

**类型：** 新规律（Planner 裁决职责 P5 二级模式扩展）

**内容：**

Reviewer 报告"全套 `npm run test:integration` 红"时，Planner 裁决前必须先做"**失败点 vs 本批次范围**"的正交性判断：

- **acceptance 边界**：spec § acceptance 逐项列表，**不含**"全套测试普遍绿"这种隐式门槛
- **正交性判断**：`git log --all` 追溯失败测试文件的引入批次 → 与本批次 commit 集做交集 → 交集为空 = 范围正交
- **裁决落实**：范围正交的失败（外部网络依赖 / 预存在 framework reliability 缺陷 / 既有 flaky）→ 不计入本批次评分 + 独立批次治理（建立 BL-XXX backlog）+ 同 commit 追加 §Planner 裁决段到 verifying 报告 + 更新 project-status.md

**实物时间线（BL-052 5/7 17:30 → 5/8 01:07）：**

1. **5/7 17:30** Generator johnsong 启动 BL-052 building；20:10 完成 11/11 features，staging deployed @ commit `3ba3fe2`
2. **5/7 23:40** Reviewer partial 报告：L1 lint/tsc/unit PASS + staging smoke PASS，但 default `npm run test:integration` 中 `tests/integration/pre-commit-hook.test.ts` 全套并发抖动 fail（隔离跑 PASS）→ grade C / Readiness Not ready
3. **5/8 00:10** Planner johnsong 裁决：
   - `git log --all -- tests/integration/pre-commit-hook.test.ts` → 来自 BL-027-F004（commit `2c8af8a`）
   - `git log --all -- scripts/regenerate-material-symbols-subset.sh` → 来自 BL-025-F009 / BIx-mvp-polish-pass
   - `git log --oneline c4afd5a..HEAD -- tests/integration/pre-commit-hook.test.ts scripts/regenerate-material-symbols-subset.sh` → 输出空 → 范围正交确认
   - acceptance 边界检查：BL-052 spec §3.10 + §4.5 各自 acceptance 列表，不含"npm run test:integration 必须全绿"约束
   - 落实：commit `4ede09e`（同 commit 追加 §Planner 裁决段到 `docs/test-reports/BL-052-verifying-2026-05-07.md` + 新建 BL-054-flaky-network-test-isolate backlog medium + 更新 `.auto-memory/project-status.md`）
4. **5/8 01:07** Reviewer 复验仅 BL-052 引入代码（KPI snapshot IT × 3 + Part B 单测 5 文件 + acceptance 表逐项 + staging smoke 6 路）→ 全 PASS → grade B+ / Readiness Ready @ commit `722fc66`

**BL-052 13 commits（`c4afd5a..3ba3fe2`）覆盖：**

- F001 c4afd5a kpi_daily_snapshot table + RLS + ROLLBACK
- F002 47e4954 kpi-trends.ts + kpi-snapshot.ts + 15 单测
- F003 dd5700c kpi-snapshot:daily cron + ops runbook + 3 集成测试
- F004+F005 baa28b0 KpiRow 删 4 mock + trends prop / StatCard.tooltip / DashboardPage Promise.all loadKpiTrends + 9 component test
- F006 8ba38ce 公共 EmptyState 组件 + 3 单测
- F007 0d906d3+82977c8 useNetworkStatus + NetworkStatusBanner + (app)/layout 注入 + 6 单测 + react-hooks/set-state-in-effect 修复
- F008+F009 f69b941 5 缺失 root loading.tsx + /assets error.tsx
- F010 ce767ef /knowledge-base ProductsClient empty CTA + 5 locale i18n
- F011 2262d1c+3ba3fe2 /database empty 改用 EmptyState 然后 revert（CI E2E visual regression baseline 不兼容，BL-053 一并处理）

**零交集证据：** 上述 13 commits 全部 diff 不含 `tests/integration/pre-commit-hook.test.ts` 或 `scripts/regenerate-material-symbols-subset.sh` 任一行修改。

**v0.9.9 / v0.9.14 / v0.9.15 铁律 1 现行表述局限：** 铁律 1 矩阵只覆盖 spec / audit / readiness-report 起草前的实物核查，**未明文 verifying 阶段 Reviewer 报全套测试红时的裁决路径**。Planner 默认接受"全套测试不绿就是 Not ready"会让 acceptance 边界向"全套测试普遍绿"漂移，与 spec 明文 acceptance 列表脱节。

**反面（不适用此规律时）：**

- 拖延 done → 上线时间线收紧（BL-052 案例：buffer 5+ 天可能瞬变 < 1 天）
- Generator 被迫给"不属于本批次的 flaky"写 fix → 跨批次污染 commit history（违反铁律 #10 commit-tag 一致性）
- 隐式假门槛"测试不全绿就是不能 done"与 spec 明文 acceptance 不一致 → 评分系统失活
- Reviewer 反复 fail 评分让"修不好就是不能 done"成为不可见门槛，掩盖真实 framework reliability 缺陷

**适用场景边界：**

| 情形 | 是否适用 P5.2 |
|---|---|
| 失败测试文件来自历史批次 + 本批次零修改 | ✅ 适用（范围正交，建独立 backlog） |
| 失败测试文件本批次新增 / 修改 | ❌ 不适用（属于本批次范围，必须 fix） |
| 失败由本批次代码改动引发的 regression | ❌ 不适用（即使测试文件来自历史，行为变更归本批次） |
| 失败属于 setupFiles / 全局 mock / fixture 通用基础设施 + 影响所有批次 | ✅ 适用（应建独立 framework 治理批次，参 v0.9.15 #2） |

**建议写入：** `framework/harness/planner.md` §"Planner 裁决职责"末尾追加 §"规则 P5.2：acceptance 边界 vs 全套测试基线（v0.9.16 新增）"段（含 git log 正交性判断流程命令模板 + 4 项裁决落实模板 + 反面案例 + 适用场景边界 4 行表 + BL-052 实物范例）。

**状态：** ✅ Accept + 落档（v0.9.16 — 用户 5/8 决议）。`planner.md` §P5.2 段。CHANGELOG v0.9.16 已记录。

---

## 综合：v0.9.16 与既有规则的关系

| 既有规则 | v0.9.16 延伸点 |
|---|---|
| P1-P5（Pre-Implementation Audit） | P5 增 P5.2 二级模式 — 从 building 阶段歧义裁决扩到 verifying 阶段范围正交裁决 |
| v0.9.9 铁律 1（spec 起草前实物核查） | 延伸到 verifying 阶段 — Reviewer 报全套测试红时也要 git log 实物追溯 |
| v0.9.14 铁律 1 #1（"文件:行 + 现状描述"类引用核查） | 延伸到"失败测试文件 vs 本批次 commit 集"的交集判断 |
| v0.9.15 #2（stub environment-agnostic） | 范围正交识别后建独立批次治理（如 BL-054）— framework reliability 缺陷不污染业务批次评分 |
| 铁律 #10（commit-tag 一致性） | 防御层补全 — 范围正交的 fix 不应混入本批次 commit，否则违反 commit-tag 与 features.json 对应原则 |
