# calib-cure-b2 验收报告（verifying-1，隔离 evaluator L1）

> 角色：隔离 evaluator subagent（fresh context，无自评）。署名 `local/evaluator-subagent`。
> 日期：2026-07-18。分支 `feat/calib-cure-b2`（基线 cb24337 → HEAD 36ad3ab）。
> 范围：**本轮只做 L1**（代码 + 测试可验证部分）。F008 是 L2 真实浏览器验收，**本轮无浏览器环境、未获用户在场授权只读重拉 PIPL 病例照** → 记 `pending-user`，F008 状态保持 `pending`。
> 结论基于实物（代码、测试运行输出、golden 逐字节），不基于任何实现叙述。

## 总体 verdict

**L1：PASS（F001–F007 全 7 条 PASS，0 blocking）。** 门未被放宽（红线守住）；既有 400/409 家族零回归；golden 逐字节不动；两套 pytest 全绿 0 skip；tsc/lint/ruff（产品代码）clean。
**L2（F008）：pending-user** —— 判定"解算真的修好了没有"的唯一实物门本轮未执行（见 §L2）。

## 测试运行实证

| 检查 | 命令 | 结果 |
|---|---|---|
| api pytest | `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` | **433 passed, 0 skip**（17.8s） |
| engine pytest | `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q` | **154 passed, 0 skip**（0.56s） |
| golden 逐字节 | `pytest test_render_snapshot.py -v` | **5 passed**（2 条 `render_string_matches_baseline_byte_for_byte` 均 byte-identical；`.phase0-baseline/` 本地存在，真跑非 skip） |
| tsc | `cd apps/web && npx --no-install tsc --noEmit` | **exit 0** |
| next lint | `next lint --file {4 个改动组件}` | **No ESLint warnings or errors** |
| ruff（产品代码） | `ruff check calib_features.py perspective.py test_calib_features.py test_calibration_quality.py` | **All checks passed** |
| ruff（main.py） | 同上含 main.py | I001（Organize imports）=**仓库既有基线噪声，非本批**（本批 main.py diff 未动 import 区） |
| ruff（spike） | `ruff check scripts/spike/calib_solve/solver.py` | **1 × E702**（分号，line 112）—— 见 non-blocking N1 |

flake：session_notes 提及的 `test_atomic_write` 偶发负载 flake 本轮**未复现**（433 一次全绿）。

## 逐条 feature 判定

### F001 — Spike 闸门·解算原型 + 验准配方报告 · **PASS**
- `scripts/spike/calib_solve/solver.py`（199 行，纯 numpy）存在；**隔离达标**：不 import main.py，仅在函数内 `from aigc import perspective` 惰性复用纯几何 `Camera`（只读，不改产品路径），符合红线"spike 严格隔离"。
- 报告 `docs/test-reports/calib-cure-b2-spike-20260717.md` 存在：CONDITIONAL GO + 验准配方（异面点取哪些/精修法/退化阈值/RMS 指标）+ 诚实边界（R1 几何失配 / R2 小房间边际 / 门不放宽）。
- 研究码非产品；产品件独立性由本 L1 + F008 L2 承载。**符合 acceptance。**

### F002 — 异面特征点供给（derive_features）· **PASS**
- `derive_features` 在既有地面点（wall_corner/door_jamb/window_floor，z=0）外新增异面点：`ceiling_corner`(z=`perspective._REAL_CEILING_MM`)、`door_head`(z=`_DOOR_HEAD_MM`=2050)、`window_head`(z=2700)；天花板角与地面角同 (x,y) 竖直配对。
- **红线核查通过**：`_REAL_CEILING_MM = 2700`（perspective.py:64，真实毫米），**未借 axon `WALL_H=1450`**（axon.py:21 是 POC 挤出尺度）。
- id 稳定可复算（`ceilcorner:/doorhead:/winhead:` 前缀）+ `feats.sort(key=id)` 确定性排序。
- 新单测：`test_derive_features_adds_coplanar_breaking_noncoplanar_points`（天花板角一一对应 + 两高度）、门顶/窗顶断言、端点透出异面 kind；既有 derive 单测零回归。
- 非阻断观察：spec §D1 列的 `wall_edge_vertical` kind 未单独实现，改由 corner(z=0)+ceilcorner(z=2700) **同 XY 竖直配对**实现竖直边约束（功能等价，异面供给达成）。见 N2。

