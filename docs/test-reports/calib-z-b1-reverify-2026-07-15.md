# calib-z-b1 — 复验报告（reverifying, fix-round 1）

> **Evaluator：** local/evaluator-subagent（fresh context，未继承实现/首轮验收的任何对话）
> **日期：** 2026-07-15
> **分支：** `calib-z-b1`（未推 main = 未部署）
> **被验 commit：** `ddb5363`(R1 修) → `f9ee326`(fix-round 1) → `916119e`；对照基线 `307fb5e`
> **依据：** 修订后 `docs/specs/calib-z-b1-spec.md` §6 + `features.json` F003 acceptance + 首轮 3 条阻断项
> **结论：** **PASS → 可进 done；可上线（须按顺序铁律执行）**

---

## 0. 结论速览

| # | 项 | 首轮 | 本轮 |
|---|---|---|---|
| **R1** | F002 commit 夹带越界 `data/projects` 变更 | ❌ BLOCKING | ✅ **CLOSED** — 净 diff 空；**成因已被我定性确证（非活泄漏）**，且比 fix commit 自己的说法更强 |
| **R4** | `1537e` 无定论 → 排除 2 条 / 自愈 9 条 | ❌ 需拍板 | ✅ **CLOSED** — 生产副本实测 healed 9 / excluded 2；排除项逐字节原样；3 条新测试经变异对照证明承重 |
| **R5** | 下游误报口径不得写"已消除" | ❌ BLOCKING | ✅ **CLOSED** — spec §6.6 + F003 acceptance 已改实测结论；全仓扫描零残留 |
| **R2** | "7 条 z 朝下"须标明按存量值计 | 非阻断 | ✅ 已补 spec §2.1，**我独立复现属实** |
| **R3** | `dabcb`/`1537e` 是水平镜像非 z 翻转 | 非阻断 | ✅ 已补 spec §2.3，**我独立复现属实** |
| — | 回归（两套 pytest + golden + 417ae + 合成真值） | — | ✅ **PASS** |
| 7 | [L2] 真实 AI 出图 | ⏸ | ⏸ **[L2] 未执行**（无 key + 需计费授权） |

**F002 的 `status` 仍为 `pending`（fix-round 1 未回填）→ 进 done 前须由 Planner/Generator 修正为 `completed`、`completed_features` 2→3。这是状态机卫生，不是产品缺陷，不阻断本轮判定。**

---

## 1. 取证独立性

| 项 | 做法 |
|---|---|
| 生产数据 | **自行** `scp` 取回 `deploysvr` 的 `photos_{v1,v6,v7}.json` + `geometry.json`；本地 sha256 与**生产端 `sha256sum` 逐字节一致**（只读，全程未写生产） |
| fixture 真伪 | **未默认可信** → 从我自己的生产副本**重新推导** 11 条标定，与 `apps/api/tests/fixtures/prod_calibrations.json` 逐字段比对 → **11/11 MATCH，无遗漏、无夹带** |
| 修前/修后对照 | `git worktree` 检出 `307fb5e`，把 pre-fix / post-fix `perspective.py` 作为两个独立模块**同时加载**对跑 |
| 合成真值 | **第三次独立构造**（既不复用审计的、也不复用首轮 Evaluator 的）：位姿 yaw 207°/pitch −11°/`C=(6200,4100,1650)`，全程**不强加 det** |
| 迁移脚本 | 在 **`/tmp` 的生产副本**上跑 dry-run / `--apply` / 幂等 / `.bak` 回退；**未对生产执行 `--apply`** |
| 新测试是否空转 | **变异阳性对照**（见 §3.3），非"跑绿即算数" |

---

## 2. R1 — 越界 `data/projects` 变更：CLOSED，且成因已定性确证

### 2.1 文件层面已闭合

```
git diff 307fb5e...HEAD -- data/projects/     -> 空
git status --short data/projects/             -> 干净
HEAD:data/projects/D/schemes/default/renders.json  = blob 0637a08 = 基线值 []
```

### 2.2 成因：**不是活泄漏 —— 是 2026-07-11 的旧 stash 被中途恢复进工作区**

编排者要求我独立判断"是否可能是尚未复现的活泄漏（参考 render-fix-b1 R4 的 monkeypatch + 后台 job 竞态）"，并指出 fix commit 自陈的矛盾：**会话启动 git status 为 clean，与"工作区早已脏"对不上**。

