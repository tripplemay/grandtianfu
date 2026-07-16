# decor-envelope-b1 — 隔离验收报告（verifying 首轮，F003）

- **批次：** decor-envelope-b1（F001 + F002 = generator；F003 = evaluator，本报告）
- **角色：** 隔离 Evaluator（fresh context，未继承实现上下文）
- **日期：** 2026-07-16
- **轮次：** verifying round 1（fix_rounds=0）
- **验收对象代码：** `apps/api/aigc/acceptance.py`（F001）、`apps/api/aigc/perspective.py`（F002）
- **总判定：** **PASS**（8 项 L1 硬门全过；[L2] 真实出图未授权，如实降级记录，不据此判 FAIL）
- **独立性声明：** 本次结论**不采信** `progress.json.generator_handoff` 的任何实测数字，全部自取 fixture、自建 worktree pre/post 对照、自算 sha256、自建阳性对照后独立复现。前一位 Evaluator 因 API idle timeout 中途死亡、未落结论、未碰生产；本报告从零开始。

> **⚠ 口径铁律（沿用 calib-z-b1，未软化）：** 本批修的是**验收器盒几何**，验证用的 `out.png` 是模型看着**修前的错引导图**生成的。因此本报告**不表述为「误报已消除」**，只表述为「**盒几何已修正；坏块 3/96 → 2/92；是否真正消除待 [L2] 用修后引导图重出一张复测**」。

---

## 0. 生产实证锚点（独立解析，非采信 handoff）

从生产 `projects/D/schemes/scheme_ai_20260714_130354_01_baec/renders.json` 直接解析 render `fc8823be`：

| 字段 | 值（独立读出） |
|---|---|
| id | `fc8823be4bd148a3ad35c2ddd1ef2252` |
| auto_check | `ok=False / score=0.95 / fail_reasons=["盒区外出现新结构 (新边缘坏块 3/96)"] / attempts=2` |
| photo_id | `417ae5589afe475a9bdfa4b310c32986`（room=`r_live`） |
| base_url == guide_url | `real-base/e55c7ea3…png`（**guide==base 确认**） |
| out url | `real-render/fc8823be…png` |

参数来源（照 `main.py:2340-2506` 独立复原）：baseline `v7` geometry（`mm_per_px=10`，`r_live` rect `[495,580,720,830]`）+ scheme furniture + 417ae calibration（`img_wh=[2048,1536]`，`det(R)=-1` = calib-z-b1 自愈后相机）+ `axon.merge_group_ids(G,'r_live') = {r_live, r_foyer, r-itki-331}` → 过滤出 14 件家具（2 挂画 + 1 落地窗帘 w=719 横跨南墙 + 沙发/餐桌等）。

**engine 血缘核对：** `git diff a69ad7f 9a18668 -- acceptance.py perspective.py` = **空**。生产 engine `a69ad7f` 与本批 pre-baseline `9a18668` 在两目标文件上**逐字节相同** ⇒ 用 `9a18668` worktree 重放即忠实复现生产 engine 的验收行为。

---

## 1. (1) 重放自证保真 — **PASS**

pre-fix worktree（`9a18668`）对生产实物重放：

```
{ ok: false, score: 0.95, structure: {bad_tiles: 3, total_tiles: 96}, det_R: -1.0,
  fail_reasons: ["盒区外出现新结构 (新边缘坏块 3/96)"] }
```

**逐字复现生产 auto_check（`ok=False / 0.95 / 3/96 / fail_reasons 完全一致`）。** 重放器由此被证明有视力（§10 阳性对照先行）——修后结论才有据。

## 2. (2) 修后坏块数/score + 逐块归因 — **PASS**

HEAD（F001+F002）对**同一** out/guide 重放：

```
{ ok: true, score: 0.967, structure: {bad_tiles: 2, total_tiles: 92}, det_R: -1.0 }
```

坏块 **3/96 → 2/92**。逐块归因（独立重建内部 mask，坐标 = tile 左上角）：

| 阶段 | tile(work) | orig | 归因（列对齐 + 目检确认） |
|---|---|---|---|
| PRE | (0,64) | (0,256) | **落地窗帘顶** —— F002 后消失 |
| PRE/POST | (96,128) | (384,512) | **山水画①框顶**（在挂画盒顶 y=181 上方） |
| PRE/POST | (128,128) | (512,512) | **山水画②框顶** |

**目检独立确认（诊断图叠加 allowed 上沿绿线 + 新边缘红）：**
- 窗帘块：post-fix 绿色 allowed 边界已向上包住整片落地窗帘区，**该处无红色新边缘** → F002 的 0..2700 窗帘盒正确吸收了模型画的落地帘。
- 2 挂画块：**红色新边缘精确勾勒两幅画框的顶边**，画框顶超出欠建模的挂画盒（400mm）；红边**只勾家具本身，其后深色墙面/天花/筒灯结构全部未变**。

