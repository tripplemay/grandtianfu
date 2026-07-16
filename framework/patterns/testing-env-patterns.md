# 验收环境与测试稳定性 Patterns（框架沉淀）

> 原为 `harness/evaluator.md` §13-§16 / §18-§19，v1.0 重构移入 patterns/。Evaluator 跑 L1/L2 验收命中对应技术栈（Prisma / Node / jsdom / Playwright / 字体子集 / RLS）时按需查阅；`harness/evaluator.md` 保留流程性规则。

> **⚠️ 适用栈耦合提示（v1.0 — 单工具契合度评估）：** 本文件多数条目 stack-coupled（Prisma / Next.js / Node 版本 / jsdom / Playwright / Postgres-RLS / 字体子集），换技术栈时大半不可移植。当前阅天府项目栈为 Python（FastAPI + 纯 stdlib `floorplan_core`）+ Next.js/Yarn——纯 Python 引擎侧的几何/渲染对抗测试自成一类（见 §7），与前半部分的 Web/Prisma 条目不共享前提。**接入新栈时不要照搬本目录，应按新栈重播种**：保留"验收前先核环境前提（版本 / pool / 相机视野 / RLS 视角）"的元规律，具体条目按新栈实测重写。

---

## 1. L2 烟测含字体子集（Material Symbols / etc）必须 ≥ 5 dynamic callsite spot check

**背景：** BIx F005-B Material Symbols self-host 子集脚本仅 3 grep pattern，漏 5 类动态范式（JSX prop / 三元 / 对象值 key≠icon / 数组元素 / return + ?? fallback），prod 用户在 dashboard / discovery / crm / roi / database / knowledge-base 6 页都看到 19 个字符方框（`TRENDING_FLAT` / `bookmark_added` 等）。spec §F005 acceptance "100+ 处 material-symbols-outlined 全渲染无字符方框" 是抽样验证，未跑全 callsite。

**Reviewer L2 烟测处理规则：**

| 情境 | 处理 |
|---|---|
| Feature 含字体子集（Material Symbols / Font Awesome subset / 自定义 woff2 等） | L2 烟测必须 spot check ≥ 5 个 dynamic callsite（不只看 grep 出的 baseline icons）。dynamic = JSX prop / 三元 / 对象值 / 数组 / return + ?? fallback 等 grep pattern 难命中的写法 |
| Spot check 命中字符方框 / 缺字 | 标 FAIL，触发 fixing。同时建议 Generator 在 manifest 文件显式列漏 icon |
| 子集脚本无 manifest 文件兜底 | signoff 注 soft-watch："字体子集脚本仅靠 grep，建议下批次加 manifest 兜底" |

**配套：** 详见 `framework/patterns/material-symbols-pattern.md`（5 漏范式 + manifest 维护 + CI 守门 test 完整 pattern）。该文件已在 BL-025-F009 落地。

