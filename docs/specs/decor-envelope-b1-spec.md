# decor-envelope-b1 — 第7步 auto_check 残余误报：窗帘建模 + allowed 上沿容差

**批次：** decor-envelope-b1
**来源：** `backlog.json` → `BL-decor-allowed-envelope`（high，用户 2026-07-15 立项 + 选定本批）
**前置：** calib-z-b1（标定 z 轴，已上线 `a73f92d`）；本批是其**下游残余项，根因不同**——不是回归。

---

## 1. 生产实证（重放已自证保真）

生产 render `fc8823be`（2026-07-15T21:55Z，baseline `v7` / `r_live`，engine `a69ad7f` = calib-z-b1 修复后代码 + 自愈后标定）：`auto_check` 仍 `ok:false`。本地重放**逐字复现**生产 verdict（`ok=False` / `score=0.95` / 坏块 `3/96`）——重放保真已自证，结论有据。

**坏块演进（三个阶段）：**

| 阶段 | 坏块 | score |
|---|---|---|
| calib-z-b1 修前 | 20/111 | 0.85 |
| 只修代码 | 9/96 | — |
| 代码 + 存量标定全修（今天的生产） | **3/96** | **0.95** |

判据是 `acceptance.py:246`：`struct_ok = tiles_bad < _NEW_EDGE_TILES_MIN`（`=3`）⇒ 本张恰好 3 块，**差一块过门**。

**3 块逐块归因，全部是家具本身**（非模块注释所设想的「窗景重绘噪声」）：

| # | 原图坐标 | 件 | 性质 |
|---|---|---|---|
| 1 | (384,512) | 挂画 | 新边缘**全在 allowed 包络 12px 内** —— 画框上沿略高于 allowed 封顶 |
| 2 | (512,512) | 挂画 | 同上，**8px 内** |
| 3 | (0,256) | 窗帘 | 有新边缘 **>32px** 远离任何 allowed 盒 = **建模缺口**，非「略微溢出」 |

**代价：** 误报触发重试（该张 `attempts=2`）⇒ 每次实拍出图**烧 2 倍 AI 预算**，且给用户一个假的「未通过」标记。

---

## 2. 根因

### 2.1 窗帘（坏块 #3）：把「轴测压扁世界」的数字照抄进了「实拍真实毫米世界」

本仓存在**两个 z 世界**，各自自洽，但数字**不可互借**：

| | 轴测 / dollhouse 世界 | 实拍 / perspective 世界 |
|---|---|---|
| 墙高 | `WALL_H = 1450`（`axon.py:21`）—— 为看清内部**刻意压扁** | 真实层高 **≈2700**（calib-z-b1 生产实测：地面 v=1161 → 天花板 v=571） |
| 家具高 | 钳到 `1450-50=1400`（`scene.py:21-23`） | 真实值：`wardrobe: 2000` / `bookshelf: 2000`（`perspective.py:63-68`）—— **2000 > 1450，在压扁世界里立不住** |
| 数据 | D 户型 `meta.wall_height_mm = 1450`（压扁值） | 无层高概念（本批引入） |

`axon.py` 的窗帘 SPECS（`:643-648`）：帘头盒 `z:(1400,1450)` + 长幔 vplane `z:(150,1400)` —— 即在压扁世界里，窗帘占 `150..1450`，是「几乎顶天立地的落地帘」（占 1450 墙高的 **90%**）。

而 `perspective.py` 的：

```python
_DEFAULT_HEIGHT_MM = {..., "wall_art": 1400, "curtain": 1450}   # :63-68  ← 注意: 这是绝对顶高, 非高度
_ITEM_Z0_MM = {"wall_art": 1000, "curtain": 150}                 # :72
```

**正是那两个数字的逐字照抄**（`:62` 注释自陈「顶高对齐 axon SPECS 渲染画框 z」）。`_box_polys`（`:294-303`）证实 `hz` 是**绝对顶高**（`base` 在 `z0`、`top` 在 `hz`），故实拍世界的窗帘盒 = **150..1450mm**。

