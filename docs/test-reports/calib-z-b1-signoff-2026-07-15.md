# calib-z-b1 Signoff 2026-07-15

> 状态：**已验收 PASS**（第 2 次复验 / fix-round 2；progress.json status=reverifying → done）
> 触发：标定世界 z 轴符号未被任何约束钉住 → 生产 11 条标定全部带病（相机解到地板下方 / 平面被镜像）
> 验收者：local/evaluator-subagent（第 3 位隔离验收者，fresh context）
> 详细报告：`docs/test-reports/calib-z-b1-reverify2-2026-07-15.md`
> 前序（均原样保全，未改写）：`calib-z-b1-verifying-2026-07-15.md` / `calib-z-b1-reverifying-2026-07-15.md` / `calib-z-b1-reverify-2026-07-15.md`

---

## 变更背景

`apps/api/aigc/perspective.py::calibrate()` 的姿态 z 列写成 `+cross(x_col, y_col)`，**强制 det=+1**。但世界系 `(X=东, Y=南, Z=上)` 是**左手系**（East×South = Down），相机系（右,下,前）是右手系 ⇒ 物理正确的 world→camera `R` **必然 det = −1**。⇒ x/y 列拟合正确时 **z 列被系统性取反**。

加之两条打分约束**全部只用地面锚点**（生产 11/11 锚点 z 全为 0 → z 列恒被乘 0、对打分零贡献）⇒ 2 锚点时两候选 err **精确平局**（相对差 1e-13~1e-16）⇒ z 朝上朝下由**浮点噪声抛硬币**（铁证：同一份存量输入换台机器重算即得相反的 z，本批已被**三方独立复现**）。

后果：贴墙件（挂画/窗帘）被画在**地板上**、家具盒**朝地下拉伸** → 模型明智地无视错盒 → `evaluate_geometry_lock` 判「盒区外出现新结构」→ `auto_check` 持续 false alarm。

---

## 变更功能清单

### F001：`calibrate()` 用物理约束定 z 方向（根治）

**Executor：** generator　**状态：** completed　**验收：PASS**

**文件：** `apps/api/aigc/perspective.py`（修改，+65/−? 行含 docstring）

**改动（两处，缺一不可）：**
1. 构造式：`R = column_stack([sx*ex, sy*ey, -cross(sx*ex, sy*ey)])` —— 尊重左手性，det=−1
2. 候选筛选加同级硬约束：`float((-R.T @ t)[2]) > 0`（相机必须在地板上方 —— 地面锚点给不了、物理必然成立）
3. 4 候选全排除 → 明确 `raise`（诚实报错优于产出朝地下的相机）

**验收证据（Evaluator 第四次独立构造，全程不强加 det）：**
- 在**右手系 ENU** 里 look-at 造真值 → 换基到 ESU ⇒ **`det(R_true) = −1.000000`（推导，非设定）** = 左手系论点独立成立
- 修复后**精确还原真值**：`max|R−R_true| = 2.737e-14`，`|C−C_true| = 3.239e-10 mm`
- 修复前：`det=+1`，`C_z = −1620`（真值 +1620），z 列恰为真值取反（2.612e-14）= **系统性，非偶发**
- **随机对抗扫描 214 组良态场景：还原真值 214/214；物理门后存活候选恒 = 1（214/214）** ⇒ 抛硬币根因已除
- 生产 11/11：`C_z>0` + 门后候选唯一 + `R` 精确正交（max\|RᵀR−I\| < 1e-12）
- 阳性对照：把 `perspective.py` 换回基线 `307fb5e` → **11 条测试变红**

---

### F002：存量 11 条标定自愈迁移（重跑原始输入，免用户重新标定）

**Executor：** generator　**状态：** completed　**验收：PASS**

**文件：**
- `apps/api/aigc/calib_heal.py`（新增，纯函数、无 I/O、不改入参）
- `apps/api/scripts/migrate_calibration_z.py`（新增，薄 CLI，**默认 dry-run**）
- `apps/api/tests/test_calib_heal.py`、`apps/api/tests/fixtures/prod_calibrations.json`（新增）

**改动：** 存储载荷 `photo.calibration` 完整保留原始输入（`x_lines`/`y_lines`/`anchors`/`img_wh`）⇒ 修好 F001 后**重跑即可导出正确 camera，无需用户重新标定**。

**范围：全量 11 条自愈，不排除任何一条**（fix-round 1 曾排除 1537e，fix-round 2 依 R6 撤销；`exclude_photo_ids` / `--exclude-photo` 能力一并移除）。

**验收证据（只读生产副本，sha256 与生产逐字节一致）：**
- dry-run：`{'healed': 11}`，**零写入**（跑前跑后整树 sha256 一致）；地板下方 **7 → 0**；地面移动 4 条（dabcb×2 / 1537e×2）
- `--apply`：自愈后 **11/11 `C_z>0` + det=−1 + `R` 正交**
- **幂等**：二次 `--apply` → `{'unchanged': 11}`，写 0 文件
- **`.bak` 与生产原件逐字节一致**（v1/v6/v7 全对）⇒ 回退可用
- 剩余 10 条测试经 **4 个定向变异**（纯函数性 / 幂等 / 优雅降级 / failed 兜底）证明**全部承重**，删掉 3 条排除测试未留空洞
- 自愈重写 camera **不被判 stale**（`_calibration_stale_reason` 指纹只含 `room_id`+`room_rect_hash`）

