# render-fix-b1 Signoff 2026-07-15

> 状态：**已验收通过**（progress.json status=done，fix_rounds=2）
> 触发：用户报「户型 v7/胡桃石韵轻奢 最新效果图餐桌位置错」→ 实证两个独立 bug + 一处静默失败面
> Evaluator：隔离 evaluator subagent（fresh context，`local/evaluator-subagent`），三轮均为独立上下文
> 完整验收轨迹：`docs/test-reports/render-fix-b1-verifying-2026-07-14.md`（首轮 + 复验 1 + 复验 2）

---

## 变更背景

用户报第 7 步实拍效果图餐桌落位错误。取**生产实物**（`D/scheme_ai_20260714_130354_01_baec` 的 render `412b6acc` + photo `417ae5589afe` 标定 + v7 几何）复现，定位两个**互相独立**的 bug —— 任一都足以致错 —— 另加一处静默失败面：

- **P0（主因）**：`curtain` 盒顶点落在相机背后（`minDepth<0`），`_box_polys` 无近平面守卫 → 除以负深度 → 多边形炸开到 ~1e5px，品红覆盖全画幅，把餐桌紫盒**完全埋掉**（实测餐桌可见面积 **0.00%**）→ AI 无位置信号，自由发挥。
- **P1**：`ANNO_PALETTE` 仅 8 色且静默 `% len()` 回绕 → 第 9 种 `plant` 撞第 1 种 `dining_table`，生产 prompt 原文并存两条 `purple` 映射，画面 4 个紫盒语义不可区分。
- **静默失败面**：该 render `auto_check` 打 **0.967 / ok:true 通过** —— 现有验收不校验引导图本身，灾难完全静默。

---

## 变更功能清单

### F001：`_box_polys` 近平面裁剪（P0 主因）

**Executor：** generator ｜ **判定：PASS**

**文件：** `apps/api/aigc/perspective.py`（修改）

**改动：** 在**相机系**做单平面 Sutherland–Hodgman 近平面裁剪（`NEAR_MM = 10.0`）后再投影：8 顶点求 `c = R@w+t`（不乘 K）→ 每面对 `z=NEAR_MM` 裁剪、交点线性插值 → 裁剪后 <3 顶点整面丢弃 → 存活顶点乘 K 投影。

**验收标准与证据：**
- 生产实物复现→修复：curtain 画幅内覆盖 **92.05% → 1.66%**；餐桌由 **0% 可见** 恢复到 **1.46% 完整可见** ✅
- **byte-safe**：对照 `git worktree` 检出的**真 main 代码**，生产 75 件逐件比对 `repr`：64 件逐字节等价，11 件有差异且**每件都确有顶点 `z < NEAR_MM`**（真跨相机平面，非误裁）✅
- 生产真实矩阵（5 照片 × 6 方案 = 30 组合）：仅 **2/30** 投影变化，变化件均为 `['curtain']` ✅
- `footprint_mask` 同步受益：15 房间中仅 3 个病灶房 mask 改变，其余 12 房 hash 完全相同 ✅
- 阈值 `NEAR_MM=10.0` 处于**极宽平台区**：受影响件 minDepth 在 -132~-4338mm，取 1mm 或 50mm 被裁集合**完全相同** ✅

### F002：调色板扩容 + 撞色断言不静默 + 跳过 `entry_door` / 无 `en` 件（P1）

**Executor：** generator ｜ **判定：PASS**

**文件：** `apps/api/aigc/perspective.py`、`apps/api/main.py`（修改）

**改动：** `ANNO_PALETTE` 8 → **14 色**（前 8 色顺序/取值冻结）；去掉静默 `% len()` 回绕，耗尽即 `raise`；legend 单射显式断言；`ANNO_SKIP_TYPES` 纳入 `entry_door`；`_geometry_lock_prompt` 不把无 `en` 的原始标识符写进英文 prompt。

