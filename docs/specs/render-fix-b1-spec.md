# render-fix-b1 — 第7步实拍引导图退化修复

> 批次类型：Bug 修复（spec 非硬性，但本批含非平凡几何设计，故成文）
> 来源：用户报「最新效果图餐桌位置错误」（2026-07-14）。根因分析见下 §1，实物证据取自生产
> `D/scheme_ai_20260714_130354_01_baec` 的 render `412b6acc`（2026-07-15T03:59:24Z）。

## 1. 背景与根因（已实证）

用户报第7步实拍效果图中餐桌落位错误。取生产实物（标定 + 家具 + 引导图 + 存档 prompt）复现，定位到**两个独立 bug**，任一都足以导致餐桌错位；另发现一处静默失败面。

### P0 —— 盒投影退化：窗帘盒炸开糊死整张引导图（主因）

`r_live` 的 curtain 贴窗，而空房照相机就站在窗边 → 该盒有顶点**落在相机背后**：

```
curtain  minDepth = -55mm     投影 u: -8903..6580   v: -47843..111194   (画面 2048x1536)
```

`perspective._box_polys` 直接 `uv[0]/uv[2]`，**无近平面守卫**；除以负深度 → 多边形穿过相机翻转、炸开到 ~1e5 px → 品红色覆盖整幅画面，把餐桌紫盒在内的所有盒全部埋掉。AI 收到的引导图无有效位置信号 → 自由发挥。

**关键结构缺陷：** 兄弟函数 `box_usability` **已正确检测**该退化（顶点深度 `<= 1e-6` → `usable: False`），但 `annotate_boxes` 只把该结果用于 **prompt 措辞降级**（`entry["partial"] = True`），**仍照常调用无守卫的 `_box_polys` 把炸开的盒画上去**。即：检测到了 ≠ 拦住了 —— 属 `framework/patterns/cross-layer-consistency.md` 记载的「守卫存在于一个 enforcement 点、兄弟点没用」模式。

### P1 —— 调色板撞色：紫色同时 = 餐桌 + 绿植

`ANNO_PALETTE` 仅 **8 色**，`annotate_boxes` 用 `ANNO_PALETTE[len(color_by_type) % len(ANNO_PALETTE)]` **回绕且无撞色检测**。`r_live` 跳过 rug 后恰好 **9 种**类型 → 第 9 种 `plant` 回绕撞上第 1 种 `dining_table`。

生产存档 prompt 原文（render `412b6acc`）：

```
purple box = a long dining table with chairs; blue boxes = a sofa (2 pieces, one per box);
orange box = a coffee table; green box = a low TV media console; cyan box = entry_door;
red box = a wine cabinet; yellow boxes = framed wall art (2 pieces, one per box);
magenta box = floor-length curtains; purple boxes = potted plants (3 pieces, one per box).
```

同一句内两条 purple 映射；画面上 4 个紫盒（1 餐桌 + 3 绿植）语义不可区分。

附带：`entry_door` 是结构件却进了彩盒（`annotate_boxes` 只跳 `partition`/`rug`），且目录无 `en` → prompt 漏出原始标识符 `cyan box = entry_door`。

### 静默失败面

该 render 的 `auto_check` 打分 **0.967 / ok:true 通过** —— 现有验收不校验引导图本身的健全性，故上述灾难完全静默，用户只能靠肉眼发现。

## 2. 功能范围

| ID | 内容 | 层 |
|---|---|---|
| F001 | `_box_polys` 近平面裁剪（P0 主因） | `apps/api/aigc/perspective.py` |
| F002 | 调色板扩容 + 撞色断言 + 跳 `entry_door` / 无 `en` 件（P1） | `perspective.py` + `main.py` |
| F003 | 引导图健全性前置门禁（防呆，堵静默失败面） | `perspective.py` + `main.py` |

## 3. 关键设计决策

### D1 — F001 用「近平面裁剪」而非「跳过不可用盒」

盒子**部分可见**时（curtain 正是如此：大部分在画面内，仅少许越过相机平面）应画其**可见部分**，而非整件丢弃。丢弃会让重要件（窗帘/贴镜头电视柜）失去盒引导，等于用一个 bug 换另一个。