**在层高 2700 的真实照片上，同一个盒子 = 从脚踝到胸口的下半墙。**

而管线的另外两处**同时**在告诉模型画落地帘：
- `catalog.py:193` 窗帘的 `en` = **`"floor-length curtains"`**（进 prompt）
- `axon.py:1252` 南墙窗**无条件强制升级为 `full`**（落地窗）

⇒ 模型**老老实实照做**，画出从天花垂到地面（~2700mm）的帘子；盒子比实物**矮了约 1.25m**，上沿之外的部分自然被判「盒区外出现新结构」。**这不是容差不够，是建模自相矛盾。**

### 2.2 挂画（坏块 #1/#2）：allowed 上沿容差不足

`acceptance.py:67`：`_WALL_BAND_ALLOWED_Z = {"wall_art": 1500, "curtain": 1550}` —— 在渲染顶（1400/1450）之上给 100mm 余量，供「模型画框略高于渲染顶」不误判（decor-b2 审查 #3）。实测该余量**不够**：画框上沿溢出 8~12px。

注：挂画的 `1000..1400` 在**实拍真实毫米**下**恰好是合理的**（胸口高度的画）——它是「借错数字但碰巧不出错」。故本批**不动挂画的盒几何**，只调容差。

### 2.3 结构性隐患：`_WALL_BAND_ALLOWED_Z` 是一张双写登记表

`{wall_art: 1500, curtain: 1550}` 与 `_DEFAULT_HEIGHT_MM` 的 `{1400, 1450}` 是**同一组事实写了两遍**（各 +100）。一旦改渲染顶而忘了改这张表，allowed 盒会**比渲染盒还矮** —— 比今天更糟。

这正是刚沉淀的 `framework/patterns/cross-layer-consistency.md` §「集合式修法是把知情自律往后挪一格」所描述的形态。**本批必须先把它机制化派生掉，再改数字**（见 §3 F001→F002 顺序）。

### 2.4 「对齐 axon SPECS」是愿望，不是机制（已查实）

- `perspective.py` 的 import 只有 `io` / `dataclasses` / `numpy` + 函数内局部 `PIL` —— **不 import `floorplan_core`**。
- 反向：`packages/floorplan_core/` 全仓 grep `perspective` 只命中**一条注释**（`catalog.py:299`），零 import、零读取。

⇒ **两边各写各的硬编码数字，一致性仅靠 `perspective.py:62` 那行注释声称，且无任何跨侧一致性测试。**

**推论（承重）：** 改 `perspective.py` 的窗帘盒 **绝不会**改变轴测输出，**golden 字节快照零影响**（golden 走 `axon.render` + `render_plan_2d`，纯 `floorplan_core`，不 import `apps/api`；且 `test_decor.py:166-171` 断言 D 默认方案数据**不含** wall_art/curtain，实测 grep 命中 = 0）。

---

## 3. 修法（裁决已定，见 §8）

### D1 — F001：allowed 上沿改为「渲染顶 + 余量」单一真源派生（**先做**）

- 删除 `_WALL_BAND_ALLOWED_Z` 这张双写表，改为 `_WALL_BAND_ALLOWED_MARGIN_MM`（单一余量常量）。
- allowed 盒顶由 **`perspective` 的渲染顶派生**（`acceptance.py:32` 已 `from . import perspective`，无新依赖）：
  `allowed_top = <渲染顶>(it) + _WALL_BAND_ALLOWED_MARGIN_MM`
- 余量值由 **实测驱动**：须覆盖实测的 8~12px 溢出 + 安全余量。**Generator 必须给出 px→mm 的换算依据**（该照片在挂画所处墙面带的实际 mm/px），不得凭感觉拍一个数。
- 此步对窗帘**行为等价或仅扩容差**（余量从 100 提高），不改任何盒几何 ⇒ **可独立上线、可独立回滚**。

### D2 — F002：窗帘盒改为实拍真实毫米世界的落地帘模型（**后做**）

