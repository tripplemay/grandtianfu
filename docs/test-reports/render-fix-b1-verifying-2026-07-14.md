# render-fix-b1 首轮验收报告（verifying, fix_rounds=0）

> Evaluator：隔离 evaluator subagent（fresh context，local/evaluator-subagent）
> 日期：2026-07-14 ｜ 分支：`fix/render-guide-degeneracy` ｜ 对照基线：`main` (35e7da5)
> 判定：**F001 PASS ／ F002 PASS ／ F003 PARTIAL** → status = `fixing`

## 0. 结论摘要

| Feature | 判定 | 一句话 |
|---|---|---|
| F001 `_box_polys` 近平面裁剪 | **PASS** | 生产实物复现→修复实证：curtain 画幅覆盖 92.05% → 1.66%，餐桌盒由 **0% 可见** 恢复到 1.46% 完整可见；byte-safe 对照**真 main 代码**逐字节成立 |
| F002 调色板 / 撞色 / 结构件 | **PASS** | 生产 30 组合 legend 全单射；4 个原撞色组合修复；entry_door 不进盒；prompt 无标识符泄漏；14 色两两 ΔE ≥ 28 |
| F003 引导图健全性门禁 | **PARTIAL** | 拦截有效且不误拦（生产 30/30 放行），但 ① acceptance 明列的**「阈值边界用例」缺失** ② `DEGENERATE_GUIDE` 映射到 **HTTP 500** 且 `code` 无人消费（与同族 `STALE_CALIBRATION`→409 不一致） |

**另有 1 项超出本批范围的独立发现（见 §6）：`calibrate()` 的 z 轴符号未被约束，生产 5 份标定中 3 份为 z 朝下 → 家具引导盒被向地下拉伸。** 不影响本批三条判定，但与用户原始报障（家具落位错）同源，建议单独立批。

## 1. 取证方法与独立性声明

- **不采信任何实现叙述**：未读 `generator_handoff` 的结论作为依据；全部判定基于代码、实跑输出、自建对抗用例。
- **不复用 Generator 的对照基线**：Generator 测试中的 `_naive_box_polys` 是修复前代码的**重实现**（若其漂移，byte-safe 断言即落空）。本次改用 `git worktree` 检出**真 main**，同进程并排加载 `main` 与 `HEAD` 两份 `perspective.py` 对比。
- **不采信交接的 fixture**：`scratchpad/probe/` 由 Generator 备好。已从 `deploysvr`（**只读**）独立重取 `baselines/v7/{photos,geometry}.json` 与 6 份 scheme `furniture.json`，与交接件做 sha256 规范化比对：

```
geometry  match: True 2cff61e1ba56d8dc
furniture match: True ae8d30b8058933b2
calib full match: True
```
→ 交接 fixture 属实，但本报告全部结论均基于**独立重取**的副本。

- 测试脚本产物：`scratchpad/indep/{ev_common,t1_f001,t2_coverage,t3_bytesafe,t4_f002,t5_noen,t6_f003,t7_palette,t8_httppath,t9_matrix}.py`（临时取证脚本，不入库；关键输出已内联本报告）。

## 2. L1 基线

| 项 | 结果 |
|---|---|
| `packages/floorplan_core/tests` | **154 passed, 0 skipped** |
| `apps/api/tests` | **331 passed, 0 skipped** |
| `rsvg-convert` | **存在**（`/opt/homebrew/bin/rsvg-convert`）→ golden/快照测试**实跑**，非 skip |
| `test_render_snapshot.py`（golden） | 5 passed（覆盖 axon SVG 链路，本批未触及） |
| decor/perspective/annotate/footprint 相关 | 66 passed |
| ruff | `main.py` I001 —— **HEAD 与 main 同报**，且本批 **零 import 行改动**（`git diff` 实证）→ 既有噪声，不计入 |
| `perspective.py` / `test_perspective.py` ruff | 干净 |

**范围核验（本批只改校验与投影层）：** 改动文件仅 `aigc/perspective.py`、`main.py`、`tests/test_perspective.py`、spec、状态机 JSON。`calibrate` / `vanishing_point` / `box_usability` / `_footprint_corners_px` / `_item_z0_mm` / `_item_height_mm` **零增删行** ✅。

## 3. F001 — PASS

### 3.1 生产实物复现（对照 = 真 main 代码）

用生产标定（photo `417ae5589afe`）+ v7 几何 + `scheme_ai_20260714_130354_01_baec` 家具重生引导图：

**单盒画幅内实际覆盖率：**

| type | 修复前(main) | 修复后(HEAD) |
|---|---|---|
| **curtain** | **92.05%** | **1.66%** |
| dining_table | 1.46% | 1.46% |
| 其余 12 件 | 与修复后**逐字不变** | 同左 |

**画家算法合成后各类型最终可见面积（决定 AI 收到什么）：**

```
修复前(main):  curtain 88.23% ／ 空(照片) 7.95% ／ media 3.82%
               → dining_table 0.00%  ← 餐桌盒被完全埋掉, AI 无任何位置信号
修复后(HEAD):  空(照片) 85.09% ／ sofa 5.25% ／ media 3.82% ／ curtain 1.66%
               ／ dining_table 1.46% ／ coffee_table 1.00% ／ plant 0.93%
               ／ wine_cabinet 0.71% ／ entry_door 0.08%
```

**目检（引导图重生，见 §3.2）**：修复前=全画幅品红 + 右下绿块（与 session_notes 记载的生产 real-base 一致）；修复后=房间清晰可辨，紫色餐桌盒清晰可读，8 类盒均可区分。

→ acceptance「修前 curtain 覆盖全画幅、修后仅覆盖真实可见区且餐桌紫盒可读」**成立**。

### 3.2 引导图目检产物

`scratchpad/indep/guide_BEFORE_main.png` / `guide_AFTER_head.png`（已目检，见上）。

### 3.3 byte-safe（本批最大回归面）— 成立

对照 **真 main 代码**，生产全部 **75 件**家具逐件比对 `_box_polys` 输出 `repr`（精确到 float 位模式）：

```
逐字节等价 : 64 件
有差异     : 11 件
```

**11 件差异全部合法**（每件都确有顶点 `z < NEAR_MM`，即真的跨/越相机平面，非误裁）：

```
r_mbath/vanity      minDepth=-1073.0    r_master/rug        minDepth=-3730.0
r_mbath/tub         minDepth=-1563.5    r_master/bed        minDepth=-3545.6
r_master/nightstand minDepth=-2288.0    r_master/chaise     minDepth= -441.4
r_live/curtain      minDepth= -132.0    r_master/curtain    minDepth=-4338.3
r_master/wall_art   minDepth=-3154.8    r_master/plant      minDepth=-1862.2
```
（注：r_master/r_mbath 各件是我用 r_live 相机做的合成压力测试，生产不会这样组合；生产真实组合见下）

