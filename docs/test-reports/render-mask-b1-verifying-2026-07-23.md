# render-mask-b1 隔离验收报告（2026-07-23）

> 批次：`render-mask-b1`（分支 `feat/render-mask-b1`，工作区未提交）。
> 验收人：**隔离 evaluator**（未参与本批实现，独立复测；本报告即 F005 交付物）。
> 规格：`docs/specs/render-mask-b1-spec.md`；验收标准：`features.json` F005 acceptance 六条。
> 沙箱：`artifacts/route-eval-20260723/`（gitignored；照片 PIPL 不入仓；凭据 source 导入未落盘未打印）。
> 数据：沙箱快照项目 D / 方案 `scheme_ai_20260714_130354_01_baec`，本地 API（8018 端口，已杀）。
> **AI 预算实测：6 gen（2 fal inpaint + 4 gpt-image-2 edits）+ 8 VLM（2 划区 + 6 关系验收），
> 在 ≤6 gen + ≤10 VLM 红线内。**

## 批次级判定：**FAIL（不通过，打回）**

硬指标（mask 外 diff==0）确实由构造保证并实测成立，但**同两张照片的对照实验证明第四档
当前不可交付**：fal flux inpaint 的 mask 内填充在两张真实空房照上全部失败（房间类型错乱 +
插画化），放置命中率 0% / 11.1% 对 relational 的 76.9% / 88.9%，远超 ±10% 噪声带；
合成边界无像素级接缝但有肉眼即见的风格断裂。F005 六条中第 (2)(3) 条 FAIL。

---

## F005 六条逐项

### (1) 硬指标：mask 外（羽化带豁免）像素 diff == 0 —— **PASS（附重大保留）**

方法：产品化 API（本地沙箱 8018）POST render-real `strategy=relational_mask`，2 张真实空房照
（r_live 客厅 v2 `bcc61531`、r_master 主卧 v2 `40109907`，均 2048×1536 JPEG）。
后端记录自带 `background_diff`，evaluator **独立复算**（自写 numpy：二值 mask 外逐像素
diff + 与 `acceptance.background_diff_check` 同法的腐蚀 12px 严格外部复算）：

| 照片 | 后端 changed_frac / max_diff | 独立复算：二值 mask 外改动像素 | 独立复算：严格外部 changed_frac | mask 覆盖率 |
|---|---|---|---|---|
| r_live | 0.0 / 0（checked_px 1,025,565） | **0**（max_diff=0） | 0.000000（checked_px 1,025,565，与后端逐数一致） | **66.4%** |
| r_master | 0.0 / 0（checked_px 637,492） | **0**（max_diff=0） | 0.000000（checked_px 637,492，一致） | **78.8%** |

结论：`composite_masked` 的构造保证真实生效——mask 外字节即原图解码字节，diff 恒 0，
非近似。**保留**：该保证只覆盖画面 21-34%（主要是天花与一小段墙）；floor+window_wall+
art_wall 三区并集吃掉 66-79% 画面，「背景逐像素锁定」的实际受益面远小于直觉，
且健全门只约束单区占比（floor≤80%、可选区≤85%），**对并集覆盖率无上限**（见 blocking-2）。

### (2) 放置命中率不劣于 relational（±10%）—— **FAIL**

同照片同方案、同一套 relation-check VLM（gpt-5.5）对照：

| 照片 | relational_mask | relational（对照） | 差值 |
|---|---|---|---|
| r_live（13 条约束） | **0/13 = 0%** | 10/13 = 76.9%（rounds=2） | **-76.9pp** |
| r_master（9 条约束） | **1/9 = 11.1%** | 8/9 = 88.9%（rounds=2） | **-77.8pp** |

VLM 判定与 evaluator 目检一致（非误判）：r_live mask 产物左半被填成**酒店客房**
（床+床头柜，地面变地毯）、右半被填成**卡通风格厨房中岛插画**；r_master mask 产物为
**日式动漫插画**——两张单人床（约束要一张双人床）、落地窗被改成装饰格窗、
窗外实景（城市楼群+山）被替换成**富士山**。relational 对照产物则照片级写实、
家具落位大体正确。0% / 11.1% vs 76.9% / 88.9%，任何噪声带都解释不了。