- `perspective.py` 新增 `_REAL_CEILING_MM = 2700`，docstring 显式写明：**这是实拍真实毫米世界的层高，与 `axon`/`scene` 的压扁 `WALL_H=1450` 无关，两者数字不得互借**。
- 窗帘：`z0 = 0`（落地 —— 呼应 `catalog` 的 `"floor-length curtains"`）、顶 `= _REAL_CEILING_MM`（帘杆在天花）。
- 因 F001 已把 allowed 派生化，**allowed 盒自动跟随**，无需第二处改动。
- 订正 `perspective.py:62` 的错误声称：删「顶高对齐 axon SPECS」，改为显式的两世界警告。

**已声明的近似（不含糊）：** D 户型 13 扇窗实为 **8 `full` / 2 `high` / 3 `normal`**（`openings`）。`0..2700` 对 `full` 窗**精确**（且 `axon.py:1252` 把南墙窗强制升为 `full`，本次失败的 `r_live` 正是全落地窗面）；对 `normal`(sill 750) / `high`(sill 1100) 窗的落地帘会在**顶部过覆盖约 400mm**。用户裁决取常量而非按 `wtype` 派生（perspective 无窗模型，派生需跨包依赖，面过大）。**过覆盖 = 该处 allowed 偏大 = 验收器在该处偏钝** → 由 F003 的失明门实测其代价，超标则立 backlog。

### D3 — 禁令（红线）

1. **不得改 `_NEW_EDGE_TILES_MIN = 3`**（今天恰好卡在 3）。改阈值 = 把体温计调高来退烧 = **metric gaming**，直接判 FAIL。
2. 不得改 `evaluate_geometry_lock` 的判据结构（calib-z-b1 spec §7 已划界，本批承接）。
3. 不得动 `axon` SPECS / `scene` / `catalog`（是**另一个世界**，与本问题无关；动它反而会破坏轴测）。
4. 不得写入 `data/projects/`（git-tracked 种子快照，项目红线）。推送前必查 `git status --short data/projects/`。
5. 不得为过门而放宽 `_MARGIN_MM` / `_ALLOWED_DILATE_FRAC` / `_LOST_EDGE_FRAC`（未经实测归因的放宽 = 同类 gaming）。

### D4 — 反证（防「改得好看但验收器瞎了」）

**用户已裁决：阳性对照是硬验收门，不是建议项。**

1. **主反证 — 阳性对照（硬门）：** 构造一张**真的改了结构**的图（如抹掉/重绘窗框、挪门），修后**仍须 FAIL**。否则「误报没了」与「验收器瞎了」不可区分 —— 即 `patterns/testing-env-patterns.md` §10。
2. **失明门：** 实测修后 allowed 区占画幅面积比（窗帘盒 150..1450 → 0..2700 会显著膨胀，且叠加 `_extend_down(_REFLECT_EXTEND=0.9)` 会再向下延伸）。须给出修前/修后数字与「验收器还剩多少视野」的判断。
3. **只治该治的：** 非墙面带件（sofa/dining_table/rug…）的盒投影**逐字节不变**（`_ITEM_Z0_MM` 不在表内者 `z0=0` 的 byte-safe 契约不得破）。
4. 两套 pytest + golden 全绿（golden 零影响已查实，但仍须实跑证实，**不得以推理代替实跑**）。

---

## 4. 已知会红的测试（须随实现更新，非回归）

`apps/api/tests/test_perspective.py:197-201` 字面 pin 了本批要改的数值：

```python
assert P._item_z0_mm({"t": "curtain"}) == 150        # F002 → 0
assert P._DEFAULT_HEIGHT_MM["curtain"] == 1450       # F002 → 2700
assert P._DEFAULT_HEIGHT_MM["wall_art"] == 1400      # 不变
assert P._item_z0_mm({"t": "wall_art"}) == 1000      # 不变
```

更新时**不得只换数字** —— 须补**语义**断言（数字断言挡不住「借错世界」，这正是本 bug 带着 200+ 全绿测试上线的原因，见 `patterns/testing-env-patterns.md` §8）：
- 窗帘盒在实拍世界**跨越地面到天花**：盒底投影 ≈ 地面投影、盒顶投影 v **明显高于**地面（相对断言，不 pin 像素）
- **派生不变量**：改渲染顶 → allowed 顶**自动跟随**（防 §2.3 双写回归复发）
- 窗帘盒高 **> 挂画盒高**（落地帘必然比一幅画高 —— 借错压扁世界数字时此条必红）