**生产真实组合矩阵（5 张已标定照片 × 6 个方案 = 30 组合）：**

```
F001 影响面: 仅 2/30 组合投影发生变化, 变化件均为 ['curtain'], 均为 photo 417ae5589afe
             → 其余 28/30 组合逐字节不变
```

**footprint_mask 字节级（acceptance d 同步受益）：** 15 个房间逐一比对，仅 `r_live`（真病灶）、`r_master`/`r_mbath`（合成压力）mask 改变，其余 12 房间 mask **hash 完全相同**。`r_mbath` 由「炸开垃圾」变为「空 mask」= 改善。

**既有断言：** 485 tests 全绿、0 skip，golden 快照实跑通过 → acceptance「既有 golden/快照/decor-b2 断言不得变」成立。

### 3.4 裁剪数学复核（独立）

- `_clip_face_near` 为标准单平面 Sutherland–Hodgman，**在相机系**执行、**投影前**执行 —— 符合 D1（投影后坐标已丢失深度符号，无法补救）。
- 交点插值 `t = (near - za) / (zb - za)`：仅在 `a_in != b_in` 时求值，此时 `za`、`zb` 必分居 `near` 两侧 ⇒ `zb - za ≠ 0`，**无除零风险** ✅。
- byte-safe 机理：全可见时 `out` 逐个 append **原对象** `a`，顺序不变；投影 `uv = cam.K @ c` 与原 `cam.K @ (cam.R @ w + cam.t)` 为同一浮点运算序列；深度沿用 `uv[2]`（与原实现一致，比 D1 字面的「相机系 z 均值」更严格地保字节）✅。
- 整面在背后 → `len(clipped) < 3` → 丢弃 ✅（acceptance c，实测 `_box_polys(...) == []`）。

### 3.5 阈值 `NEAR_MM = 10.0` 独立复核 —— 合理

- 落在 spec 要求的 1~50mm 量级内 ✅。
- **不误裁**：生产 75 件中 64 件完全不受影响；受影响的 11 件 minDepth 均在 **-132 ~ -4338mm**，距 10mm 阈值有 2~3 个数量级余量 —— 即使 `NEAR_MM` 取 1mm 或 50mm，被裁集合**完全相同**。阈值处于极宽的平台区，非临界值 ✅。
- 室内照相机前 1cm 内无有意义几何，物理上安全。

### 3.6 acceptance 措辞偏差（记账，不判 FAIL）

features.json F001 acceptance 写「修后投影**包围盒收敛到画幅量级**」。**实测未成立**：修复后 curtain 投影仍为 `u:-41316..130  v:997..240479`（bbox ≈ 画幅 3155 倍）。

但这与 **spec §D1 明文**冲突——D1 写「裁剪后坐标偏大属正常（近平面顶点本就趋向无穷），几何仍正确」。要让 bbox 收敛必须再做一次 2D 画幅裁剪，那会**破坏 byte-safe**（部分出画的盒极常见）且无必要（PIL 栅格化自带裁剪）。

→ **spec D1 正确、features.json acceptance 该句措辞有误**；实现遵循了 D1。acceptance 的真实意图「只覆盖真实可见区」以覆盖率口径**已达成**（92.05%→1.66%）。按 evaluator.md §13（checklist 文本与代码漂移时直接订正而非判 FAIL）处理，记录于此供后续读者避免误读。

## 4. F002 — PASS

### 4.1 生产实证：病灶复现 → 修复

```
修复前(main) legend:  purple=dining_table  blue=sofa  orange=coffee_table  green=media
                      cyan=entry_door  red=wine_cabinet  yellow=wall_art  magenta=curtain
                      purple=plant        ← 重复色 ['purple'], drawn=13
修复后(HEAD) legend:  purple=dining_table  blue=sofa  orange=coffee_table  green=media
                      cyan=wine_cabinet  red=wall_art  yellow=curtain  magenta=plant
                      → 单射 True, entry_door 不进盒 False, drawn=12
                      → 餐桌=purple  绿植=magenta  同色=False ✅
```
修复前 legend 与生产存档 prompt 原文（spec §1 P1 引用）**逐条吻合** → 病灶复现无误。

**生产全量矩阵（30 组合）：**

```
HEAD annotate_boxes 全跑:
    legend 单射且正常出图 : 30
    重复色                : 0
    抛错(调色板耗尽等)    : 0
    异常行                : 无
修复前会撞色的组合: 4/30  (bcc615315c78 + 417ae5589afe) × (baec + manual_20260714) 重复色 ['purple']
```
注：撞色影响面比 spec 记载更广 —— **另一张 r_live 照片 `bcc615315c78` 同样撞色但不炸开**，反证了 P0/P1 确为两个独立 bug。

### 4.2 逐条 acceptance

| 项 | 结果 | 证据 |
|---|---|---|
| (a) ≥14 色且视觉可区分 | ✅ | 14 色；**两两 ΔE(CIE76, Lab) 最小 = 28.03**（cyan/teal），全部 91 对 ≥ 28 —— 远离 ΔE<10 的「相近色」区。Generator 自测只断言「名称/RGB 元组唯一」（唯一≠可区分），本项为 Evaluator 独立补测 |
| (b) 耗尽抛错不静默回绕 | ✅ | 代码去 `% len(ANNO_PALETTE)`，`>= len` 即 `raise ValueError("调色板耗尽…")`；实测超容量类型集抛错 |
| (c) legend 不得重复色 | ✅ | `annotate_boxes` 末尾显式单射断言 `raise`；生产 30/30 单射 |
| (d) 跳过 entry_door | ✅ | `ANNO_SKIP_TYPES = {partition, rug, entry_door}`；生产 legend 无 entry_door |
| (e) prompt 不含原始标识符 | ✅ | 见下 |
| 前 8 色冻结 | ✅ | 顺序/取值未变（`purple…magenta`），既有 legend 字节安全 |

**(e) 独立核验：** 我的初筛把 `sofa/media/curtain/plant` 报为「泄漏」，经查为**我的检查误报**——它们是 `en` 描述里的正常英文词（"a sofa"/"TV media console"/"floor-length curtains"/"potted plants"），非标识符泄漏。真实结论：全部 48 个 catalog 类型**均有 `en`**；生产 31 个家具类型中唯一非 catalog 者为 `entry_door`，已被跳过 → **无泄漏** ✅。生产 prompt 全文已复核，`entry_door` 已消失。

### 4.3 回归风险核查：调色板耗尽会否打断存量方案？

F002 把「静默撞色仍出图」改成「耗尽即硬阻断」。若存量房间类型数 >14，本批将**从能出图变成完全不能出图**（硬回归）。实测生产**全部 6 方案 × 全部房间**：