### (3) 边缘自然度目检 —— **FAIL**

- 像素级：合成边界**无 alpha 接缝、无色带**（全分辨率截图核查 r_live 窗墙上缘 y≈482
  与 r_master 窗墙上缘 y≈415 边界带；只向内羽化 8px 的构造成立，mask 外逐字节原图）。
- 语义级：**FAIL**——mask 上缘一侧是照片级写实的原天花/灯带，另一侧是卡通插画风
  墙面/吊柜，风格断裂肉眼即见，产物不可交付。「无接缝」成立，「自然」不成立。
- 证据（沙箱内，PIPL 不入仓）：`artifacts/route-eval-20260723/out/verify/`
  `orig_live.jpg` / `mask_live_out.png` / `mask_live_mask.png` / `orig_master.jpg` /
  `mask_master_out.png` / `mask_master_mask.png` / 对照 `job_rel_live.png` / `job_rel_master.png`。

### (4) 降级路径 —— **PASS**

- 实测：未标 room_id 照片（`7296858f`）调 relational_mask → **400**
  `RELATIONAL_NOT_READY`（与 relational 同一道门，零 AI 消耗，budget 计数不变）。
- 区域估计失败路径（VLM 异常/畸形多边形 → relational 整链 + `mask_degraded` 记录）：
  代码审查 `_render_real_mask`（`main.py:3795` 附近）确认 `zones_res.degraded` 时走
  `_relational_submit(..., mask_degraded=reason)`；`test_render_mask.py::test_relational_mask_degrades_to_relational_on_bad_zones`
  以 floor 缺失的 fake VLM 响应覆盖：断言 strategy 落 `relational`、`mask_degraded` 有值、
  **fal 未被调用**、relay edit 被调 1 次——测试有效且在 473 套件中绿。
- 健全门本身：13 条 `test_mask_zones.py` 覆盖顶点不足/面积越界/自交/可选区丢弃/
  VLM 异常，全绿。

### (5) 回归：三档零改动 + 双套件 + web build/lint —— **PASS**

- `packages/floorplan_core`：**165 passed**；`apps/api/tests`：**473 passed**（含新增
  test_mask_zones 13 + test_render_mask 4）。
- `apps/web`：`yarn lint` 绿（仅 `useViewport.ts` 既有无关 warning）、`yarn build` 绿。
- `git diff origin/main` 逐行审查：`relational` 重构为 `_relational_sync`/`_relational_submit`
  语义等价——同步段校验/预扣/简报/提示词逐项原样；异步段 round1→有 fail 才重试→
  两轮取优、round2 独立预扣、失败退预扣语义逐行保留；记录字段仅在 mask 参数存在时
  追加（`background_diff`/`mask_zones`/`base_url`/`mask_degraded`），relational 记录形态不变
  （实测对照记录无 mask 字段）。softref/geometry_lock 路径 diff 零触碰。
  本批两次 relational 对照实跑（rounds=2、记录字段齐全）亦实证闭环行为与 relation-b1 一致。

### (6) 红线 —— **PASS**

- 仓库 `data/projects/` 零写入（`git status -- data/` 干净；渲染写沙箱 DATA_DIR）。
- AI 调用 6 gen + 8 VLM，在 ≤6 gen + ≤10 VLM 内（budget daily_count=6、
  total_tokens=44,242 与计数吻合）。
- PIPL/凭据：`artifacts/` 命中 `.gitignore:21`，照片/prod.env/产物均不入仓；
  凭据仅 source 导入，未打印未落盘。
- 8018 进程已杀（`lsof :8018` 空）。

## F001-F004 复核