⇒ **独立确认这 2 块是挂画（家具）本身，非真结构改动。** 属 `BL-wall-art-box-undermodeled`（裁决 #4:A 已立项，本批不修、**未用容差掩盖**）。**不据此判 FAIL。**

## 3. (3) 阳性对照【硬门】 — **PASS**

在生产 out.png 的 **outside（受检）区**注入真结构改动，验证修后验收器**仍 FAIL**：

| 阳性对照 | 位置 | 结果 | 有效性 |
|---|---|---|---|
| **PC2 幻觉窗**（粗高对比） | 左上，**紧邻膨胀后的窗帘盒** | **ok=False, 12/92** | ✅ **干净有效**：坏块 work(128,32)(160,32)(128,64)(160,64)(160,96) 全落窗框内，区域内 `new_edges=495`，**≥3 块来自窗户自身边缘**（非全局伪迹） |
| PC1 幻觉门 | 顶部中央 | ok=False, 11/92 | 有效但含 `_gain_fit` 全局亮度偏移的扩散成分，locality 较弱 |
| PC3/PC3b 护墙板/幻觉龛 | 右墙 | ok=True（未触发） | **无效对照**：右墙空房照本身已有真实窗/玻璃幕墙（`Ee=3673`），注入结构与既有边缘重叠 `new_edges=0`；且该区本批前即 outside+边缘密集 → **非本批回归** |
| PC-clean 中对比门 | 上墙 | ok=True（未触发） | 揭示既有属性（见下） |

**结论：PC2 干净满足硬门 —— 修后验收器对真结构改动（含膨胀窗帘带邻域）仍 FAIL、仍有牙，未被致盲。**

**诚实边界（须记，非本批引入）：** 验收器工作在 512 宽工作分辨率，**细/中对比的结构改动经 4× 下采样会被冲掉**（`_WORK_W`/`_EDGE_TAU=12`/`_EDGE_DILATE=5` 本批**未动**，diff 已证）。这是**既有敏感度下限**，与本批正交；阳性对照须用粗、高对比结构方能有效（PC2 即是）。

## 4. (4) 失明门【硬门】 — **PASS（附 soft-watch）**

allowed 占画幅面积比（独立重建 allowed mask）：

| | pre-batch(9a18668) | HEAD | Δ |
|---|---|---|---|
| allowed_frac | **52.46%**（103135/196608 px） | **54.89%**（107922 px） | **+2.43pp** |

修后验收器仍保留 **~45.1% 画幅**在受检 outside 区；PC2 实证其在膨胀窗帘带邻域仍能抓真结构。**失明代价温和、可接受。**

**soft-watch（非阻断）：** r_live 是南墙全落地窗，`0..2700` 落地帘**合法精确**。spec §7 声明的 normal/high 窗顶部过覆盖（~400mm）**无法在 r_live 上被实测**（生产无 normal/high 窗房间的 render 可用）→ 建议按 spec §7 保留 backlog 追踪，待有该类房间 render 数据再量化，超标则单立项。

## 5. (5) byte-safe（非墙面带件盒投影不变） — **PASS**

逐件 `footprint_mask` sha256（pre `9a18668` vs HEAD）：

- **仅 `curtain` 变**（`7585c8de → e289cfc4` = F002 的 1450→2700 修正）。
- 其余 **13 件全部逐字节不变**：dining_table / rug / sofa×2 / coffee_table / media / entry_door / wine_cabinet / plant×3 **以及 2 个 wall_art**（墙面带但 F002 未碰）。

⇒ 非墙面带件的 z0=0 byte-safe 契约完好，改动外科精准。

## 6. (6) 两套 pytest + golden 实跑 0 skip — **PASS**

| 套件 | 结果 |
|---|---|
| `apps/api/tests`（359 项） | **359 passed, 0 skipped** |
| `packages/floorplan_core/tests`（154 项） | **154 passed, 0 skipped** |
| golden `test_render_string_matches_baseline_byte_for_byte`（2 参数化） | **PASS 逐字节**（repo 根 `.phase0-baseline` 存在，`rsvg-convert 2.62.1` 在位，`-v` 确认 0 skip） |
| 本批目标 test_perspective + test_acceptance（52 项） | **52 passed** |

Golden 逐字节通过独立证实：改 `perspective.py`（apps/api）对 `axon` 轴测 golden（floorplan_core）**零影响**（两世界不共享代码）。环境：本机 Python 3.9.6（CI 3.12），numpy 2.0.2，PIL 11.3.0。

## 7. (7) 红线核查 — **PASS（无 metric gaming）**