```
最大 distinct 类型数（去 SKIP 后）= 8   （r_live / r_bed_g）
超过  8 色的房间数: 0
超过 14 色的房间数: 0     → 无耗尽回归风险 ✅
```
附带结论：`entry_door` 跳过后 r_live 恰好降到 8 类 —— **当前生产数据靠「跳 entry_door」一项即可消除撞色**，8→14 扩容属纯余量（符合 D2「覆盖单房现实类型数」的预留意图）。

### 4.4 Soft-watch（不阻断 done，建议记入 backlog）

- **S1 —「画了盒但 prompt 无描述」的潜在静默面：** `_geometry_lock_prompt` 对无 `en` 的 legend 条目改为**静默 `continue`**。若某类型不在 `ANNO_SKIP_TYPES` 且无 `en`，则**盒照画、prompt 只字不提**，且 F003 门禁不检查此项 → 静默。已用对抗用例证实（构造非 catalog 类型 `service_hatch`：画出 lime 盒，prompt 完全不提 lime，门禁放行）。
  **当前不可达**：非 catalog 类型全集 = `{partition, entry_door, rug}` == `ANNO_SKIP_TYPES`，且 48/48 catalog 类型有 `en`。但该不变量**无任何测试/断言守护** —— 将来任何人往 CATALOG 加一条没写 `en` 的目录、或新增结构件忘了进 `ANNO_SKIP_TYPES`，即静默复发。建议：legend 条目无 `en` 时改为 `raise`（与 D2「描述不了就拒绝出图」同精神），或补一条 catalog `en` 完整性测试。
- **S2 — 最紧色对：** `cyan`/`teal` ΔE=28.03、`blue`/`navy` ΔE=32.61 为最紧两对，且**色名在语言上也相邻**（模型靠色名映射，"cyan" vs "teal" 的语义区分度弱于视觉区分度）。仅在单房 ≥9 类时才会用到（当前生产最大 8 类，不可达）。若将来真出现 9+ 类房间，建议优先复核这两对。

## 5. F003 — PARTIAL

### 5.1 有效性：双向均达标

**正证（真退化必被拦）** —— 用真 main 的无守卫投影模拟生产病灶引导图：

```
❗ 家具 curtain 的标注盒覆盖了 92% 画面 —— 相机标定与该家具位置严重不符
   (相机可能陷在家具体内), 引导图无有效位置信息
→ 拦下? True
```

**反证（门不得关死）** —— 不止交接建议的那一张照片，我按**生产真实全矩阵**（5 张已标定照片 × 6 方案 = 30 组合）跑门禁：

```
被拦下: 0/30  → 全部放行 ✅ 门没关死
```

**成本**：门禁耗时 **7ms**（256×192 探针），不调 AI、不花钱 ✅。**预算安全**：门禁位于 `_render_real_geometry_lock` 同步段、`_generate()` 之前，`except` 段 `_budget.release(house)` 退预扣 ✅。

**接入点** ✅（`main.py` `annotate_boxes` 之后）；**(c) `drawn==0` 保留** ✅（`main.py:2423`）；**(b) legend 重复色** ✅（由 `annotate_boxes` 的 `raise` 在门禁之前阻断，效果等价）。

### 5.2 spec D3 措辞偏离 —— 实现正确，spec 字面错误（加分项）

D3 字面写「任一单盒**投影包围盒面积** > 画幅面积 N%」。实现改用「**画幅内实际覆盖率**」。此偏离**不是取巧，而是必要**：

```
若按 D3 字面 bbox 实现, 生产(修复后)各盒 bbox/画幅:
    curtain   bbox/画幅 = 3155.25x   ← 会被字面实现误拦!!
    media     bbox/画幅 =    0.29x
    其余      bbox/画幅 <  0.06x
```
即：**若照 spec 字面实现，F001 修好的合法窗帘盒会被门禁误拦，等于「用一个 bug 换另一个」**。近平面裁剪后的合法盒坐标本就趋向无穷（D1 已明示），bbox 口径与 D1 自相矛盾。实现选择了正确口径并在代码注释写明理由 ✅。

### 5.3 阈值 `GUIDE_SINGLE_BOX_MAX_FRAME_FRAC = 0.9` 独立复核 —— 合理

```
生产 r_live 全部单盒画幅内覆盖率: 最大 = 4.36% (sofa)
                                 退化病灶 = 92.05% (curtain)
→ 合法最大值距阈值余量 85.6 个百分点; 合法区与退化区相差 ~21 倍, 阈值处于极宽平台区
```
- **不会误拦**：生产 30/30 组合放行，最大合法覆盖仅 4.36%。
- **不会漏放真退化**：本案 92% 被拦。理论上 60~90% 的「半退化」会漏放，但 F001 已根治主因，F003 定位是防御纵深兜底，且单件家具合法覆盖 >50% 的构图本身即无有效位置信息（拦掉也不算错）。**0.9 为保守但合理的取值** ✅。
- **判定一致性**：我做了扫描探针，全部样本均满足 `门禁命中 ⟺ 覆盖率 > 0.9`，无偏移/抖动 ✅。
- **探针精度**：256×192 低分辨率探针 vs 全分辨率，唯一类型件偏差 ≤ 0.12pp（dining_table 0.03 / media 0.03 / wine_cabinet 0.02 / curtain 0.12）—— 对 0.9 阈值（余量 85.6pp）绰绰有余 ✅。

### 5.4 PARTIAL 事由

**问题 1 — acceptance 明列的「阈值边界用例」缺失。**
F003 acceptance 明确要求三项单测：「本案退化输入必被拦且错误信息可操作；正常方案不被误拦（反证门没关死）；**阈值边界用例**」。新增的 4 条门禁测试为：正常布局放行 / 罩死画面被拦 / 合法裁剪盒放行 / 结构件跳过。**无任何一条逼近 0.9 边界**（实际样本覆盖率约 1.7% 与 ~100%，两端极值）。阈值一旦被改动（或探针分辨率变化导致偏移），现有测试**不会变红**。

**问题 2 — `DEGENERATE_GUIDE` 映射到 HTTP 500，且 `code` 字段无人消费。**
实测（走 `main.py` except 段真实分支顺序 + 真 `_layout_gate_response`）：

```
--- DEGENERATE_GUIDE (本批新增) ---
    HTTP 500
    body: {"error": "标注图/提示词生成失败: {\"ok\": false, \"error\": \"引导图退化，已阻断
           AI 出图：…请重新标定该空房照或更换照片。\", \"code\": \"DEGENERATE_GUIDE\"}"}
    前端可读 code 字段? False
--- STALE_CALIBRATION (同族既有, 同样是"请重新标定") ---
    HTTP 409
    body: {"ok": false, "error": "户型已变更，请重新标定", "code": "STALE_CALIBRATION"}
    前端可读 code 字段? True
```