| Feature | 判定 | 依据 |
|---|---|---|
| F001 mask_zones（划区+健全门） | **PASS** | 13 测试绿；两张真实照划区几何质量不错（floor 贴墙脚线、窗墙/挂画墙合理）；降级语义合 spec §D3 |
| F002 relational_mask 路径 | **PARTIAL** | 机械面全通（路由/400/合成/双验收/记录/退预扣测试），但真实照片产出不可用（F005-2/3 FAIL），档位的交付目的未达成 |
| F003 background_diff_check | **PASS** | 独立复算逐数一致；三路径测试绿；确定性构造验证成立 |
| F004 前端第四档 | **PASS** | 类型/文案/fal 禁用/徽章/降级提示齐全；lint+build 绿；既有三档零回归 |

## Blocking（打回理由）

1. **fal flux inpaint 填充质量灾难性失败（2/2 真实照片）**：房间类型错乱（客厅→卧室+厨房）、
   全图插画化（与实拍天花并置）、窗外实景被替换（富士山）。放置命中率 0%/11.1% 对
   对照 76.9%/88.9%。疑似成因（供修复参考，非验收范围）：relational 提示词为整图编辑模型
   （gpt-image-2）设计，直接喂给 inpaint 模型 + mask 并集过大（66-79%）给模型自由度过大；
   开工前调查 1 的样本（下半 40% mask）未暴露此问题。
2. **mask 并集覆盖率无上限**：floor 80% + 可选区 85% 的单区上限允许并集吃掉近 8 成画面，
   「背景锁定」退化为只锁天花；window_wall 整区入 mask 意味着**窗外景色允许被模型重画**
   （r_master 实例：实景→富士山）——这正是用户最在意的「这就是我家」保真点。建议：
   并集占比上限门（超限降级 relational）、window_wall 默认不入 mask 或只取窗框条带。

## Non-blocking

1. mask 记录 `usage` 仅 `{width,height}`（fal 无 token 计量，经 on_usage 回调落账）——可用但信息量弱于 relay 记录。
2. `RelationCheckPanel` 对 mask 记录可能同时亮「背景疑似被改动」（VLM 分级，宽松/偏严均有噪声）与
   「背景逐像素锁定 ✓」（确定性 diff）两枚语义相左的徽章——建议面板对 mask 记录以 diff 徽章为准或加文案区分「mask 外」。
3. 工作区有一个与本批无关的未跟踪文件 `docs/实拍出图效果图-几何锁定优化方案-20260717.md`，PR 前需清理归属。
4. mask 档 relation-check 不做重试（rounds 恒 1，spec §D1 即如此设计）——在当前填充质量下
   失败即交付废图；修复 blocking-1 后可考虑复用 relational 的回写重试。

## 复核轨迹（可复现）

- 双套件：`PYTHONPATH=packages/floorplan_core apps/api/.venv/bin/python -m pytest packages/floorplan_core/tests -q`（165）；
  `PYTHONPATH=packages/floorplan_core:apps/api apps/api/.venv/bin/python -m pytest apps/api/tests -q`（473）。
- 实跑 job（沙箱记录）：mask `1ac58e82`/`a1b1263e`；对照 `16d06399`/`ccf1f999`；
  降级 400 用照片 `7296858f`。产物与独立复算脚本输出见沙箱 `out/verify/`。

---

# reverifying-1（fix_round 1 复验，2026-07-23）

> 复验人：同 verifying-1 隔离 evaluator。对象：fix_round 1（生成引擎 fal inpaint → relay 整图编辑
> + 羽化合成；新增 `_MASK_MAX_COVER_FRAC=0.60` 并集覆盖率降级门）。沙箱/方法同前次，
> 端口 8019（已杀）。**AI 预算实测：4 gen + 7 VLM（≤6 gen + ≤8 VLM 内）。**

## 批次级判定：**PARTIAL（仍不签收）**

原两个 blocking 的根因**机制上确实已除**（证据见下），但 fix 的覆盖率门过度矫正：
**第四档在全部 3 次真实照片调用中 100% 降级、从未激活**，fix 后的「relay 编辑 + 羽化合成」
主路径**零真实照片实证**。F005 的 (1) 硬指标、(2) 命中率、(3) 接缝目检对 mask 产物**无对象可验**。

## 原 blocking 复核

