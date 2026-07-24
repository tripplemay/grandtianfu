# render-mask-b1 — mask 级背景锁定实拍出图（精准保真档）

> 状态：**已 lock（用户 2026-07-23 批准，"同意"）**。分支 `feat/render-mask-b1`（off main）→ PR → squash；绝不单推 `main`。
> 证据基座：`docs/test-reports/route-eval-real-render-2026-07-23.md` §4（背景重绘是三路线共同天花板）+
> 本批开工前调查（2026-07-23，沙箱两次实测，见 §2）。
> 用户裁决（2026-07-23）：开启 BL-render-mask-edit。

## 1. 为什么立这批

render-relation-b1 上线后，放置意图传递已解决（relational 91-93%），**剩下的唯一天花板是背景保真**：
gpt-image-2 整图重生成，「不得改动结构」的 prompt 强约束锁不住背景（13 张评测产物全线重绘——
地板纹理、天花灯位、大理石纹样全变）。「这就是我家」的保真只能靠 mask 级编辑解决。

## 2. 开工前调查（已完成的两个关键实测）

**调查 1 — fal flux inpaint 的 mask 外保真度**（`fal-ai/flux-general/inpainting`，1 次真实调用）：
- 输出分辨率**不保持**（请求 2048×1536 → 返回 1920×1440，重采样本身即整图改动）；
- mask 外（上半 60%）改动像素比 5.86%（>8），非严格像素级保留；
- 但构图是全帧对齐的（无裁剪）→ **resize-back 后逐区合成可行**；
- mask 内模型填充能力正常（下 40% mask 内被合理摆满卧室家具）。
- **结论：不能信任模型的 mask 外承诺，必须 mask 内取模型输出、mask 外取原图字节做合成——
  背景保真由构造保证（mask 外 diff 恒 0），不依赖任何模型行为。**

**调查 2 — VLM 区域估计精度**（gpt-5.5，2 张真实空房照）：
- 地面多边形：贴墙脚线精度好（r_live 样本近乎完美，r_master 样本上缘有抖动但可用）；
- 窗墙区域：较粗（主卧样本下缘越界到地面带），用于窗帘挂载可接受；
- **结论：VLM 区域估计可作 mask 源头，但必须有健全性门（面积/顶点/覆盖比）与失败降级。**

## 3. 关键设计决策

### D1 架构：VLM 区域 → 栅格 mask → fal inpaint → 回缩对齐 → 羽化合成
```
空房照 + placement_brief(决定需要哪些区)
  → VLM 区域估计 (floor 必有; window_wall 有窗帘时; art_wall 有挂画时)
  → 栅格化 'L' mask + 健全门 (失败 → 降级为 relational 无 mask 路径, 记 degraded)
  → fal flux inpaint (relational 同款提示词)
  → 输出 resize 回原图尺寸 (全帧对齐, 调查1已证)
  → 羽化合成: mask 内取模型输出, mask 外取原图字节 (边缘羽化 ~8px)
  → VLM 关系验收 (relation-check, 与 relational 同一套)
  → 确定性背景验收: mask 外像素 diff == 0 (构造保证, 羽化带除外)
```

### D2 新档而非替换：`strategy=relational_mask`（精准保真档）
- relational 保持默认档不动；relational_mask 为第四档，供对比与逐步切换；
- fal 缺 key 时该档 400（不做静默降级——降级到 relational 由调用方显式选择）；
- 成本/单：1 VLM 区域 + 1 fal inpaint + ≤2 VLM 验收（与 relational 同量级 + 1 VLM）。

### D3 健全门与降级（诚实失败优于坏 mask）
区域估计须过：多边形 ≥3 顶点、floor 面积占画面 5%-80%、无自交、顶点在图内。
任一不过或 VLM 异常 → **降级为 relational（无 mask）路径交付并记 `mask_degraded`**，
不阻断出图（同 relation-b1 的 VLM 降级原则）。

### D4 背景验收是确定性硬指标（不接受 VLM 宽松判定）
`acceptance.background_diff_check(orig, final, mask)`：mask 外（腐蚀 4px 后的严格外部）
像素 diff 统计——改动像素比必须 == 0（合成边界羽化带 ~8px 豁免）。
这是本批的核心交付物，也是 route-eval §4 发现的「VLM 保真判定偏松」的对治。
指标入 render 记录。

### D5 mask 产物可审计
mask PNG 落 artifacts（复用 real-base kind），render 记录关联——出问题可回看「当时允许模型改哪里」。

## 4. Features

