# F012 spike：L1 简模引导 vs L0 彩盒 A/B 实测 — 执行报告（2026-07-17，重跑完成）

> 批次 calib-cure-b1 · executor:evaluator · 执行者 local/evaluator-subagent（隔离上下文）
> **结论先行：result = PASS · go/no-go = GO（立项 3D 化 S1-S3，带条件）**
> 用户 2026-07-17 授权重跑：从 `deploysvr:.env` 只读取 relay+fal 三项 key（仅作 run_ab.py 子进程
> 环境变量，未打印/未落盘/未 commit），**8/8 真实出图全部成功**。
> **核心发现（一句话）：** 在弱后端 fal（nano-banana）上，L0 彩盒把书柜画成窄条（生产失败模式复现），
> **L1 简模引导把书柜画满整面东墙（结构性修复）**；4 张 L1 出图**零灰体穿帮**；窗帘遮窗副作用**未兑现**。
> 主要保留：强后端 relay（gpt-image-2，生产默认）L0 本已达标，L1 增益偏小 → L1 价值主要是**跨后端鲁棒性**
> 而非在生产默认后端上的质变；auto_check 分数**形体盲且在关键案例上反转**，立项须配形体评分器。

---

## 1. 执行摘要

| 项 | 计划（acceptance） | 实际（重跑） |
|---|---|---|
| 前置：病例照片副本 | 本地只读拉取，不入 git | ✅ 2 张（472015c4→study_798 / ed881ccf→living_f4d），仅存 `/tmp` scratchpad，未入库 |
| 前置：可信标定 | dry-run 式校验 | ✅ study assess ok=True(suspect,41.5px)；f4d ok=False(126.8px,超广角贴角极限，两臂共用故公平)（§3） |
| 前置：材料复现忠实性 | — | ✅ geometry v7 + `scheme_ai_20260714_130354_01_baec` furniture；`--dry` 重建 legend 与已入库 `rows.json` **逐字节一致** |
| 出图：2 场景 × L0/L1 × relay/fal | ~¥20-30，≤16 图 | ✅ **8/8 成功**（relay 4 + fal 4） |
| 量化表 score/fail_reasons/tokens | 逐图记账 | ✅ §4.1（8 行完整） |
| 落位/形体目检 | 书柜铺满东墙/沙发酒柜落位/简模穿帮 | ✅ §4.3（逐图目检） |
| go/no-go 建议 | 是否立项 3D 化 S1-S3 | ✅ §7：**GO（带条件）** |
| BL-decor-b2-L2-realphoto | 挂画/窗帘真进实拍图不触发 structure FAIL | ✅ §6：**确认成立**（挂画/窗帘均入图，且从未出现在任一 fail_reason） |
| 预算记账 | ≤16 图 ~¥20-30 | ✅ 8 图；relay 19155 tokens（4 图）+ fal 4 图（1184×864≈1.02MP/图）（§5） |

## 2. 环境（重跑：双后端已就绪）

