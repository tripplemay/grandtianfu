# Framework 提案暂存区

> Generator 和 Evaluator 在工作中发现值得沉淀的经验时，追加到本文件。
> Planner 在 done 阶段读取本文件，逐条提交给用户确认。
> 确认后由 Planner 正式写入 `framework/` 对应文件，并在 `CHANGELOG.md` 追加记录，最后从本文件移除已确认条目。
> 已闭环条目归档到 `framework/archive/proposed-learnings-archive-vX.Y.md`。

---

<!-- 2026-05-04: v0.9.9 沉淀完成（8 条 learnings 来源 BL-030/BL-031/BL-032），全部已写入 framework/ 对应文件 + CHANGELOG。 -->

<!-- 2026-05-04: v0.9.10 沉淀完成（3 条 learnings 来源 BL-033 + prod-mvp-readiness-audit），全部已写入 framework/ 对应文件 + CHANGELOG。 -->

<!-- 2026-05-05: v0.9.11 沉淀完成（5 条 learnings 来源 BL-020 + backend-full-scan-2026-05-04 audit），全部已写入 framework/ 对应文件 + 项目根 .nvmrc + .auto-memory/environment.md + CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.11.md。 -->

<!-- 2026-05-05: v0.9.12 沉淀完成（3 条 learnings 来源 BL-034），全部已写入 pre-impl-adjudication.md §11 + database-patterns.md §8.1 + deploy-patterns.md §5 + evaluator.md §17 + CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.12.md。 -->

<!-- 2026-05-06: v0.9.13 沉淀完成（2 条 learnings 来源 BL-024），全部已写入 deploy-patterns.md §5.1 + ai-action-contract.md §4.7 + CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.13.md。 -->

<!-- 2026-05-06: v0.9.14 沉淀完成（2 条 learnings 来源 BL-040 + BL-041 audit 过期 + BL-043 staging fix），全部已写入 planner.md 铁律 1 矩阵 +2 行延伸 + deploy-patterns.md §1.7（v0.9.7 §1.6 范围扩展）+ CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.14.md。 -->

<!-- 2026-05-07: v0.9.15 沉淀完成（2 条 learnings 来源 BL-021 F002 撤再翻盘 + BL-049 测试基建 audit），全部已写入 planner.md 铁律 1 矩阵 +2 行（v0.9.15 #1 跨 pool 复现 + #2 stub environment-agnostic）+ CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.15.md。 -->

<!-- 2026-05-08: v0.9.16 沉淀完成（1 条 learning 来源 BL-052 verifying P5 裁决），全部已写入 planner.md §"Planner 裁决职责" §P5.2 段 + CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.16.md。 -->

<!-- 2026-05-08: v0.9.17 沉淀完成（1 条 learning 来源 BL-012 apify-kol fork audit），全部已写入 planner.md 铁律 1 矩阵 +1 行（v0.9.17 记忆条目陈旧风险）+ 反面案例段（BL-012 5/7→5/8 实战）+ CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.17.md。 -->

<!-- 2026-05-08: v0.9.18 沉淀完成（1 条 learning 来源 BL-012 F001 fix-round 1 admin role enum mismatch），全部已写入 planner.md 铁律 1 矩阵 +1 行（v0.9.18 auth role enum 实物核查）+ CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.18.md。 -->

<!-- 2026-05-08: v0.9.19 沉淀完成（1 条 learning 来源 BL-012 F002 fix-round 2 prod zod schema mismatch），全部已写入 planner.md 铁律 1 矩阵 +1 行（v0.9.19 external API response zod schema 实物 sample 验证）+ CHANGELOG。归档：framework/archive/proposed-learnings-archive-v0.9.19.md。 -->

<!-- 2026-05-10: v0.9.20 沉淀完成（1 条 learning 来源 BL-060 fix-round 1→2 e2e suite-level isolation vs 单 case 信号区分），写入 .auto-memory/role-context/evaluator.md §"E2E suite 稳定性诊断" + .auto-memory/role-context/generator.md §"扩范围 vs 单点修的判断"。后续 batch 候选（抽 tests/e2e/helpers/auth.ts + global-setup.ts + storageState 复用）入 backlog 跟踪。归档暂未写 framework/archive/proposed-learnings-archive-v0.9.20.md（git history 已有 commits cae1f8f / 821c094 完整记录）。-->