**实现：** 在**相机系**做单平面 Sutherland–Hodgman 裁剪，再投影：

1. 8 个盒顶点求相机系坐标 `c = R @ w + t`（**不乘 K**）
2. 每个面（4 点多边形）对平面 `z = NEAR_MM` 裁剪，保留 `z >= NEAR_MM` 部分；交点线性插值
3. 裁剪后顶点数 `< 3` → **整面丢弃**（完全在相机背后）
4. 存活顶点再乘 K 投影：`uv = K @ c; (uv[0]/uv[2], uv[1]/uv[2])`
5. 面深度 = 裁剪后顶点 `z` 均值

**byte-safe 铁要求：** 盒**完全在近平面之前**时，裁剪是 no-op（顶点与顺序逐字不变）→ 投影结果与改造前**逐字节一致**。既有 golden / 快照 / decor-b2 断言不得变。

`NEAR_MM` 取值由 Generator 实测定（建议 1~50mm 量级）：需同时满足 (a) 不误裁真实可见盒 (b) 裁剪顶点投影坐标不至于大到 PIL 绘制异常。裁剪后坐标偏大属正常（近平面顶点本就趋向无穷），几何仍正确。

### D2 — F002 撞色**不得静默**

扩容调色板后仍须**显式断言**：同一 legend 内两条目不得同色。palette 耗尽时**不回绕**，按以下降级（不得静默出错图）：

- 首选：调色板扩到足够宽（≥14 色，覆盖单房现实类型数），并保证颜色**视觉可区分**（模型要靠颜色认盒）
- 兜底：仍耗尽 → 明确报错阻断出图（错图比不出图更贵：烧 AI 预算 + 误导用户）

`entry_door` 按结构件跳过（与 `partition` 同列）。任何 `catalog.appearance/en` 缺失的类型不得把原始标识符写进英文 prompt。

### D3 — F003 门禁判据

送 AI 之前校验引导图健全性，任一命中即**阻断并给可操作提示**（提示重新标定 / 换空房照）：

- 任一单盒**在画幅内的实际覆盖率** > **N%**（阈值由 Generator 用生产实物定，须让本案 curtain 的退化盒必被拦、正常大件如沙发/餐桌不误拦）

  > **订正（首轮验收 §3.6）：** 本条初稿写的是「投影**包围盒**面积 > 画幅面积 N%」，**该口径错误**，照字面实现会误拦 F001 修好的合法窗帘——近平面裁剪后的合法盒坐标本就趋向无穷（见 §D1），其 bbox 可达画幅 3155 倍，但画幅内实际只覆盖 1.66%。判据必须用**画幅内实际覆盖率**（低分辨率探针栅格估算即可），不得用包围盒。
- legend 出现重复颜色（F002 的防御纵深）
- `drawn == 0`（已有）

门禁属**确定性输入侧检查**，与 `aigc/eval_scenarios.py` 既有 lint/场景校验同族，不调 AI、不花钱。

## 4. 验收要点（Evaluator）

1. **P0 复现→修复**：用生产实物（photo `417ae5589afe475a9bdfa4b310c32986` 标定 + `scheme_ai_20260714_130354_01_baec` 家具）重生引导图 —— 修复前 curtain 盒覆盖全画幅、修复后仅覆盖其真实可见区，餐桌紫盒可见。
2. **byte-safe**：完全可见的盒投影逐字节不变；两套 pytest + golden 快照全绿。
3. **P1**：同一 legend 不再出现重复颜色；`entry_door` 不进盒；prompt 不含原始标识符。
4. **反证（防止把门关死）**：正常方案（无退化盒、类型数 ≤ 调色板）仍能正常出图，不被 F003 误拦。
5. **门禁有效性**：本案退化输入必被 F003 拦下且报错可操作。

## 5. 边界

- 不改标定算法本身（`calibrate`）—— 本案标定并非"错"，是相机贴近窗帘导致盒越过相机平面，属投影实现缺陷。
- 不调 AI、不跑真实出图（无 key / 需授权）；验收走确定性几何 + 引导图重生目检，与 decor-b2 同降级口径。