---

## 5. 验收项（F003，Evaluator 隔离执行）

1. **重放自证保真**：先复现修前生产 verdict（`ok=False` / `0.95` / `3/96`），再下修后结论。
2. 修后坏块数与 score；逐块归因（不接受「总数降了」这种整体结论）。
3. **阳性对照硬门**（D4.1）：真结构改动仍 FAIL。
4. **失明门**（D4.2）：allowed 面积占比修前/修后实测。
5. byte-safe：非墙面带件盒投影不变（D4.3）。
6. 两套 pytest + golden 实跑全绿、0 skip（`rsvg-convert` 须在位；**skip ≠ pass**）。
7. `_NEW_EDGE_TILES_MIN` / `evaluate_geometry_lock` 判据**未被触碰**（D3.1/D3.2 核查）。
8. **[L2] 真实 AI 出图**：需 `OPENAI_API_KEY` + **用户明确计费授权**。未授权则按 decor-b2 / render-fix-b1 / calib-z-b1 降级口径如实记 [L2] 未执行。

**⚠ 口径铁律（沿用 calib-z-b1，不得软化）：** 在本批修完**并用修后引导图重出一张图**验证前，**不得表述为「误报已消除」**。只能写：「盒几何已修正；坏块 20/111 → 3/96 → N/96；是否消除待 [L2] 复测」。

理由（诚实边界）：今天这张 `out_png` 是模型看着**修前的错引导图**生成的。用修后的盒去评判修前的图，只能说明错盒是误报的**部分**成因 —— 判定是否真消除，必须用**修后引导图**重出一张。

---

## 6. 车道与编排

- **快车道**（默认）：Planner / Generator 主上下文，Evaluator 以隔离 subagent 运行。
- **F003 升档对抗验收**：几何/渲染正确性属「渲染错隐蔽」域（CLAUDE.md 明列的升档场景）。本批**同时改验收器的容差**——即改的是「守门人自己」——失明风险不可用普通验收覆盖。F003 应 fan-out 多维度 + 阳性对照。
- 前批教训直接适用：勿用退化位置 fixture（`testing-env-patterns` §7）；「跑完没脏/没报错」类结论须先建阳性对照（§10）。

---

## 7. 边界（本批**不**做）

- `BL-calib-min-3-anchors`（标定精度，1537e err ~124px）—— 方向已解决，纯精度议题，另批。
- 按 `wtype` 派生窗帘高度（需把窗模型引入 perspective = 跨包依赖）—— 见 §D2 的过覆盖声明；若 F003 失明门实测超标则立项。
- `_WALL_BAND_ALLOWED_Z` 之外的验收器判据 —— calib-z-b1 §7 划界。
- 把「两个 z 世界」真正机制化（如 perspective 从 `axon.SPECS` 派生）—— 用户裁决**只订正注释**：两世界本就**不应**对齐，断言对齐反而会把错误固化。

---

## 8. 关键裁决（用户 2026-07-15）

| # | 议题 | 裁决 |
|---|---|---|
| 1 | 实拍世界层高来源 | **A：perspective 新增常量 `2700`** + docstring 说明与 axon 压扁世界无关。（否决：新增 `real_wall_height_mm` meta 字段 = 动生产数据 + 迁移，面过大；否决：从标定反推 = 会把 ~124px 标定误差传进盒几何） |
| 2 | 窗帘盒膨胀致验收器失明 | **A：强制阳性对照作硬验收门** + 实测 allowed 面积占比。（未额外改 `_REFLECT_EXTEND` —— 先量清代价再决定是否动它） |
| 3 | 「假对齐」是否机制化 | **A：只订正注释 + 写清两个世界。**（否决加跨侧一致性断言：两世界不应对齐，断言会固化错误） |