### blocking-①（fal inpaint 填充灾难）—— 机制性消除 ✓（替代路径未实证 ⚠️）

- 分派不再查 `fal_enabled`（`main.py:3181`）；mask 分支改 `provider.edit`（relay，
  与 relational 同引擎 gpt-image-2）+ `composite_masked` 羽化合成；fal 在该档已无调用点。
- 测试 `test_relational_mask_happy_path` 断言 `fal.calls == 0` 且 relay 编辑被调 1 次（绿）。
- 灾难引擎（fal flux inpaint）已不可能再产出。**但**：替代路径的合成质量（放置/接缝/风格）
  没有任何一张真实照片产出作证——3/3 运行在覆盖率门处降级（见下），合成代码路径
  仅有合成数据单测覆盖。

### blocking-②（mask 覆盖率无上限）—— 已修，且过度矫正 ⚠️→ 新 blocking

- `_MASK_MAX_COVER_FRAC=0.60`（`main.py:3788` 附近）：`sum(各区面积)` 超上限即降级记
  `mask_degraded="区域并集覆盖画面超 60% 上限, 背景锁定意义不足"`。
- 口径实证 ≈ 实际并集：按 verifying-1 的 zones 复算面积和，r_live 0.664 / r_master 0.788，
  与前次栅格化实测并集 66.4% / 78.8% 几乎一致（两案各区基本不重叠）。
- **实跑 3/3 全降级**：
  | 照片 | needs | 降级原因 | 产物 |
  |---|---|---|---|
  | r_live（客厅 v2） | floor+window_wall+art_wall | 面积和 ≈0.66 > 0.60 | relational，11/13 = 84.6%（2 uncertain，relation_pass=True） |
  | r_master（主卧 v2） | floor+window_wall+art_wall | 面积和 ≈0.79 > 0.60 | relational，9/9 = 100% |
  | r_study（书房 v0，补充第 3 张） | **floor 单区** | floor 一区即 >0.60 | relational，rounds=2 |
- r_study 案是关键证据：连「只有 floor」的最简 needs 都能超线——VLM 地面多边形在
  地面主导构图的照片里天然 0.35-0.80，0.60 的和值上限使该档在真实照片上几乎必然降级。
- 每次调用白付 1 次划区 VLM（约占该档 1/3 的 VLM 成本）后拿到的是 relational 产物。

## 复验项逐条对应

1. **命中率**：mask 档 0 次激活，无 mask 产物可核对；降级产物（实为 relational 整链）
   84.6% / 100%，不劣于前次 relational 对照 76.9% / 88.9%（±10% 内偏优）——
   证明的是 relational 链路与降级诚实性，不是第四档。
2. **目检**：两张降级产物均为照片级写实、房型正确（客厅沙发组+餐桌+大理石背景墙；
   主卧双人床+整墙窗帘+贵妃）、窗景为原城市景观（gpt-image-2 整图重绘保留了窗景结构）。
   无合成产物，**接缝/色带/纹理断裂检查无对象**。
3. **硬指标**：`background_diff` 为 null（降级即无 mask 无合成），独立复算无对象。
   覆盖率记录：3/3 超 0.60（见上表）。
4. **覆盖率降级实证**：✓ 代码 + `test_relational_mask_coverage_over_cap_degrades`（绿）+
   实跑 3/3 均记 `mask_degraded`，前端 RelationCheckPanel 降级提示路径前次已验。
5. **回归**：floorplan_core 165 + apps/api 473 + 抽跑 test_render_relational.py 10 全绿；
   `git diff` 逐行确认 fix 只动 mask 分支/分派/测试，relational 闭环（round1→重试→取优、
   预扣/退扣、记录字段）逐行未变。前端已同步去掉 fal 禁用逻辑（page.tsx 无 maskDisabled），
   与后端「不再依赖 fal」一致。

## 新 blocking（reverifying-1 → 建议 fix_round 2）

