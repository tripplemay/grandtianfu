# calib-z-b1 Signoff 2026-07-15

> 状态：**已签收 — PASS**（隔离 Evaluator 复验，fix-round 1）
> 触发：标定世界 z 轴符号未约束 → 家具盒朝地下拉伸、贴墙件画在地板 → `auto_check` 持续误报
> 完整证据见 **`docs/test-reports/calib-z-b1-reverify-2026-07-15.md`**（本文件为签收摘要，不重复其证据）
> 首轮报告：`docs/test-reports/calib-z-b1-verifying-2026-07-15.md`（PARTIAL）

---

## 变更背景

`calibrate()` 的旋转矩阵 z 列写作 `+cross(x, y)`，**强制 det(R)=+1**；而世界系 `(X=东, Y=南, Z=上)` 是**左手系**（East×South=Down）、相机系 `(右,下,前)` 是右手系 ⇒ **物理正确的 R 必然 det=−1**。于是 x/y 拟合正确时 z 列被**系统性取反**。

加之两条打分约束**全部只用地面锚点**（生产 11/11 锚点 z 全为 0 ⇒ z 列恒乘 0、对打分零贡献），2 锚点时两候选重投影误差**精确平局**（相对差 1e−13~1e−16）⇒ **z 朝上朝下由浮点噪声抛硬币**（铁证：同输入换机器重算即得相反 z —— 本批已被**三方独立复现**）。

生产 11 条实证：**7 条**相机解在地板下方（按存量值计）+ **4 条** z 朝上但**平面被镜像**。与用户原始报障（餐桌位置错）同源；render-fix-b1 已修好平面 footprint，**本批只治垂直维度**。

---

## 变更功能清单

### F001：`calibrate()` 用物理约束定 z 方向（根治）

**Executor：** generator ｜ **commit：** `ca96b61` ｜ **验收：** ✅ PASS（首轮判定，复验确认 `perspective.py` 自那时起**逐字节未变** ⇒ 不可能回归）

**文件：** `apps/api/aigc/perspective.py`（修改）、`apps/api/tests/test_perspective.py`（新增用例）

**改动（两处，缺一不可）：**
1. 构造式改 `R = column_stack([sx·ex, sy·ey, -cross(sx·ex, sy·ey)])` —— 尊重左手性，det(R)=−1
2. 候选筛选加同级硬约束 `float((-R.T @ t)[2]) > 0`（相机必须在地板上方 —— 地面锚点给不了、物理必然成立）；4 候选全排除时明确 `raise`

**验收标准与结果：**
- 合成真值控制（**主反证，不依赖生产歧义**）：Evaluator **第三次独立构造**（不复用审计/首轮脚本，不强加 det）→ `det(R_true)=−1.000000`；`PRE: C_z=−1650, max|R−R_true|=1.963` → **`POST: C=(6200,4100,+1650), max|R−R_true|=1.97e−14`** ✅
- 生产 11/11 `C_z>0` + **门后存活候选唯一**（抛硬币根因根除）+ R 精确正交 ✅
- `417ae`/`bcc615`/`ae8e5` 地面投影不变（≤1e−6 px；`417ae` 本地 PRE→POST **精确 0**）⇒ render-fix-b1 餐桌保住 ✅

### F002：存量标定自愈迁移（9 条自愈 + `1537e`×2 排除）

**Executor：** generator ｜ **commit：** `910ad7d` → `ddb5363`(R1) → `f9ee326`(R4/R5) ｜ **验收：** ✅ PASS

**文件：** `apps/api/aigc/calib_heal.py`（新增，纯函数无 I/O）、`apps/api/scripts/migrate_calibration_z.py`（新增，薄 CLI，**默认 dry-run**）、`apps/api/tests/test_calib_heal.py`（新增 13 条）

**改动：** 标定载荷完整保留原始输入 ⇒ 修好 F001 后**重跑即可导出正确 camera，无需用户重新标定**。`--exclude-photo` 支持把"自愈方向无法定论"的标定明确排除、原样保留并报出理由。

**验收标准与结果（在**真实生产只读副本**上实测）：**
- `{'healed': 9, 'excluded': 2}`；9 条自愈后 **11/11 C_z>0、det=−1** ✅
- 排除项 `1537e`×2 **逐字节原样**（deep-equal + same-object；`--apply` 后 byte-identical；ground shift 精确 0）✅
- 排除项**报出理由**、`new_camera_z=None`、**不计入"已修好"** ✅
- **未连累其余 9 条**：`dabcb` 仍自愈（1556.4 px，与自报数字精确一致）✅
- dry-run 真的不写（sha256 不变、无 `.bak`）；`--apply` 幂等（二次 → 0 写入）；`.bak` 与原始生产**逐字节一致** ⇒ 单步回退可用 ✅
- 自愈后不被判 stale（`binding` 指纹不含 camera）✅

### F003：生产实物几何对抗验收

**Executor：** evaluator ｜ **交付物：** 首轮 `calib-z-b1-verifying-2026-07-15.md` + 复验 `calib-z-b1-reverify-2026-07-15.md`

**结果：** §1–§5、§5b 全部 PASS（`1537e` 经用户裁决改为**排除**，缺口以 `BL-calib-min-3-anchors` 承接）；**§6 下游误报：未消除**（如实记录，见下）；§7 [L2] 未执行。

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| `_box_polys` / `annotate_boxes` / `footprint_mask` / 调色板 | spec §7 明文排除（render-fix-b1 刚验收过），**零触碰** |
| `evaluate_geometry_lock` 判据 | spec §7 明文不改；若根因在验收器本身，另立批 |
| `perspective.py`（fix-round 1 全轮） | 自 `ca96b61` 起**逐字节未变** ⇒ F001 不可能回归 |
| 生产数据 | 本轮**未执行任何写操作**，全部在 `/tmp` 副本上验证 |
| `1537e`（衣帽间）×2 标定 | 自愈方向无法定论 → **明确排除、保持原样**（spec §2.5） |