### F003 — 通用 PnP + 非线性精修（solve_pnp）· **PASS**
- `solve_pnp` 升级为调度器：全 z≈0（`max|z|≤1`）→ `_solve_pnp_coplanar`（**既有共面单应路径逐字保留**，经差异比对：仅剥离两条 guard 上移到调度器，数值内核 `_homography/_score/_pose_candidates/两级细扫` 逐字不变）；含异面点 → `_solve_pnp_general`（新 `_pose_known_K` 归一化 DLT + 物理门 + 最小重投影初值 + `_refine` Gauss-Newton/LM 精修）。
- 几何正确性实证（新单测全绿）：异面合成真值往返 `max<2.0px`、焦距误差 `<2%`、`det(R)<0`（左手世界物理相机，与既有约定一致）；σ=8px 点击噪声下相机中心误差 `<300mm`。
- 数学内核既有单测零回归（`test_perspective` / `test_calib_features` / 生产 fixture 重放皆在 433 内绿）。
- **EXIF 焦距先验增补**：building 期实测 `imaging.normalize_photo`（imaging.py:159）上传即剥全部 EXIF（PIPL 剥 GPS 顺带剥焦距）→ 存储照片无 EXIF → EXIF 分支不可行，**已诚实立项 backlog `BL-calib-exif-focal-prior`(low)**（非静默丢弃）。acceptance 的"无 EXIF 则回落焦距扫描"分支正是实装行为，且 F001 报告本就把 EXIF 列为"待裁决是否纳入"的可选增补 → 不构成 F003 失败。见 N3。

### F004 — 退化/可见性守门 + 引导 · **PASS**
- `_validate_points_payload`（解算前校验层，**不改数学内核**）将 points 路径的共线检查换为 `calib_features.degeneracy_reason`：3D SVD 第二主轴比 `<0.12` 拦近共线、全同高且 XY 比 `<0.30` 提示补天花板/异面点、点近重合另拦；保守（只拦明显退化，边际交 assess reproj 门）；返回可行动中文提示。
- `≥4` 点 guard（main.py:952）先于 degeneracy 调用；`degeneracy_reason(<4)` 返 None 由上层管，无空窗。
- 新单测 `test_degeneracy_reason_guards` + `test_validate_points_payload_accepts_noncoplanar`（近共线拦、纯共面共线仍拦"共线"、异面/铺开放行）全绿。
- **零回归**：`_anchors_non_collinear` 仍服务 anchors（专家模式）路径（main.py:939），未被误删；expert 路径校验不变。

### F005 — 稳健 reproj 指标 + 门保持诚实 · **PASS（红线守住）**
- `assess_calibration_quality` 将门/评级指标从"取最大"换 **RMS**；`reproj_max_px` 保留供单点离群另标；单点离群走软信号（level→suspect，**不整体判死**）。
- **红线核查——门未放宽**：
  - 门值 `CALIB_MAX_REPROJ_PX = 50.0`（perspective.py:585）**未变**；`CALIB_MAX_REPROJ_PX` escape hatch **保留**。
  - 门仍诚实：`test_assess_rms_still_fails_systematic_error`——所有点系统性全偏(~120px)→RMS>门→`ok=False`。真歪相机（投影处处错=系统性偏）仍被拦。
  - 仅在高方差（单点离群）场景放宽：`test_assess_gate_uses_rms_not_max`（max=70/RMS≈41→放行 suspect）、`test_assess_flags_single_gross_outlier_softly`（8@10+1@120→放行 suspect + 离群另标）。
  - 判定：这是 spec §D4 / 用户裁决**明令允许的唯一改动**（改指标形状不改门诚实性），**非放宽门**。见 §红线结论。
- 既有 400/409 家族（STALE_CALIBRATION main.py:2762 / BAD_CALIBRATION 1252,2772,2787 / DEGENERATE_GUIDE 2832）**diff 零触碰**，同 code 同 HTTP 语义，测试全绿。

### F006 — 前端多高度点选 + 构图引导 · **PASS**
- `FeaturePointCalibrator.tsx`：KIND_LABEL 补 ceiling_corner/door_head/window_head（tsc 通过=联合类型穷尽）；`isElevated` 对 Z>0 显"↑ 点画面里的「高处」"提示、地面点显"点落地位置"；`≥MIN_POINTS` 时出构图引导 NoticeBanner（"铺开到不同墙面 + 覆盖不同高度…拍摄时让画面同时含地面墙角与天花板转角"），呼应 F001 §2.7。
- `CalibrationMiniMap.tsx`：2D 俯视图按 `world[2]<=1` 过滤只画地面孪生（异面点同 XY 重叠去重）；`planId` 把异面 target 的高亮/已放映射回地面孪生 id（`ceilcorner:→corner:` 等）。逻辑自洽。
- **D6 规范**：复用设计系统 `NoticeBanner/Badge/Button/Modal/LoadingState`（components/studio/ui/）；新增标记成对 `dark:`（text-amber-600 dark:text-amber-400）；**无新增 `bg-*-50` 硬编码**（diff grep 为空）；tsc + next lint 绿。