| ID | 一句话 | executor |
|---|---|---|
| F001 | `aigc/mask_zones.py`：VLM 区域估计 + 栅格化 + 健全门（D1/D3） | generator |
| F002 | render-real `strategy=relational_mask` 路径（inpaint + 合成 + 验收接入） | generator |
| F003 | `acceptance.background_diff_check` 确定性背景验收 + 记录（D4） | generator |
| F004 | 前端第四档「精准保真」+ 背景 diff 指标展示 | generator |
| F005 | 隔离验收：硬指标复测 + 命中率对照 + 回归 | evaluator |

## 5. 验收总则（F005）

1. **硬指标**：≥2 张真实空房照，mask 外（羽化带除外）像素 diff == 0 —— 这是本批的存在理由，不接受近似。
2. **放置命中率不劣于 relational**：同照片同方案对照（relational_mask vs relational 统一 VLM 核对，±10% 噪声带）。
3. **边缘自然度**：合成边界无可见接缝/色带（目检 + 报告附证）。
4. **降级路径**：人为破坏区域估计（模拟 VLM 异常/畸形多边形）→ 必走 relational 降级且记录 `mask_degraded`。
5. **回归**：relational/softref/geometry_lock 三档零改动（既有测试全绿）；pytest 双套件 + 前端 build/lint 绿。
6. 红线：不写 data/projects/；AI 调用在验收预算内（≤6 gen + ≤10 VLM）；PIPL 照片不入 git。

## 6. 开工前调查清单（lock 前已完成 §2 两项；剩余随 F001）

- F001：VLM 区域 prompt 定稿（frame 文案是否提升精度）；羽化半径与 mask 腐蚀量的起始值（8px/4px）。
- F002：fal inpaint strength/steps 起始值（默认 0.9/30 沿用 providers 现值）；fal 输出回缩的重采样方式（LANCZOS）。
- F003：diff 阈值 0 的适用性确认（JPEG 原图 vs PNG 输出的编码差已在合成外——合成保证外部字节即原图字节，diff 必为 0）。

## 7. 本批不做什么

- 不把 relational_mask 设为默认档（下批视生产对比再定）；
- 不做分割模型（SAM 等）路线（VLM 区域已够用，不引新模型依赖）；
- 不做 art_wall 之外的墙面细分（踢脚线/灯槽等）；
- 不动 relational 主路径的任何行为（只加新档）。

## 8. 订正（fix_round 1，2026-07-23，F005 verifying-1 FAIL 驱动）

**verifying-1 打回（`docs/test-reports/render-mask-b1-verifying-2026-07-23.md`），两个 blocking：**

1. **fal flux inpaint 填充质量灾难（2/2 照片）**：指令式长 prompt（为 gpt-image-2 写）+
   66-79% 大 mask，flux 被迫重想整个房间——客厅变酒店客房+卡通厨房插画、主卧变日式动漫
   插画、窗外实景被换成富士山。命中率 0/13 与 1/9（vs relational 对照 10/13、8/9）。
2. **mask 并集覆盖率无上限**：66.4%/78.8% 画面入 mask，「背景锁定」实际只锁住天花。

**订正 D1（生成引擎选型）**：~~fal flux inpaint~~ → **relay 整图编辑（与 relational 同引擎，
gpt-image-2）+ 区域 mask 羽化合成**。理由：放置质量直接继承 relational 的已验 91%，
不必赌 flux 学会按约束摆家具；背景锁定仍由构造保证（mask 外取原图字节，diff==0）。
代价：fal 依赖从该档移除（geometry_lock 的 fal 后端不受影响）；合成边界接缝风险
由 reverifying 目检判定。

**订正 D3（健全门加一条）**：mask 并集覆盖率 > 60%（`_MASK_MAX_COVER_FRAC`）→ 降级为
relational 并记 mask_degraded——锁定名存实亡时不假装锁定。

**订正 D3 再订正（fix_round 2，2026-07-23，F005 reverifying-1 B1 驱动）**：覆盖率门改为
**栅格化后实际并集 > 0.85 才降级**（`_MASK_MAX_COVER_FRAC=0.85`），且只拦「VLM 几乎把整图
标为可画」的病态。理由：reverifying-1 实测 0.60 上限把 3/3 真实照片全部挡在门外（第四档
实际不可达）；floor+window_wall 占 6-8 成是家具/窗帘的**合法**需求区，锁定承诺的本体是
mask 外的天花与实墙（大理石电视墙/灯带/开关面板——「我家」的感知主体）。覆盖率改用
栅格化并集实测（多边形面积和会重复计重叠区）。

**不变**：§D2（第四档非替换）、§D4（确定性 diff==0 硬指标）、§D5（mask 审计）、§5 验收总则
（命中率不劣于 relational、边缘自然度目检——正是 reverifying 要过的两关）。