<!-- 2026-07-09: v1.0.0 沉淀完成（1 条 learning 来源 BL-064 IA refactor redirect scope），写入 memory/role-context/generator.md §"IA refactor redirect scope 评估" + memory/role-context/planner.md §"IA refactor 类批次 redirect 清单评估" + CHANGELOG。归档：framework/archive/proposed-learnings-archive-v1.0.md。 -->

<!-- 2026-07-14: v1.0.4 沉淀完成（8 条 learnings 用户逐条确认）。
     引擎域 3：patterns/cross-layer-consistency.md（新建，A1 成对豁免）+ testing-env-patterns.md §7（A2 fixture 退化）+ 顶部适用栈耦合提示（P2-3）。
     harness-fit 5：orchestration-patterns.md §7 红队校准 + docs/01-concepts.md（P1-1）；harness/workflow-bridge.md 新建（P1-3）；harness-rules.md §机制化守门"诚实边界"（P2-1）+ §Feature 执行者"路由位提示"（P2-2）+ 铁律区"commit 粒度理由重述"（P2-5），后三者根+framework 双副本同步。
     机件改动 3 条（P0-3/P1-2/P2-4）用户裁决为待办，留单独一轮 harness 机件重构；P0-1/P0-2 保持部分落地。CHANGELOG v1.0.4。
     注：本轮已确认条目状态就地标 ✅，未物理移除/归档（harness-fit 块含未闭环项 P0-1/P0-2/待办 3 条，整块不宜移除）。 -->

---

## [2026-07-12] Claude（harness-fit 分析 · 独立任务）— 来源：单工具 Claude + dynamic Workflow 工作流契合度评估（本会话 workflow wt27gd5xu，三视角 + 红队对抗复核）

**背景：** 用户已把主 coding 工作流收敛到单工具（仅 Claude Code），编码阶段用 Claude dynamic Workflow 编排。评估结论：harness 高契合且真提质，但价值不对称——**契约纪律 + 持久骨架**是纯增量（引擎给不了），**阶段内部编排**与引擎重叠、**多工具/多机底座**大部分是死重。以下提案已经过红队校准（推翻了"状态机=冗余仪式""慢车道=死重""Workflow 1:1 替代无自评"三个过度自信结论）。

---

### P0 —— 正确性前置（naive 上 Workflow 会踩的坑）

**P0-1 · 类型：新坑 / 铁律补充**
- **内容：** Claude Workflow 的 loop-until-done 天生会自主推进到"完成"并自排下一步，直接违反 `orchestration-patterns.md` §6 硬铁律「→verifying / →done 不得在无人值守循环中自动完成」。把阶段内部交给 Workflow 时，若不定契约就是**正确性回归**，不只是重复仪式。
- **建议写入：** `harness/orchestration-patterns.md` 新增「§8 Workflow run ⇄ progress.json 日志契约」小节（引擎只跑阶段内部、绝不 flip status 跨阶段；每步结果落盘持久文件；中途崩溃逐条对账）+ `harness-rules.md` 铁律区补一条呼应。
- **状态：** 部分落地 —— §8 已写入 `orchestration-patterns.md`（CHANGELOG v1.0.2）；剩余待确认：`harness-rules.md` 铁律区呼应条。

**P0-2 · 类型：新坑（最高风险）**
- **内容：** 沉淀闭环是事故驱动的，靠每批次一份 Evaluator 验收记录喂养。in-tool Workflow 若只在 context 里验完、不落"命名验收工件（BL-id + verdict + fix_round）"，`proposed-learnings.md` 会因**无 emitter 而静默饿死**（本文件现已显示"当前无待确认提案"即征兆）。这是模块级、产品级的静默失败——维护闭环本身就是本框架的产品。
- **建议写入：** `harness/orchestration-patterns.md` §4 + §8 + `templates/claude/skills/verify/SKILL.md`（verify 每轮必须持久化命名验收工件回喂沉淀，不可省）。
- **状态：** 部分落地 —— §8 契约 4 已写入 `orchestration-patterns.md`（CHANGELOG v1.0.2）；剩余待确认：verify SKILL.md 改写（Patch B，未落）。