HEAD grep 逐条确认**未被触碰**：

```
_NEW_EDGE_TILES_MIN = 3      _NEW_EDGE_TILE = 0.08     _STRUCT_TILE = 32
_MARGIN_MM = {dining_table:700,desk:700,round_table:700,rug:1000}  _MARGIN_MM_DEFAULT = 150
_ALLOWED_DILATE_FRAC = 0.04  _LOST_EDGE_FRAC = 0.50    _REFLECT_EXTEND = 0.9
_EDGE_TAU = 12.0             _EDGE_DILATE = 5          _WALL_BAND_ALLOWED_MARGIN_MM = 100
```

`evaluate_geometry_lock` 的 `struct_ok = tiles_bad < _NEW_EDGE_TILES_MIN` 判据结构**完好**；`git diff 9a18668 HEAD` 在 evaluate 内只改了墙面带上沿派生的 2 行分支（F001 本意），score/tiles_bad/reframe 逻辑未动。**未为过门放宽任何阈值/判据。**

## 8. (8) F001 = 纯机制化重构 — **PASS**

allowed mask sha256（独立重建，逐字节）：

| | mechanism | sha256 | on_px |
|---|---|---|---|
| pre-F001（9a18668，旧双写表 `_WALL_BAND_ALLOWED_Z`） | `_WALL_BAND_ALLOWED_Z` | `81cdbeea2dc6f8bd…` | 103135 |
| F001（9fa4c1d，派生 `wall_band_allowed_top_mm`） | `wall_band_allowed_top_mm` | `81cdbeea2dc6f8bd…` | 103135 |

**sha256 完全相同、代码路径已换（mechanism 串不同）、输出逐字节等价** ⇒ F001 是真正的纯机制化重构。余量常量 `_WALL_BAND_ALLOWED_MARGIN_MM = 100`（grep 确认），**未扩容差掩盖挂画欠建模**（裁决 #4:A）。承重单测 `test_allowed_top_derives_from_render_top_not_a_second_table`（monkeypatch 派生不变量）通过。

## 9. (9) [L2] 真实 AI 出图 — **未执行**

无 `OPENAI_API_KEY`、无用户计费授权。按 decor-b2 / render-fix-b1 / calib-z-b1 降级口径：**[L2] 未执行**。因此「盒几何修正后模型是否真的不再画出触发误报的结构」**尚不可判**——须 [L2] 用**修后引导图**重出一张 v7 / r_live 实拍图方能定论。**不据此判 FAIL。**

---

## 生产安全（零写入自证）

全程仅 `scp`/`ssh ... read`。收尾生产 sha256 双向核对——我依赖的文件与本地副本**逐字节一致**：

| 文件 | 生产 == 本地 |
|---|---|
| geometry_v7.json | `0b595bba…` ✓ |
| scheme furniture.json | `0219bb6d…` ✓ |
| empty.jpg | `3aab46c9…` ✓ |
| out.png | `c115acd7…` ✓ |
| guide.png | `fc49906c…` ✓ |
| photos.json 中 417ae 条目 | `73f7d4f9…`（逐字段未变；photos 仍 12 张，验收窗口内无新增） |

**⇒ 对生产零字节写入，测量基于忠实 fixture。** PIPL：生产照片只存 `/tmp` scratchpad，未入库（仓库无照片文件；仓库 clean，未触碰任何产品代码）。

---

## 独立复核 vs handoff 数字

handoff 全部关键数字**独立复现一致**：fidelity `3/96·0.95`、post `2/92·0.967`、blindness `52.5%→54.9% (+2.4pp)`、f001_byte_identity `81cdbeea…·103135`、byte_safe「只有 curtain 变」、scale。**未发现与 handoff 冲突之处。**

**本报告在 handoff 之外补充的诚实边界（不改判定）：**
1. 阳性对照非全部干净——PC1 含 gain-shift 扩散、PC3/PC3b 因撞既有真实窗边缘密集区而无效；**PC2 干净满足硬门**。
2. 验收器 512 工作分辨率对细结构有既有敏感度下限（非本批引入）。
3. normal/high 窗过覆盖代价在 r_live 无法被实测（soft-watch）。

---

## 结论

**F003：PASS。** F001（纯机制化重构，allowed 逐字节等价）、F002（窗帘落地帘 0..2700，byte-safe 仅 curtain 变）经生产实物对抗验收成立；阳性对照硬门（PC2）与失明门均通过；红线未破、无 metric gaming；两套 pytest + golden 实跑 0 skip。2 块挂画坏块系已立项欠建模、非结构改动、未被容差掩盖，不构成 FAIL。**「误报是否真消除」待 [L2] 修后引导图复测——这是本批唯一悬而未决项，属计费授权门，非代码缺陷。**
