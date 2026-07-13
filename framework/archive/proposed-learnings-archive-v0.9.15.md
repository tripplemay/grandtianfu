# Proposed Learnings Archive — v0.9.15

> 归档日期：2026-05-07
> 来源批次：BL-021-suspense-critical-paths fix-round 1 (commit 9fa2a49) + BL-049 测试基建系统性升级 audit (13 项发现合并 X1 / 7 features)
> 闭环情况：2 条 learnings 全部 Accept（用户 5/7 13:10 决议）+ 落 framework，CHANGELOG v0.9.15 已记录。

---

## [2026-05-07] Generator Kimi → Planner johnsong（BL-047 撤再翻盘三拍）— v0.9.15 #1：跨 pool 测试复现

**类型：** 铁律延伸（v0.9.9 / v0.9.14 铁律 1「实物核查」延伸到测试断言场景的跨环境复现）

**内容：**

BL-047 backlog 条目历时三拍真实复现：

1. **5/7 10:30 Planner johnsong 起 BL-047** — Reviewer 简述「`AiSuggestionsClient` localStorage stub 跨环境 fail，1043 → 1042/1043」；Planner 不能直接复现，按"无法证伪先建条目"原则起 backlog。
2. **5/7 10:30 Generator Kimi 开工前实地跑** — `npx vitest run AiSuggestionsClient.test.ts` on WSL2 forks pool（项目默认）→ **1043/1043 PASS**。误判 BL-047 premise 错误（"Generator 自己跑 PASS = 没有 bug"），撤条目入 closed-not-reproducible。
3. **5/7 11:51 Codex Reviewer reverifying** — Codex 在 BL-021 reverifying 阶段跑同一测试集，**真复现** `TypeError: Cannot read properties of undefined (reading 'getItem')`（AiSuggestionsClient.test.ts:42）。Codex 写 evaluator_feedback：BL-047 是真 cross-environment bug，需 fix-round 1 真修。
4. **5/7 13:00 Generator Kimi fix-round 1 真修（commit 9fa2a49）** — 实装 Map-backed 自实装 localStorage stub（不依赖 jsdom 默认 storage），跨环境 pool 启动顺序均能 init 完成。
5. **5/7 13:06 Codex reverifying PASS @ commit da94b73** — fix-round 1 PASS，BL-021 done。
6. **5/7 13:10 backlog 修正** — BL-047 状态从 closed-not-reproducible → closed-resolved（by BL-021 fix-round 1 @ 9fa2a49）。

**根因（pool 行为差异）：** vitest 4.x forks pool 与 threads pool 在 setupFiles 执行时序、jsdom 全局 init 时机、worker 隔离粒度上存在差异。Generator WSL2 默认 forks pool 时 setup 已完成 + jsdom storage 已 init；Reviewer Codex 环境（threads pool / 不同 vitest version / 不同 setup 顺序）下 setup 与 test 启动竞态，stub 未及时挂载。两侧"跑同样命令"实际跑的是不同的环境矩阵。

**v0.9.9 / v0.9.14 铁律 1 现行表述局限：** 仅覆盖 spec / audit / review 起草前的"代码/路由/migration"实物核查，**未覆盖测试断言层**。Backlog 条目报"测试 fail" 是断言而非记述，Generator 默认在自己 pool 跑一次就采信，跨 pool 行为差异成为盲区。

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 1 行（v0.9.15 #1）：

| 内容（v0.9.15 #1 新增） | 核查动作 |
|---|---|
| Backlog / spec 涉及"测试 fail / PASS / 覆盖"类断言 | 实地 `npx vitest run <target>` 验证 + 复现 reviewer 实际跑测试的环境（pool 类型 forks vs threads / vitest version / Node version / OS）；Generator forks pool PASS ≠ Codex threads pool PASS — 只跑自己环境 = 不能证伪 reviewer 报告的 fail |

**状态：** ✅ Accept + 落档（v0.9.15 — 用户 5/7 13:10 决议方案 A 立即切 BL-049 building）。`planner.md` 铁律 1 矩阵 +1 行（v0.9.15 #1）。CHANGELOG v0.9.15 已记录。

---