**验收标准与证据：**
- (a) ≥14 色且**视觉可区分**：两两 **ΔE(CIE76, Lab) 最小 = 28.03**，全部 91 对 ≥28 —— 远离 ΔE<10 的相近色区（Generator 自测只断言「RGB 元组唯一」，唯一≠可区分，此项为 Evaluator 独立补测）✅
- (b) 耗尽抛错不静默回绕 ✅ (c) legend 单射断言 ✅ (d) `entry_door` 不进盒 ✅ (e) prompt 无标识符泄漏（48/48 catalog 类型均有 `en`）✅
- 生产 30 组合全跑：legend **30/30 单射**，重复色 0，抛错 0；修复前 **4/30** 会撞色 ✅
- **回归风险核查**（耗尽即硬阻断会否打断存量方案）：生产全部 6 方案 × 全部房间，最大 distinct 类型数 = **8**，超 14 色房间数 **0** → 无耗尽回归风险 ✅

### F003：引导图健全性前置门禁（防呆，堵静默失败面）

**Executor：** generator ｜ **判定：PASS**（经 2 轮 fix 闭合）

**文件：** `apps/api/aigc/perspective.py`、`apps/api/main.py`（修改）、`apps/api/tests/test_perspective.py`、`apps/api/tests/test_render_real_geometry.py`（测试）

**改动：** 送 AI 前做确定性输入侧校验（不调 AI、不花钱，实测 **7ms**）：任一单盒**画幅内实际覆盖率** > `GUIDE_SINGLE_BOX_MAX_FRAME_FRAC=0.9` / legend 重复色 / `drawn==0` → 阻断并给可操作提示；接入 `_render_real_geometry_lock`（`annotate_boxes` 之后、调 AI 之前），code 登记进 `_INPUT_GATE_CODES_409` → 映射 409。

**验收标准与证据：**
- 拦截有效：生产病灶引导图**必被拦**（92% 覆盖）✅；反证不误拦：生产 **30/30 全部放行**（最大合法覆盖仅 4.36%，距阈值余量 85.6pp）✅
- 门禁位于预扣预算的 `except` 段内，`_budget.release(house)` 退预扣 ✅
- **409 接线**（首轮 PARTIAL → fix_round1 闭合）：Evaluator **不采信 Generator 的 stub**，另写对抗用例（不 stub 门禁，解出真能罩死画幅的家具触发**真门禁**）端到端实证：HTTP **409** + `code` 可读 + 载荷未被字符串化 + `error` 非嵌套裸 JSON + **provider 未被调**（`relay.calls==0 and fal.calls==0`）+ 不被布局门禁抢先 ✅。全仓穷举 raise 载荷 code：`LAYOUT_NOT_READY`→400 / `STALE_CALIBRATION`→409 / `DEGENERATE_GUIDE`→409 三个**全有归宿，无孤儿** ✅
- **阈值边界用例**（首轮 PARTIAL → fix_round1 闭合）：实测该盒覆盖 **81.79%**（注释宣称 ~82% 属实），`0.90 放行 / 0.80 拦下` **两侧夹逼**；模拟阈值改 0.70~0.99 **全会变红**（靠 `assert == 0.9`）→ **阈值真承重** ✅
- **R4 测试侧缺陷**（复验 1 发现 → fix_round2 闭合）：见下节

---

## R4 闭合记录（本轮唯一改动，测试侧）

**缺陷（复验 1 发现，fix_round1 引入）：** `test_render_real_passes_when_guide_is_sane` 断言 200 后未 `_wait` 排空后台 job → monkeypatch 拆除后 `main.DATA_DIR` 复原成**真实仓库目录** → job 线程把 `renders.json` 写进 **git-tracked 的 `data/projects/`**（违反 CLAUDE.md 红线「e2e never writes `data/projects`」精神；仓库现存 stash「本地测试残留 renders.json」证明**已真实咬过人**）；同理未 stub 的真 `acceptance` 在泄漏线程里跑 = 2 条 `RankWarning` 来源。