**P0-3 · 类型：模板修订**
- **内容：** `/verify` step 3、`/build` step 5 把 fan-out/并行以**散文指针**（"按 §4 / §3"）交付，未真正 invoke Workflow——按框架自己"装进工具链才是强制"的标准，这层仍停在"写在文件里"。注意：fan-out 是**尾部场景**（触发门 ≥4 features），日常默认=单个隔离 evaluator subagent 本就 native，**不要把机制化 fan-out 当最高优先级**（红队降级）。
- **建议写入：** `templates/claude/skills/verify/SKILL.md` step 3 / `templates/claude/skills/build/SKILL.md` step 5 改为触发门命中时真正调 Workflow，并显式"停在阶段边界交还用户"。
- **状态：** 确认待办（2026-07-14 用户裁决：机件改动，留单独一轮 harness 机件重构做，不夹在 bug-fix 尾巴）

### P1 —— 结构精简 + 定位重申

**P1-1 · 类型：新规律（红队纠正，勿一刀切）**
- **内容：** 慢车道拆分：git **同步总线**语义单机确为死重，但两样单机也真实的能力搭在同一标签上不可一起砍——① **独立会话 evaluator** 是比 subagent **更强**的独立性（无编排者写的 prompt，免疫铁律 12 的作者污染风险）；② **跨会话/抗压缩交接**（多日批次 + 压缩会在同一会话内重现"新读者"问题）。
- **建议写入：** `docs/01-concepts.md` 慢车道段 + `harness/orchestration-patterns.md` §7（区分"同步总线"与"独立会话隔离 / 跨会话持久"两类，前者可选、后者保留）。
- **状态：** ✅ 已沉淀 v1.0.4（orchestration-patterns.md §7 红队校准 + docs/01-concepts.md 慢车道段）

**P1-2 · 类型：模板修订**
- **内容：** 快车道热路径剥离慢车道底座：`/plan /build /verify` step 1 的 `git pull --ff-only` + `.agent-id`/`.agents-registry` 读、`session-start.sh` 的 `role_assignments` 注入、`bootstrap.sh:71` 无条件铺 `AGENTS.md`——单机全是空转仪式，改为多机模式 opt-in。
- **建议写入：** 三个 skill SKILL.md step 1 + `templates/claude/hooks/session-start.sh` + `bootstrap.sh`。
- **状态：** 确认待办（2026-07-14 用户裁决：机件改动，留单独一轮 harness 机件重构做）

**P1-3 · 类型：新规律（定位重申）**
- **内容：** 把 harness 明确定位为坐在 Workflow 引擎之上的**薄契约纪律 + 持久骨架层**：引擎给编排**形状**，harness 给**常设默认强制 + 约束载荷（受限工具集 / 只认实物 / 误报预检 / 测试设计权）+ 用户闸门 + 抗压缩骨架**——这四样引擎都没有。
- **建议写入：** 新增 `harness/workflow-bridge.md`（角色 ⇄ Workflow stage 映射；标注哪些规则由引擎结构性强制、哪些仍是散文护栏）。
- **状态：** ✅ 已沉淀 v1.0.4（新建 harness/workflow-bridge.md）

### P2 —— 清理与补缺（须外科式，勿误伤承重项）

**P2-1 · 类型：铁律澄清（红队纠正）**
- **内容：** 机制化其实比宣传的薄：唯一硬阻断是 `validate-state-json.sh`（还只查 JSON **语法**，不查"status=done 但 signoff 为空"这种语义）；无自评 / done-门 / 裁决不洗白 / spec 源码核查**都活在散文里**。推论："砍散文仪式"必须外科式，勿把承重约定当仪式误删。
- **建议写入：** `harness-rules.md` §机制化守门（标注"当前硬阻断仅覆盖 JSON 语法，语义门仍靠约定"）。
- **状态：** ✅ 已沉淀 v1.0.4（harness-rules.md §机制化守门"诚实边界"注 · 根+framework 双副本）