**我找到了那个矛盾的解，它指向"非活泄漏"，且比 fix commit 的论证强一个数量级。**

关键证据 —— 一个 **unreachable 的 stash commit**：

```
740e4a8  2026-07-11 03:27:11 -0700  "On main: 本地测试残留 renders.json (待用户决定去留)"
  └─ data/projects/D/schemes/default/renders.json = blob 862b457337e78a43375fdd2944f56b76225e42c9

910ad7d  2026-07-15 02:22:37 -0700  "feat(calib-z-b1-F002): ..."（夹带）
  └─ data/projects/D/schemes/default/renders.json = blob 862b457337e78a43375fdd2944f56b76225e42c9
                                                          ^^^^^^^ 同一个 blob，逐字节相同
```

**时间线（全部可独立复核）：**

| 时刻 | 事实 | 来源 |
|---|---|---|
| 2026-07-11 03:27:11 | stash `740e4a8`「本地测试残留 renders.json (**待用户决定去留**)」创建，内含 blob `862b457` | `git log 740e4a8` |
| 2026-07-15 00:50:38 | render-fix-b1 signoff（`6e0f203`）白纸黑字写「**仓库现存 stash「本地测试残留 renders.json」**」→ 此刻 stash **仍在**，工作区干净 | `git show 6e0f203:docs/test-reports/render-fix-b1-signoff-2026-07-15.md` |
| 2026-07-15 01:29–01:45 | calib-z-b1 开批 / 切分支；Generator 观察到 git status **clean** ✅ **与上一行完全自洽** | `git reflog` + `ddb5363` message |
| 2026-07-15 02:22:37 | `910ad7d` 提交，含 blob `862b457` = **那个 4 天前 stash 的内容** | `git show 910ad7d` |
| 现在 | `git stash list` **空**；`refs/stash` **不存在**；`740e4a8` **unreachable** | `git fsck --unreachable` |

**结论：stash 在 01:45–02:22 之间被 `pop`/`apply`（pop = apply + drop，正好解释 `refs/stash` 消失），把 07-11 的污染 renders.json 还原进工作区，随后被 `git add -A` 扫进 F002 commit。**

> 触发方式高度可疑地指向仓库既有的 ruff 工作流 —— `environment.md` / 本项目惯例里就有「**可 `git stash` 在基线复核** ruff 噪声」这一步。经典踩法：工作区干净时 `git stash` 是 no-op（"No local changes to save"），紧接着的 `git stash pop` 就会弹出**栈顶那个别人 4 天前的 stash**。

### 2.3 为什么这**排除**了活泄漏（结构性论证，不是"我跑了 5 次没看见"）

**活泄漏在结构上不可能产出这个 blob。** 泄漏是通过 API 写路径落盘的，`created_at` 必然戳**当次时间**；而夹带内容的两条记录是 `created_at = 2026-07-11T04:20:48Z / 02:17:37Z`，且与 4 天前的 stash blob **逐字节相同**（`862b457`）。一次 2026-07-15 的新写入不可能重建出 07-11 的字节。⇒ **内容只可能来自那个 stash，不可能来自本会话的泄漏。**

这一点很重要：fix commit 给的理由是「连跑 5 次全套测试无泄漏」—— 那是**证据不足式论证**，对竞态型泄漏（render-fix-b1 R4 正是竞态）本就不可靠，编排者的怀疑完全合理。**但结论碰巧是对的，只是理由不对。** 我用 blob 同一性给出了确定性论证。

**我的独立旁证（仍然做了）：** 跑完 356+154 全套后，`data/projects` 整树 sha256 `688de0a1707d2244…` **跑前跑后完全一致**，`git status` 干净。

### 2.4 对记录的订正（fix commit 的成因叙述有误，须以本报告为准）

| fix commit `ddb5363` 的说法 | 实况 |
|---|---|
| 「成因是 `git add -A` 扫入了工作区**既有脏文件**」 | ❌ **工作区在会话启动时确实是干净的**（它自己的观察是对的）。文件是**中途**被 stash 恢复弄脏的 |
| 「**陈旧的本地 API 运行残留**」 | ⚠️ 内容确实源自 07-11 的本地 dev 出图，但它当时**已被 stash 收走、工作区是干净的** —— 不是"一直脏着没人管" |
| 「诚实边界：git status clean 与『早已脏』对不上，**我未能复现弄脏它的操作**」 | ✅ 这个自陈是诚实且关键的。**该缺口现已关闭**：弄脏它的不是"操作写文件"，而是 `git stash pop` |