- **B1：第四档实际不可达。** 0.60 和值口径在目标方案全部已试房间（3/3，含 floor 单区案例）
  拦截，「relay 编辑 + 羽化合成」主路径零真实实证即线上死档。建议（任一或组合）：
  ① 口径改为栅格化后实际并集且只计「家具可入区」（window_wall/art_wall 是挂载面，
  本不需要整面重绘，可不计入或只计条带）；② 上限提至 ~0.75；③ 划区 prompt 让
  window_wall/art_wall 收敛到窗洞/挂画框而非整面墙。修后**必须用真实照片跑通合成路径**
  （命中对照 + diff==0 复算 + 接缝目检）方可签收。

## Non-blocking（reverifying-1）

1. mask 分支 relay 编辑后未调 `_budget.record_tokens(res.usage)`（`edit()` 不像 `chat_json`
   内部回调 on_usage）——若该路径真跑起来，生成 token 不进 total_tokens 计量
   （daily_count 预扣不受影响，仅监控口径缺损）。
2. `main.py:3146` 分派注释仍写「VLM 区域 -> fal inpaint」，与 fix 后实现不符（comment rot）。
3. spec §8 订正后，F005 acceptance「≥2 张真实照跑 relational_mask 且 mask 外 diff==0」
   与 0.60 上限在当前方案数据上自相矛盾（指定两张照片必然降级）——验收设计需随口径
   一并订正（调阈值或换可满足的照片/方案）。

## 复核轨迹（reverifying-1）

- 实跑 job（沙箱）：r_live `15bdb585`（降级）、r_master `032517db`（降级）、
  r_study `c8b4bb3d`（降级）；记录 JSON 与产物图在沙箱 `out/verify/job_fix_*`。
- 套件：`packages/floorplan_core` 165、`apps/api` 473、`test_render_relational.py` 10 全绿
  （2026-07-23 fix_round 1 工作区复跑）。
- 红线：4 gen + 7 VLM 在预算内；仓库 `data/` 零写入；PIPL/凭据未入仓未外泄；8019 已杀。

---

# reverifying-2（fix_round 2 复验，2026-07-23）

> 复验人：同 verifying-1 / reverifying-1 隔离 evaluator。对象：fix_round 2（覆盖门
> `_MASK_MAX_COVER_FRAC` 0.60→0.85 且改**栅格化后实际并集**；mask 分支补
> `_budget.record_tokens`；分派注释订正）。沙箱/方法同前次，端口 8020（已杀）。
> **AI 预算实测：2 gen + 4 VLM（≤6 gen + ≤8 VLM 内）。**

## 批次级判定：**PASS（签收）**

reverifying-1 的新 blocking B1（第四档不可达）**真实消失**：两张指定真实照片本次均实际走通
「VLM 划区 → relay 整图编辑 → 羽化合成」全链（`strategy == "relational_mask"`，非降级），
F005 六条全部通过。

## B1 消失证据（复验项 1：可达性）

| 照片 | strategy | mask 覆盖率（栅格并集实测） | 0.85 门 | 结果 |
|---|---|---|---|---|
| r_live（bcc61531 客厅 v2） | **relational_mask** | 54.1% | 未拦 | 走通合成全链 |
| r_master（40109907 主卧 v2） | **relational_mask** | 72.4% | 未拦 | 走通合成全链 |

覆盖门代码审查确认（`main.py:3826-3837`）：`cover = (np.asarray(mask) > 0).mean()` 为栅格化
实际并集，阈值 0.85 只拦「整图几乎全标可画」的病态；门位于栅格化之后，语义正确。
测试两侧齐备：并集 100% 病态降级（`coverage_over_cap`）+ 并集 ~70% 合法不误拦
（`large_but_legit_coverage_not_blocked`），474 全绿。

## 硬指标（复验项 2）

| 照片 | 后端 background_diff | 独立复算：二值 mask 外 | 独立复算：严格外部（腐蚀 12px） |
|---|---|---|---|
| r_live | ok=true, changed_frac=0.0, max_diff=0 | **0 改动像素, max_diff=0** | changed_frac=0.000000, checked_px=1,391,517（与后端逐数一致） |
| r_master | ok=true, changed_frac=0.0, max_diff=0 | **0 改动像素, max_diff=0** | changed_frac=0.000000, checked_px=836,598（一致） |

