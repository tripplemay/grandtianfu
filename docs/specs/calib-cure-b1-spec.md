# calib-cure-b1 — 标定根治（A 预览 / B 硬门禁 / C 特征点对齐）+ L1 简模引导 spike

> 状态：spec lock（用户 2026-07-17 plan 批准）。批次分支 `feat/calib-cure-b1` → PR → squash；绝不单推 main（push main = 部署生产）。
> 背景三份核查文档（与本 spec 同 PR 入库，Generator/Evaluator 必读）：
> - `docs/AIGC链路核查-带评论效果图根因-20260717.md` — 生产两案根因链
> - `docs/标定功能缺陷核查-20260717.md` — 19 项缺陷（A1-A9/B/C/D/E/F/G）+ §4 根治方案 + 数值实验
> - `docs/3D模型引导-出图质变评估-20260717.md` — spike 方案（S0）

## 1. 背景与目标

生产两张带评论效果图（798f23d3 书房 / f4dab9bc 客餐厅）落位全错，根因 = **标定输入易错 + 全链路零质量门禁**（标定自报 2353px/112px 重投影误差仍畅通入库出图）。本批三层根治：

- **A 期（预览速赢）**：标定即预览——用户提交前看到线框叠照片 + 误差评级，坏标定当场可见；
- **B 期（硬门禁）**：保存/渲染双端质量门 + 输入语义校验 + InputGateError 机制化 + 可删除标定；
- **C 期（范式替换）**：特征点 PnP 对齐——对应关系由构造保证正确（点自带世界坐标），画线步骤消失；
- **spike**：L1 简模引导 vs L0 彩盒 A/B 实测（relay+fal 双后端），为 3D 化立项拿数据。

## 2. 用户裁决（2026-07-17，plan 批准时确认）

| # | 裁决 |
|---|---|
| 1 | backlog 收编 3 条：`BL-calib-min-3-anchors`(→F004/F002/F009)、`BL-input-gate-error-class`(→F003)、`BL-decor-b2-L2-realphoto`(→F012 顺带)；并入后从 backlog.json 移除 |
| 2 | spike 预算授权：**relay+fal 双后端**，2 场景 × L0/L1 × 2 后端 ≈ 12-16 图（~¥20-30）；本地 api + 用户 key，不碰生产 data |
| 3 | 存量坏标定：**渲染时硬拦 409**（798/f4d/1537e 等超阈值存量被拦提示重标；A 期预览使重标成本低） |

## 3. 关键设计决策

### D1 质量评估 = 纯函数单一真源
新增 `perspective.assess_calibration_quality(cam, anchors, *, room_rects_mm, img_wh) -> dict`：
```python
{ "ok": bool, "level": "good"|"suspect"|"bad", "reasons": [str],
  "metrics": { "reproj_px": float, "camera_z_mm": float,
               "camera_room_dist_mm": float, "hfov_deg": float } }
```
**硬门**（bad 任一命中即 ok=False）：
- `reproj_px > CALIB_MAX_REPROJ_PX`（默认 **50**；依据：诚实点击 σ=8px 时 P90≈23px 的 2 倍余量；生产病例 112/2353/123.9 全拦。env `CALIB_MAX_REPROJ_PX` 可调作 escape hatch）
- 相机高度 `camera_z_mm ∉ [800, 2200]`（`-R^T t` 的 z，同 `calib_heal.camera_height_mm` L49-53 算法；**不改 calib_heal**）
- `hfov_deg = 2·atan((W/2)/f) ∉ [35°, 110°]`