---

## 预期影响

| 项目 | 改动前 | 改动后 |
|---|---|---|
| 生产标定相机在地板下方 | **7 条**（按存量值） | **0 条** |
| `det(R)` | ≡ +1.000（**病症本身**） | −1.000（9 条自愈）／+1.000（2 条排除） |
| 2 锚点时 z 方向 | 浮点噪声**抛硬币** | 物理门后**候选唯一**、完全确定 |
| `dabcb`(主卧) 地面投影 | 画到阳台外、相机在建筑外 3294mm（**物理不可能**） | 纠正，移动 1556.4 px（已获真实照片视觉定论） |
| `417ae` 地面投影（餐桌） | — | **9.66e−10 px（不变）** ⇒ render-fix-b1 修复保住 |
| 下游 `auto_check` 误报 | `ok:false 0.85`，新边缘坏块 **20/111** | 仍 `ok:false 0.85`，坏块 **9/96** ⇒ **减半但门未过** |

> **口径铁律（spec §6.6，不得违反）：** 只能表述为「**盒几何已修正；误报由 20/111 降至 9/96；是否消除待 [L2] 复测**」，**不得表述为已消除**。
> 诚实边界：该 `out_png` 是模型**看着修复前的错引导图**生成的 —— 要判定误报是否真消除，必须用**修复后的引导图**重出一张 = [L2]。

---

## 类型检查 / CI

```
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q
    -> 356 passed in 16.65s          (0 skip)

PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
    -> 154 passed in 0.52s           (0 skip)

golden: test_render_snapshot.py -> 5 passed   (rsvg-convert 在位，非 skipif 静默跳过)

python3 -m ruff check <本批文件>  -> All checks passed!
python3 -m ruff check .          -> 203 errors   （基线 307fb5e 同样 203 = 本机 ruff 版本噪声，零新增）

data/projects 整树 sha256 跑前跑后一致 (688de0a1707d2244…) -> 无测试泄漏
```

CI：分支 `calib-z-b1` **未推 main**（本项目 push main = 部署生产）。

---

## L2 实测记录

**[L2] 未执行** —— 无 `OPENAI_API_KEY` + 需用户计费授权，按 decor-b2 / render-fix-b1 降级口径。

**待用户闭环：** 部署 + 迁移后重新生成 1 张 v7 `r_live` 实拍图，一次闭合 (a) 原始报障（餐桌）确认、(b) 误报是否随修后引导图消除、(c) 盒几何真实出图目检。

---

## 上线顺序（铁律，顺序错会把数据写坏）

1. **PR squash-merge → 部署**（**必须最先**：写路径 `main.py:953` 会重解算；迁移先跑则期间任何一次重新标定都会用旧 `calibrate()` 把数据写回带病值）
2. 生产 dry-run 核对：`DATA_DIR=/opt/grandtianfu/data/projects python3 scripts/migrate_calibration_z.py --exclude-photo 1537e6d839504230972de8a05ee98c8f`
   - 预期：`{'healed': 9, 'excluded': 2}`、`地板下方 7 -> 0`、`dabcb` ×2 各 1556.4 px
3. 核对无误后加 `--apply`（`.bak` 可单步回退）
4. [L2] 重新生成 1 张实拍图目检闭环

---

## 进 done 前须处理（状态机卫生，非产品缺陷）

| # | 项 | 现状 → 要求 |
|---|---|---|
| H1 | `features.json` F002 `status` | `pending` → `completed`（fix-round 1 只改了 acceptance/notes，未回填） |
| H2 | `progress.json.completed_features` | `2` → `3` |
| H3 | `.auto-memory/project-status.md` | 陈旧（仍写「building 未开工」/「3/5 反转」/「存量 3 份」= 已被推翻的口径）→ 覆盖写刷新 |

---

## Soft-watch

| # | 项 |
|---|---|
| S1 | **`1537e` 的"排除"保住的是抛硬币的一面，不是已知正确值**（本机重算得相反面）。"不动" ≠ "安全"。真解 = `BL-calib-min-3-anchors`（已 high，含"重标衣帽间"） |
| S2 | `ae8e5`(r_garden) 标定质量本就不可用（自愈后 `C_z=+156mm`、锚点 err 178px）—— 与本 bug 无关 |
| S3 | 迁移脚本 CLI 对 excluded 行的「相机z(前)」留空，运维看不到存量值 `+1515.1`（理由行已打印，信息性小缺口） |
| S4 | 迁移后生产为**混合手性**（9×det=−1 + 2×det=+1）。已复核 spec §D2「下游零 det 依赖」成立：`cam.R` 全部用法只有 `R @ w + t`，`inv()` 只作用于 `K` ⇒ 功能安全 |
| S5 | **R1 的真实成因是 2026-07-11 的 stash 被中途 `pop`**（非活泄漏、非"工作区早已脏"）—— 详见复验报告 §2。那个「待用户决定去留」的 stash 已被 drop，内容仍可由 `740e4a8` 恢复 |

---

## 签收

**PASS —— 可进 done，可上线**（按上述顺序执行）。

- Evaluator：`local/evaluator-subagent`（fresh context，全程未采信任何转述）
- 未修改任何产品代码；未对生产执行任何写操作；未把 PIPL 敏感照片入库
- 3 条阻断项 R1 / R4 / R5 **全部闭合**；R2 / R3 已如实补进 spec 且经独立复现属实
