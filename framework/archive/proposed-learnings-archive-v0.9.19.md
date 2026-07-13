# Proposed Learnings Archive — v0.9.19

> 归档日期：2026-05-08
> 来源批次：BL-012-apify-kol-integration F002 fix-round 2（prod zod schema mismatch — 41 fields shape error）
> 闭环情况：1 条 learning Accept（用户 5/8 决议 2A）+ 落 framework，CHANGELOG v0.9.19 已记录。

---

## [2026-05-08] Planner johnsong（BL-012 F002 fix-round 2）— v0.9.19：external API response zod schema 实物 sample 验证

**类型：** 铁律 1 v0.9.14 / v0.9.15 / v0.9.17 / v0.9.18 同源延伸（spec 起草前实物核查 → 扩展到外部 API response shape）

**内容：**

Planner 起草 spec / Generator 实装 **zod schema for external API response** 时，必须 ≥5-10 真数据 row sample 验证 schema 兼容，不能仅依赖文档/sample/字面假设。尤其当外部 API 可能返回 **union shape**（`string | object`）/ **record vs array** 等灵活类型时，audit 阶段 sample 不足导致严格 schema 在 prod 真数据触发 parse error。

**实物时间线（BL-012 F002 5/8 02:00 → 19:13）：**

1. **5/8 02:00** Planner johnsong audit fork @ `gh api repos/guang-tech/apify` — 抽样审 README + .env.example + docs/specs/2026-05-07-tikhub-migration-design.md + ai-usage.md 前 120 行（response shape 注释 "IG 的多外链原结构"），但**未 SSH 拉真数据 row sample 验证**
2. **5/8 02:30** spec v2 §3.1 数据契约段写：
   ```ts
   "externalUrls": [...],     // IG 的多外链原结构（注释含糊 — 实际是 [{url, title}] not [string]）
   "aggregatorLinks": null,   // L2 Linktree (实际 null OR array OR record，未明示）
   ```
3. **5/8 ~14:00** Generator F002 实装 zod schema 按字面假设：
   ```ts
   externalUrls: z.array(z.string()),                       // ❌ 严格 string array
   aggregatorLinks: z.record(z.string(), z.unknown()),     // ❌ 严格 record
   ```
4. **5/8 ~16:00** 单测 mock 用 string array 通过（未触发 union shape）→ Reviewer signoff PASS @ `f2f5dbb` (fix-round 1 之后)
5. **5/8 ~17:00** prod redeploy 后用户实地审视 — 50 KOL 中 41 row externalUrls 是 `[{url, title}]` + 1 row aggregatorLinks 是 array → zod safeParse **41 fields error** → preview 页加载失败 banner
6. **5/8 19:00** Planner 起 fix-round 2 evaluator_feedback：
   ```ts
   externalUrls: z.array(z.union([
     z.string(),
     z.object({ url: z.string(), title: z.string().optional() }).passthrough(),
   ])).nullable().optional(),
   aggregatorLinks: z.union([
     z.record(z.string(), z.unknown()),
     z.array(z.unknown()),
     z.null(),
   ]).optional(),
   ```
7. **5/8 19:06** Generator fix-round 2 (`commit 894a303`)：union schema + passthrough + +2 单测（externalUrls 混合 `[{url,title}, plain-string]` / aggregatorLinks 同 page 一行 array + 一行 record）
8. **5/8 19:13** staging deploy + reverify
9. **5/8 19:15** prod redeploy + 用户实地确认 OK
10. **5/8 19:01** Reviewer Codex 综合 signoff PASS @ `4712066`（covers fix-round 1 + F006a + fix-round 2）

**根因：**