根因：`main.py` except 段只显式识别 `validation`→409 与 `code == "STALE_CALIBRATION"`→409（`_layout_gate_response` 只认 `LAYOUT_NOT_READY`→400），其余一律落到 `500 + f"标注图/提示词生成失败: {exc}"` —— 结构化载荷被**字符串化塞进另一个信封的 error 字段**。

后果：
1. **语义错位**：这是用户可操作的输入侧问题（标定/照片不合适），与 `STALE_CALIBRATION` 同族，却报 500 服务器故障 → 污染生产错误监控、可能触发告警/重试。
2. **`"code": "DEGENERATE_GUIDE"` 是死字段**：全仓无任何读取方（前端 `studioApi.ts` 只对 `400 + LAYOUT_NOT_READY` 做结构化处理）。Generator 显然**打算**做结构化处理才写了这个 code，但未接线、也无任何测试覆盖 `main.py` 的接入（12 条新测试全部在 `test_perspective.py`，无一覆盖 HTTP 映射）。
3. **用户体验降级**：前端 `renderReal` 走 `throw new Error(parsed?.error)` → toast 显示 `生成失败:标注图/提示词生成失败: {"ok": false, "error": "…"}` —— 可操作文案确实**送达**了（且 `msg.includes('标定')` 会触发 reload），但包在两层「失败」前缀 + 裸 JSON 里。

**这正是本批自己引用的 `cross-layer-consistency.md` 模式**：守卫存在于一个 enforcement 点（raise），兄弟点（except 映射 / 前端）不知情。批次在修一个跨层一致性 bug 的同时，引入了一个（更轻的）同类缺口。

**修复点（均为小改，低风险）：**
1. `main.py` except 段把 `code == "DEGENERATE_GUIDE"` 与 `STALE_CALIBRATION` 并列返回 **409**（同族同解法：都是「请重新标定」），使 `code` 成为前端可读字段；
2. 补一条 **阈值边界单测**：构造覆盖率略低于/略高于 `GUIDE_SINGLE_BOX_MAX_FRAME_FRAC` 的盒，断言恰好放行/拦下（锁死阈值语义，防未来漂移）；
3. （建议）补一条覆盖 `main.py` 门禁接入的测试，断言 HTTP 状态码与 `code` 字段可读。

## 6. 超出本批范围的独立发现（**不影响本批判定**，建议单独立批）

### 【HIGH】`calibrate()` 的世界 z 轴符号未被约束 → 3/5 生产标定为 z 朝下，家具引导盒被向**地下**拉伸

**证据链（全部基于生产实物 + 真实空房照）：**

1. 生产标定 `417ae5589afe` 的相机位置 `eye = -Rᵀt = [12271.7, 13656.8, **-1382.2**]` —— 若 z 朝上则相机在**地板下 1.38m**（不合理）；若 z 朝下则相机高 **1.382m**（完全合理）。
2. 把 r_live 的子矩形分别投到 z=0 / z=-2700 / z=+2700 三个平面并**叠回真实空房照**目检（`scratchpad/indep/z_convention_check2.png`）：
   - **绿框 z=0 → 精确落在地面** ✅
   - **红框 z=-2700 → 精确落在天花板** ✅ ← 决定性
   - 蓝框 z=+2700 → 落在地面以下
   ⇒ 该标定 **+z 朝下**，负 z 才是「上」。
3. 但 `_box_polys` 一律把家具从 `z0` 拉伸到 **`+hz`**（正高度）⇒ 家具盒被拉向**地下**。逐件实测：生产 r_live **每一件**家具的顶面在画面上都**低于**底面（`dining_table` 底 v=875.7 → 顶 v=965.7；`wine_cabinet` 底 843.2 → 顶 967.5 …），即盒子朝下长。
4. 最直接的佐证：`wall_art`（`z0=1000, hz=1400`，本应挂在墙上 1.0~1.4m）实测被画在 **v=1047.8~1099.9**，即**地板上**而非墙上。而 prompt 里恰好有一句人工补丁在对冲这个错误：
   > "The framed wall art marker sits high on the wall: render it as flat framed artwork mounted on the wall … **not a freestanding object on the floor**."

   —— 需要专门告诉模型「别当成地上的东西」，正因为 marker 真的画在地上。
5. **符号不稳定**（比单张错更糟）：5 张已标定照片中 **3 张 z 朝下、2 张 z 朝上**：

   | photo | room | eye_z | 解读 |
   |---|---|---|---|
   | bcc615315c78 | r_live | -2266.8 | ⬇ z 朝下 |
   | dabcb9513905 | r_master | +874.3 | ⬆ z 朝上 |
   | 1537e6d83950 | r_cloak | +1515.1 | ⬆ z 朝上 |
   | 417ae5589afe | r_live | -1382.2 | ⬇ z 朝下 |
   | ae8e5b875fd9 | r_garden | -156.0 | ⬇ z 朝下（且高度 156mm 本身可疑） |

   标定的两个 anchors 均在 world z=0（地面）平面上 → **没有任何约束能钉住「上」是哪一侧**，解算器按输入任意取号。

**影响：** 对 3/5 的照片，AI 收到的彩盒只有正确的**地面 footprint**，垂直体积朝地下延伸 —— 而 prompt 却要求 "fills its box's footprint, **height** and orientation"。即高度/体积引导长期静默失真。

**与本批的关系：**
- **不是本批引入**（main 同样如此），且 spec §5 明文把 `calibrate` 排除在外 → **不作为 F001/F002/F003 的扣分项**。
- **不影响 F001 的正当性**：我验证过，即使把 z 方向改正，curtain 仍跨相机平面（深度 -233.8 vs -132.0）—— 因为窗帘是沿整面窗墙的 7.19m 长条，相机就站在窗边，其 footprint 本身横向绕过了相机。近平面裁剪独立必要 ✅。
- **但与用户原始报障同源**：用户报「餐桌位置错」。本批修掉的两个 bug 足以解释该次事故（餐桌盒 0% 可见）。修复后餐桌 footprint 引导已恢复，落位应显著改善；但**垂直体积引导对 3/5 照片仍是错的**，属残留风险。建议 Planner 单独立批处理（钉住 `calibrate` 的 z 符号，例如约束相机高度为正、或用已知层高/竖直线定向）。

### 【LOW，记账】`box_usability` 与 `_box_polys` 判的不是同一个盒

