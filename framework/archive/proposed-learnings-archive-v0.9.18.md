# Proposed Learnings Archive — v0.9.18

> 归档日期：2026-05-08
> 来源批次：BL-012-apify-kol-integration F001 fix-round 1（admin auth gate role mismatch）
> 闭环情况：1 条 learning Accept（用户 5/8 决议 1A）+ 落 framework，CHANGELOG v0.9.18 已记录。

---

## [2026-05-08] Planner johnsong（BL-012 F001 fix-round 1）— v0.9.18：auth role enum 实物核查

**类型：** 铁律 1 v0.9.14 / v0.9.17 同源延伸（spec 起草前实物核查 → 扩展到 auth role enum / DB schema 字段值）

**内容：**

Spec 起草 / 实装 auth role check / 权限 enum / DB schema 字段值时，**必须先 `grep -rn` 真实 enum 值**，不可依赖字面字符串假设（如 `'admin'` / `'user'`）。即使业界通用 `'admin'` 字面看起来"明显"，实际项目可能用 `platform_admin` / `tenant_admin` 等更具体的 enum 值。

**实物范例（BL-012 F001 5/8 15:32 → 15:39）：**

1. **5/8 ~13:30** Generator F001 实装 `/[locale]/admin/apify-preview` 路由：按 spec 字面写 `if (session?.user?.role !== 'admin') redirect('/dashboard')`
2. **5/8 ~14:00** 单测 mock `session.user.role = 'admin'` → 4 case 全过（admin 渲染 / marketer redirect / unauth redirect / null user redirect）→ Reviewer signoff 接受单测
3. **5/8 ~15:00** staging deploy + L2 实地：admin@kolmatrix.local 登录访问 `/zh/admin/apify-preview`
4. **5/8 15:32** Reviewer Codex partial fail：admin 真账户被踢回 dashboard。Reviewer 实地查 architecture.md §3.3 + seed.ts → 真实 enum 是 `platform_admin / tenant_admin / marketer / client` 4 值；seed 创建 admin@... 用 `tenant_admin` role
5. **5/8 ~15:39** Generator fix-round 1 (`commit 4b4ae96`)：
   ```ts
   // 改前 (字面假设)
   if (session?.user?.role !== 'admin') redirect('/dashboard');
   // 改后 (枚举核查 + 锁回归)
   if (!['platform_admin', 'tenant_admin'].includes(session?.user?.role ?? '')) {
     redirect('/dashboard');
   }
   ```
   测试 case 7 个含锁 "admin literal MUST reject" 防回归
6. **5/8 ~15:51** Reviewer reverifying signoff PASS

**根因：**

- v0.9.14 铁律 1 矩阵已覆盖"spec 涉及具体代码细节时必须核查源码"（含 schema 字段 / 函数签名 / regex 等），但 **auth role / 权限 enum / DB schema 字段值** 没明示 — Spec 起草时若按业界通用习惯字面假设 `'admin'`，会撞真实项目 enum 不匹配
- KOLMatrix architecture.md §3.3 明示 4 值 enum 但 spec 起草未引用 / 未 grep 验证 → Generator 字面实装通过单测但 staging 实地撞真账户

**修订规则：**

Spec 起草 / 实装 / Reviewer 验收 auth role check / 权限 enum / DB schema 字段值时，**必须先 `grep -rn` 真实 enum 值**：

| 内容类型 | 核查动作 |
|---|---|
| auth role check 字面字符串 | `grep -rn "role" src/auth.ts src/lib/auth/ prisma/schema.prisma prisma/seed.ts` 找真实 enum 值 |
| 用户/权限 enum 值 | `grep -rn "enum.*Role\|UserRole\|role:" prisma/schema.prisma` 找 schema 定义 |
| DB schema 字段值 / fixture / seed 数据 | `grep -rn "<字段名>" prisma/seed.ts tests/fixtures/` 找真实 fixture |

**单测必须含负面 case 锁回归：** 字面字符串 `'admin'` / `'user'` MUST reject（确保未来 enum 调整 / Generator 误回退到字面假设时单测立即失败）。

**反面（不修订时）：**

- spec 字面假设 → Generator 字面实装 → 单测 mock 用同样字面通过 → Reviewer signoff PASS → staging 真账户撞 enum 不匹配 → fix-round
- BL-012 5/8 案例：F001 字面 `'admin'` 通过单测 + signoff，但 staging admin 真账户访问 redirect → fix-round 1 + 锁回归测试

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 1 行（v0.9.18）：

| 内容（v0.9.18 新增） | 核查动作 |
|---|---|
| auth role enum / 用户角色 / 权限 enum / DB schema 字段值 | 不可依赖字面 `'admin'` / `'user'` 等假设 — 必须 grep auth.ts / src/lib/auth/ / schema.prisma / seed.ts 验证真实 enum 值；spec lock 前必查 |

**状态：** ✅ Accept + 落档（v0.9.18 — 用户 5/8 决议 1A）。`planner.md` 铁律 1 矩阵 +1 行（v0.9.18）。CHANGELOG v0.9.18 已记录。

---

## 综合：v0.9.18 与既有铁律的关系

| 既有规则 | v0.9.18 延伸点 |
|---|---|
| v0.9.9 铁律 1（spec 起草前实物核查） | 延伸到 auth role / 权限 enum / DB schema 字段值层 — 不能按业界通用字面假设 |
| v0.9.14 铁律 1 #1（"文件:行 + 现状描述"类引用核查） | 延伸到 enum 实物核查 — schema.prisma 是字段权威源，必须 grep |
| v0.9.17（记忆条目陈旧风险） | 同源 — 默认信任记忆/字面 = 信任过期/不准确假设；都需要 grep 实物验证 |

**Planner 起草 spec 阶段的"实物核查"完整 layer（v0.9.18 增）：**

```
Layer 1 (v0.9.9):  代码 / migration / route 路径    → grep / Read
Layer 2 (v0.9.14): "文件:行" / 完整 pattern        → grep -rn 全仓
Layer 3 (v0.9.15): 测试 fail / stub 设计           → 多 pool / Map-backed
Layer 4 (v0.9.17): .auto-memory / 跨项目状态      → gh api / git log / curl health
Layer 5 (v0.9.18): auth role / 权限 enum / DB enum → grep schema.prisma / auth.ts / seed.ts
```