**软信号**（不 fail，reasons 记录 + level 降为 suspect）：
- 相机水平位置到绑定房（merge 组成员 rect 并集）的距离 > **1500mm** → 提示『相机似在离绑定房间较远处拍摄，请确认房间绑定正确』。
- 【2026-07-17 pre-impl 裁决，原为 1000mm 硬门】降级理由：(a) 站门口/相邻房间拍大景是合法姿势——既有合成 fixture（`test_render_real_geometry._calib_payload` 相机在玄关拍客厅，离并集 ~1950mm）即实证，硬拦会误拦一票合法用例；(b) 该门的动机案例 798 相机离房仅 474mm，硬门反而拦不住它（靠 reproj 2353px 硬拦）；(c) 数值实验 case A 镜像粗差的相机位置同样合理，位置门无检测增益。生产两案在硬门三项下仍全部被拦（798: reproj；f4d: reproj+相机高 399mm）。

`level`：good = reproj < 25px 且无任何 reasons；suspect = 25-50px 或存在软信号；bad = ok=False。
**三处共用**：保存 400（F003）、渲染 409（F005）、dry-run 展示（F001）——杜绝阈值漂移。

### D2 `calibrate()` 数学内核一行不改
≥3 锚点、语义校验、质量门全部在**端点/校验层**（main.py）。理由：`calibrate()` 被 `calib_heal` 存量重放与 154+373 测试复用；内核改动会破幂等重放。渲染门（F005）**只查质量不查锚点数**——存量 n=2 好标定（reproj 达标）继续可用。

### D3 InputGateError 机制（废除人工登记表）
`class InputGateError(ValueError)`（main.py 顶部，携 `status:int` + `payload:dict`），统一 `except InputGateError` 返回 `JSONResponse(e.status, e.payload)`。迁移现有两处 raise（`STALE_CALIBRATION` main.py:2392-2399、`DEGENERATE_GUIDE` main.py:2434-2445）与 `_INPUT_GATE_CODES_409`(main.py:1306) 判定段(main.py:2460-2472)。**code 与 HTTP 语义不变**（既有 409 测试零回归）。新 code：`BAD_CALIBRATION`（保存 400 / 渲染 409，同 code 不同 status 按 raise 点定）。

### D4 dry-run 语义（F001）
`POST /api/projects/{house}/baselines/{version}/photos/{photo_id}/calibration?dry_run=1`：
- **不落盘**；`GEOM_READONLY` 下**仍可用**（只读计算，403 门仅拦真保存）；
- 可解算 → 200 `{ok, camera, reprojection_error, quality, wireframe}`，其中 `wireframe = [{room_id, floor:[[u,v]×4], ceiling:[[u,v]×4]}]`（merge 组每成员 rect 的 z=0 / z=2700 角投影；**层高用 `perspective._REAL_CEILING_MM=2700`，严禁借 axon 1450**）；quality 为 bad 也返回 200（前端要画出"有多歪"）；
- 解算失败（`calibrate()` raise）→ 400（沿既有 error 文案路径 main.py:952-955）。
真保存路径在 assess 不过时 → 400 `BAD_CALIBRATION`（F003），保存成功时把 `quality` 快照与 `reprojection_error` 一起入 calibration 载荷。

### D5 spike 严格隔离
- 工具在 `scripts/spike/`（新目录），**不 import main.py、不改任何产品代码路径**；perspective 按路径 importlib 加载（同本批核查实验方法）；
- L1 部件高度表**硬编码在脚本内**（sofa 座 420/靠背 800/扶手 620 等），不进产品数据/目录；
- 出图直调 `aigc.providers`（`Settings.from_env()`），本地环境变量提供 relay/fal key；
- 输入照片 = 生产**只读拉取**副本，放本地未跟踪路径（CLI 参数传入）——**PIPL：照片一律不得 commit**（data/uploads gitignored 的延伸）；标定/几何 JSON（纯数值）可作 fixture 入库；
- 双臂公平性：L0 臂用产品 `annotate_boxes` + 产品 prompt 模板逐字；L1 臂仅替换"盒→家具"映射段为简模措辞；两臂同 photo/同 camera/同 furniture/同 size；
- 量化复用 `acceptance.evaluate_geometry_lock`（auto_check 同款指标）+ `eval_harness.metrics_row/classify_failures`（eval_harness.py:72,127）。