`box_usability` 硬编码底面 `z=0.0`，而 `_box_polys` 用 `_item_z0_mm(item)`（decor-b2 的逐件墙面带底面）。对 `wall_art`/`curtain` 这类 `z0≠0` 的件，「usable / in_frame_frac / near」判的盒与实际画的盒不是同一个。这解释了 spec 记载的 `curtain minDepth = -55` 与我实测的 `-132.0` 的差异（前者用 z=0 底面，后者用 z0=150）。两者都为负、不影响本批结论。属既有跨层不一致，非本批引入。

## 7. 判定与后续

| Feature | 判定 | 处置 |
|---|---|---|
| F001 | **PASS** | — |
| F002 | **PASS** | Soft-watch S1/S2 建议入 backlog |
| F003 | **PARTIAL** | features.json 改回 `pending`，见 §5.4 两个修复点 |

**status → `fixing`。** F001/F002 的实现质量高（byte-safe 严格成立；D3 口径的偏离是正确的工程判断，避免了把门关死）；F003 主体有效，仅差一条边界测试与一处错误码接线。

**[L2] 未执行：** 真实 AI 出图（无 `OPENAI_API_KEY`，且需用户授权 + 计费）。按 spec §5 与 decor-b2 同降级口径，走确定性几何 + 引导图重生目检，如实记账。修复后引导图的**模型实际响应**未经验证。

---

# 复验（reverifying, fix_rounds=1） — 2026-07-14

> 范围：首轮 F003 PARTIAL 两条整改 + 无回归确认。对照基线 `6f77d09`（我的首轮验收 commit），
> 本轮新增 `75548e5`（修复）、`9ee3caf`（口径订正）。
> 判定：**F001 PASS ／ F002 PASS ／ F003 PARTIAL（首轮两条均已闭合，新发现一条测试侧缺陷）** → status = `fixing`

## R0. 复验结论摘要

| 项 | 结果 |
|---|---|
| F003-① DEGENERATE_GUIDE 落 500 + code 死字段 | **已闭合 ✅**（端到端实证，且我用**未 stub 的真门禁**独立复现） |
| F003-② 阈值边界用例缺失 | **已闭合 ✅**（实测该盒覆盖 81.79%，两侧夹逼；`==0.9` 断言使阈值真承重） |
| 接入层测试补齐 | 已补，但**该测试自身引入新缺陷**（见 R4） |
| 口径订正（我的 §3.6） | **已闭合 ✅**（无裸残留，spec/acceptance 与实现口径一致） |
| 无回归 | **确认 ✅**（`aigc/perspective.py` 本轮**零改动**；生产实物复测数值与首轮完全一致） |
| **新发现（本轮引入）** | **`test_render_real_passes_when_guide_is_sane` 泄漏后台 job 线程 → 写入 git-tracked 的真实仓库 data 文件**（见 R4） |

L1：`floorplan_core` **154 passed**；`apps/api` **334 passed**（+3 新增）。ruff：仅 `main.py` I001 既有噪声（测试文件 All checks passed）。

## R1. F003-① —— 已闭合（独立端到端复现，不依赖 Generator 的 stub）

**修法核验：** `main.py` 新增 `_INPUT_GATE_CODES_409 = frozenset({"STALE_CALIBRATION","DEGENERATE_GUIDE"})`，except 段由逐个 `if` 改为集合成员判断。本轮 `main.py` 仅删除两行（旧 `if ... == "STALE_CALIBRATION"` 分支及其注释），改动外科式 ✅。

**独立性补强：** Generator 新增的接入层测试用 `monkeypatch.setattr(main.perspective, "guide_sanity_issues", lambda: [...])` **伪造门禁命中** —— 那只锁住了 `raise → HTTP` 接线，**未证明真门禁能端到端走到 409**。故我另写对抗用例（`scratchpad/indep/test_ev_e2e_gate.py`），**不 stub 门禁**，改用真实退化家具（实测单盒覆盖 **100.00%**，把相机包在体内）触发真门禁：

```
test_ev_real_gate_reaches_409_without_stub      PASSED
test_ev_gate_not_shadowed_by_layout_gate        PASSED
```
断言（全部通过）：HTTP **409**；`body["code"] == "DEGENERATE_GUIDE"` 可读；`body["ok"] is False`；载荷**未**被外层信封字符串化（`"标注图/提示词生成失败"` 不出现在 body 中）；`error` 以「引导图退化」开头且含「重新标定/更换照片」、**不再是嵌套裸 JSON**；`relay.calls == 0 and fal.calls == 0`（**未烧预算**）；且不被 `_layout_gate_response` 抢先误判成 400。

> 副产物：构造用例时先撞上 400 `LAYOUT_NOT_READY`（悬空柜先被布局门禁拦下）—— 属我的 fixture 问题，非产品缺陷；同时反证了门禁的**先后顺序合理**（布局门禁在引导图门禁之前）。

### R1.1 「集合式修法是否真堵住了『兄弟点不知情』模式？」—— 我的独立判断

**今天：确实堵住了（已穷举验证）。** 全仓扫描所有 `"code":` raise 载荷，能流经 render-real except 段的只有三个，全部有归宿：

| code | 归宿 | 状态 |
|---|---|---|
| `LAYOUT_NOT_READY` (main.py:1326) | `_layout_gate_response` → 400 | ✅ |
| `STALE_CALIBRATION` (main.py:2396) | 在集合 → 409 | ✅ |
| `DEGENERATE_GUIDE` (main.py:2441) | 在集合 → 409 | ✅ |

`REAL_NOT_READY` (main.py:2718) 是**直接 `return JSONResponse(400,…)`**、非 raise，不经 except 映射，本就正确 —— **无孤儿 code** ✅。
（main.py:546~614 与 scene.py:657 / lint.py:113 的 `"code"` 是 readiness/issue 记录构造器，非 raise 载荷，不涉及。）

**但结构上：是「往后挪了一格」，不是「机制化关死」。** 依据 harness-rules.md §机制化守门 的判据（「写在文件里的规则」依赖自觉，「装进工具链的规则」才是强制）：

- `_INPUT_GATE_CODES_409` 仍是**人工维护的登记表**，其注释「**新增门禁 code 必须登记到此集合**」本质上是**写给人看的纪律**，即仍属「知情自律」。
- raise 点与映射点**仍是两处**，无任何机制强制二者一致。新写一句 `raise ValueError(json.dumps({..., "code": "FOO"}))` 照样能编译、跑通、测试全绿，然后**静默落 500** —— 与首轮病灶同一失效模式。
- 客观改进（值得肯定）：从「散落的逐个 if」收敛为**单一命名锚点 + 写明不变量的注释**，新增码从「加分支」降为「加一个 token」，且失效说明就写在修复该去的地方。