**1537e（衣帽间）方向定论 —— 依据（Evaluator 订正后的承重判据）：**
> 生产在用的 11 条**全部 det=+1 = 手性错误 = 成像被镜像 = 物理不可实现**（可证伪地不对）。修复后物理门筛完 **11/11 恰好只剩 1 个候选**且 det=−1。1537e 的 stored 与 healed 是**精确镜像对**，对锚点 err **完全相同**（max 均 123.9 / sum 均 195.7）⇒ 数据本身对二者无偏好，方向只能由物理定。
> ⇒ **healing 不是赌方向，是把可证伪为不可实现的镜像相机换成唯一物理可容许解。「healed 严格优于 excluded」，且与那扇窗是不是 w02 无关。**

---

### F003：生产实物几何对抗验收

**Executor：** evaluator　**状态：** completed　**验收：PASS（本报告 + reverify2 报告即交付物）**

四轮隔离验收（首轮 A / 并发 A / 并发 B / 本轮），结论原样落盘，无一份被改写。

---

## 未变更范围

| 事项 | 说明 |
|---|---|
| `_box_polys` / `annotate_boxes` / `footprint_mask` / 调色板 | render-fix-b1 刚验收过，零触碰 |
| `evaluate_geometry_lock` 判据 | spec §7 划界：若 §6.6 显示仍误报且根因在验收器本身，另立批 |
| `data/projects/` 种子快照 | 测试红线；`git diff 307fb5e...HEAD -- data/projects/` **空**；整树 sha256 跑测试前后一致 |
| 世界系约定（不改为 Y=北） | 裁决 #5:A；影响面覆盖 floorplan_core 全链路 / golden / 存量数据 |

---

## 回归

- **353 + 154 全绿 / 0 skip**；golden 5 条**真跑**（`rsvg-convert` 在位，非 skipif）
- **417ae 地面投影位移 2.785e-10 px** ⇒ render-fix-b1 修好、用户已在生产确认的**餐桌落位完整保住**
- `bcc615`(×3) 2.97e-10 ~ 5.86e-10 px；`ae8e5`(×2) 9.388e-07 px（spec D4「≤1e-6」之内）
- `dabcb`(×2) 1556.4 px / `1537e`(×2) 1706.4 px = **预期改变**（镜像解被纠正），非回归
- ruff 全仓 **203 == 基线 203**（零新增）；本批文件 `All checks passed!`
- 无测试泄漏：`data/projects` 整树 sha256 跑前跑后一致

---

## 未闭合（不阻断上线）

| ID | 内容 |
|---|---|
| **§6.6** | 下游误报**未消除**：20/111 → 9/96（`score` 0.85），仍 `ok:false`。**口径铁律：只能写「盒几何已修正；误报由 20/111 降至 9/96；是否消除待 [L2] 复测」，不得表述为已消除。** 诚实边界：该 `out_png` 是模型看着**修前的错引导图**生成的，判定须用**修后**引导图重出一张 |
| **§7 [L2]** | 真实 AI 出图**未执行**（无 key + 需计费授权）→ 同 decor-b2 / render-fix-b1 降级口径 |
| **R10** | spec §2.5 的「定论依据」应由 w02 视觉判据改为 det/唯一性判据（前者存在两位前任未检、本轮亦未能关闭的**遮挡缺口**；后者 robust 且已验证）。不改变任何决定与代码 |
| soft-watch | `ae8e5`(r_garden) 标定质量本就不可用（C_z=+156mm / err 178.1px），与本 bug 无关 |
| soft-watch | `1537e` **精度**仍不合格（err max 123.9 / sum 195.7）→ `BL-calib-min-3-anchors`（与已定的**方向**是两件事） |

---

## 上线 runbook（顺序铁律）

> **必须先部署本批代码，再跑迁移。** 反了的话生产仍跑修复前的 `calibrate()`，期间任何一次重新标定都会把数据又写回带病值。

1. PR → **squash-merge** 到 `main`（= 部署生产）；确认镜像已含本批修复
2. `ssh deploysvr && cd /opt/grandtianfu` → `DATA_DIR=/opt/grandtianfu/data/projects python3 <migrate_calibration_z.py>` **dry-run** 核对
   - 期望：`{'healed': 11}`、地板下方 **7 → 0**、地面移动 4 条（dabcb×2 1556.4px / 1537e×2 1706.4px）
3. 核对无误 → 加 `--apply`（用户已授权范围 = **全量 11 条**）。`.bak` 已验证与原件逐字节一致，可回退
4. 重出 1 张 v7 `r_live` 实拍图 → 一次闭合 (a) 原始报障（餐桌）最终确认 (b) §6.6 误报是否随修后引导图消除（[L2]）

---

## 生产安全声明

本轮**未对生产执行任何写操作**。生产数据经 scp **只读**取回，会话首尾 sha256 双向核对**完全一致**（v1 `aef10696…` / v6 `0dcbb1f0…` / v7 `7c339bf0…`）。迁移脚本仅在 `/tmp` 生产副本上跑。PIPL 照片只存 `/tmp`，**未入库**。**Evaluator 未修改任何产品代码。**