## [2026-05-07] Generator Kimi → Planner johnsong（commit 9fa2a49 Map-backed localStorage stub 范式）— v0.9.15 #2：Stub environment-agnostic

**类型：** 模式范式（test fixture / 全局 mock / setupFiles 内 stub 设计阶段强制项）

**内容：**

BL-021 F002 fix-round 1 实装 commit 9fa2a49（`src/components/ai/AiSuggestionsClient.tsx` + `tests/setup.ts`）的 Map-backed localStorage stub 是 environment-agnostic stub 的实装范式：

```typescript
// 范式：tests/setup.ts (illustrative — 实物详见 commit 9fa2a49)
// 不依赖 jsdom / happy-dom / Node global 默认 storage
// 用 Map 自实装即可跨任何 pool / 任何 worker 启动顺序工作
const _storage = new Map<string, string>();
const mapBackedLocalStorage: Storage = {
  get length() { return _storage.size; },
  key: (i: number) => Array.from(_storage.keys())[i] ?? null,
  getItem: (key: string) => _storage.get(key) ?? null,
  setItem: (key: string, value: string) => { _storage.set(key, value); },
  removeItem: (key: string) => { _storage.delete(key); },
  clear: () => { _storage.clear(); },
};

if (typeof globalThis.localStorage === "undefined") {
  Object.defineProperty(globalThis, "localStorage", {
    value: mapBackedLocalStorage,
    configurable: true,
    writable: false,
  });
}
```

**为什么这是范式：**

1. **不依赖 jsdom default Storage** — jsdom 在不同 pool / 不同启动时序下可能未及时挂载；Map-backed 是 plain JS object 立即可用
2. **不依赖 Node global** — Node 18+ 也无 `localStorage`，Map-backed 不依赖任何宿主环境
3. **行为同 Storage interface 100% 兼容** — `length / key / getItem / setItem / removeItem / clear` 全实装，调用方代码无感
4. **跨 pool 一致** — forks / threads / vmThreads 任意 pool 启动 Map-backed stub 都立即可用，消除 init 竞态

**v0.9.15 #2 适用范围：** 任何 setupFiles / global mock / test fixture 涉及宿主全局对象（`localStorage` / `sessionStorage` / `IndexedDB` / `fetch` / `crypto.subtle` 等）时，**默认走 Map / Set / 自实装路径**而不是依赖 jsdom default — 设计阶段就消除 race，比运行时再修便宜得多。

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 1 行（v0.9.15 #2）：

| 内容（v0.9.15 #2 新增） | 核查动作 |
|---|---|
| Test fixture / 全局 mock / setupFiles 内 stub 设计 | stub 必须 environment-agnostic — 用 Map / Set 等自实装数据结构而不是依赖 jsdom / happy-dom / Node global 默认行为；不同 vitest pool 的 worker 启动顺序可能让 jsdom 全局 init 时机异于预期 → 不依赖默认行为才能消除跨 pool 的初始化 race（commit 9fa2a49 Map-backed localStorage stub 即为范式） |

**状态：** ✅ Accept + 落档（v0.9.15 — 用户 5/7 13:10 决议）。`planner.md` 铁律 1 矩阵 +1 行（v0.9.15 #2）+ Map-backed stub 范式段。CHANGELOG v0.9.15 已记录。

---

## 综合：v0.9.15 与既有铁律的关系

| 既有规则 | v0.9.15 延伸点 |
|---|---|
| v0.9.9 铁律 1（spec 起草前实物核查） | 延伸到"测试断言"层 — Backlog 报"测试 fail" 也要实地复现 |
| v0.9.14 铁律 1 #1（"文件:行 + 现状描述"类引用核查） | 延伸到"跨环境 reviewer pool 复现" — 单一 pool PASS 不足以证伪 |
| v0.9.14 铁律 1 #2（"完整 pattern 模式"全仓 grep） | 延伸到"测试 stub 设计阶段消除 race" — pattern 不限源代码也含 test fixture |
| v0.9.11 §pre-impl-adjudication 短格式裁决 | BL-047 撤再翻盘三拍场景下也适用 — Generator 撤前应留 audit pause 给 Planner 裁决，不能单方面误判 premise 错 |