**修复（`6ac7afd`，+6 行，产品代码零改动）：** 补 `job = _wait(c, r.json()["job_id"])` + `assert job["status"] == "done"`（即该文件自身 7/7 既有 200-path 的既有约定）。

**复验 2 独立验证（四问四答）：**

| 问 | 结论 | 证据 |
|---|---|---|
| 污染是否止住 | **是** | 全套 + 单跑：`4f53cda18c2b` → `4f53cda18c2b` 不变，整树 hash 不变，`git status` 全干净。**关键：另建阳性对照** —— `git worktree` 检出 buggy `f10c2dc` 同命令跑 → sha `4f53cda18c2b`→`c87679ce31fc` **污染复现**、` M` 脏 ⇒ **检测非盲，差分归因明确** |
| warning 是否归零 | **是** | 334 passed，全量 stdout+stderr 捕获中 `warning` 出现 **0** 次。**订正一条检测陷阱**：这 2 条 RankWarning **不进 pytest `warnings summary`**（泄漏线程在 session 结束**之后**才跑到 polyfit，超出捕获窗口，实测为会后裸 stderr）→ 只看 summary **会漏报**，必须合并 stderr 全量 grep |
| 线程泄漏是真消除还是被 `_wait` 掩盖时序 | **真消除，结构保证** | `jobs.py:65` `result = fn()` **返回后**才 `_set(status="done")`；`main.py:2617` `_generate` **最后一句正是落盘**且 `DATA_DIR` **调用时**读全局 ⇒ `_wait` 返回 ⟹ 落盘已完成于 monkeypatch 仍在时。对抗实证：人为拖慢落盘 0.6s → `t_write_done <= t_wait_return`（差 0.018s）、落盘 `DATA_DIR` **在 tmp 沙箱内** |
| 反证是否真验到「放行→出图链路正常」 | **是** | provider **真被调用**（relay 1）、`mode=real-photo`、`method=geometry-lock`、**`furniture_locked=6`**，与 docstring 语义一致。**附带增益**：把 F003 acceptance 的「反证门没关死」一条**从形同虚设变为真承重**（修前即使出图链路完全打断该测试照样绿） |

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| `calibrate()` 标定算法本身 | spec §5 明文排除。本案标定并非「错」，是相机贴近窗帘致盒越过相机平面，属投影实现缺陷 |
| `aigc/perspective.py`（fix_round1/2） | 自首轮 PASS 判定起**逐字未变** → F001/F002 实现不可能回归 |
| 产品代码（fix_round2 全轮） | **零改动**（`git diff --name-only f10c2dc..HEAD -- <所有产品路径>` 为空）；本轮仅动 1 个测试文件 + 2 个状态机 JSON |
| 前端 `studioApi.ts` | 409 + `code` 已可结构化读取；本批不改前端展示 |

---

## 预期影响

| 项目 | 改动前 | 改动后 |
|---|---|---|
| curtain 盒画幅内覆盖（生产实物） | **92.05%**（糊死全画幅） | **1.66%**（真实可见区） |
| 餐桌盒最终可见面积（决定 AI 收到什么） | **0.00%**（被完全埋掉） | **1.46%**（完整可见） |
| 合成后画面构成 | curtain 88.23% / 空 7.95% / media 3.82% | 空 85.09% / sofa 5.25% / media 3.82% / curtain 1.66% / **dining_table 1.46%** / … |
| legend 重复色（生产 30 组合） | **4/30 撞色**（purple = 餐桌 + 绿植） | **0/30**，30/30 单射 |
| `entry_door` | 进彩盒 + 原始标识符漏进英文 prompt | 按结构件跳过，prompt 无泄漏 |
| 调色板 | 8 色 + 静默回绕 | 14 色（前 8 冻结）+ 耗尽即 raise |
| 引导图退化 | **静默出错图**（auto_check 0.967 通过） | **409 阻断** + 可操作提示，provider 未被调（不烧预算） |
| 全套测试污染 git-tracked data | fix_round1 会污染 + 2 RankWarning | **零污染 + 零 warning** |

