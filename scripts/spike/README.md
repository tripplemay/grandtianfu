# spike: L1 简模引导 vs L0 彩盒 A/B（calib-cure-b1 F011/F012）

第7步实拍出图的引导升级实验工具：把「半透明彩盒」（L0，产品现状）升级为「部件级
不透明 3D 简模」（L1：沙发有靠背扶手、书柜有隔板、餐桌有腿），在 relay + fal 双后端
A/B 实测是否带来落位/形体质变（`docs/3D模型引导-出图质变评估-20260717.md` §2）。

## 严格隔离（spec §D5，产品代码零改动）

- 全部代码在 `scripts/spike/`，**不 import `apps/api/main.py`**、不改任何产品文件；
- `perspective.py` / `catalog.py` / `plan2d_shapes.py` 用 importlib 按文件路径加载
  （`_product.py`）；aigc 包级模块（providers/config/acceptance/eval_harness/raster）
  经 `sys.path` 按包导入（只读消费，且仅真实出图时懒加载）；
- L0 prompt 模板**逐字复制**自 `apps/api/main.py:2263-2353`（`run_ab._geometry_lock_prompt`，
  来源行号已注明）；出图调用形态参照 `main.py:2475-2487 _edit_once`；
- 部件高度表硬编码在 `parts3d.py`（不进产品数据/目录）：sofa 座 420/靠背 800/扶手 620、
  bookshelf 框 2000+每 350mm 一层隔板、dining_table 面 760 厚 40+四腿、media 550、
  wine_cabinet 1400、coffee_table 420、desk 750、chair/desk_chair 座 450+靠背 900、
  plant 900 锥台近似、curtain 全高薄板（0..2700）、无 builder/spec 类型回退整盒
  （挂画沿产品墙面带 z0=1000）。整盒顶与产品 `_DEFAULT_HEIGHT_MM` 同数值，`item.z`
  覆盖时部件高按包络夹取 —— **L1 外包络 = L0 盒**，两臂只差内部结构；
- 简模一律**真实毫米世界**（层高 2700 = `perspective._REAL_CEILING_MM`），严禁借
  axon 压扁世界的 1450。

## PIPL 红线

- **空房照片一律不得进仓库**（`data/uploads` gitignore 的延伸）。照片路径只通过
  CLI/清单参数传入，放本地未跟踪目录；
- `--blank`（灰底）与两臂引导图不含照片像素，可作自证物入库；
- 真实出图产物（渲染图）无 PIPL 问题，可按 F012 约定存 `docs/test-reports/`。

## 用法

### 1. 单张 L1 引导图（`l1_guide.py`）

```bash
python3 scripts/spike/l1_guide.py \
  --photo /local/untracked/empty_472015c4.jpg \   # 或 --blank（灰底，离线自证）
  --calibration cal.json \      # {camera:{K,R,t}, img_wh:[W,H]}（产品 photo.calibration 亦可）
  --geometry data/projects/D/geometry.json \
  --furniture data/projects/D/schemes/default/furniture.json \
  --room r_live \               # 逗号分隔；merge 组照片请列全成员（如 r_foyer,r_live）
  --out /tmp/l1_guide.png
```

### 2. A/B 编排（`run_ab.py`）

```bash
# 干跑（默认建议先跑；零成本，只产两臂引导图+prompt）：
python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ --dry

# 真实出图（花钱！执行权在 F012/Evaluator，需用户预算授权；本地环境变量提供 key）：
OPENAI_BASE_URL=... OPENAI_API_KEY=... FAL_KEY=... \
python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ --backends relay,fal
```

`scenes.json`（路径相对清单文件目录解析；`"photo": "blank"` 用灰底）：

```json
[{"id": "study_798", "photo": "/local/untracked/empty.jpg",
  "calibration": "cal_798.json", "geometry": "geometry.json",
  "furniture": "furniture.json", "rooms": ["r_guest2"],
  "style": "modern light-luxury (现代轻奢)"}]
```

输出：`{scene}_{L0|L1}_guide.png`、`{scene}_{L0|L1}_prompt.txt`、
`{scene}_{arm}_{backend}.png`、`summary.md`（场景×引导×后端×score/fails/tokens 表 +
预算记账）、`rows.json`（结构化明细，供 F012 报告引用）。

## 两臂公平性（spec §D5）

同 photo / 同 camera / 同 furniture / 同 size；L0 = 产品 `annotate_boxes` 逐字 + 产品
prompt 逐字；L1 = 同 prompt 结构仅替换「彩盒→家具」映射段为简模措辞（"gray 3D
primitive mockups... replace each mockup with a photorealistic piece"），rug/墙面带/
附着/near/partial 降级话术全保留（仅去掉颜色指涉）；类型跳过集、调色序、legend、
`box_usability` 判定与产品逐字对齐。引导退化（`guide_sanity_issues`）默认阻断，
`--force` 可越过（会烧钱出错图，慎用）。

## 预算口径

- 每图记录 provider usage：relay = `usage.total_tokens`（relay 按 token 计费）；
  fal = 输出分辨率（`width x height`，按百万像素 MP 汇总，费用按 fal 模型单价换算）；
- `summary.md` 末尾给出 tokens 合计与 MP 合计；`rows.json` 含逐图明细与耗时；
- 量化指标复用产品 `acceptance.evaluate_geometry_lock`（auto_check 同款
  score/fail_reasons）+ `eval_harness.classify_failures`（失败类型归类）；
- 授权预算（用户 2026-07-17 裁决）：2 场景 × L0/L1 × 2 后端 ≈ 12-16 图（~¥20-30），
  本地 api + 用户 key，不碰生产 data。

## 已知简化（诚实边界）

- 房间过滤按清单 `rooms` 显式列出（产品用 `axon.merge_group_ids` 自动展开 merge 组；
  spike 不 import axon，merge 组照片须手工列全成员）；
- 产品出图前的 STALE_CALIBRATION / 布局 lint / 预算闸门不在 spike 复刻（输入由
  实验者手工把关）；`guide_sanity_issues` 门保留；
- brief 片段（`compile_brief`）不注入（spike 场景无 brief，两臂同缺 = 公平）；
- `photo="blank"` 灰底场景上若真实出图，`evaluate_geometry_lock` 的数值**无意义**
  （其 gain-fit 对常数参考图退化，盒内差恒 0）——量化只对真实照片场景有效；
  `--dry` 不调 evaluate，不受影响。