**净效果：R1 的处置（还原为 `[]`）正确且已生效；成因结论（非活泄漏）成立；成因的机理须按本节订正。**

### 2.5 附带影响（需告知用户，非阻断）

那个 stash 的标题是「待用户**决定去留**」—— 它现在**已被 drop 掉了**，用户那个悬而未决的决定被无声地替用户做了。内容并无价值（本地 dev 出图记录污染），且在 `git gc` 之前仍可由 `740e4a8` 恢复：

```bash
git show 740e4a8:data/projects/D/schemes/default/renders.json   # 仍可读回
```

---

## 3. R4 — 1537e 排除：CLOSED

### 3.1 范围确实收窄为「9 自愈 + 1537e×2 排除」（在**真实生产副本**上实测）

```
[migrate_calibration_z] DATA_DIR=/tmp/rv-calib/data  模式=DRY-RUN (不写任何文件)
  排除 (保持原样): 1537e6d83950
      D/v1   bcc615315c78    r_live      healed     -2427.1   +2427.1       0.0
      D/v6   bcc615315c78    r_live      healed     -2266.8   +2266.8       0.0
      D/v6   dabcb9513905  r_master      healed      +874.3    +874.3    1556.4
      D/v6   1537e6d83950   r_cloak    excluded
             └─ 按裁决明确排除, 保持原样 (自愈方向无法定论, 待重新标定)
      D/v6   417ae5589afe    r_live      healed     -1382.2   +1382.2       0.0
      D/v6   ae8e5b875fd9  r_garden      healed      -156.0    +156.0       0.0
      （v7 同 v6）
合计标定 11 条: {'healed': 9, 'excluded': 2}
```

### 3.2 逐条核对编排者要求的四点

| 要求 | 结论 | 证据 |
|---|---|---|
| 排除项**逐字节原样保留** | ✅ | 纯函数层：`deep-equal=True` 且 **`same-object=True`**（原样透传，非重建）；`--apply` 后在生产副本上：`v6/1537e6d8` `v7/1537e6d8` **byte-identical = True**；ground shift **精确 0.0000e+00 px** |
| 排除项**报出理由** | ✅ | `status="excluded"` + `reason="按裁决明确排除, 保持原样 (自愈方向无法定论, 待重新标定)"`，CLI 以 `└─` 单独打印，**非静默跳过** |
| 排除项**未被计入「已修好」** | ✅ | `new_camera_z = None`（它没被重算）；不进 `healed` 计数；不进 `camera_below_floor_after` 统计；不进 `ground_moved` |
| 排除**未连累其余 9 条**（尤其 `dabcb` 必须仍自愈） | ✅ | `healed=9`，**`dabcb` 仍自愈**（v6/v7 各一条，ground shift 1556.4 px，与批次自报数字精确一致）；9 条 `--apply` 后 **11/11 C_z>0、det=−1** |

**`--apply` 后逐 photo diff（生产副本）：** 只有 `calibration.camera` 一个键变化，**其余字段/其余照片零触碰**；未标定的照片（`7296858f`/`d24741d4`）原样。

**幂等 + 回退：** 二次 `--apply` → `{'unchanged': 9, 'excluded': 2}`、写入 0 个文件；`.bak` 与**原始生产文件 sha256 逐字节一致**（`aef1069671cabc7f5…` / `0dcbb1f0bf551e09c8…` / `7c339bf0957c4d1f74…`）⇒ 单步回退可用。

**dry-run 真的不写：** 跑完 3 个 `photos.json` 的 sha256 与 pristine 完全一致，且**未生成任何 `.bak`**。

### 3.3 3 条新测试**不是空转**（变异阳性对照）

编排者明确要求建阳性对照。我在隔离 worktree 里**保留函数签名、只摘除排除分支**（模拟"排除写了但没生效"），三条全部变红，且是**语义性断言失败**而非 `TypeError`：