### D6 前端规范
复用设计系统组件（`Modal`/`Badge`/`Button`/`NoticeBanner`/`LoadingState`，见 PerspectiveCalibrator.tsx:3-8 既有 import）；成对 `dark:`；禁 `bg-*-50` 硬编码；`tsc`+`yarn lint` 绿。

### D7 direction 交叉校验的诚实边界（F010）
photo.direction ∈ v0..v3（baselines.py:614 白名单，"拍摄视角→轴测旋转对齐"）。**v_i ↔ 罗盘 yaw 的映射本 spec 未实证**——Generator 开工时先读轴测旋转与视角选择器代码（BaselinePhotosCard.tsx:31 一带 + axon 旋转）实证映射；映射清晰 → 反向即 assess 拦截；映射不清 → 该子项降级为"仅记录 mismatch 到 quality.reasons 不拦截"（宁可不拦不可误拦），并在 commit message 注明。

## 4. Features 与 acceptance

> 详细 acceptance 写在 `features.json`（含参照实物 file:line）。此处只列范围断面：

| ID | 期 | 一句话 | executor | 依赖 |
|---|---|---|---|---|
| F001 | A | dry-run 预览参数（camera+误差+quality+wireframe，不落盘，GEOM_READONLY 可用） | generator | — |
| F002 | A | 前端两步提交（dry-run 线框叠照片 + 误差徽章 + 确认才保存 + 锚点 UI 引导 ≥3） | generator | F001 |
| F003 | B | InputGateError + assess 保存硬门（400 BAD_CALIBRATION） | generator | F001 |
| F004 | B | 输入语义校验（线/锚点退化拦截 + 新保存 ≥3 不共线锚点） | generator | F003 |
| F005 | B | 渲染入口存量质量复查（409 BAD_CALIBRATION 硬拦） | generator | F003 |
| F006 | B | guide 健全性扩展（>1/3 出画阻断）+ near×0%可见矛盾话术禁止 | generator | F003 |
| F007 | B | DELETE 标定端点 + 前端清除入口 | generator | — |
| F008 | C | 特征点池派生 + solve_pnp（共面单应分解 + 焦距扫描 + 物理门，纯 numpy） | generator | F003 |
| F009 | C | 特征点对齐 UI（平面小窗引导 + 照片点选 + ≥4 点自动解算预览 + 确认保存） | generator | F008,F002 |
| F010 | C | 专家模式动态文案 + direction 交叉校验（D7 边界） | generator | F009 |
| F011 | spike | spike 工具（L1 简模引导渲染 + run_ab 双后端出图记账） | generator | — |
| F012 | spike | spike 执行 + A/B 结论报告（12-16 图 + go/no-go + BL-decor-b2-L2 顺带） | **evaluator** | F011,F002 |

## 5. 接口与数据模型摘要

- `POST .../photos/{id}/calibration`：既有 payload（x_lines/y_lines/anchors/img_wh，main.py:836-859 校验）扩展——新增可选 `mode:"points"` + `points:[{feature_id?, world:[x,y,z], px:[u,v]}]`（F008；服务端按 world/px 转 anchors 结构复用 `calibrate`→否，points 模式走 `solve_pnp`；存盘载荷保留 mode 与 feature 引用，兼容读取方）；`?dry_run=1` 见 D4。
- `GET .../photos/{id}/calibration-features`（F008）：`{features:[{id, world:[x,y,0], label_zh, kind:"wall_corner"|"door_jamb"|"window_floor"}], room_ids:[...]}`——merge 组成员（axon.merge_group_ids，axon.py:131-141）实体墙角 + openings（geometry `openings[].wall{axis,at,span}`，×mm_per_px）门框竖边×地面交点；落地窗（wtype 判定，仅 z=0 角）。
- `DELETE .../photos/{id}/calibration`（F007）：镜像 `set_photo_calibration`（baselines.py:697-719，允许历史版本，GEOM_READONLY 403），移除 `photo.calibration` 键。
- calibration 存盘载荷新增：`quality`（D1 快照）、`mode`（缺省 "lines" 兼容存量）。binding 指纹（main.py:869-891）在 points 模式追加 openings 来源 hash（几何 openings 变更 → stale）。

