# Proposed Learnings Archive — v0.9.14

> 归档日期：2026-05-06
> 来源批次：BL-040 + BL-041 audit 过期发现 + BL-043 staging .env.staging 修复
> 闭环情况：2 条 learnings 全部 Accept（用户 2026-05-06 决议）+ 落 framework，CHANGELOG v0.9.14 已记录。

---

## [2026-05-06] Planner johnsong（BL-041 audit 过期 + BL-040 spec scope 漏 grep 双案例）— v0.9.14 #1：v0.9.9 铁律 1 反向延伸到 audit / spec / review / readiness-report 起草

**类型：** 铁律延伸（v0.9.9 铁律 1「spec 涉及具体代码细节时必须核查源码」反向应用 + 范围扩展）

**内容：**

实战双案例：

1. **BL-041 audit 过期**：`prod-mvp-readiness-audit-2026-05-04.md §5 D2` 写「Dashboard 缺 PRD §4.1 三元素」，但 grep `dashboard/page.tsx` 即可发现 line 79+88+89 已 import + 渲染全 3 组件 — `MVP-internal-demo-prep-F001` (commit 4fd778b @ 2026-05-01) 早已实装齐全。Audit 起草人 Planner Kimi 漏 grep 实物状态 → BL-041 在 backlog 错挂 3 天 + Planner johnsong 在 BL-040 planning 阶段 grep 发现 → 直接 retroactive 关闭。

2. **BL-040 spec scope 漏 grep**：spec §F001 acceptance 列「删 generateAiAssets.ts:175 ?? 'Not specified' fallback」一处，但 Generator 开工前 grep 实物发现 email-generator.ts:74 + video-script-generator.ts:80 同样含 `?? 'Not specified'` 模式（D5 同根理由但 spec 未列）。Generator 按铁律 #10 没越界，留 Planner judgement → 入 BL-045 backlog deferred 跟踪。

两案例同根：**audit/spec 涉及"完整模式 X 全仓未/已实装"类断言时，必须先 grep 全仓而非依赖记忆 / 文档字面 / 单文件假设。** v0.9.13 §5.1 也是同根问题（spec 注释明示但实装漏）。

**根因：** v0.9.9 铁律 1 现行表述局限于 "spec 起草" 语境 + 仅覆盖单一字段类核查 — 未明示：
1. audit / review / readiness-report 类文档**也适用同一规则**
2. 涉及"完整模式"（如 fallback / dead code / migration）必须 `grep -rn '完整模式' src/` 看全仓

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 2 行：

| 内容（v0.9.14 新增） | 核查动作 |
|---|---|
| 任意"文件:行 + 现状描述"类引用 | grep / Read 实物核对当前 import / component / migration 状态；任何「未含 X / 缺 Y / 待实装 Z」类断言必须 5sec grep 验证；git log 看是否后续批次已 retroactive 实装 |
| 完整 pattern 模式（不仅 grep 单一关键词） | 当 spec acceptance 列「删某 fallback / 收紧某 type / 清某 pattern」时必须 `grep -rn '完整模式' src/` 看全仓出现次数 |

文档类型范围扩展：从「spec 起草」延伸到「spec / audit / review / readiness-report 所有起草类文档」。

**状态：** ✅ Accept + 落档（v0.9.14 — 用户 2026-05-06 决议）。`planner.md` 铁律 1 检查矩阵 +2 行新增 + BL-041 + BL-040 实战双反面案例段。CHANGELOG v0.9.14 已记录。

---

## [2026-05-06] Planner johnsong（BL-043 staging .env.staging 修复实战）— v0.9.14 #2：v0.9.7 §1.6 PM2 sediment 范围扩展（不限于 env_file 字段）

**类型：** 模板修订延伸（v0.9.7 §1.6 reaffirm + 范围扩展）

**内容：**

BL-043 staging .env.staging KOLMATRIX_APP_PASSWORD 修复（2026-05-06）实战触发：

1. Planner SSH staging append `KOLMATRIX_APP_PASSWORD=PROD_PWD` + sed 同步 DATABASE_URL 中密码
2. 一致性验证 PASS：staging .env DATABASE_URL pwd == staging KOLMATRIX_APP_PASSWORD == prod PROD_PWD
3. `pm2 reload kolmatrix-staging --update-env` → 仍 28P01 password authentication failed
4. `pm2 restart kolmatrix-staging --update-env` → 仍 28P01
5. pm2 jlist 验证：DATABASE_URL 在 process env 但是**旧值**（缓存）；KOLMATRIX_APP_PASSWORD 根本不在 env（PM2 没读 .env 新加的 line）
6. 直接 `PGPASSWORD=$NEW_PWD psql -h localhost -U kolmatrix_app -d kolmatrix_staging` 通 — 证 PG 角色密码与 .env 一致，根因是 PM2 进程 env 与 .env 文件不一致
7. v0.9.7 §1.6 标准方案：`pm2 delete + set -a; source .env.staging; set +a + pm2 start ecosystem.config.js --only kolmatrix-staging` ✓

**v0.9.7 §1.6 当前局限：** 标题 + 例都说"PM2 6.0.14 env_file 不可靠 anti-pattern"，描述中假设用户用 `env_file: /opt/<app>/.env.<env>` 字段。但实战 KOLMatrix `ecosystem.config.js` **不用 env_file 字段**（deploy-staging.sh 走 `set -a; source .env; set +a; pm2 start` 路径），仍踩同坑。

**根因深一层：** PM2 daemon 持有所有 process 的 env snapshot（process 启动时从 fork 的 shell 继承）。reload/restart --update-env 只重启 process（保持 daemon 缓存的 env），不会重新 source .env — daemon 不知道 .env 存在。

**建议写入：** `framework/harness/deploy-patterns.md` §1.6 后追加 §1.7「不限于 env_file — 任何 .env 改动后 PM2 reload/restart 都不重读」（v0.9.14 实战再现）：

- 标题更新：从「env_file 字段不可靠」延伸到「.env 改动场景全覆盖」
- 含实战触发场景（pm2 reload/restart --update-env 全失败的诊断证据）
- pm2 jlist 验证证据（DATABASE_URL 旧值 + KOLMATRIX_APP_PASSWORD 不存在）
- 修复模板（reaffirm pm2 delete + sourced shell start）
- 反面案例 BL-043 staging gap 修复

**状态：** ✅ Accept + 落档（v0.9.14 — 用户 2026-05-06 决议）。`deploy-patterns.md §1.7` 含实战诊断证据 + 修复模板 + BL-043 反面案例。CHANGELOG v0.9.14 已记录。