```
FAILED test_excluded_photo_is_left_untouched_and_reported
FAILED test_exclusion_does_not_affect_other_calibrations
        AssertionError: 其余 9 条仍须自愈, 实得 {'healed': 11}   <- 排除失效时 11 条全被改
FAILED test_excluded_calibration_stays_physically_invalid_and_is_not_hidden
        AssertionError: assert None == 2   (counts 里没有 'excluded')
3 failed, 10 deselected
```

⇒ 这 3 条测试**承重**，锁的是排除**行为**而非签名。

### 3.4 我额外验证的一点：排除在生产**真的会生效吗**？

这是 spec / 首轮报告都没问的问题 —— 如果渲染时是**重新解算**而非读存量，那"排除"只保住 JSON、渲染照样变，排除就是自欺。**实测架构分离，排除有效：**

| 路径 | 代码 | 行为 |
|---|---|---|
| **写**（用户重新标定） | `main.py:953` `_calibration_camera(payload)` → `perspective.calibrate()` | 重新解算 |
| **读 / 渲染** | `main.py:2400` `perspective.Camera.from_dict(cal["camera"])` | **读存量 camera** |

⇒ 被排除的 `1537e` 存量 camera（det=+1、镜像解）会被渲染路径原样读取，**不会被静默重算覆盖**。排除真实有效。

**同时这也印证了「先部署代码、再跑迁移」顺序铁律的必要性**：写路径重解算 ⇒ 若迁移先跑、代码后部署，期间任何一次重新标定都会用旧 `calibrate()` 把数据写回带病值。

### 3.5 诚实边界（soft-watch，不阻断）

**"排除"保住的不是一个已知正确的值，而是一次抛硬币的结果。** 我独立复现：`1537e` 的生产存量 `C_z=+1515.1`，而**本机修复前重算同一份输入得 `C_z=−1515.1`** —— 同输入换机器即得相反面。所以"保持原样"≠"更安全"，只是"不动"。它与"自愈"两个候选**都未被证明正确**。真出路是 `BL-calib-min-3-anchors`（已升 `high`，含"重标衣帽间(1537e)"）。这一点 spec §2.5 已如实写明，判定无异议。

---

## 4. R5 — 误报口径：CLOSED

**spec §6.6** 已改为实测结论 + 口径铁律：

> 6. **下游 false alarm 是否消除** → **实测结论：未消除（Evaluator R5，2026-07-15）**。
> **口径铁律（任何文档/签收中不得违反）：** 只能表述为「盒几何已修正；误报由 20/111 降至 9/96；是否消除待 [L2] 复测」，**不得表述为已消除**。

**`features.json` F003 acceptance** 同步改为同一实测口径 ✅。

**全仓扫描（含 commit message / `.auto-memory/` / 报告 / spec / JSON）：**

```
git grep -E "误报(已)?消除|不再误报|消除了?误报|false alarm.*(eliminat|resolv|gone)"
git log 307fb5e..HEAD --format=%B | grep -E "已消除|不再误报"
grep -rn -E "已消除|不再误报" .auto-memory/
```

→ 关于本批的命中**全部是正确口径**（"未消除"/"不得表述为已消除"）。**零残留违规表述。**
（命中的 `decor-b3-fix` / `ops-cleanup-b1` / `前端组件审查清单.md` 中的"已消除"属**其他批次的其他事项**，与本项无关，不构成残留。）

---

## 5. R2 / R3 — 已如实补进 spec，且我独立复现属实

### R2（spec §2.1 口径注）✅

| 口径 | 实测 |
|---|---|
| 按**生产存量值**计 | **7/11** 相机在地板下（`bcc615`×3 / `417ae`×2 / `ae8e5`×2） |
| **本机重算修复前** | **9/11** —— 多出的正是 `1537e`×2（本机 −1515.1 vs 存量 +1515.1） |

⇒ spec 写的「7 条是按存量值计、本机重算得 9/11、该差异恰是抛硬币的独立复现」**完全属实**。这是该现象的**第三次独立复现**（审计 / 首轮 Evaluator / 我）。

### R3（spec §2.3 水平镜像非 z 翻转）✅ — 精确成立

