# proposed-learnings 归档 — v1.0.3（2026-07-13）

用户确认转正（默认安装）的两项能力，原提案条目归档留存。正式变更见 CHANGELOG v1.0.3。

---

## 自主开发模式（来源：design workflow w05dglv38 — 4 立场架构师 → 4 评委对抗打分 → 红队攻击领先方案）

**背景：** 用户问"能否在本框架下实现多 agent 自主推进 / 自主开发"。评估：可以，状态机脊椎天然适合当自主骨架。推荐架构 = S2 Heartbeat（`/loop` 心跳把 progress.json.status 当程序计数器，31/40 领先）+ S3/S4 安全机件嫁接。红队核心发现：硬保证不能只放在**状态迁移高度**——危险动作（deploy/prod/花钱）是**阶段内部工具调用**，真正的强制在**工具层 deny-list**。S1（deterministic-first）架构师本轮 API stall 未参评。

- **A1（新模板）：** `harness/autonomous-mode.md` 规范 + 机件初稿 → 转正入 `templates/claude/{agents,skills/autodrive,autonomous}/`，规范文档 T2 保留。
- **A2（安全缺口 🔴）：** 框架原只有 `evaluator.md` 受限工具集，无 generator/fix subagent → 并行/自主 subagent 会继承 Bash + 花钱 MCP，可无人察觉触发 deploy/prod/花钱。修复：`generator-restricted.md` + `settings.autodrive.json` deny-list（工具层强制）。
- **A3（铁律澄清）：** 铁律 12 原为模型自律 → `/autodrive` 用固定模板派 evaluator（只插值 {批次, 路径, L2-flag}，无实现叙述）。

**安全边界：** 安装≠开启；开启需人类建 `autonomy-policy.json` + 显式 `/autodrive`（步骤 0 前置断言，否则 HARD_HALT）；deploy/prod/spend 永留人类闸门。**仍待建（需接真实项目）：** §9 运行时锁/告警、gate-arbiter build/plan 接真实逻辑、端到端演练。

---

## 进度看板（来源：用户希望长时开发中有图形化看板观测研发进度）

**背景：** Claude Artifact 做进度看板。关键约束 CSP **禁 fetch** → 看板是**快照**，harness 在阶段边界**重渲染 + 重发到同一 URL**（存 `progress.json.dashboard_url`）。数据零额外来源，全来自已落盘状态文件。

- **D1（新模板 + 新 skill）：** `templates/dashboard.template.html` + `templates/claude/skills/dashboard/SKILL.md`（`/dashboard`）+ `progress.init.json` 加 `dashboard_url` + bootstrap 铺入 + `harness-rules.md §四` / `CLAUDE.md` 加"顺手刷看板"。看板是**只读镜像非真相源**。
- **D2（顺带红利）：** 默认私有、可分享只读链接给干系人；与自主模式天然搭（每唤醒阶段边界顺手刷）。