---

## 类型检查 / CI

```
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
→ 154 passed, 0 skipped   (rsvg-convert 存在 → golden 快照 5 条实跑, 非 skip)

PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
→ 334 passed, 0 skipped, 全量 stdout+stderr 中 warning 计数 = 0

焦点: test_perspective.py + test_render_real_geometry.py → 61 passed
ruff check apps/api/tests/test_render_real_geometry.py → All checks passed!
ruff: main.py I001 = 既有噪声(HEAD 与 main 同报, 本批零 import 行改动), 不计入
```

> CI 只跑 Playwright smoke，**不跑 pytest**（CLAUDE.md）→ 以上本地实跑即唯一防线，已全绿。
> **注意（本项目覆盖 harness 默认）：push `main` = 部署生产**。本批走 branch `fix/render-guide-degeneracy` → PR → squash-merge，**部署由用户手动决定**。

---

## L2 实测记录

| 项 | 证据 |
|---|---|
| Staging git_sha == main HEAD | **N/A** —— 本项目无 staging；生产由用户手动部署（push main = 部署生产） |
| 端到端流验证 | **[L2] 未执行** —— 真实 AI 出图需 `OPENAI_API_KEY` + 用户授权 + 计费。按 **spec §5** 与 **decor-b2 同降级口径**：走确定性几何 + 引导图重生**目检**（`scratchpad/indep/guide_BEFORE_main.png` / `guide_AFTER_head.png`：修前=全画幅品红+右下绿块，与生产 real-base 逐像素吻合；修后=房间清晰可辨、紫色餐桌盒清晰可读、8 类盒均可区分） |
| 关键 invariant | 门禁不调 AI 不花钱（实测 7ms，`relay.calls==0 and fal.calls==0`）✅；byte-safe 对照真 main 代码成立 ✅；生产 30 组合 legend 单射 ✅ |
| 浏览器手动验 | N/A（本批无 UI 改动） |

> **未验证残留（上线后须人工确认）：修复后引导图的「模型实际响应」未经验证** —— 几何与引导图已确定性证明正确，但 AI 是否据此把餐桌画对，只能在真实出图后目检。**建议用户部署后人工目检首张实拍图**（这正是用户原始报障的验证闭环）。

---

## Ops 副作用记录

**本批次无数据库 ops**（项目为文件存储，无 DB）。

**数据副作用记录（Evaluator）：** 验收过程中 `data/projects/D/schemes/default/renders.json` 曾被 fix_round1 的泄漏线程污染（历史残留 + 复验 1 实测所致），已由 Generator `git checkout` 复位。**复验 2 全程主仓工作树保持干净**：阳性对照在 `git worktree`（scratchpad 内）执行，污染只落 worktree，实测主仓 sha 与 `git status` 全程未动，worktree 已 `git worktree remove --force` 清理。Evaluator 临时脚本全部写在 scratchpad，**未入库**。

---

## Harness 说明

本批改动经 Harness 状态机完整流程（planning → building → verifying → fixing → reverifying → fixing → reverifying → done）交付，`fix_rounds=2`。
`progress.json` 已设为 `status: "done"`，signoff 路径已填入 `docs.signoff`。
三轮验收（首轮 / 复验 1 / 复验 2）均在**隔离 evaluator subagent（fresh context）** 中执行，结论原样落盘，未经主上下文改写（harness-rules.md 铁律 12）。

---

## Soft-watch（不阻塞 done，需后续跟进）

