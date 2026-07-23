# calib-cure-b2 — 标定解算根治（通用 PnP + 异面特征点 + 精修）

> 状态：**待用户 plan 批准（spec lock）**。批次分支 `feat/calib-cure-b2` → PR → squash；绝不单推 main（push main = 部署生产）。
> 前置：calib-cure-b1（A 预览 / B 硬门禁 / C 特征点对齐）已上线生产（b8344f1, PR #87）。本批不改门禁语义（门是对的），只根治**解算**。
> 会话根因证据：见本文件 §1（2026-07-17 主上下文数值实验，非猜测）。

## 1. 背景与根因（已数值实证）

**用户 2026-07-17 生产反馈：** calib-cure-b1 上线后，实际体验中**大量图片在新人工标定流程下无法保存成功**——两种模式（特征点/专家）都能出线框预览，但**线框明显歪/框到墙外**，报错**重投影误差 > 50px**，"确认保存"按钮变灰。

**裁决方向（用户确认）：** 门禁是对的（如实拦截歪相机；放宽门 = 把 798/f4d 那类错图放回生产）。**病在解算本身——对真实照片大量产出几何错误的相机。** 走"彻底修解算（含 spike 先验证收益）"。

**数值实验结论（主上下文本会话跑，真值相机 + 噪声/真实几何）：**

| 模式 | 病灶 | 证据 |
|---|---|---|
| **专家（线+角）** `perspective.calibrate` (perspective.py:208) | 消失点估焦距对手画线误差**病态敏感** | σ=3px 手抖 → **55% 撞 50px 门**；σ=5px → 73%；σ=8px → 81% |
| **特征点（默认）** `calib_features.solve_pnp` (calib_features.py:168) | **全部特征点在地面 z=0 单一平面**；真实斜拍照可见地面点**又少又近共线** → 共面单应退化 | 真实 D 户型 + 门口相机：r_study 可见 4 点共线比≈0、r_master 5 点 0.45 → **100% 失败**；r_live 仅 2 点可见 < 4 根本不够 |

**关键补充发现（原型验证挖出）：** "加竖直点 + 通用 PnP"是**必要但不充分**——真实机位单张照片里能同时看清、点得准的特征点太少（4 墙角常只 1–2 个入画）。加天花板点在点较多的房间（r_live）把失败率 77%→55%，方向对；小房间点太稀疏，**光改解算救不动，须"解算 + 特征点供给"一起改**。故本批 **spike 先行**：用真实点击数据把配方验准再建生产件。

**当前用户处境：** 标定存不进 → 走不了精准"几何锁定"出图，只能回退老"轴测软参考"路径（`_render_real_response` main.py:3080-3087：有标定才走 geometry-lock，否则落 B2 readiness 软参考）。批次核心能力（精准落位）实际不可用。

## 2. 目标与非目标

**目标：** 让**默认（特征点）模式**在真实照片上真正可用——诚实门禁下（reproj 稳健指标 ≤ 阈值 + 线框贴合），常见房间/机位的标定成功率显著提升；专家模式降级。

**非目标（本批不做）：**
- **不放宽/不架空质量门禁**（reproj 门语义保持；只在 F006 把"取最大值"换稳健指标，门仍诚实）。
- 不碰 3D 模型引导路线（那是 calib-cure-b1 spike 的独立立项，见 [[grandtianfu-real-render-placement-route-a]] 与 BL-wall-art-box-undermodeled 的 2026-07-17 关联）。
- 不改渲染/家具投影/annotate_boxes 几何（golden 逐字节不动）。

## 3. Spike 闸门（F001 — 建生产件前必须验准配方）

**why：** §1 补充发现证明"通用 PnP + 竖直点"必要不充分；直接建生产解算器有"仍因点太少而失败"的风险。spike 用**真实点击数据**验准配方，Planner 裁决后再锁 F002+ acceptance。

**harness 结构说明：** 混合批次先 building（全部 generator）再 verifying（全部 evaluator），故 spike 不能拆成"generator 建 + evaluator 跑"（会让 evaluator 反在生产件之后、闸门失效）。**spike 建+跑+报告合并为一条 generator 件（F001，研究码非产品代码）**；Planner 据其报告裁决配方后才建 F002+；独立性由 **F008 隔离 evaluator 对产品件 L2 验收**保证（spike 报告是研究产物，非产品 signoff）。