上一轮判 BLOCKED 的唯一原因是本机无 relay/fal key。本轮按用户 2026-07-17 明确授权（"你帮我重跑"），
从生产主机 `.env` **只读取** `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `FAL_KEY` 三项到当前进程环境
（原批次红线"禁碰生产 .env"对**此三项读取**一次性解除；数据/写入红线不变）：

- 取值方式：`eval "$(ssh deploysvr "grep -E '^(OPENAI_API_KEY|OPENAI_BASE_URL|FAL_KEY)=' .env" | sed 's/^/export /')"`，
  与 run_ab.py 出图在**同一子进程**内完成；**key 值全程未 echo/未打印/未写入任何文件、报告或 commit**。
- preflight（不打印值，仅布尔）：`ai_enabled=True`、`fal_enabled=True`；relay 模型 `gpt-image-2`（生产 OpenAI 兼容 relay 端点，
  地址属受保护 `OPENAI_BASE_URL`，本报告不载），fal 模型 `fal-ai/nano-banana/edit`。
- 出图产物（渲染图，无 PIPL）入库 `docs/test-reports/spike-l1-guide/`；**空房原照与真实照片引导叠图（含照片像素）
  仅存 scratchpad，绝不入 git**（已核验 git-tracked 目录只含 `*_blank_*_guide.png`）。

## 3. 可信标定构造实录（沿用上一轮，纯数值入库）

方法与坐标详见入库件 `spike-l1-guide/cal_study_798.json`、`cal_living_f4d.json`。要点：

- **study_798（书房 r_guest2）**：camera=(15269,6800,1720)mm，hfov 59.5°；`assess ok=True/suspect/reproj 41.5px`（<50 硬门）。
  wireframe 目检踢脚线/东北角竖棱/窗位红线贴合 → **可作绝对落位主判场景**。
- **living_f4d（客餐厅 m_living）**：camera=(12950,6131,800)mm，yaw 142°，hfov 109.5°；`assess ok=False/bad/reproj 126.8px`
  —— 超广角贴角拍摄触针孔模型全幅拟合极限。中央区贴合、画面左右缘系统偏差。**门禁实证：该生产病例照按 F005 渲染 409
  硬门无论如何标定都会被拦**（用户须重拍）。**对 A/B：两臂共用同一相机，偏差同向作用 → 内部公平性不受影响，但"绝对落位"
  目检须打折扣**（故 living 作形体/相对关系判，不作绝对落位判）。

> 材料忠实性核验（本轮新增）：生产 geometry v7 的 `r_guest2=[1515,250,300,330]`、`r_live=[495,580,720,830]` 与标定锚点
> 世界坐标（y=2500 北墙 / y=14100 南墙）严格一致；家具取自渲染两案实际绑定方案 `scheme_ai_20260714_130354_01_baec`
> （渲染 798f23d3→photo 5bd5b7c9/r_guest2、f4dab9bc→photo c3d47972/r_foyer，逐一对上）。用此材料 `--dry` 重建的
> 两臂 legend 与上一轮已入库 `rows.json` **逐字节一致** → 本轮真实出图所用引导 = 上一轮已验证公平性的引导。

## 4. 真实出图 A/B 量化表与目检（本报告核心）

### 4.1 量化表（8 图；auto_check `evaluate_geometry_lock` + usage）

| 场景 | 引导 | 后端 | 出图 | score | auto_ok | 失败类型 | fail_reasons | tokens | 实际尺寸 | 耗时s |
|---|---|---|---|---|---|---|---|---|---|---|
| study_798 | L0 | relay | ✅ | 0.85 | ❌ | 重取景* | 盒区外原有边缘丢失 100% | 4741 | 1448×1086 | 99.5 |
| study_798 | L0 | fal | ✅ | **0.95** | ❌ | 结构改动 | 新边缘坏块 3/12 | — | 1184×864 | 21.8 |
| study_798 | L1 | relay | ✅ | 0.85 | ❌ | 重取景* | 盒区外原有边缘丢失 100% | 4825 | 1448×1086 | 120.0 |
| study_798 | L1 | fal | ✅ | 0.85 | ❌ | 重取景* | 盒区外原有边缘丢失 100% | — | 1184×864 | 41.6 |
| living_f4d | L0 | relay | ✅ | 0.908 | ❌ | 彩盒残留+结构 | entry_door 残留(3)；坏块 4/118 | 4794 | 1448×1086 | 107.6 |
| living_f4d | L0 | fal | ✅ | 0.871 | ❌ | 漏画+结构 | entry_door 未见家具(9)；坏块 4/118 | — | 1184×864 | 53.7 |
| living_f4d | L1 | relay | ✅ | 0.858 | ❌ | 彩盒残留+结构 | entry_door 残留(10)；坏块 7/118 | 4795 | 1448×1086 | 124.2 |
| living_f4d | L1 | fal | ✅ | 0.875 | ❌ | 彩盒残留+结构 | entry_door 残留(1)；坏块 6/118 | — | 1184×864 | 22.2 |

结构化明细：`spike-l1-guide/ab-rows-real.json`。

### 4.2 量化表解读：**auto_check 分数不能判形体，且在关键案例上反转**

三条必须写清的判读（否则会被 score 误导）：

1. **全部 auto_ok=❌ 不代表出图坏。** 8 张图目检均为高质量照片级成图（§4.3）。失败项全是**度量假象**：
   - **"重取景 100%"（study relay 两臂 + study L1 fal）**：relay 出图实际尺寸 1448×1086、fal 1184×864，**都不等于**输入
     2048×1536。auto_check 把两图缩到 512 宽比边缘时，全局重采样使窗/顶/踢脚线整体偏移超 5px 膨胀容差 → 判"原边缘全丢"。
     **目检证实相机取景完全保留**（窗在左、东墙在右、透视一致），非真重取景。
   - **entry_door（living 4 张全部）**：entry_door 是开口标记不是家具，annotate 引导本就 skip 它、盒区不画东西，但 auto_check
     仍按其 footprint 查"有没有画家具"→ 必报残留/漏画。**两臂等量出现**，A/B 对消。
2. **score 在关键案例上与真实质量反向。** study fal：L0=**0.95** > L1=**0.85**，但目检 L0 是**错的**（窄条书柜），L1 是**对的**
   （满墙书柜）。原因：L0 把书柜画成窄条后东墙大片留白 → 盒区外"新结构"少 → score 高；L1 画满整墙的书架反而触发更多
   边缘 → score 低。**结论：auto_check 是"尾部兜底"（画没画/改没改结构），不是形体质量度量；立项不能用它当形体裁决器。**
3. **A/B 分数聚合（仅供参考，非形体判据）：** 同后端 L0 vs L1 —— study relay 0.85=0.85；study fal 0.95>0.85（假象，见上）；
   living relay 0.908>0.858；living fal 0.871<0.875。数字上 L1 不优于 L0，但这**恰恰暴露 auto_check 的形体盲**，不构成 L1 更差的证据。

### 4.3 逐图目检（形体/落位/穿帮，人工判——形体质量的**唯一**可信证据）

**study_798（好标定，绝对落位主判场景）**

| 目检点 | L0 relay | L1 relay | L0 fal | L1 fal |
|---|---|---|---|---|
| 书柜铺满东墙 | ✅ 满墙内嵌书柜（上架下柜） | ✅ 满墙开放书架（多层+黄铜框，更贴 L1 简模） | ❌ **窄条书柜仅占东墙≈1/3，其余大片留白（生产失败模式复现）** | ✅ **满墙通长书架（失败模式被 L1 修复）** |
| 书桌/椅形体 | ✅ 桌+台灯+扶手椅 | ✅ 桌+椅完整 | ✅ 白金书桌+抽屉+椅 | ✅ 桌+椅完整 |
| 窗帘/窗 | ✅ 窗保留，纱帘+布帘 | ✅ 窗保留，纱帘+布帘 | ✅ 窗保留，米色帘 | ✅ 窗保留，纱帘+布帘 |
| 灰体穿帮 | — | ✅ **无**（全木/黄铜照片质感） | — | ✅ **无** |

→ **study 是本 spike 最关键的一格：L0 fal 复现"书柜画成窄条"、L1 fal 修复为满墙**——这是"简模引导带来落位/形体质变"
命题在**真实生产病例 × 真实弱后端**上的直接实证。强后端 relay 两臂皆达标（gpt-image-2 对 L0 彩盒 footprint 跟随已足够好），
故 L1 在生产默认后端上是**无回归**而非质变。

**living_f4d（坏标定，作形体/相对关系判，不作绝对落位判）**

- 四张（L0/L1 × relay/fal）均为构图合理、形体完整的客餐厅：双人沙发/L 形沙发（座+靠背+扶手成形）、大理石茶几、
  餐桌+餐椅、酒柜（含酒瓶）、墙面挂画、绿植、地毯。**无 gross 形体错误，无灰体穿帮。**
- L1 relay 沙发/餐桌形体与 L0 relay 相当；L1 fal 出 L 形转角沙发（形体清晰）。因 f4d 标定超限，"沙发/酒柜绝对落位"
  两臂都受同一偏差影响，无法据此分胜负（符合 §3 预判）。
- **窗帘遮窗副作用（上轮 §4.2-1 必看点）未兑现**：尽管 L1 引导把 curtain 画成全高不透明板（olive 大块），**8 张出图无一
  把窗糊死**——模型遵从 prompt "floor-length curtains ... not a solid boxy object" 覆盖了引导板状外形，窗景（城市天际线+
  中国结）在所有图中保留。→ 上轮标记的最大风险点，本轮**证伪**。

### 4.4 简模穿帮率（L1 核心风险）——实测 0/4

L1 出图的第一风险是"AI 保留灰体质感/低模棱角"。**4 张 L1 出图（study×2 + living×2，relay+fal 各半）无一出现灰体、
色块、低模棱角或未替换的原始简模**——全部替换为符合"现代轻奢"的照片级材质（木/黄铜/织物/大理石）。该风险本轮**清零**。

## 5. 预算记账（实数）

| 项 | 数量 | 计量 |
|---|---|---|
| relay 出图（gpt-image-2） | 4 图 | total_tokens 合计 **19155**（均 ~4788/图） |
| fal 出图（nano-banana/edit） | 4 图 | 输出 1184×864 ≈ 1.02 MP/图，合计 ≈ 4.1 MP（provider usage 未回传 w/h，故 summary 记 0 MP；实际尺寸已由 PNG 头确认） |
| **合计** | **8 图** | 远低于授权 ≤16 图 / ~¥20-30 上限；单次调用零失败、零重试 |

## 6. BL-decor-b2-L2-realphoto 观察点（顺带项）——**确认成立**

acceptance 目标：含配饰方案出图中**挂画/窗帘真进实拍图、且不触发 acceptance structure FAIL**。本轮实测确认：

1. **挂画/窗帘真入图**（目检 §4.3）：挂画以墙面带框艺术品呈现（living relay 两张、living L1 fal 均见 2 幅框画贴墙、
   非落地摆件）；窗帘以落地纱帘+布帘呈现（全部 8 图），非板状实体。
2. **不触发 structure FAIL**（本地复跑 `evaluate_geometry_lock` 逐图核验，无 API）：`wall_art`/`curtain` 属 `_ALLOWED_ONLY`，
   **不进逐盒 furnished 检查**（被检盒类型：dining_table/sofa×2/coffee_table/media/entry_door/wine_cabinet/plant×3），且其
   footprint 进 `allowed` 掩膜受结构豁免。**8 张出图的 fail_reasons 中，`wall_art`/`curtain`/挂画/窗帘 从未被点名**。
3. 出现的 structure 坏块（living 4-7/118）来自**大理石亮面倒影 + 窗景城市天际线重绘**（acceptance 已知盲区，见 acceptance.py
   §已知盲区），与挂画/窗帘无关。

→ BL-decor-b2-L2-realphoto 观察点：**挂画/窗帘进实拍图成立，未因其触发 structure 误判**，机制（`_ALLOWED_ONLY`+allowed 豁免）
按设计生效。

## 7. go / no-go 建议（3D 化 S1-S3 立项）——**GO（带条件）**

**判定：GO。** 依据本仓纪律「换引导要重赛」——本轮以真实出图数据重赛，L1 的形体/落位收益经实证确认，且首要风险清零：

支持 go 的**实测**证据（非干跑推断）：
1. **失败模式被真实修复**：L0 fal 复现"书柜画成窄条"（生产 798 病例的核心失败模式），L1 fal 修复为满墙书架——3D 化评估
   文档 §2 的失败模式 #1 在真实病例×真实弱后端上被 L1 结构性消解；
2. **灰体穿帮 0/4**（L1 首要风险清零，spike 核心问题得到肯定回答）；
3. **窗帘遮窗副作用未兑现**（prompt 覆盖板状引导，窗景全保留）；
4. 两臂公平性经字节级复现确认；成本结构不变（8 图 ~¥20-30 以内）。

**必须挂上的条件（否则易高估收益）：**
1. **收益是后端依赖的**：生产默认后端 relay（gpt-image-2）对 L0 彩盒已足够好（study relay 两臂皆满墙）——L1 的清晰质变
   主要出现在**弱/廉后端 fal**。故 L1 的价值定位应是**跨后端鲁棒性 + 失败模式保险**，而非"在生产默认后端上的质变"。
   立项理由若写成后者会夸大。**建议 S1 先量化"relay 上 L1 相对 L0 的边际收益"是否值回 3D 化工程成本。**
2. **须配形体评分器**：auto_check 形体盲且在关键案例上反转（§4.2），不能作 S1-S3 的验收裁决器；S 阶段须引入 VLM/人工
   形体评分（现有 `semantic_accept.py` VLM 可扩展）。
3. **样本仍小**：2 场景 × 每格 1 图、无重复采样；f4d 场景因标定超限不能作绝对落位判。S1 应扩到多场景 × 多次采样，
   并**优先补一张好标定的客餐厅**（隔离"沙发/酒柜落位"失败模式，本轮被 f4d 标定极限confound）。
4. **curtain 简模须特殊处理**：本轮虽未兑现遮窗，但 L1 引导把 curtain 画成全高不透明板本身是隐患（换一个更"听话"照抄引导
   的模型就可能糊窗）——S 阶段 curtain 应改半透明/仅侧幔+帘盒。

**建议路径：GO 进 S1（原型验证），在 S1 gate 用形体评分器 + 扩样本复核后再决定 S2-S3。** 本轮已把立项从干跑的"暂定 go"
升级为"实证 go"，但收益边界（后端依赖）须在 S1 澄清。

## 8. 复现指引（已全程跑通）

```bash
# 素材（PIPL：空房照放本地未跟踪路径；标定 JSON 已入库）
#   docs/test-reports/spike-l1-guide/cal_study_798.json / cal_living_f4d.json
#   geometry: deploysvr baselines/v7/geometry.json（只读）
#   furniture: deploysvr schemes/scheme_ai_20260714_130354_01_baec/furniture.json（只读）
#   photos: deploysvr data/uploads/D/empty/{472015c4...,ed881ccf...}.jpg（只读，不入 git）
eval "$(ssh deploysvr "grep -E '^(OPENAI_API_KEY|OPENAI_BASE_URL|FAL_KEY)=' /opt/grandtianfu/.env" | sed 's/^/export /')"
python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ --backends relay,fal
# 2 场景 × L0/L1 × relay/fal = 8 图；summary.md / rows.json 自动记账
```

## 9. 未执行项清单

| # | 项 | 状态 |
|---|---|---|
| 1-5（上轮：真实出图/量化/目检/BL/go-no-go） | — | ✅ **本轮全部执行**（§4/§5/§6/§7） |
| 6 | [L2] 用户浏览器走查：A 期标定预览 + 用新 UX 重标两张病例照片 + 生产落位改善目检 | ⏳ 属**批次级用户项**（spec §8.3），非 F012 出图范畴；待用户授权/自行走查，不阻断 F012 |

## 10. 产物清单

**入库（`spike-l1-guide/`，均无 PIPL）**：
- **本轮新增**：8 张真实出图 `{scene}_{L0|L1}_{relay|fal}.png`（渲染的照片级家具成图）+ `ab-rows-real.json`（8 图结构化量化明细）；
- 上轮：blank 两臂引导图 ×4、两场景标定 JSON ×2、两臂 prompt ×4、dry `summary.md`/`rows.json`、`scenes.example.json`、`dry-run/` ×4。

**仅存本地 scratchpad（含照片像素，PIPL 不入库）**：2 张空房原照、4 张真实照片版两臂引导叠图、scenes.json（含照片路径）、
生产 geometry v7 / scheme furniture 只读副本。会话结束随 `/tmp` 生命周期清理；重建方法见 §8。

## 11. 框架提案候选（供 Planner 裁决，Evaluator 不直接写 framework/）

1. **新坑（实证）**：`acceptance.evaluate_geometry_lock` 的 auto_check **形体盲且可与真实质量反相关**——本轮 study fal L0 窄条书柜
   0.95 > L1 满墙书柜 0.85。凡"引导升级/形体质变"类 A/B，**不得以 auto_check score 作形体裁决**，须配 VLM/人工形体评分。
   建议写入 `framework/patterns/`（LLM 图像验收）+ 该函数 docstring 已有"不判美观"声明可加一句"跨引导 A/B 慎用 score 比形体"。
2. **新坑（实证）**：relay(gpt-image-2 1448×1086)/fal(nano-banana 1184×864) 出图尺寸**均不等于输入 2048×1536**，导致
   auto_check reframe 检查对"整体重采样"误报 100% 边缘丢失（好图全线超阈）。建议 reframe 判定前先按输入尺寸归一化，或改用
   尺度不变的匹配。
3. **新规律（沿上轮）**：手机超广角(hfov≳105°)贴角拍摄针孔模型全幅 reproj≈100px+ 必触硬门；产品拍摄指引宜明示"1x 主摄、离墙 2m+"。

---

*Evaluator: local/evaluator-subagent（隔离上下文）· 2026-07-17 重跑*
*本报告基于实物：生产几何/家具/照片只读副本、scripts/spike 工具双后端实跑 8 图、perspective/assess/acceptance 实调、8 图逐张目检。*