**结论：** 按**订正后的 F003 acceptance**（明文写「登记进 `_INPUT_GATE_CODES_409`」）—— 实现与验收标准**一致，判 PASS**。结构性硬化（如让 code 与状态码同生：`class InputGateError(ValueError): status=409` + `except InputGateError as e: return JSONResponse(e.status, e.payload)`，使「新增门禁」在语法上就不可能忘记登记）属**改进项而非缺陷**，建议入 backlog，不阻断本批。

## R2. F003-② —— 已闭合（阈值确实承重）

新增 `test_guide_sanity_threshold_boundary_is_load_bearing`。独立复算该盒（`wardrobe dx=400 dy=400 w=300 h=300 z=2500`，`_synth_camera`）：

```
实测覆盖率 = 81.79%   (注释宣称 ~82% —— 属实 ✅)
  默认阈值 0.90 -> 放行   (测试断言: 放行) ✅   距阈值 8.21pp
  下调阈值 0.80 -> 拦     (测试断言: 拦)   ✅   距阈值 1.79pp
```
**两侧夹逼**，是名副其实的边界用例（对比首轮：样本只有 1.7% 与 ~100% 两端极值）。

**承重性验证（我的首轮原话是「阈值漂移不会让测试变红」）：** 逐一模拟阈值改成 0.70/0.75/0.80/0.85/0.88/0.92/0.95/0.99 —— **任一改动都会让该用例变红**，由显式的 `assert P.GUIDE_SINGLE_BOX_MAX_FRAME_FRAC == 0.9` 挡下。即阈值已被钉死，不能悄悄漂移 ✅。

**「82% 的选取是否站得住」：** 站得住。
- 距 0.90 有 8.21pp 余量 —— 远大于我首轮实测的探针误差（唯一类型件 ≤0.12pp），不会因栅格抖动误红。
- 距 0.80 仅 1.79pp（较紧），但该侧一旦漂移即变红，属**响亮失败**而非静默 —— 且触发条件是有人改了探针/几何，本就该复核。
- 补充：`monkeypatch.setattr(P, "GUIDE_SINGLE_BOX_MAX_FRAME_FRAC", 0.80)` 生效可靠 —— `guide_sanity_issues` 在调用时读模块全局，非闭包捕获 ✅。

## R3. 口径订正与无回归 —— 均确认

**口径订正（我的 §3.6）✅：** 全仓扫描 `包围盒`，spec + features 共 3 处命中，**全部位于显式「订正/注意」说明中**（明确指出旧口径错误并给出正确判据），**无裸判据残留**。spec §D3 现为「任一单盒**在画幅内的实际覆盖率** > N%」+ 订正引注；features F001/F003 acceptance 同步订正。

**订正后的 F001 acceptance 是否真被满足（按新口径重测生产实物）：**

```
curtain 画幅内覆盖 = 1.66%           (首轮同值, 未回归 ✅)
无面双轴罩死画面?  True              ✅
存活面深度全 >= NEAR_MM(10.0)?  True  ✅
餐桌盒覆盖 = 1.46%                   (首轮同值, 未回归 ✅)
```
→ spec/acceptance 现已**跟上实现**，我首轮认定的「实现偏离 spec 字面是必要的」矛盾已消除 ✅。

**无回归 ✅：**
- `apps/api/aigc/perspective.py` 本轮 **零改动**（投影/近平面裁剪/调色板逻辑未被触碰）。
- 本轮产品代码改动**仅** `main.py`（门禁码集合 + except 段）。
- 生产实物复测：F002 生产 **30/30** 组合 legend 仍单射且无 `entry_door`；F001 数值与首轮逐位一致。
- 两套 pytest 全绿（154 + 334）。

## R4. 【新发现，本轮引入】接入层反证测试泄漏后台 job → **写入 git-tracked 的真实仓库 data**

`test_render_real_passes_when_guide_is_sane` 断言 `r.status_code == 200` 后**直接返回，未 `_wait` 排空后台 job**。而该文件**自己的既有约定**是：所有 7 个 200-path 测试（line 321/395/420/448/479/497/518）**一律** `_wait(c, r.json()["job_id"])`。

**实证（sha256 隔离比对，逐条单跑）：**

| 测试 | 真实仓库 `data/projects/D/schemes/default/renders.json` |
|---|---|
| 既有 200-path 测试（**用 `_wait`**） | `b5ca092eec2b` → `b5ca092eec2b` **未污染 ✅** |
| **新增 `guide_is_sane`（无 `_wait`）** | `b5ca092eec2b` → `b597d818c3ec` **污染真实 data ❗** |
| 新增 409 测试（阻断路径，不起 job） | 未污染 ✅ |

**机理（已用 traceback 坐实）：** `client_fal` 靠 `monkeypatch.setattr(main, "DATA_DIR", str(tmp_path/"projects"))` 建沙箱；测试函数一返回，monkeypatch **立即拆除**，`main.DATA_DIR` 复原成**真实仓库目录**。而后台 job 线程仍在跑，落盘时解析到的已是真实目录 → 写进仓库。同一机理的第二个证据：拆除后 `main.acceptance.evaluate_geometry_lock` 也复原成**真函数**，于是**未被 stub 的真 acceptance** 在后台线程里跑了起来（这正是本轮新出现的 2 条 `RankWarning: Polyfit may be poorly conditioned` 的来源 —— 首轮基线 `6f77d09` 全套 331 tests **零 warning**）：

```
jobs.py:68 in _run  ->  main.py:2504 in _generate
  -> acceptance.py:164 in evaluate_geometry_lock   ← stub 已被拆除, 跑的是真函数
    -> acceptance.py:88 in _gain_fit -> np.polyfit -> RankWarning
```

**危害：**
1. **越过测试沙箱写 git-tracked 文件**：`data/projects/` 是仓库种子快照。每次跑全套都会静默弄脏工作树，开发者可能误提交测试残留。**这个坑已经真实咬过人** —— 仓库现存 stash：`本地测试残留 renders.json (待用户决定去留)`，与本机实测同一文件。精神上也违反 CLAUDE.md 红线「e2e never writes `data/projects`. Keep it that way.」
2. **线程泄漏 → 套件不确定性**：拆除后执行未 stub 的真代码，时序不定，是后续 CI flaky 的经典来源（`framework/patterns/testing-env-patterns.md` §14 fire-and-forget 测试 race 模式）。
3. **潜在（本次未观测到，属竞态窗口）**：teardown 同样会把 `main.get_provider` 复原成**真工厂**。本次观测到的时序是「`_edit_once` 时 fake 仍在 → acceptance 时已拆除」，故未打真 provider；但线程启动更慢的机器（CI 负载高）可能在 `_edit_once` 前就越过 teardown → **在配置了 `OPENAI_API_KEY` 的机器上发起真实计费调用**。讽刺的是，F003 的存在意义正是「不静默烧 AI 预算」。