来源：BIx hotfix bb637a1（19 漏 icon prod 暴露）+ BL-025-F009 守门加固 + framework CHANGELOG v0.9.6 [#6]。

---

## 2. 回归测试稳定性 — fire-and-forget audit pattern 测试约束

**背景：** Server actions 用 `void logAudit({...})` fire-and-forget 模式（不 await）让业务路径少一次 round-trip，但 integration test 在 action 返回后立即查 audit_log 会偶发 race（CI 高并发下成立，本地 dev 不易复现）。BL-025 F003/F004 两轮跨同 commit 一次 PASS 一次 FAIL 验证为 flake，rerun 全绿。

**case 站点：** `src/app/[locale]/(app)/kols/[id]/actions.ts:83`（`void logAudit`）+ `tests/integration/kol-profile.test.ts:127`（`expect(audits).toHaveLength(1)`）。

**两选一规约：**

| 方案 | 适用场景 |
|---|---|
| (A) **Action 内部 `await logAudit`** | 业务路径不是热点（< 100 RPS） + 测试需观察 audit_log，简单可靠 |
| (B) **测试改用 `vi.waitFor(() => expect(audits)...)`** | 业务路径是热点，必须保留 fire-and-forget；waitFor 50-100ms retry 上限 |

**Generator 选择决策（开工时落 generator_handoff）：** 优先 (A)，仅在业务路径明确是热点（>100 RPS / <100ms p99）时降级 (B)。

**Reviewer 验收：** 看到 `void logAudit` + integration test 直接 `expect(audits)` 同时存在 → 直接标 PARTIAL（race condition 风险），要求 Generator 选 (A) 或 (B) 之一显式声明。

来源：BL-025 F004 CI flaky `kol-profile.test.ts` + framework CHANGELOG v0.9.6 [#7]。

---

## 3. L1 本机 tsc 跑前必先 `prisma generate`（v0.9.10 — BL-033 沉淀）

**背景：** Reviewer L1 跑 `npx tsc --noEmit` 时如本机 prisma client 在最近 schema migration 后未重生，会出现 80+ "Property 'asset' does not exist on PrismaClient" 误报。看似 in-flight 批次引入实际是本地环境状态。

**误报模式：**
```
src/app/[locale]/(app)/assets/actions.ts:142:23 - error TS2339:
Property 'asset' does not exist on type 'PrismaClient<...>'.
```

类似错误 80+ 行但真实代码完全正确。Reviewer 误判为"批次引入"将导致：

1. Reviewer 拒绝接收，写 evaluator_feedback "TypeScript 80 errors"
2. Generator 困惑 "本地 npm test 全绿 + CI 8/8 success 怎么 tsc 80 errors"
3. 浪费 1 轮排查时间发现是 prisma client 未生成

**修订规则（L1 标配前置命令，顺序固定）：**

```bash
# Reviewer L1 启动必跑
npx prisma generate    # 1. 重生 prisma client（30s）
npx tsc --noEmit       # 2. 然后跑 tsc（确保读最新 client types）
npm run lint           # 3. lint 跑（独立于 prisma client，但同一阶段一起跑）
```

**适用范围：**

- 任何含 schema.prisma 改动的批次（BL-025/BL-030/F004 等）
- Reviewer 切到新 worktree 或 git pull 含 migration 后首跑
- CI 不受影响（CI 在 npm ci 后自动跑 postinstall hook 触发 prisma generate）

**反面（BL-033 Reviewer 命中）：** Reviewer 接 BL-033 verifying 启动跑 tsc，因前批次 schema 改过 + 本机未跑 prisma generate → 80 errors。`prisma generate` 后立即清空。本可作为 L1 标配前置避免误判。

来源：BL-033 Reviewer signoff §Framework Learnings 新坑。

---

## 4. L1 本机 Node 版本必须与 `.nvmrc` 一致（v0.9.11 — BL-020-F002 沉淀）

**背景：** Node 25.x 引入 native `localStorage`，但要 `--localstorage-file <path>` flag 才启用持久化路径；无 flag 时 jsdom 29 的 `window.localStorage` shim 与 Node 25 native 占位 detect 互斥触发 fall-through，结果 `window.localStorage` 变 `undefined`。所有触及 `window.localStorage.setItem/getItem/clear` 的测试 100% fail，且本地复现明显但 CI（Node 20 LTS）不复现 — Reviewer 误判风险高。

**误报模式：**
```
TypeError: window.localStorage.setItem is not a function
  at AiSuggestionsClient.test.tsx:42
```

类似错误集中在 jsdom + localStorage 路径，本机 fail / CI Node 20 PASS。

**修订规则（L1 启动前置 + 误判判据）：**

```bash
# Reviewer / Generator L1 启动必查
node -v                          # 必须与项目根 .nvmrc 一致
cat .nvmrc                       # 当前锁 Node 20（lts/iron）
nvm use                          # 不一致时切换；无 nvm 装 Node 20 LTS
```

**适用范围：**

- 任何含 jsdom 环境单测 / `window.localStorage` / `window.sessionStorage` 测试的批次
- Node 22+ 引入 native `Web Storage` API 后均可能触发兼容性新坑
- 本机 fail 但 CI PASS 的 jsdom 类测试，**先核 Node 版本一致性**，不一致时本机 fail 不算反面证据

**反面（BL-020-F002 命中）：** Reviewer 本机 Node 25.7 + jsdom 29 跑 `AiSuggestionsClient.test.tsx` 2 集成 case fail，CI run 25330969685 Node 20 PASS。验证差异源于 Node 25 native localStorage incompat，不是产品 bug；锁 Soft-watch S4 + 本规则。

**来源：** BL-020-F002 Reviewer L1 本机 unit fail / CI PASS 对比。

---

## 5. E2E suite 稳定性诊断（v0.9.20 — BL-060 沉淀）

**背景：** BL-060 fix-round 1 单点放宽 timeout/正则只缓解症状，整组 E2E 仍 FAIL；fix-round 2 抽 `tests/e2e/<role>.setup.ts` + 各 spec opt-in `test.use({ storageState })`，N 次 login 收敛 1 次后 suite PASS。

**诊断信号：** 单例 PASS / 整组 FAIL = **suite-level isolation 问题**（不是 case 内容/正则问题）。

**候选根因：**
- 每 case `beforeEach` 重 login 累积抖动
- staging 8GB RAM 资源压力

**根治方案：** 抽 `tests/e2e/<role>.setup.ts` + 各 spec opt-in `test.use({ storageState })`，N 次 login 收敛 1 次。

**反模式：** 单点放宽 timeout / 正则只缓解症状，不解决 suite-level isolation。

**来源：** BL-060 fix-round 1（cc82a54 正则放宽失败）→ fix-round 2（f75cafd storageState PASS）。

---

## 6. SQL 跨 tenant 全量查询 RLS 注意（v0.9.20 — BL-061 沉淀）

**背景：** BL-061 F003 验收时 Reviewer 用 `kolmatrix_app` role + Prisma RLS 跨 tenant 查 audit_log 返回 0 行，误判为数据缺失；实际是 RLS 视角限制。

**处理规则：** 跨 tenant 全量验收 SQL 必须 `sudo -u postgres psql kolmatrix(_staging)` superuser bypass RLS。普通 `kolmatrix_app` role + Prisma RLS 跨 tenant 看 0 行（不是数据缺失，是 RLS 视角限制）。Reviewer only-read 验收尤其要走 superuser path。

**来源：** BL-061 F003 Generator 实战发现 + Codex Reviewer signoff 确认。

---

## 7. 几何/渲染对抗验收 fixture 退化校验（v1.0 — decor-b2 沉淀）

**背景：** 几何/渲染类对抗验收若沿用现网单测 fixture 的坐标，可能命中**退化位置**。decor-b2 head-line 单测 `test_geometry_lock_decor_wall_art_paint_in_allowed_no_structure_fail` 用 `wall_art@(dx=300,dy=300)`，房内坐标映射到世界 `(3000,3000)mm` 恰是合成相机眼位 → 投影退化 → allowed 覆盖整画幅 → structure 边界断言 trivially 成立（测试仍正确 PASS，但根本没压到边界）。

**处理规则：** Evaluator 做几何/渲染对抗验收前，先核 fixture 是否在相机**正视野**内（`box_usability` usable + `in_frame_frac ≈ 1`）。退化位置的"绿"不等于边界被真正验证。改用正视野墙位重验才量化出真实覆盖余量（decor-b2：0 未覆盖 + 21px 顶余量）与 load-bearing 反证（无 allowed 时 7 坏块 FAIL）。

**来源：** decor-b2 F007 第7步几何对抗验收头号项（Evaluator 实战发现 fixture 退化陷阱）。

---

## 8. fixture 与被测代码共享同一错误假设 → 两错相消 → 该 bug 永远测不出（v1.0.5 — calib-z-b1 沉淀）

**背景（本条是 §7 的更深一层：§7 是 fixture 位置退化，本条是 fixture 前提错误）：** 阅天府 `calibrate()` 在**左手系** `(东,南,上)` 里用 `+cross(x,y)` 强制 `det=+1`，导致世界 z 轴系统性取反（相机被解到地板下方、挂画画在地板上）。该 bug 带着 **200+ 全绿测试上线数月**。根因不在测试少，而在测试 fixture `_synth_camera` **自己也是 `det=+1` 的镜像相机**（其 "right" 实际指向左）—— 它与被测代码犯**同一个**手性错误，往返投影因此完美"自洽"。**两错相消的测试，绿得毫无意义。**

**判据：** 当被测对象是**全局假设**（坐标系约定 / 手性 / 字节序 / 时区 / 编码 / 单位）时，fixture **不得复用被测代码的构造式**，必须由**独立于被测实现的第一性原理**构造。本案正解：用物理 look-at 造一台**已知真值**的相机（`C=(5000,2000,+1500)`、`det(R_true)=-1`），渲染其墙线/锚点喂给真实 `calibrate()` → 立刻暴露「col0/col1 精确恢复 1.4e-13，唯 col2 恰为真值取反 9.55e-14」。

**自查条：** 「这条测试如果被测代码和 fixture 犯同一个错，它还会红吗？」答不上来 = 该测试不承重。

**来源：** calib-z-b1 F001（Generator 实现时发现 fixture 同源缺陷；4 位隔离 Evaluator 复验确认）。

---

## 9. 验证手性/约定类 bug 时，反证脚本本身极易犯同一个错（v1.0.5 — calib-z-b1 沉淀）

**背景：** §8 的正解（合成真值控制）**自己也会踩同一个坑**。calib-z-b1 第三位隔离 Evaluator 的**第一版**合成真值构造，在**左手系里做叉乘** → 造出的"真值相机"上下颠倒 → 据此一度得出「**修复后是错的**」的**相反结论**。

**订正法：** 在**已知右手系**（如 ENU）里做 look-at 构造，再**换基**进被测的约定（ESU）。即：**先在没有争议的坐标系里把真值造对，再搬进被测约定** —— 而不是直接在被测约定里用叉乘（那正是被测 bug 的所在）。

**判据：** 验证 X 类 bug 时，反证工具**不得依赖 X**。手性 bug 的反证不得用叉乘定手性；编码 bug 的反证不得用同一套编解码；时区 bug 的反证不得用同一个 tz 库。

**旁证（同批）：** 该 Evaluator 的随机扫描起初得「13/200 不还原真值」，查明是**它自己的生成器**把锚点造到了相机背后（病态构图）；剔除后良态 214/214 还原真值。**反证工具的 bug 会伪装成被测对象的 bug。**

**来源：** calib-z-b1 复验（Evaluator 自陈并订正，其结论因此从 PASS 改判 PARTIAL 又最终 PASS）。

---

## 10. 「跑完没脏」不足以证明修复有效 —— 污染/泄漏类结论必须先建阳性对照（v1.0.6 — render-fix-b1 沉淀）

**背景：** 验证「沙箱写穿已修好」「泄漏已止住」这类**否定性结论**时，「跑完一遍，目标目录没脏」是**证据不足**的 —— 「没检测到污染」与「检测方法本身失明」在这条证据下**不可区分**。render-fix-b1 首轮的「连跑 5 次没看见」正是此式，其结论恰好对、理由不成立。

**处理规则：** 先用 `git worktree` 检出**有病的 commit**，跑**同一条命令**确认污染**能**复现 —— 检测方法由此被证明有视力，HEAD 上的「未复现」才具备证据力，且归因被锁定到那一行修复。**阳性对照先行，是否定性结论的入场券。**

**同族判据（§8/§9 的姊妹条）：** §8 问「fixture 和被测代码一起错，它还会红吗」；本条问「如果 bug 还在，我这套检测**看得见**吗」。

**来源：** render-fix-b1 三轮验收（Evaluator 用 worktree 阳性对照把「工作区早已脏」的猜测证伪，实为 stash pop 夹带 —— 铁证是 blob 逐字节同一）。

---

## 11. 判断「等待是真排空还是掩盖时序」，看产品代码的偏序而非等待时长（v1.0.6 — render-fix-b1 沉淀）

**背景：** 测试里 `_wait(t=10)` 等后台 job 落盘 —— 这是**真排空**还是**把竞态藏进一个够长的 sleep**？「等 10s 大概够了」不是判据（它只是让 flake 变稀，不是消除）。

**判据：** 读出产品代码的**偏序**。本案 `jobs._run` 严格「先 `fn()` 跑完、后置 `status=done`」，而 `fn()` 最后一句正是落盘 ⇒ **等到 `done` 必然等到写完** —— 这是结构保证，与时长无关。可再**人为拖慢关键段撑开窗口**实证。

**诚实边界（本案实测）：** `_wait` 的真实语义是「把静默污染转成响亮红灯 + 把窗口收敛到 10s」，**不是语法上禁止竞态** —— 超时会 raise 而线程仍在跑。验收时须把这两档说清楚，别记成「已根治」（与 §13 / `cross-layer-consistency.md` §「集合式修法」同族）。

**来源：** render-fix-b1 复验（Evaluator 从 `jobs._run` 偏序推出 `_wait` 承重，而非采信等待时长）。

---

## 12. 后台线程在 pytest session 结束后抛的 warning 不进 `warnings summary`（v1.0.6 — render-fix-b1 沉淀）

**背景：** 用「pytest 的 `warnings summary` 是否为空」验「无泄漏线程/无异常」**会漏报**。render-fix-b1 实测 2 条 `RankWarning` 是**泄漏线程在 teardown 之后**跑到 `polyfit` 才冒出的**裸 stderr** —— 早已超出警告插件的捕获窗口，插件根本看不见。

**处理规则：** 此类项须**合并 stdout+stderr 后全量 grep**，不得只看 `warnings summary`。

**元规律：** 这是 §10 的一个实例 —— 「summary 是空的」既可能是「真没有」，也可能是「捕获窗口关了」。**任何「空即通过」的判据，先问它的视野边界在哪。**

**来源：** render-fix-b1 三轮验收（Evaluator 实测泄漏线程 warning 逃出捕获窗口）。

---

## 13. monkeypatch 沙箱 + fire-and-forget 后台 job = 沙箱写穿（v1.0.6 — render-fix-b1 沉淀）

**背景（本条是 §2 在 Python/pytest 栈的同族，但后果更重）：** 测试函数一返回，`monkeypatch` **立即拆除** —— `DATA_DIR` / provider 工厂 / stub 全部复原成**真实值**，而后台线程**仍在跑**。它随后落盘时用的是**真实** `DATA_DIR` → **写进 git-tracked 目录**；在有 key 的机器上甚至可能发起**真实计费调用**。

**处理规则：** 凡「同步返回 `job_id` + 后台落盘」的端点，测试**必须排空后台 job**。更稳的做法是 **fixture 层 `yield` + teardown 排空在途 job**，而非靠每条测试自觉写 `_wait`。

**诚实边界（本案实测）：** 阅天府今天 4 个 async 测试文件的 `job_id` 读取点 100% 配对 —— 但那是**人工约定（知情自律）**，不是机制。按 `harness-rules.md` §机制化守门 判据，这仍属「写在文件里的规则」。已立项 `BL-input-gate-error-class` 一并处理。

**关联红线（阅天府）：** `data/projects/` 是 git-tracked 种子快照，**测试绝不可写入**；验证「没写穿」须按 §10 先建阳性对照。

**来源：** render-fix-b1（Evaluator 实测 monkeypatch 沙箱被后台 job 写穿；calib-z-b1 R1 复现同族现象）。

---

## 版本历史

| 日期 | 修订 | 来源 |
|---|---|---|
| 2026-07-09 | v1.0 重构：自 `harness/evaluator.md` §13-§16 / §18-§19 原文迁出成独立 pattern 文件 | 框架 v1.0 目录分层 |
| 2026-07-15 | v1.0.5：新增 §8（fixture 与被测代码共享错误假设→两错相消）、§9（手性类 bug 的反证脚本易犯同一错） | 阅天府 calib-z-b1 |
| 2026-07-15 | v1.0.6：新增 §10（否定性结论须先建阳性对照）、§11（等待是否真排空看偏序非时长）、§12（后台线程 warning 逃出捕获窗口）、§13（monkeypatch 沙箱被后台 job 写穿） | 阅天府 render-fix-b1 |
