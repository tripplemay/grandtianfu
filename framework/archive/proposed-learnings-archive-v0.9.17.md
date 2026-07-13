# Proposed Learnings Archive — v0.9.17

> 归档日期：2026-05-08
> 来源批次：BL-012-apify-kol-integration v2 spec 修订前 Planner 旁路 audit（fork 实物 vs 记忆陈旧）
> 闭环情况：1 条 learning Accept（用户 5/8 决议 A）+ 落 framework，CHANGELOG v0.9.17 已记录。

---

## [2026-05-08] Planner johnsong（BL-012 apify-kol fork audit 2026-05-08）— v0.9.17：记忆条目陈旧风险

**类型：** 铁律 1 v0.9.14 延伸（记忆条目陈旧风险 — 涉及外部协作方 / 第三方仓库的"X 已交付/已审过"类断言）

**内容：**

`.auto-memory/project-status.md` 涉及外部协作方 / 第三方仓库 / 跨项目状态的记忆条目（"爬虫团队 5/7 提前交付"、"X 团队已部署"、"fork audit 推荐方案 A"等）可能 stale at write-time —— 前一轮 Planner 写时反映当时事实，但实物在后续被外部协作方主动更新。后续 Planner 起 spec / 起批次时若不实物核查，会引入"基于过期记忆"的偏差，导致 spec 字面与 fork 实物脱节 → Generator 开工撞实物差异 → 多 1 轮 fix-round 或 retroactive spec 修订。

**实物时间线（BL-012 5/7 → 5/8）：**

1. **5/7 ~14:00** Planner Kimi 在 `.auto-memory/project-status.md:16` 写「爬虫团队 5/7 提前交付 https://github.com/guang-tech/apify；fork audit 推荐方案 A 分平台分源 IG/TT 给 apify YouTube 给 B6；4 阻塞项待用户决议」 —— **3 平台分流口径**
2. **5/7 16:57** fork 实物 `guang-tech/apify` 完成重大更新（`gh api repos/guang-tech/apify` updatedAt 实物字段）：
   - **Apify → TikHub 全迁移**（`docs/specs/2026-05-07-tikhub-migration-design.md` 16KB 设计文档落地）
   - **新增 X(Twitter) 平台**（4 平台齐全，不是 3 平台分流）
   - 成本结构改变：Apify $850-$1170/月 → TikHub ~$515/月（省 $300-650/月 = $4k-7.8k/年）
3. **5/8 ~02:00** Planner johnsong 启动 BL-012 planning，Planner 角色文件第 0a 步 grep `.auto-memory/project-status.md` 看到 line 16 记忆条目，**默认信任记忆字面**，准备按 3 平台分流口径起 spec
4. **5/8 ~02:05** Planner 自检发现 project-status.md:16 记录"5/7 fork audit"但仓库 0 audit 报告 / 0 commits / 0 docs 实物支撑（铁律 1 v0.9.14 反面案例自检）→ 触发实地补 audit
5. **5/8 ~02:15** 实地补 audit（`gh api repos/guang-tech/apify` 抓 README + .env.example + 4 份 docs/specs/）→ 发现 fork 5/7 重大变化与记忆字面**严重脱节**
6. **5/8 ~02:30** audit 输出 `docs/reviews/apify-fork-audit-2026-05-08.md`（462 行）+ 用户决议 5 项 + 修订 BL-012 spec v1（按记忆字面起草）
7. **5/8 ~02:30** 用户重新讨论后 v2 修订（13 features Stage 1.5 admin preview + 决策门 + Stage 2 真接入）

**根因：**

铁律 1 v0.9.14 已覆盖 spec / audit / readiness-report 起草前 grep 实物状态，但**对项目内 `.auto-memory/` 涉及外部协作方的记忆条目**仍存在盲区 — Planner 默认信任记忆 = 信任前一轮写入的快照，但外部协作方 / 第三方仓库可能在记忆写入后被独立更新。

3 个月协作中外部 / 内部状态频繁变动：
- 第三方仓库（fork / mirror）可能新增 commits / 重命名分支 / 切换数据源
- 跨项目部署（aigcgateway / staging / prod）可能版本切换 / DB schema 演进
- 外部团队（爬虫团队 / 翻译同事 / 设计师）"已交付"承诺可能延期 / 提前 / 重新规划