### F007 — 专家（线+角）模式降级 · **PASS**
- `PerspectiveCalibrator.tsx`：按钮文案 → "专家(线+角·高级)"；`mode==='expert'` 时出 warn NoticeBanner（"手画墙线法…病态敏感…建议改用特征点(默认)"）。
- **既有 F002 两步提交逻辑逐字保留**（可回退，未删），符合 acceptance"不删"。tsc + next lint 绿；D6 规范。

### F008 — L2 真实浏览器重标生产病例 · **pending-user（本轮未验）**
见 §L2。状态保持 `pending`。

## 红线核查结论

| 红线 | 结论 |
|---|---|
| 不放宽/不架空质量门 | **守住**。门值 50px 不变、escape hatch 保留、系统性错标仍判死（有单测）。max→RMS 是用户+spec 明令唯一允许的指标形状改动，非放门。 |
| 不写 data/projects/ | **守住**。`git diff --stat data/` 空。 |
| 不动 floorplan_core | **守住**。axon.py 等未在 diff；仅只读调用 merge_group_ids。 |
| spike 严格隔离 | **守住**。solver.py 不 import main.py，只惰性只读复用 perspective.Camera。 |
| PIPL 照片不入 git | **守住**。`git ls-files` 无 472015c4/ed881ccf/uploads。 |
| 不单推 main | **守住**。工作在 feat/calib-cure-b2；未推 main。 |
| golden 逐字节 + 400/409 零回归 | **守住**。golden 2 条 byte-identical；错误家族 diff 零触碰。 |
| 铁律 10 commit tag 映射 | **守住**。F001×2(原型+报告)/F002–F007 各 1，全映射 features.json；无孤儿 tag。 |

## Non-blocking 观察

- **N1（spike ruff E702）**：`scripts/spike/calib_solve/solver.py:112` 有分号双语句（E702），本批新引入。属研究码（scripts/spike 未被产品 import、CI 无 ruff step、ruff.toml 未 exclude scripts 但 CI 不跑），不影响生产/CI。session_notes 称"ruff 本批clean"对**产品代码**成立，对 spike 文件不完全成立——透明记录，非阻断。
- **N2（wall_edge_vertical kind 命名）**：spec §D1 列的独立 kind `wall_edge_vertical` 未实现，改由 corner(z=0)+ceilcorner(z=2700) 同 XY 竖直配对达成竖直边约束（功能等价，异面供给目的达成）。命名差异不影响解算，非阻断。
- **N3（EXIF 焦距先验撤出 F003）**：已立项 backlog（low）并注明技术原因（imaging 剥 EXIF），实装回落焦距扫描——诚实处置，非静默丢弃，非阻断。
- **N4（通用 DLT 无 Hartley 归一化）**：`_pose_known_K` 不像共面 `_homography` 那样做数据归一化，极端点位配置理论上条件数偏差；但焦距扫描初值 + GN 精修补偿，合成零噪声达 0.000px、σ=8px→<300mm，目标工况已验证。非阻断，供 F008 L2 关注真实点位下的数值稳定性。

## L2（F008）pending-user 说明

**本轮未执行**，原因（非"跑失败"）：
1. **无浏览器环境**：隔离 evaluator subagent 无真实浏览器，无法操作新 UX 重标。
2. **未获用户在场授权**：只读重拉 deploysvr 病例照（472015c4 书房 / ed881ccf 客餐厅）属 PIPL 敏感操作，需用户明确在场授权（spec §5 / 计划批准中知悉但需实时确认）。

L2 是**判定"解算真的修好了没有"的唯一实物门**。L1 只证：代码几何正确（合成真值 + 隔离验证台）、门诚实未放宽、零回归。**尚未确认**（spike 报告 §4 诚实边界照搬）：
- **R1**：真人在真实 UX 标注真实照片后的**实际 reproj**（世界坐标取自理想化 rect，层高/墙厚/描摹误差会注入 reproj，光靠解算/精修不能消）。
- **R2**：小房间（单窗卧室 ~5–6 异面点）边际是否够——可能需构图引导/EXIF 先验兜底。
- 线框叠真实照片**目检贴合** + 保存成功 + 出图**落位改善** vs b1 前失败率的定量/半定量结论。

**F008 建议**：待用户在场 + 授权只读重拉照片后，由隔离 evaluator 或用户配合执行；照片副本用完即删、绝不入 git。若 L2 发现真实 reproj 仍高 → 红线：继续提升供给/加先验，**不是**放宽 50px 门。

## 诚实边界（本报告自身）

- L1 全绿**不等于**"真实照片标定已修好"——那是 L2 的活，本轮 pending-user。
- RMS 指标的宽容是**针对高方差单点离群**的定向放宽（有单测边界），对均匀误差的边界行为与 max 一致；系统性错标仍判死。评估者判定其在用户+spec 授权范围内，但如实标注这一语义权衡供用户知情。
- 本报告不修改任何产品代码，仅落测试报告与结论。