**F001 交付（`scripts/spike/calib_solve/`，严格隔离，不 import main.py、不改任何产品代码）：**
1. **候选解算器原型**（纯 numpy）：通用 PnP（接受**异面点** z∈{0, 2700, 及竖直边中点}，非共面单应）+ **非线性精修**（对全部点最小化总重投影，Levenberg–Marquardt / 高斯牛顿手写或 scipy 若可用；退化到 numpy 最小二乘迭代）+ **点位条件数/退化度量**。
2. **真实数据台**：读 `apps/api/tests/fixtures/prod_calibrations.json`（11 条真实生产点击，皆 lines 模式 2–3 锚点）+ 只读拉取生产病例照片副本（`deploysvr:/opt/grandtianfu/data/uploads/D/empty/{472015c4…,ed881ccf…}.jpg`，**PIPL：不入 git**）。
3. **多高度标注小工具**：能在拉取照片上人工点选地面 + 天花板/竖直特征点（供获取真实多高度点击——现有生产数据只有地面点，答不了竖直点可见性问题）。
4. **对比量化 + 报告**：候选 vs 现（solve_pnp / calibrate），指标 = reproj（稳健 + 最大）、相机中心可信度（高度∈[800,2200]、离房距离）、**线框叠真实照片目检贴合**、诚实门下失败率；覆盖 ≥3 种房型 × ≥2 机位。产出 `docs/test-reports/calib-cure-b2-spike-YYYYMMDD.md`：
   - **go/no-go**：通用 PnP + 异面点 + 精修能否在真实照片上把常见房型/机位带进诚实门（含"哪些房型仍救不动"的诚实边界）；
   - **验准的配方**：竖直/天花板特征点具体取哪些、需要几个、精修用什么、退化守门阈值、reproj 稳健指标选型（RMS / 分位）与门值；
   - 若 no-go 或部分 → 明确替代/降级建议（如"引导用户拍能看到天花板的构图""接受先验焦距 EXIF""某些房型只能专家模式"）。

**→ Planner 裁决检查点（F001 报告后）：** 我据报告 lock F002–F007 acceptance（pre-impl-adjudication 模式）。**若 spike no-go，F002+ 范围就地重议，不盲建。**

## 4. 关键设计决策（配方待 spike 验准，方向已定）

### D1 异面特征点供给（F002，扩 `calib_features.derive_features` calib_features.py:38）
现只派生 z=0 地面点（墙角 + 门/落地窗地面交点）。新增**异面点**（破共面退化的关键）：
- **墙-天花板角**（z=2700 = `perspective._REAL_CEILING_MM`，**严禁借 axon 1450**）：每个实体墙角上方的天花板角；
- **门/窗竖框**：门框/窗框竖边（地面点 z=0 已有，追加**顶点** z=门/窗高）；
- **竖直墙棱**：墙角处 z=0..2700 的竖直棱线（给纯竖直方向约束）。
kind 扩展：`ceiling_corner` / `door_head` / `window_head` / `wall_edge_vertical`。id 稳定可复算（binding/UI 引用），排序确定性。层高/门窗高数据来源在 F001 spike 内先确认（geometry openings 有无高度字段；无则用合理常量并在 spec 注明）。

### D2 通用 PnP + 非线性精修（F003，`calib_features` / `perspective`）
- `solve_pnp` 从"共面单应分解"升级为**接受异面点的通用 PnP**（DLT 投影矩阵分解 或 EPnP 思路 + 焦距扫描；保持纯 numpy、确定性、左手系约定 det(R)=-1 与既有一致）；
- 解后加**非线性精修**：对全部点对最小化总重投影残差（把点击噪声平均掉，显著压低 reproj）；
- **数学内核既有单测钉死**：`test_perspective` 合成真值往返 <2px 与 `test_calib_features` 必须仍绿；生产 11 条 lines 重放（`test_prod_fixture_*`）行为按 spike 裁决处理（可能因精修数值变化，届时同 commit 更新基线并注明）。

