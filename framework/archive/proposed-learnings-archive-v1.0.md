# Proposed Learnings 归档 — v1.0.0（2026-07-09 闭环）

> 本文件归档 v1.0.0 沉淀时闭环的提案。原文出自 `proposed-learnings.md`，用户 2026-07-09 确认按提案建议沉淀。

---

## [2026-05-11] Claude CLI — 来源：BL-064 fix-round 3 实战（顶层 IA refactor 7→4 路由）

**类型：** 新规律 / 模板修订（适用未来所有 IA refactor / page consolidation 批次）

**事实链：**

1. BL-064 spec §4 原预期 redirect ~12 条（7 老路由 + 子路径继承 + parametric）
2. fix-round 1-3 实战发现：embed-old-components 策略下，redirect 到 destination route **未 wire ready** 时（如 /campaigns/new → /brief?action=new 但 /brief 本批次只 embed /knowledge-base，没 wire form action），用户体验比 kept 旧路由 **差** — 跳转后看到的是 placeholder URL 但内容仍是旧的，反而 confusing
3. 最终缩减到 6 条 redirect = 5 content-equivalent prefix（/dashboard→insight / /discovery→match / /database→match / /knowledge-base→brief / /outreach→reach）+ 1 parametric（/campaigns/[id]→/match?campaignId=:id）
4. 4 条原预期 redirect 改 kept deep-link，推迟到后续 Phase 批次 wire destination 后再启：
   - /campaigns 列表 → kept；BL-066 wire /match view=campaigns 后启
   - /campaigns/new → kept；BL-069 wire /brief form 后启
   - /roi / /weekly-report / /analytics → kept；BL-070 unify /insight 后启
   - /outreach/templates 等 sub-path → kept；BL-070 wire /reach 子路由后启

**升级后的教训（适用未来批次）：**

A. **IA refactor batch 的 redirect scope 应根据 destination route wire-readiness 评估** — 不是所有老路由都立即 redirect，destination route 必须含等效或更优的功能才启 redirect；否则 kept deep-link 让 UX 不退化

B. **embed-old-components 占位策略下的 redirect 评估清单**（spec 起草时套用）：
   - destination route 是否已 wire 该 content？（如有则 redirect OK）
   - destination route 仅 embed-old 占位时，redirect 到那里只是 URL 换名 → UX 不变但用户认知混乱，**kept 更优**
   - 决策点放 spec §4 关键决策点，让 Planner 起草时 explicit 标记每条 redirect 的 wire-readiness 状态

C. **redirect scope 缩减是良性 fix-round** — fix-round 数不计入"质量问题"，反映 IA refactor 需要 building 中段实战验证才能确定最优 scope

**沉淀落点（2026-07-09 执行）：**
- `memory/role-context/generator.md` §"IA refactor redirect scope 评估"（3 行）
- `memory/role-context/planner.md` §"IA refactor 类批次 redirect 清单评估"（2 行）

**状态：** 已闭环（v1.0.0）