| ID | 描述 | 风险等级 | 建议处置 |
|---|---|---|---|
| **S1** | `_geometry_lock_prompt` 对无 `en` 的 legend 条目静默 `continue` → 盒照画、prompt 只字不提，且 F003 门禁不检查此项 = 静默面。**今天不可达**（非 catalog 类型全集 == `ANNO_SKIP_TYPES`，48/48 catalog 有 `en`），但该不变量**无任何测试守护** | low（今天不可达） | 无 `en` 时改 `raise`（与 D2「描述不了就拒绝出图」同精神），或补一条 catalog `en` 完整性测试。入 backlog |
| **S2** | 最紧色对 `cyan`/`teal` ΔE=28.03、`blue`/`navy` ΔE=32.61，且**色名语言上也相邻**（模型靠色名映射，语义区分度弱于视觉）。仅单房 ≥9 类时才用到（当前生产最大 8 类，不可达） | low（今天不可达） | 若将来真出现 9+ 类房间，优先复核这两对。入 backlog |
| **S3** | `_INPUT_GATE_CODES_409` 仍是**人工登记表**，注释「新增门禁 code 必须登记」= 写给人看的纪律；raise 点与映射点仍是两处，无机制强制一致 → 新写带 code 的 raise 照样能静默落 500 | medium | `InputGateError(ValueError)` 让 code 与状态码**同生**（`except InputGateError as e: return JSONResponse(e.status, e.payload)`），使「新增门禁忘登记」在语法上不可能。**已由编排者采纳为 backlog 候选** |
| **S4**（复验 2 新增） | `_wait` 约定是**知情自律非机制强制**：`client_fal` fixture 用 `return` 而非 `yield`，**无 teardown 排空钩子**。全仓穷举确认该 bug 类**今天已关闭**（所有 async 测试点 100% 配对 `_wait`），但将来新写一条 POST async 端点却忘 `_wait` 的测试，照样能绿并静默写穿 `data/projects`。**与 S3 同构**（都是「往后挪一格」而非机制化） | medium | fixture 改 `yield` + teardown 排空在途 job（或断言无在途 job）→ 把该 bug 类从「约定」升级为「结构上不可能」。入 backlog |
| **S5**（复验 2 新增） | `_wait(t=10.0)` 超时 → `raise AssertionError("job 超时")`，此时线程仍在跑且 teardown 仍发生 → 理论上仍可污染。故 `_wait` 语义是「把静默污染转成**响亮红灯**」+ 窗口收敛到 10s，非语法禁止竞态。**非本批引入**（8/8 一致的既有约定），不构成回归 | low | 与 S4 同解（fixture teardown 排空）。随 S4 一并处理 |
| **S6**（超范围，**HIGH**，已报用户单独立批） | `calibrate()` 世界 z 轴符号**未被约束** → 生产 5 份标定中 **3 份 z 朝下**，家具引导盒被向**地下**拉伸（`wall_art` 本应挂墙 1.0~1.4m，实测画在地板上；prompt 里恰有一句人工补丁 "not a freestanding object on the floor" 在对冲此错）。标定两个 anchors 均在 z=0 平面 → 无任何约束能钉住「上」是哪侧 | **high** | **非本批引入**（main 同样如此）且 spec §5 明文排除 → 不计入本批判定。**与用户原始报障同源**：本批修掉的两 bug 足以解释该次事故（餐桌 0% 可见），修后 footprint 引导已恢复，但**垂直体积引导对 3/5 照片仍是错的**。**已由编排者采纳报用户单独立批** |
| **S7** | `box_usability` 硬编码底面 `z=0.0`，`_box_polys` 用 `_item_z0_mm(item)` → 对 `wall_art`/`curtain` 这类 `z0≠0` 的件，「判的盒」与「画的盒」不是同一个（这解释了 spec 记载 `minDepth=-55` 与实测 `-132.0` 的差异）。既有跨层不一致，非本批引入，不影响本批结论 | low | 记账。可与 S6 同批处理 |

---

## Framework Learnings

### 新规律