mask 外字节即原图解码字节，构造保证第三次实测成立（verifying-1 fal 版、本次 relay 版均恒 0）。

## 接缝目检（复验项 3，前次无对象本次重点）

原生分辨率（2048×1536）边界带截图 4 处：

- **r_live 地板上缘/墙脚线**（x0-1100, y880-1140）：大理石墙面与地板纹理跨边界连续，
  沙发压边自然，**无接缝/色带**。
- **r_live 窗墙上缘**（x880-1980, y380-620）：原天花灯带（mask 外字节）与生成纱帘之间
  由窗帘盒暗带过渡，沿结构线贴合，**无硬切/色偏**。
- **r_master 房间中部**（x100-1400, y600-880）：木格栅墙（原图）到生成墙面/床区过渡
  不可辨，**无纹理断裂**。
- **r_master 窗顶右缘**（x1500-2048, y130-430）：原天花与生成厚帘衔接于窗帘轨道凹槽，
  **无接缝**。

整体：房间类型正确（客厅/主卧）、照片级写实与 relational 同级；窗外城市实景保留
（纱帘后楼群/栏杆清晰）；r_live 大理石背景墙本次在 mask 外 = 原图字节逐像素保留。
证据存沙箱 `out/verify/f2_*.png`。

## 命中率（复验项 4，统一 relation-check VLM ±10% 带）

| 照片 | relational_mask（本次） | relational 对照（verifying-1 实测） | 差值 | 判定 |
|---|---|---|---|---|
| r_live | 9/13 = **69.2%** | 10/13 = 76.9% | -7.7pp | 带内 ✓ |
| r_master | 9/9 = **100%** | 8/9 = 88.9% | +11.1pp（更优） | ✓ |

r_live 的 4 条 fail（餐桌×2、挂画×2）与 relational 对照的弱项高度重合（对照同失挂画 C7/C9），
属模型放置噪声而非 mask 路径缺陷。

## 回归（复验项 5）

- `apps/api/tests` **474 全绿**（fix_round 2 工作区复跑）；`git diff` 逐行确认 fix_round 2
  只动覆盖门/计量/注释：relational 闭环分支逐行未变；mask 分支补
  `_budget.record_tokens(res.usage)`（reverifying-1 NB-1 已修）；分派注释已改
  「relay 整图编辑」（NB-2 已修）。

## Non-blocking（reverifying-2）

1. `main.py:3593` `_relational_submit` docstring 仍残留「relational_mask: fal inpaint」
   字样（comment rot，仅文档面）。
2. 覆盖门降级文案「超 85% 病态上限」中的 cover 实测值会随 zones 波动，记录清晰可用。
3. r_study 类 floor 主导构图（单区 >0.6）在 0.85 门下可达，但 floor 单区 >0.85 的极端
   俯拍仍会降级——属设计意图（病态拦截），非缺陷。

## 复核轨迹（reverifying-2）

- 实跑 job（沙箱）：r_live `dd027970`、r_master `73a40548`；记录 JSON 与产物/mask/原图
  在沙箱 `out/verify/`（`job_f2_*.json`、`f2_*_out.png`、`f2_*_mask.png`）。
- 套件：474 全绿（含 test_render_mask 5 条）。
- 红线：2 gen + 4 VLM 在预算内；仓库 `data/` 零写入；PIPL/凭据未入仓未外泄；8020 已杀。

## 三轮验收总结

- verifying-1（FAIL）：fal inpaint 填充灾难 + 覆盖无上限。
- reverifying-1（PARTIAL）：根因机制性消除，但 0.60 面积和门使档位 3/3 不可达（B1）。
- reverifying-2（**PASS**）：0.85 栅格并集门下两指定照片实际走通合成全链；diff==0 独立
  复算成立；命中率 69.2%/100% 对 76.9%/88.9% 在 ±10% 带内；4 处原生分辨率边界带目检
  无接缝/色带/纹理断裂。F005 六条全过，批次签收。