**P2-2 · 类型：新坑**
- **内容：** `executor:generator|evaluator` 是**活的路由位**（把报告类任务路进 verifying、选 Evaluator-only 批次流），与已死的 `executor:"codex"` 别名同段落；清 Codex 血缘时须**外科分离**，勿连带误删路由。
- **建议写入：** `harness-rules.md` lines 47/108 + `evaluator.md` + `planner.md` 相关行的清理注意事项。
- **状态：** ✅ 已沉淀 v1.0.4（harness-rules.md §Feature 执行者"路由位提示"注 · 根+framework 双副本；evaluator/planner.md 重复注记从略避免 planner 双副本分叉）

**P2-3 · 类型：新坑**
- **内容：** 对抗复核的误报目录（`patterns/testing-env-patterns.md`）是 **stack-coupled**（Prisma/Next/Postgres-RLS），换技术栈大半不可移植，且框架无"给新栈重播种目录"的机制。
- **建议写入：** `patterns/testing-env-patterns.md` 顶部标注适用栈 + 提供"新栈重播种"指引。
- **状态：** ✅ 已沉淀 v1.0.4（testing-env-patterns.md 顶部"适用栈耦合提示"）

**P2-4 · 类型：模板修订（与上一轮接入缺口同源）**
- **内容：** 补存量项目接入路径：`bootstrap.sh` 遇 `harness-rules.md` 存在即 abort（仅 greenfield）；加 `--adopt` 模式只装 `.claude/` 机制层（hooks + evaluator subagent + skills + progress.json），跳过 memory/spec 脚手架。
- **建议写入：** `bootstrap.sh` + `docs/03-quickstart.md` 补一节「已有项目接入」。
- **状态：** 确认待办（2026-07-14 用户裁决：机件改动，留单独一轮 harness 机件重构做）

**P2-5 · 类型：铁律澄清**
- **内容：** commit 粒度：per-feature commit 的**跨设备恢复**理由单机已失效，仅**抗压缩**承重（写状态文件即可恢复，逐 feature 打 git commit 是额外审计/回滚开销）；可放宽为 per-phase-boundary commit（保留状态文件写入 + JSON hook）。
- **建议写入：** `harness-rules.md` 铁律 2/3 理由重述（"跨设备恢复 + 抗压缩" → "抗压缩持久 + 审计轨迹"）。
- **状态：** ✅ 已沉淀 v1.0.4（harness-rules.md 铁律区"commit 粒度理由重述"注 · 根+framework 双副本）