- **「跑完没脏」不足以证明修复有效 —— 验证「污染已止住」类结论必须先建阳性对照。** 否则「没检测到」与「检测方法失明」不可区分。本轮用 `git worktree` 检出 buggy commit、跑**同一条命令**确认污染**能**复现，才使 HEAD 的「未复现」具备证据力，并把归因锁定到那一行修复（而非环境偶然）。
  - 来源：render-fix-b1 复验 2 / R4
  - 建议写入：`framework/patterns/testing-env-patterns.md`（新增「污染/泄漏类修复的阳性对照要求」）

- **判断「等待是排空还是掩盖时序」，看的是产品代码的偏序，不是等待时长。** `_wait` 之所以是真排空，是因为 `jobs._run` 严格「先 `fn()` 跑完、后置 `status=done`」，而 `fn()` 的最后一句正是落盘 ⇒ 等到 done 必然等到写完。判据应是**读出这条偏序**（+ 人为拖慢关键段撑开窗口来实证），而非「等 10s 大概够了」。
  - 来源：render-fix-b1 复验 2 / R4-③
  - 建议写入：`framework/patterns/testing-env-patterns.md` §14（fire-and-forget race 段落补「排空 vs 掩盖」判据）

### 新坑

- **后台线程在 pytest session 结束后才抛的 warning，不会进 pytest 的 `warnings summary`。** 本案 2 条 `RankWarning` 是泄漏线程在 teardown **之后**跑到 `np.polyfit` 才冒出的**裸 stderr**，早已超出警告插件捕获窗口 → 用「warnings summary 是否为空」验此类项**会漏报**。正解：合并重定向 stdout+stderr 后全量 grep。
  - 来源：render-fix-b1 复验 2 / R4-②
  - 建议写入：`framework/patterns/testing-env-patterns.md`（§14 邻近）

- **monkeypatch 沙箱 + fire-and-forget 后台 job = 沙箱写穿。** 测试函数一返回 monkeypatch 立即拆除，`DATA_DIR` / provider 工厂 / stub 全部复原成真实值，而后台线程仍在跑 → 落盘写进 git-tracked 目录，甚至可能在有 key 的机器上发起**真实计费调用**。凡「同步返回 job_id + 后台落盘」的端点，测试必须排空后台 job 再返回；更稳的做法是 fixture 层 `yield` + teardown 排空（本案是 8/8 靠人工约定，属知情自律）。
  - 来源：render-fix-b1 fix_round1 引入 → 复验 1 发现（R4）→ fix_round2 闭合
  - 建议写入：`framework/README.md` §经验教训 + `framework/patterns/testing-env-patterns.md`

- **修一个跨层一致性 bug 的批次，自己引入了同类（更轻的）跨层缺口。** 本批病灶是「守卫在一处存在、兄弟点不知情」（`box_usability` 检测到退化但 `annotate_boxes` 照画），而 fix_round1 又引入 `DEGENERATE_GUIDE` raise 带 code、except 段不认识 → 落 500。说明该模式**极易复发**，`cross-layer-consistency.md` 应加一条自查：「新增 raise/信号时，是否所有消费点都被机制（而非纪律）保证认识它？」
  - 来源：render-fix-b1 首轮 §5.4 + 复验 1 R1.1
  - 建议写入：`framework/patterns/cross-layer-consistency.md`

- **「集合式修法」是把知情自律往后挪一格，不等于机制化关死。** `_INPUT_GATE_CODES_409` 从散落 `if` 收敛为单一命名锚点（客观改进：新增码从「加分支」降为「加一个 token」），但仍是人工登记表。真正机制化需让**不变量在语法上不可违反**（如 `InputGateError` 让 code 与状态码同生）。验收时应显式区分这两档，避免把「更整洁的自律」误记为「已机制化」。
  - 来源：render-fix-b1 复验 1 R1.1（S3）/ 复验 2 V6（S4）
  - 建议写入：`framework/harness/evaluator.md` 或 `framework/patterns/cross-layer-consistency.md`

### 模板修订

- 本批次无模板修订提案。