| 条目 | `R_post = R_stored @ ?` | stored DOWN vs 重力 | post DOWN vs 重力 |
|---|---|---|---|
| `bcc615`×3 / `417ae`×2 / `ae8e5`×2 | **`diag(1,1,-1)` Z-FLIP** | **175.2°–179.1°**（"下"指向天花板，物理荒谬） | 0.86°–4.78° ✅ |
| `dabcb`×2 / `1537e`×2 | **`diag(1,-1,1)` Y-MIRROR** | **4.79° / 1.07°**（垂直本就正确） | 4.79° / 1.07°（**不变**） |

⇒ spec §2.3「这 4 条是世界 Y 轴水平镜像、不是 z 翻转、垂直本就正确、`C_z>0` 门对其非直接判据」**逐字成立**。§2.4（`dabcb` 已获视觉定论）/ §2.5（`1537e` 排除理据）表述与证据一致。

---

## 6. 回归

| 项 | 结论 | 证据 |
|---|---|---|
| **fix-round 1 影响面** | 产品代码仅 `calib_heal.py` **+11/−1** | `git diff --stat 93397a5..HEAD -- <产品路径>` |
| **F001 不可能回归** | `perspective.py` **自 `ca96b61`（首轮判 PASS 的那次）起逐字节未变** | `git diff ca96b61..HEAD -- apps/api/aigc/perspective.py` = 空 |
| **两套 pytest** | **356 + 154 全绿，0 skip** | 实跑 |
| **golden 真跑** | `test_render_snapshot.py` **5 条实际 PASSED**（`rsvg-convert` 在位，非 skipif 静默跳过） | 实跑 + `which rsvg-convert` |
| **合成真值控制（主反证）** | ✅ **我第三次独立构造复现** | `det(R_true) = −1.000000`（由物理导出，**从未强加 det**）；`PRE: det=+1, C_z=−1650, max|R−R_true|=1.963`；**`POST: det=−1, C=(6200,4100,+1650), max|R−R_true|=1.97e−14`** |
| **417ae 地面不变（餐桌保住）** | ✅ | 存量→自愈后 **9.66e−10 px**；本地 PRE→POST 重算 **0.0000e+00 px（精确零）** ⇒ render-fix-b1 已在生产确认的餐桌落位**完整保留** |
| **bcc615 / ae8e5 地面不变** | ✅ | `bcc615` 9.32e−10 px；`ae8e5` 9.39e−07 px（按 spec 探针）⇒ 均 ≤1e−6 |
| **无测试泄漏** | ✅ | `data/projects` 整树 sha256 跑前跑后一致（`688de0a1707d2244…`） |
| **ruff** | ✅ **零新增** | 本批文件 `All checks passed!`；全仓 **203 errors**，而基线 `307fb5e` **同样 203** ⇒ 是本机 ruff 版本噪声，非本批引入 |

---

## 7. [L2] 未执行

无 `OPENAI_API_KEY` + 需用户计费授权 → 按 decor-b2 / render-fix-b1 降级口径。**未执行，如实记 [L2]。**

**建议用户在部署 + 迁移后重新生成 1 张 v7 `r_live` 实拍图**，一次闭合三件事：
(a) 原始报障（餐桌位置）的最终确认；(b) §4 的误报是否随**修后引导图**消除；(c) 盒几何在真实出图链路上的目检。

---

## 8. 上线判断

**可上线 —— 但必须按顺序执行（顺序错会把数据写坏）：**

1. **PR squash-merge → 部署**（**必须最先**：写路径会重解算；迁移先跑的话，期间任何一次重新标定都会用旧 `calibrate()` 把数据写回带病值）
2. 生产 **dry-run** 核对：
   ```bash
   DATA_DIR=/opt/grandtianfu/data/projects python3 scripts/migrate_calibration_z.py \
       --exclude-photo 1537e6d839504230972de8a05ee98c8f
   ```
   预期报告：`{'healed': 9, 'excluded': 2}`，`相机在地板下方: 自愈前 7 条 -> 自愈后 0 条`，`dabcb` ×2 各 1556.4 px
3. 核对无误后加 `--apply`（`.bak` 已验证可单步回退）
4. [L2] 重新生成 1 张 v7 `r_live` 实拍图目检闭环

**授权边界：** 用户已授权「9 条自愈 + 排除 1537e」这一**范围**；本轮**未对生产执行任何写操作**（全部在 `/tmp` 副本）。