### D3 退化/可见性守门 + 引导（F004，端点/校验层 main.py，不改内核）
解算前查**点位条件数**（近共线 / 太挤 / 全在单一高度 / 有效点 < N）→ 明确可行动中文提示（"再点一个天花板角""点到对面墙角把点铺开"），杜绝静默产出垃圾相机（现 `solve_pnp` 对共线点静默给灾难相机）。阈值由 spike 定。

### D4 稳健 reproj 指标 + 门保持诚实（F005，`assess_calibration_quality` perspective.py:612）
现 reproj = **所有点最大值**（一个点没点准整体判死，perspective.py:637）。换**稳健指标**（RMS 或 P75/P90 + 单点离群另标）。**门仍诚实**：线框贴合仍是真判据，只是不让单坏点误杀。既有 400/409 家族（STALE / DEGENERATE_GUIDE / BAD_CALIBRATION，main.py:2759-2790）**零回归**（同 code 同 HTTP 语义）。门值/指标选型由 spike 定。

### D5 专家（线+角）模式降级（F007，前端 PerspectiveCalibrator.tsx:93 模式路由）
专家模式数学上最脆（σ=3px→55%）。降级为**高级选项 + 明确警告**（"手画线法对精度极敏感，建议用特征点模式"），或按 spike 结论决定去留。不删既有 F002 两步提交逻辑（保留可回退）。

### D6 前端多高度点选（F006，前端）
`FeaturePointCalibrator` 支持**地面 + 天花板/竖直点**点选（平面小窗高亮 + 高度提示），点位铺开引导（呼应 D3 守门）。复用设计系统组件（Modal/Badge/Button/NoticeBanner，见既有 import）；成对 `dark:`；禁 `bg-*-50` 硬编码；tsc + yarn lint 绿。

### D7 车道与编排
- **快车道单会话**（单实例 `local`，默认映射：Planner/Generator 主上下文，Evaluator 隔离 subagent）。
- **spike 闸门先行**：F001 建原型 → Planner 裁决配方 → 才建 F002–F007。
- verifying：隔离 evaluator subagent；F008 L2 由 Evaluator 在真实浏览器 + 重标生产病例照片执行。
- 推送前必查：`git status --short data/ docs/test-reports/ .auto-memory/`（PIPL：拉取照片副本绝不入 git）。

## 5. 数据准备（Evaluator/spike 前提）
- **真实点击**：`apps/api/tests/fixtures/prod_calibrations.json`（11 条，纯数值可入库）。
- **病例照片**：只读拉取 `deploysvr:.../uploads/D/empty/{472015c4…,ed881ccf…}.jpg`（不入 git）。
- **多高度真实点击**：spike 期在病例照片上人工标注地面+天花板点（F001 小工具）；产品期 L2 由用户以新 UX 重标。
- **正样本**：复用 `test_perspective.py` 合成真值 helper（`_real_camera` / `_calib_inputs_from`，相机高 1500mm、reproj≈0 全门通过）。

## 6. 验收总则（Evaluator，F008）
1. 两套 pytest 全绿 0 skip（含合成真值往返 <2px、异面点新单测、生产重放按裁决基线、既有 400/409 家族零回归）；golden 逐字节不动；ruff 本批代码 clean；
2. tsc + yarn lint 绿；前端 D6 规范逐条查；
3. **[L2] 真实浏览器**：用户/Evaluator 以新流程重标生产病例照片（798/f4d + 常见房型各一）→ **线框贴合目检 + 保存成功 + 出图落位改善**；对比 b1 前的失败率给定量/半定量结论；
4. 铁律 10：所有 commit tag 映射 features.json 条目；
5. **诚实边界写进 signoff**：哪些房型/机位新解算仍救不动（不粉饰），是否需要后续构图引导/EXIF 焦距等立项。

## 7. 铁律核查（Planner spec 起草自查）
- 铁律 1（源码核查）：本 spec 全部 file:line 均已 Read 核实（perspective.py / calib_features.py / main.py / 前端组件）。✅
- 铁律 5（不提交无法运行代码）：spike 原型在 scripts/spike/ 隔离；产品件每条独立 commit 可运行。
- 铁律 10（feature 号归属）：commit tag `feat(calib-cure-b2-Fxxx): …` 对应下表。
- 独立性铁则：F008 由隔离 evaluator 对**产品代码**验收；F001 spike 原型为研究码（非产品），Planner 可跑之裁决配方，不构成自评。