## 6. 数据准备步骤（Evaluator 验收前提）

### 负样本 fixture（纯数值，可入库）
生产两案标定 payload（本批核查已只读取证，坐标为准确生产值）：
- **798 书房**（预期：F004 语义校验拦近竖直线 + F003 assess 拦 reproj 2353px/相机出房）：
  `img_wh=[2048,1536]`；`x_lines=[[[2039,1214],[2042,1484]],[[2032,82],[2020,9]]]`；`y_lines=[[[1017,970],[2042,1202]],[[1026,442],[2039,67]]]`；`anchors=[{world:[18150,2500,0],px:[1019,980]},{world:[15150,5800,0],px:[6,1533]}]`（房 r_guest2 rect=[1515,250,300,330]，mm_per_px=10）
- **f4d 客餐厅**（预期：F003 assess 拦 reproj 112px+相机高 399mm；F006 拦 12 件 5 件出画）：
  `img_wh=[2048,1536]`；`x_lines=[[[1009,878],[45,1009]],[[1007,649],[43,488]]]`；`y_lines=[[[40,1014],[1,1236]],[[40,483],[0,184]]]`；`anchors=[{world:[4950,2500,0],px:[1908,945]},{world:[6750,5800,0],px:[43,1013]}]`（房 r_foyer rect=[495,250,180,330]，merge=m_living 含 r_live rect=[495,580,720,830]）
### 正样本 fixture
复用 `test_perspective.py:595` `test_calibrate_recovers_synthetic_ground_truth_camera` 的合成真值 helper 模式（相机高 1400mm、reproj≈0 → 全门通过）。
### spike 前提（F012）
- 病例照片副本：本地只读拉取 `deploysvr:/opt/grandtianfu/data/uploads/D/empty/{472015c4…,ed881ccf…}.jpg`（**不入 git**）；
- 可信标定：A/B 期上线后用户以新 UX 重标两张照片（L2 走查项），或 Generator 手工构造经 dry-run 预览确认的点对——**spike 出图前置**；
- 预算记账：run_ab 输出每图 usage tokens 汇总进报告。

## 7. 编排与阶段流

- 快车道单会话；**building 波次**：波1 F001‖F011（文件集不相交，可并行 worktree subagent）→ 波2 F003→F004→F005→F006 串行（共享 main.py）、F002 与 B 期后端并行（前端文件）、F007 在 B 期尾（main.py 空档）→ 波3 F008→F009→F010。
- 每 feature 独立 commit（`feat(calib-cure-b1-Fxxx): …`），features.json 状态随 commit 更新。
- verifying：隔离 evaluator subagent fan-out；F012 由 Evaluator 执行（预算见 §2.2）。
- 推送前必查：`git status --short data/ docs/test-reports/ docs/test-cases/ .auto-memory/`。

## 8. 验收总则（Evaluator）

1. 两套 pytest 全绿 0 skip（含 §6 负样本被拦/正样本通过/既有 STALE、DEGENERATE_GUIDE、409 家族零回归）；golden 逐字节不动；ruff 本批代码 clean（基线 203 条既有噪声不算）；
2. `tsc`+`yarn lint` 绿；前端 D6 规范逐条查；
3. [L2] 用户浏览器：A 期预览走查（好/坏标定各一次）→ 新 UX 重标两张病例照片 → 出图落位改善目检；
4. F012 报告落 `docs/test-reports/spike-l1-guide-ab-YYYYMMDD.md`：L0/L1×relay/fal 量化表 + 落位目检 + go/no-go + BL-decor-b2-L2-realphoto 观察点结论；
5. 铁律 10：所有 commit tag 必须映射 features.json 条目。