**修订规则：**

Planner Step 0 启动新批次前，对 `.auto-memory/project-status.md` / `session_notes` 涉及外部协作方 / 第三方仓库 / 跨项目状态的条目（含 "X 团队已交付 / 已部署 / 已审过 / 已上线"类断言），**必须先 grep 实物当前状态**：

| 内容类型 | 核查动作 |
|---|---|
| 第三方 GitHub repo（含 fork / mirror / external dep） | `gh api repos/<owner>/<repo>` 抓元数据 + 看 `updatedAt` 是否后于记忆写入时间 |
| 内部 fork / mirror（如 framework template）| `git log --all --since=<记忆时间戳>` 看是否有后续 commits |
| 跨项目部署状态（aigcgateway / staging / prod）| `curl <service-url>/health` + 看响应版本 / sha |
| 外部团队"已交付/已审过"承诺 | 实地索要文档 / commit hash / DB schema dump 等具体物 |

**时间戳 ≥3 天的"提前交付"类条目尤其必查** — 3 天足以让协作方完成大改动而记忆未同步。

**反面（不修订时）：**

- project-status 记忆驱动 spec 起草 → spec 字面与外部实物脱节 → Generator 开工撞实物差异 → 多 1 轮 fix-round 或 retroactive spec 修订 → 浪费上线 buffer
- BL-012 5/8 案例：若 Planner johnsong 信任记忆字面起 spec，撞 5/7 X 平台 + TikHub 全迁移会导致 ≥1 轮 spec retroactive 修订 + Generator fix-round + 用户决议项需要重新设计（如付费方 / 平台覆盖范围 / 字段映射全错）
- 长期趋势：跨周项目记忆陈旧成本随项目复杂度指数增长，没有规则化检查 = 老 bugs 反复出现

**建议写入：** `framework/harness/planner.md` 铁律 1 检查矩阵新增 1 行（v0.9.17）：

| 内容（v0.9.17 新增） | 核查动作 |
|---|---|
| `.auto-memory/project-status.md` / `session_notes` 等记忆涉及外部协作方 / 第三方仓库 / 跨项目状态的条目（"X 团队已交付/已部署/已审过/已上线"类断言） | `gh api` / `git log --all` / `curl health` 实物核查仓库当前状态 + 看时间戳是否后于记忆写入时间；时间戳 ≥3 天必查 |

**状态：** ✅ Accept + 落档（v0.9.17 — 用户 5/8 决议）。`planner.md` 铁律 1 矩阵 +1 行（v0.9.17）+ 反面案例段（BL-012 5/7→5/8 实战）。CHANGELOG v0.9.17 已记录。

---

## 综合：v0.9.17 与既有铁律的关系

| 既有规则 | v0.9.17 延伸点 |
|---|---|
| v0.9.9 铁律 1（spec 起草前实物核查） | 延伸到"项目内记忆条目"层 — `.auto-memory/` 写时为快照，读时可能 stale |
| v0.9.14 铁律 1 #1（"文件:行 + 现状描述"类引用核查） | 延伸到"外部协作方时间戳"判断 — 记忆写入时间 vs 外部 updatedAt 时间差判断 |
| v0.9.14 铁律 1 #2（"完整 pattern 模式"全仓 grep） | 延伸到"外部仓库结构核查" — fork / mirror 的目录结构 / 关键文件存在性 |
| v0.9.10 上线前 audit 模式（旁路任务） | v0.9.17 在 BL-012 5/8 实战触发 audit — 是 v0.9.10 模式在 spec planning 阶段的应用范式 |

**Planner 起草 spec 阶段的"实物核查"完整 layer：**

```
Layer 1 (v0.9.9): 代码 / migration / route 路径 → grep / Read
Layer 2 (v0.9.14): "文件:行" 类引用 / "完整 pattern" → grep -rn 全仓
Layer 3 (v0.9.15): 测试 fail / stub 设计 → 多 pool 实地跑 / Map-backed
Layer 4 (v0.9.17): .auto-memory / 跨项目状态 → gh api / git log / curl health
```