- v0.9.14 铁律 1 已覆盖"spec / audit 起草前 grep 实物状态"，但**对外部 API response shape 仍存在盲区** — 文档注释含糊（如"多外链原结构"）是 union 信号，audit 阶段未拉真数据 row sample 验证 → spec / zod schema 严格化 → prod 真数据触发 parse error
- v0.9.17 已覆盖"记忆条目陈旧风险"（外部协作方 / 第三方仓库的"X 已交付"类断言核查），但**对外部 API response shape 的 union 多 shape 验证**未明示 — Sample 1-2 row 不足以发现 union shape，必须 ≥5-10 row + 多种边界（不同 platform / nano vs mega / 含 / 不含 emails 等）
- 单测 mock 用文档假设 shape 全过 → Reviewer signoff PASS → 直到 prod 真数据触发 schema mismatch

**修订规则：**

Planner 起草 spec / Generator 实装 zod schema for external API response 前，**必须 ≥5-10 真数据 row sample 验证**：

| 场景 | 核查动作 |
|---|---|
| 外部 API（fork / 第三方 / 跨服务）GET response shape | SSH service deployed → curl 真 endpoint → 拉 ≥5-10 row sample → JSON parse 验证 zod schema 兼容；尤其当文档注释含"原结构 / 多 / 灵活"等 union 信号 |
| Union shape 候选（string \| object / record vs array / null vs undefined） | union 类型 zod schema (`z.union([...])`) 优于严格单 shape；passthrough 容忍未知字段 |
| Schema 边界 case 覆盖 | sample 必须含多 platform / 多 tier / 多边界（含 emails / 不含 / null fields）；单测必须含 union 类型每种 shape |

**反面（不修订时）：**

- spec / zod schema 严格化 → 单测 mock 用文档 sample shape 全过 → 真数据触发 schema mismatch → prod parse error → 用户体验破 / 紧急 fix-round
- BL-012 5/8 案例：F002 single-shape zod schema 通过单测 + signoff，但 prod 真数据 41 fields error → 必须 fix-round 2 + zod union 修订

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 1 行（v0.9.19）：

| 内容（v0.9.19 新增） | 核查动作 |
|---|---|
| 外部 API response zod schema（fork / 第三方 / 跨服务 GET 响应） | SSH 拉 ≥5-10 真数据 row sample → JSON parse 验证 zod schema 兼容；文档注释含"多 / 原结构 / 灵活"等 union 信号必须 union 类型；passthrough 容忍未知字段 |

**状态：** ✅ Accept + 落档（v0.9.19 — 用户 5/8 决议 2A）。`planner.md` 铁律 1 矩阵 +1 行（v0.9.19）。CHANGELOG v0.9.19 已记录。

---

## 综合：v0.9.19 与既有铁律的关系

| 既有规则 | v0.9.19 延伸点 |
|---|---|
| v0.9.9 铁律 1（spec 起草前实物核查） | 延伸到外部 API response shape 层 — 不能按文档假设字面 |
| v0.9.14 铁律 1 #1（"文件:行 + 现状描述"类引用核查） | 延伸到外部 API row sample shape 验证 — sample 1-2 row 不足以发现 union |
| v0.9.17（记忆条目陈旧风险） | 同源 — 都是外部协作方/第三方实物核查；v0.9.17 是元数据 / v0.9.19 是 response shape |
| v0.9.18（auth role enum 实物核查） | 同 BL-012 教训源 — 都是字面字符串假设 vs 实物枚举/shape 不匹配 |

**Planner 起草 spec 阶段的"实物核查"完整 layer（v0.9.19 增）：**

```
Layer 1 (v0.9.9):  代码 / migration / route 路径    → grep / Read
Layer 2 (v0.9.14): "文件:行" / 完整 pattern        → grep -rn 全仓
Layer 3 (v0.9.15): 测试 fail / stub 设计           → 多 pool / Map-backed
Layer 4 (v0.9.17): .auto-memory / 跨项目状态      → gh api / git log / curl health
Layer 5 (v0.9.18): auth role / 权限 enum / DB enum → grep schema.prisma / auth.ts / seed.ts
Layer 6 (v0.9.19): external API response shape    → SSH curl ≥5-10 row sample → JSON parse 验证 zod
```