**修复（一行，且是该文件自己的既有约定）：**
```python
r = c.post("/api/projects/D/schemes/default/render-real", json={"photo_id": photo["id"]})
assert r.status_code == 200, r.text
job = _wait(c, r.json()["job_id"])          # ← 补此行: 排空后台 job, 勿把未 stub 的线程泄漏出测试
assert job["status"] == "done", job          # (可选) 顺带把"放行后真能出图"也钉住, 反证更有力
```
**附带收益：** 现在这条反证只断言了同步段的 200，补 `_wait` 后才真正验到「门禁放行 → 正常出图链路不受影响」，与其 docstring 宣称的语义一致。

**清理建议：** 修复后跑一次 `git checkout data/projects/D/schemes/default/renders.json` 复位（该文件当前的脏状态含历史残留 + 本次验收实测所致，均为测试残留，非有效变更）。

## R5. 复验判定

| Feature | 判定 | 说明 |
|---|---|---|
| F001 | **PASS** | 本轮零改动，生产实物复测未回归；订正后的 acceptance 口径亦满足 |
| F002 | **PASS** | 本轮零改动，生产 30/30 复测未回归 |
| F003 | **PARTIAL** | 首轮两条 **均已闭合**（①端到端 409 独立实证 ②阈值真承重）；**新发现**：本轮新增的反证测试泄漏后台 job 并写入 git-tracked 真实 data（R4，一行修复） |

**status → `fixing`。** 需说明的是：**产品代码（F001/F002/F003）本轮已全部正确**，R4 是**测试侧**缺陷，不影响生产行为。仍判 PARTIAL 而非 PASS + soft-watch 的理由：该缺陷**可复现、已实证越过沙箱写 git-tracked 文件**、违反该文件自身 7/7 的既有约定与 CLAUDE.md 红线精神、且已有 stash 证明它真实造成过困扰；修复成本仅一行。

**Soft-watch（不阻断，建议入 backlog）：**
- **S3 —** `_INPUT_GATE_CODES_409` 仍是人工登记表（R1.1）。建议后续用 `InputGateError` 异常类让 code 与状态码同生，把「知情自律」升级为「语法强制」。
- 首轮 S1（`_geometry_lock_prompt` 无 `en` 静默 `continue` 的潜在静默面）、S2（cyan/teal ΔE=28 最紧色对）仍然有效。

**[L2] 未执行：** 真实 AI 出图（无 key、需授权计费），同首轮口径。

**超范围（不计入本批，已由编排者采纳报用户单独立批）：** `calibrate()` 世界 z 轴符号未约束（3/5 生产标定 z 朝下，家具盒朝地下拉伸）。

---

# 复验 2（reverifying, fix_rounds=2） — 2026-07-15

> Evaluator：隔离 evaluator subagent（fresh context，`local/evaluator-subagent`）— **与前两轮为不同上下文实例**
> 范围：**仅 R4 是否闭合 + 无回归**（F001/F002 已 PASS，不重做全量）。对照基线 `f10c2dc`（上轮验收 commit），本轮新增 `6ac7afd`（R4 修复）。
> 判定：**F001 PASS ／ F002 PASS ／ F003 PASS** → status = `done`

## V0. 复验 2 结论摘要

| 项 | 结果 |
|---|---|
| R4 污染是否止住 | **已闭合 ✅**（全套 + 单跑双向实测；且有**阳性对照**背书检测非盲） |
| R4 warning 是否归零 | **已闭合 ✅**（334 passed，全量 stdout+stderr 捕获中 `warning` 出现 **0** 次） |
| 线程泄漏是真消除还是被 `_wait` 掩盖时序 | **真消除 ✅**（结构性：写-后-置位序；并用人为拖慢落盘 0.6s 的对抗用例实证） |
| 反证测试是否真验到「门禁放行→出图链路正常」 | **是 ✅**（provider 真被调用，`furniture_locked=6`，与 docstring 语义一致） |
| 无回归（本轮产品代码零改动） | **确认 ✅**（`git diff f10c2dc..HEAD` 产品路径为空） |

L1：`floorplan_core` **154 passed**；`apps/api` **334 passed**；**0 skipped**；`rsvg-convert` 存在 → golden 快照 5 条**实跑**非 skip；ruff 对改动测试文件 `All checks passed!`。

## V1. R4-① 污染止住 —— 已闭合（附**阳性对照**，证明检测非盲）

**关键方法论：** 「跑完没脏」单独不足以证明修复有效 —— 也可能是我的检测方法本身失明。故我先建**阳性对照**：用 `git worktree` 检出上轮 buggy 版本 `f10c2dc`，**同一条命令**跑同一条测试。（`main._default_data_dir()` 由 `main.py` 位置反解 `parents[2]/data/projects` → worktree 内跑只脏 worktree，主仓隔离 ✅ 实测主仓 sha 与 `git status` 全程未动。）

| 场景 | `data/projects/D/schemes/default/renders.json` | `git status data/projects/` | RankWarning |
|---|---|---|---|
| **阳性对照** `f10c2dc`（无 `_wait`）单跑 | `4f53cda18c2b` → **`c87679ce31fc`** ❗污染复现 | ` M` 脏 | **2 条**（会后 stderr） |
| **HEAD** `6ac7afd` 单跑 `guide_is_sane` | `4f53cda18c2b` → `4f53cda18c2b` ✅ | 干净 | 0 |
| **HEAD** 跑**全套** api（334） | `4f53cda18c2b` → `4f53cda18c2b` ✅ | 干净 | 0 |

全仓工作树在全套跑完后 `git status --short` **完全干净**；`data/projects` 整树 hash 亦逐位不变（`85f8e74378350a5d` → `85f8e74378350a5d`）。

→ 检测方法**已被阳性对照证明有效**，且差分归因明确：**是这一行 `_wait` 止住了污染**，非环境偶然 ✅

## V2. R4-② warning 归零 —— 已闭合（并订正一条检测陷阱）

**334 passed；全量输出（stdout+stderr 合并捕获）中 `warning` 关键字出现 0 次**，`RankWarning` / `polyfit` / `warnings summary` 均无命中。

> **⚠ 方法论订正（供后续读者）：** 这 2 条 `RankWarning` **不会出现在 pytest 的 `warnings summary` 里**。阳性对照实测显示它们是在 pytest 打印完 `1 passed` **之后**才作为**裸 stderr** 冒出来的 —— 因为泄漏线程是在 **session 结束后**才跑到 `np.polyfit`，早已超出 pytest 警告插件的捕获窗口。**故「看 pytest warnings summary 是否为空」来验此项会漏报**，必须重定向合并 stderr 全量 grep。这也反向印证了 R4 的机理判断（真 acceptance 在 teardown 之后的线程里跑）。