---

## 9. 进 done 前的状态机卫生（须 Planner/Generator 处理，非产品缺陷）

| # | 项 | 现状 | 要求 |
|---|---|---|---|
| H1 | `features.json` F002 `status` | **`pending`**（fix-round 1 只改了 acceptance/notes，未回填 status） | → `completed` |
| H2 | `progress.json.completed_features` | `2` | → `3` |
| H3 | `.auto-memory/project-status.md` | **陈旧**：仍写「calib-z-b1 planning 完成 → building（**未开工**）」、「生产实测 **3/5 反转**」、「F002 存量 **3 份**自愈」—— 后两个口径已被 F001 审计推翻（实为 11 条 / 7 条按存量值） | done 时覆盖写刷新 |

---

## 10. Soft-watch（不阻断）

| # | 项 |
|---|---|
| S1 | **`1537e` 的"排除"保住的是抛硬币的一面，不是已知正确值**（本机重算得相反面）。"不动" ≠ "安全"。真解 = `BL-calib-min-3-anchors`（已 high） |
| S2 | **`ae8e5`(r_garden) 标定质量本就不可用**（自愈后 `C_z=+156mm` = 相机离地 15.6cm，锚点 err 178px）。与本 bug 无关，维持 soft-watch |
| S3 | **CLI 对 excluded 行的「相机z(前)」留空** —— 运维看不到 `1537e` 存量值 `+1515.1`。理由行已明确打印，属信息性小缺口，非诚实性问题 |
| S4 | **迁移后生产将是混合手性**（9 条 det=−1 + 2 条 det=+1）。我已独立复核 spec §D2 的"下游零 det 依赖"主张**成立**：`cam.R` 全部用法只有 `R @ w + t`（`perspective.py:38/236/300`），`np.linalg.inv` 只作用于 `K`。⇒ 功能安全 |
| S5 | **那个「待用户决定去留」的 stash 已被 drop**（见 §2.5），用户的待决事项被无声代办；内容无价值且 `740e4a8` 仍可恢复 |

---

## 11. 未采信 / 独立重跑清单（可审计）

| 被主张 | 我的处理 |
|---|---|
| 首轮报告「fixture 与生产一致」 | **未默认可信** → 自取生产 + 逐字段重推 → **11/11 MATCH，无夹带无遗漏** |
| 首轮「F001 PASS，别推翻它」 | **未采信** → 第三次独立构造合成真值（不强加 det）→ 独立复现 `det(R_true)=−1` 与精确还原 |
| fix commit「非活泄漏（连跑 5 次无泄漏）」 | **结论对，理由弱** → 我用 **blob 同一性**给出确定性论证（§2.3） |
| fix commit「工作区早已脏被 `git add -A` 扫入」 | **证伪** → 工作区启动时确实干净；实为 07-11 stash 中途被 pop（§2.4） |
| fix commit「healed 9 / excluded 2」 | **未复用其测试** → 在**真实生产副本**上跑脚本 → 复现 |
| commit「3 条新测试锁住排除」 | **建变异阳性对照** → 摘除排除分支后 3 条全红（语义失败）→ 承重属实 |
| spec §2.1「7 条按存量值 / 本机 9/11」 | 独立复现 → 属实 |
| spec §2.3「`diag(1,-1,1)` 水平镜像」 | 独立复现 → **精确成立**（1e−6 内） |
| commit「356+154 全绿 0 skip / ruff clean」 | 自跑复现；并额外验 golden **非 skipif** + ruff 203 == 基线 203 |
| 「排除在生产会生效」 | **spec/首轮都没问** → 我独立追读写路径分离 → 有效（§3.4） |

---

## 12. 证据留存

- 生产只读副本 + 迁移副本：`/tmp/rv-calib/`（`prod/` 原件 + `data/` 迁移后 + `.bak`）
- 复验脚本：`scratchpad/verify_fixture.py`（fixture 真伪）/ `reverify.py`（排除语义）/ `f001_check.py`（合成真值 + 地面不变）/ `coinflip.py`（stored vs pre vs post）/ `r3_check.py`（R2/R3 复核）/ `mutate.py`（变异阳性对照）
- **未修改任何产品代码；未对生产执行任何写操作；未把 PIPL 敏感照片入库。**