<!-- 2026-07-13: 自主开发模式 + 进度看板 沉淀完成（用户确认，默认安装）。
     自主：机件转正入 templates/claude/{agents/{generator-restricted,spec-lock-critic}.md, skills/autodrive/, autonomous/*}；harness/autonomous-mode.md 转正为 T2 规范。
     看板：templates/dashboard.template.html + templates/claude/skills/dashboard/SKILL.md + progress.init.json(dashboard_url) + bootstrap chmod + harness-rules §四 + templates/CLAUDE.md。
     CHANGELOG v1.0.3。归档：archive/proposed-learnings-archive-v1.0.3.md。
     注：harness-fit 分析（P0-P2）不在本次确认范围，仍保留待确认。 -->

<!-- 2026-07-13: decor-b1 沉淀 1 条（词表/注册表类 feature 拆分完整性约束）已确认，写入 planner.md 铁律 10。 -->

## [2026-07-13] Evaluator(local/evaluator-subagent) — 来源：decor-b2 F007 第7步几何对抗验收头号项

**类型：** 新坑

**内容：** 几何/渲染类对抗验收若沿用现网单测 fixture 的坐标，可能命中退化位置——本批 head-line 单测 `test_geometry_lock_decor_wall_art_paint_in_allowed_no_structure_fail` 用 `wall_art@(dx=300,dy=300)`，房内坐标映射到世界 `(3000,3000)mm` 恰是合成相机眼位，投影退化 → allowed 覆盖整画幅 → structure 边界断言 trivially 成立（测试仍正确 PASS 但没压到边界）。Evaluator 做几何对抗时应先核 fixture 是否在相机正视野内（`box_usability` usable + in_frame_frac≈1），退化位置的"绿"不等于边界被真正验证。改用正视野墙位重验才量化出真实的覆盖余量(0未覆盖+21px顶余量)与 load-bearing 反证。

**建议写入：** `framework/patterns/testing-env-patterns.md`（新增"几何/渲染对抗验证 fixture 退化校验"节）

**状态：** ✅ 已沉淀 v1.0.4（testing-env-patterns.md §7）

## [2026-07-14] Planner(local) — 来源：decor-b3-fix 贴墙软装轴测校验误判阻断出图

**类型：** 新坑

**内容：** 当给某类型加"豁免归一化/自愈"语义时，必须同步在**校验门**加对应豁免——否则自愈侧放行、校验门侧硬拦，产生"编辑器无错但出图被阻断"的分裂。本 bug：decor-b1 D13 让 NOSHADOW_TYPES(挂画/窗帘)豁免 `build_scene` 的 inner-clearance 内缩(它们本该贴墙)，但 `_validate_items` 的 AXON 路径漏加同一豁免 → 这些"正确贴墙"的件反被判 AXON_越界/穿墙 = ERROR → validation.ok=False → 出图被拦；而编辑器过滤 AXON_ 恰好把这层错误藏起来，用户无从察觉。规律：**归一化/自愈豁免与校验门豁免必须成对实现**；新增"应违反某几何约束"的类型时，grep 该约束的所有 enforcement 点(归一化 + validate + lint)确认全部同步豁免。次生教训(Evaluator 补充)：可归一化的非-noshadow 件走 `build_scene` 端到端必被 D13 自愈掩盖，类型限定的校验门反证只能在 `_validate_items` 层直注入做，端到端管线做不出干净反例。

**建议写入：** `framework/patterns/` 新增或并入"跨层语义一致性检查"节（豁免/约束类改动的成对实现 checklist）

**状态：** ✅ 已沉淀 v1.0.4（新建 patterns/cross-layer-consistency.md + README 索引）

## [2026-07-15] Evaluator(local/evaluator-subagent) — 来源：render-fix-b1 三轮验收（首轮 + 复验1 R4 + 复验2）

**类型：** 新规律 ×2 + 新坑 ×4（全文见 `docs/test-reports/render-fix-b1-signoff-2026-07-15.md` §Framework Learnings）

**内容：**

1. **（新规律）「跑完没脏」不足以证明修复有效 —— 验证「污染/泄漏已止住」类结论必须先建阳性对照。** 否则「没检测到」与「检测方法失明」不可区分。本轮用 `git worktree` 检出 buggy commit、跑同一条命令确认污染**能**复现，才使 HEAD 的「未复现」具备证据力，并把归因锁定到那一行修复。→ `patterns/testing-env-patterns.md`

2. **（新规律）判断「等待是排空还是掩盖时序」，看产品代码的偏序而非等待时长。** `_wait` 是真排空，因为 `jobs._run` 严格「先 `fn()` 跑完、后置 `status=done`」而 `fn()` 最后一句正是落盘 ⇒ 等到 done 必然等到写完。判据应是读出这条偏序（+ 人为拖慢关键段撑开窗口实证），而非「等 10s 大概够了」。→ `patterns/testing-env-patterns.md` §14

3. **（新坑）后台线程在 pytest session 结束后才抛的 warning 不进 `warnings summary`。** 本案 2 条 RankWarning 是泄漏线程在 teardown 之后跑到 polyfit 才冒的裸 stderr，早已超出警告插件捕获窗口 → 用「warnings summary 是否为空」验此类项**会漏报**。正解：合并 stdout+stderr 后全量 grep。→ `patterns/testing-env-patterns.md`

4. **（新坑）monkeypatch 沙箱 + fire-and-forget 后台 job = 沙箱写穿。** 测试一返回 monkeypatch 即拆除，`DATA_DIR`/provider 工厂/stub 全部复原成真实值而后台线程仍在跑 → 写进 git-tracked 目录，甚至可能在有 key 的机器上发起真实计费调用。凡「同步返回 job_id + 后台落盘」的端点，测试必须排空后台 job；更稳做法是 fixture 层 `yield` + teardown 排空（本案 8/8 靠人工约定=知情自律）。→ `framework/README.md §经验教训` + `patterns/testing-env-patterns.md`

5. **（新坑）修跨层一致性 bug 的批次，自己引入了同类缺口 —— 该模式极易复发。** 本批病灶是「守卫在一处存在、兄弟点不知情」(`box_usability` 检测到退化但 `annotate_boxes` 照画)，而 fix_round1 又引入 `DEGENERATE_GUIDE` raise 带 code、except 段不认识 → 落 500。`cross-layer-consistency.md` 应加自查条：**「新增 raise/信号时，是否所有消费点都被机制（而非纪律）保证认识它？」** → `patterns/cross-layer-consistency.md`

6. **（新坑）「集合式修法」是把知情自律往后挪一格，不等于机制化关死。** `_INPUT_GATE_CODES_409` 从散落 `if` 收敛为单一命名锚点（客观改进），但仍是人工登记表。真正机制化需让不变量在语法上不可违反（如 `InputGateError` 让 code 与状态码同生）。**验收时应显式区分这两档，避免把「更整洁的自律」误记为「已机制化」。** → `harness/evaluator.md` 或 `patterns/cross-layer-consistency.md`

**状态：** ✅ **用户 2026-07-15 确认，已全部落地（framework v1.0.6）** —— 落点：1→`patterns/testing-env-patterns.md` §10；2→§11；3→§12；4→§13；5→`patterns/cross-layer-consistency.md` §自查条（新增 raise/信号的消费点由机制还是纪律保证）；6→同文件 §集合式修法≠机制化关死（两档判据表）。

---

## [2026-07-15] local + 4 位隔离 Evaluator — 来源：calib-z-b1（标定 z 轴系统性取反）

**类型：** 新规律 ×3 / 新坑 ×3 / 铁律补充 ×1

**状态：** ✅ **用户 2026-07-15 逐条确认，已全部落地（framework v1.0.5）** —— 落点见下方各条

1. **（新坑·高价值）测试 fixture 与被测代码共享同一错误假设 → 两错相消 → 该 bug 永远测不出来。** 本批根因是 `calibrate()` 在左手系里用 `+cross(x,y)` 强制 det=+1；而测试的 `_synth_camera` **自己也是 det=+1 的镜像相机**（它的 "right" 实指向左）。二者犯同一手性错误，往返测试因此"自洽"通过 —— **这正是该 bug 能上线且 200+ 测试全绿的原因**。自查条：**当被测对象是"约定/坐标系/编码"这类全局假设时，fixture 必须由独立于被测实现的第一性原理构造**（本案：物理 look-at + 已知真值），不得复用被测代码的构造式。→ `patterns/testing-env-patterns.md`

2. **（新坑·同族且更狠）验证左手系 bug 时，反证脚本本身极易犯同一个错。** 第三位 Evaluator 的第一版合成真值**在左手系里做叉乘** → 真值相机上下颠倒 → 一度得出"修复后是错的"的**相反结论**。订正法：在**右手系 ENU** 里 look-at，再换基到 ESU。即：**手性 bug 的反证工具必须在已知右手系里构造，再换基进被测约定** —— 否则你用 bug 去验 bug。→ `patterns/testing-env-patterns.md`

3. **（新规律）"结论对、判据错"是对抗验证的常见失效模式，须显式分离二者。** 本批 3 位 Evaluator 中**两位**出现过：A 的窗框右缘 x≈430 落在玻璃正中（无窗框）但结论对；我（Generator）对 R1 成因用"跑 5 次没泄漏"这种证据不足式论证，结论也碰巧对。**验收/审计应把"结论"与"支撑判据"分别标注可靠性**，并优先采用**不依赖目检数字**的结构性论证（本案终审领衔判据：det 手性 + 精确镜像对 + 数据对二者无偏好 ⇒ 方向只能由物理定）。→ `harness/evaluator.md`

4. **（新规律）"排除/不修"不是中立选择，须按"主动留下已知缺陷"来论证。** fix-round 1 曾以"无法定论"排除 1537e，读起来像保守稳妥；实则是**主动把一台已知物理不可实现的镜像相机留在生产**，且自愈报告打印"相机在地板下方：0 条"**读起来像已干净**（该判据对镜像解本就不适用）。自查条：**任何 skip/exclude/降级，必须写明"留下的是什么缺陷"，且报告不得让被排除项看起来已解决。** → `framework/README.md §经验教训`

5. **（铁律补充）编排者不得在 Evaluator 存活期间另起第二个做同一验收。** 本批我误判首个 Evaluator 已死（它无 transcript、无产物、发 idle 心跳）而另起一个，导致两位并发验收同一批次、争抢 `progress.json`。所幸二者均未销毁对方轨迹（一位主动把对方记录 byte-identical 移入 history）。**判死一个 subagent 前须有积极证据**（transcript 增长停滞 + 无产物 + 明确终态），而非"我看不到进展"。→ `harness-rules.md §独立性铁则` 或 `orchestration-patterns.md`

6. **（新坑）`git add -A` 会把工作区既有脏文件扫进本批 commit，违反铁律 10。** 本批 F002 commit 夹带了 `data/projects/D/schemes/default/renders.json`（2026-07-11 的本地残留），与该 commit message 自称的"结构上不可能写穿"直接矛盾。**推送前须 `git status --short <红线目录>`**；更稳做法是显式 `git add <files>` 而非 `-A`。→ `harness-rules.md §推送前遗漏检查`

7. **（新坑·流程伤害）`git stash` 误操作可无声代办用户的待决事项。** 仓库存有一个用户标记"待决定去留"的 stash，在本会话被 pop 进工作区且 stash 被丢弃 —— **用户的决定被代做了**。查实靠 blob 同一性（stash blob 与 commit 夹带 blob 逐字节同一）；恢复靠 `git stash store <unreachable-commit>`（gc 前有效）。自查条：**stash 是用户的待办队列，不是 agent 的临时空间**；需要基线对照请用 `git worktree`。→ `framework/README.md §经验教训`

---

## [2026-07-16] Planner + Generator(local) — 来源：decor-envelope-b1（第7步残余误报：两个 z 世界 + 单位陷阱 + 验收机件）

**类型：** 新规律 ×2 + 新坑 ×1 + 机件教训 ×1

**状态：** ✅ **用户 2026-07-16「按你的判断来」授权，已全部落地（framework v1.0.7）** —— 落点见各条末尾。

1. **（新规律）Planner 期基于「读代码觉得这个数看着合理」的结论，在有生产实物可量时，不该写成 spec 断言。** 本批 spec §2.2 原断言「挂画盒 1000..1400 在实拍真实毫米下恰好合理，属借错数字但碰巧不出错」——building 期用生产实物一量就塌了：挂画盒同样是照抄轴测压扁世界的 `axon` SPECS，与窗帘同源，只是没错得那么显眼。**判据：spec 里每条「X 是对的/合理的」断言，问一句「这是量出来的，还是读代码推测的？」推测的须标注为待验，不得写成定论。** → `harness/pre-impl-adjudication.md §4.8`

2. **（新规律）纯机制化重构应以「输出逐字节等价」作为验收判据，它比「测试跑绿」强一个量级。** 本批 F001 把 allowed 上沿从双写表改为派生，余量维持不动 → 获得 byte-identical 判据（生产实物 allowed mask pre/post sha256 均 `81cdbeea..`）。跑绿只说明没崩；逐字节相同才说明「真的只是换了个写法」。**凡「重构/提取/去重，行为应等价」类改动，验收先问：能不能做出逐字节对照？** → `patterns/testing-env-patterns.md §14`

3. **（新坑）跨会话/二手报告传递的测量数字，必须带单位与坐标系——否则会被静默误读。** 本批 backlog 记的「8~12px」未标明是工作空间(512宽)还是原图(2048宽)，两者差 4 倍。靠反证才定死（若是原图 px 则今天的 100mm 余量本就该盖住 → 与实际有坏块矛盾 ⇒ 只能是 work-px）。旁证：报告者把 tile 坐标换算成原图空间，却没换算距离 → 一份二手报告里混了两个坐标系。 → `patterns/testing-env-patterns.md §15`

4. **（机件教训）长验收 subagent 应尽早、分段落盘结论，别把 `evaluator_feedback` 落盘堆在收尾最后一步。** 本批**两个** evaluator subagent 都在收尾最后一步被 API stream idle timeout 截断（第一个连报告都没写就死；第二个写完完整报告、就差落 feedback 时死）。落盘顺序应「先落 feedback 骨架、再写详细报告」；编排者判死后若报告已完整，可从报告逐字**转录**结论（转录≠改写，须标注来源）。 → `harness/evaluator.md §7`

## [2026-07-17] Evaluator(F012 spike) — 来源：f4d 客餐厅照片标定构造实测

**类型：** 新坑

**内容：** 镜面反光地面（大理石/亮面砖）把墙/门倒影映成"双底线"，点选地面特征时易取到倒影线（f4d 底轨 v 向偏 49px 实证）。特征点 UI 指引应加"点踢脚/门框与地面的真实交线，勿点倒影"。

**建议写入：** `framework/patterns/`（标定/特征点采集）+ 产品 UI 文案

**状态：** 待确认

## [2026-07-17] Evaluator(F012 spike) — 来源：living_f4d 标定极限实测

**类型：** 新规律

**内容：** 手机超广角（hfov≳105°）贴角拍摄，针孔无畸变模型全幅拟合极限 reproj≈100px+，必触 CALIB_MAX_REPROJ_PX 硬门——门禁行为正确，但产品拍摄指引应明示"用 1x 主摄、离墙 2m 以上"以降低重标挫败感。

**建议写入：** `framework/patterns/` 或产品拍摄指引

**状态：** 待确认

## [2026-07-17] Generator(calib-cure-b1 F004) — 来源：_calib_payload fixture 镜像相机现形

**类型：** 新坑

**内容：** 合成相机 fixture 用右手系惯例（right=cross(fwd,z), down=cross(fwd,right)）搭在左手世界上=镜像相机（水平相机拍地面点投到地平线上方，物理不可能），2 锚点时残差被 t 吸收成 <5px 假象，第 3 锚点一加爆 3665px——正是 case-A 病灶的活体标本。合成相机构造必须物理一致（手性+地平线方向自检），修正模板见 test_render_real_geometry._calib_payload 订正版。

**建议写入：** `framework/patterns/testing-env-patterns.md`（合成 fixture 构造）

**状态：** 待确认

## [2026-07-17] main(calib-cure-b1) — 来源：data/projects 写穿竞态实证

**类型：** 新坑 / 铁律补充

**内容：** 回退路径类测试 POST render 后不排空后台 job：测试返回即拆 monkeypatch、DATA_DIR 复原真实仓库，迟到的 append_render 写穿 git-tracked data/projects（本机有 rsvg 时旧路径真能出图；并行 worktree agent 负载放大竞态，5 跑 5 漏）。规约：**任何可能启动后台 job 的测试必须排空**（_drain_render_job 模式：200+job_id 即 _wait，done/error 均算）。

**建议写入：** `framework/patterns/testing-env-patterns.md` + evaluator/generator 行为规范

**状态：** 待确认

## [2026-07-17] main(calib-cure-b1) — 来源：4/4 并行 worktree agent 初始基不对

**类型：** 新坑

**内容：** worktree 隔离的并行 agent 初始分支基点可能停在 main 而非批次分支（本批 4/4 复现）。派发 prompt 必含前置自检："git log --oneline -3 须含 <依赖 commit>；否则 git fetch && git reset --hard origin/<批次分支>"。

**建议写入：** `orchestration-patterns.md` §3（并行 building 做法）

**状态：** 待确认

## [2026-07-17] Evaluator(F012 spike) — 来源：auto_check 与目检在关键格反转

**类型：** 新规律

**内容：** auto_check（背景保真启发式）形体盲且可与真实质量反转（study fal：L0 错误窄条书柜 0.95 > L1 正确满墙 0.85——留白少反而得分高）。任何"形体/落位质量"评测必须配 VLM 或人工目检，auto_check 只作"画没画/改没改背景"的尾部兜底。

**建议写入：** `framework/harness/evaluator.md` 或 patterns（评测方法论）

**状态：** 待确认