## V3. R4-③ 线程泄漏：**真消除**，不是被 `_wait` 掩盖时序 —— 我的独立判断

这是本轮最值得较真的一问（`_wait` 是**排空**还是**恰好等够了**？）。结论：**是排空，且由结构保证**，不靠运气。

**结构性论证（读码得出，非采信叙述）：**

1. `jobs.py:65 _run`：`result = fn()` → **返回之后**才 `self._set(job_id, status="done", result=result)`。即 **`done` 置位严格晚于 `fn()` 全部跑完**；其间 `_set` 只在锁内改 registry dict，**不碰产品代码/磁盘**。
2. `main.py:2617-2618` `_generate` 的**最后一句正是落盘**，且 `DATA_DIR` 是**调用时**读模块全局（这恰是 teardown 复原后写穿到真仓库的原因）：
   ```python
   scheme_store.append_render(DATA_DIR, house, scheme_id, record)
   return record
   ```
3. `_wait` 轮询至 `status in ("done","error")` 才返回。

⇒ **`_wait` 返回 ⟹ `fn()` 已 return ⟹ 落盘早已完成，且完成于 monkeypatch 仍在时**。这不是时序巧合，是「写-后-置位」的偏序。

**对抗实证（`scratchpad/indep/test_ev_r4_drain.py`，不入库）：** 我把落盘**人为拖慢 0.6s** 撑开窗口，记录两个时刻：

```
[Q3] t_write_done <= t_wait_return : True  (差 0.018s)
[Q3] 落盘 DATA_DIR = /private/var/.../pytest-874/test_ev_wait_is_a_real_drain_n0/projects  (沙箱内)
```
断言全过：落盘**发生在 `_wait` 返回之前**；落盘当时看到的 `DATA_DIR` **在 tmp 沙箱内**、`"/grandtianfu/data/projects"` 不在其中 ✅

**诚实边界（不阻断，见 S5）：** `_wait(t=10.0)` 超时会 `raise AssertionError("job 超时")` —— 此时线程仍在跑、teardown 仍会发生，**理论上仍可污染**。故 `_wait` 的严格语义是「把静默污染转成**响亮红灯**」+ 把竞态窗口收敛到 10s 内，而非在语法上禁止竞态。这是该文件 **8/8 一致的既有约定**，非本批引入，不构成回归。另：`ThreadPoolExecutor` 的 worker 线程本身从不 join（池内闲置存活），但**闲置线程不写盘**，危害向量（写穿沙箱 / 真实计费调用）已关闭。

## V4. R4-④ 反证测试是否真验到「放行 → 出图链路正常」—— 是

补 `assert job["status"] == "done"` 前，这条反证**只验到同步段 200**（门禁没拦），完全没碰出图链路 —— 与 docstring 宣称的「正常出图链路不受影响」不符。补后我独立核验其**实际验到了什么**：

```
[Q4] provider 调用数 = relay 1 + fal 0 = 1        ← 真走到了出图调用
[Q4] job.result.mode=real-photo method=geometry-lock furniture_locked=6
```
即：放行后 provider **真被调用**、产出 `real-photo` 记录、**真锁住 6 件家具**。docstring 语义与断言现已一致 ✅

**附带增益（值得记一笔）：** 该修复不只是「补个清理动作」—— 它把 F003 acceptance 里「**正常方案不被误拦（反证门没关死）**」这一条**从形同虚设变为真承重**：修前即使出图链路被完全打断，该测试照样绿。

## V5. R4-⑤ 无回归 —— 确认

- **产品代码本轮零改动（机械核验，非采信叙述）：**
  ```
  git diff --name-only f10c2dc..HEAD -- apps/api/aigc/ apps/api/main.py apps/api/schemes.py \
      apps/api/baselines.py apps/api/furnish.py apps/web/ packages/
  → (空)
  ```
  全部改动仅 3 个文件：`apps/api/tests/test_render_real_geometry.py`（+6 行）、`features.json`、`progress.json`。
- 自首轮基线 `6f77d09` 起，产品侧仅 `apps/api/main.py` 被动过（fix_round1 的门禁码集合），**`aigc/perspective.py` 全程零改动** → F001（投影/近平面裁剪）与 F002（调色板/撞色/结构件）的实现自其 PASS 判定以来**逐字未变**，不可能回归；上轮已用生产实物复测（curtain 1.66% / 餐桌 1.46% / 30 组合 legend 单射）逐位一致。
- 两套 pytest 全绿（**154 + 334**），**0 skipped**；`rsvg-convert` 存在故 golden 快照 **5 条实跑**（非静默 skip）；perspective + render_real_geometry 焦点 **61 passed**。

## V6. 附加独立核查：R4 是**孤例**还是**一类**？（超出交办范围，我主动做的）

一行修复止住了这一条，但**同类缺陷是否还潜伏在别处**？我对全套做了穷举扫描：

```
读 job_id 的测试文件: test_furnish_api / test_render_ai / test_render_real /
                      test_render_real_geometry / test_jobs
每个文件中「读了 job_id 却未喂进 _wait(...)」的位置: 全部为 0
→ 所有 async job 测试点 100% 配对 _wait ✅ 该 bug 类今天在全仓已关闭
```
（与全套跑完零污染、零 warning 的实测结果互证。）

**但结构上仍是「知情自律」，非机制强制** —— 与上轮 S3 同构：`client_fal` fixture 用的是 `return` 而非 `yield`，**没有 teardown 排空钩子**。将来任何人新写一条 POST 到 async 端点却忘了 `_wait` 的测试，照样能绿、照样静默写穿 `data/projects`。记 **S4**（下方），不阻断本批。

## V7. 复验 2 判定

| Feature | 判定 | 说明 |
|---|---|---|
| F001 | **PASS** | 本轮产品代码零改动（`perspective.py` 自首轮起逐字未变）；154+334 全绿、0 skip、golden 实跑 |
| F002 | **PASS** | 同上，零改动零回归 |
| F003 | **PASS** | 首轮两条（409 接线 / 阈值承重）上轮已闭合；**R4 本轮闭合**（阳性对照差分实证 + 排空语义结构性证明 + 反证测试现真承重） |

**全部 PASS → status `done`，signoff：`docs/test-reports/render-fix-b1-signoff-2026-07-15.md`。**

**[L2] 未执行（如实记账）：** 真实 AI 出图未验证（无 `OPENAI_API_KEY`，且需用户授权 + 计费）。按 spec §5 与 decor-b2 同降级口径，走确定性几何 + 引导图重生目检。**修复后引导图的模型实际响应未经验证** —— 上线后建议人工目检首张实拍图。

---
*本报告（含复验段与复验 2）由隔离 evaluator subagent 直接写入，结论未经主上下文改写（harness-rules.md 铁律 12）。*
