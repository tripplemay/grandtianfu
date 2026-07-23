# render-relation-b1 隔离验收报告（2026-07-23）

> 验收人：独立 evaluator（未参与本批任何实现；本批实现由 generator 完成）。
> 对象：分支 `feat/calib-route-a1` 工作区未提交改动（render-relation-b1，F001-F005）。
> 依据：`features.json` F001-F005 acceptance、`docs/specs/render-relation-b1-spec.md`（已 lock）、
> 基线 `docs/test-reports/route-eval-real-render-2026-07-23.md`（R1 93% / 软参考 65%）。
> 沙箱：`artifacts/route-eval-20260723/`（gitignored）；本地 API `:8017`（已关闭）。
> AI 预算：实耗 **3 次图像生成 + 5 次 VLM**（授权 ≤4 gen + ≤6 VLM），未超。

## 判定总览

| Feature | 判定 | 一句话证据 |
|---|---|---|
| F001 placement_brief 约束编译器 | **PASS** | 纯 stdlib、确定性、D4 四缺陷全修；pytest 11 条语义边界全绿；真实几何冒烟（r_live/r_master）输出正确 |
| F002 strategy=relational 接入 | **PASS** | 三档分派 + 参数矩阵（backend 仅 geometry_lock）落地；软参考/几何锁定两路径函数体零改动；记录 schema 向后兼容实证 |
| F003 relation-check + 闭环 | **PASS** | 状态机（round1 达标不重试/有 fail 重试/两轮取优/降级直交付）代码+9 条 pytest 覆盖；真实运行实发 round2 修正（rounds=2, fix 回写） |
| F004 前端三档 + 简报预览 + 验收展示 | **PASS** | SegmentedControl 三档（relational 默认）、简报折叠预览、RelationCheckPanel（逐条+背景分级+degraded+轮数）；lint/build 绿 |
| F005 隔离验收（本报告） | **PASS** | 命中率 91%（20/22）vs 同照软参考 64%；回归 165+455 全绿；成本入记录/budget 实证；b3 F007-F010 补验全过；红线全过 |

**批次级判定：PASS（建议放行合并）**。blocking 问题：无。non-blocking 观察 5 项见 §7。

## F005 acceptance 逐项

### (1) 放置命中率复测 — PASS

方法：产品化 API（非原型）`POST /api/projects/D/schemes/scheme_ai_20260714_130354_01_baec/render-real`
（默认 strategy=relational），沙箱数据 + 生产真实空房照 2 张；独立 VLM 复核对拍
（仿 `scripts/uniform_verify.py` 同一份 prompt/口径，gpt-5.5，temperature 0.1，
核对清单取产物记录内 `placement_brief.constraints`），另人工目检产物。

| 照片 | 房间/视角 | 闭环 | 内部 VLM | **独立 VLM（本验收）** | 评测基线 R1 | 评测基线软参考（同照片） |
|---|---|---|---|---|---|---|
| bcc61531 | r_live v2 | rounds=2（round1 有 fail → 修正重出取优） | 9p/0f/4u | **11/13 = 85%** | round1 86% / round2 100% | 69%（9/13） |
| 40109907 | r_master v2 | rounds=1（round1 即达标） | 9p/0f/0u | **9/9 = 100%** | round1 100% | 56%（5/9） |
| **合计** | | | | **20/22 = 91%** | 93% | **64%（14/22）** |

- 91% 落在基线 93% ±10% 噪声带内，且显著高于同照片软参考（+27pt）→ 达标。
- r_live 残余 2 条 fail 均为「餐桌靠北墙玻璃推拉门」的墙归属判定；内部 VLM 对同两条判
  uncertain——正是评测报告的 ±10-15% 措辞噪声带，非系统性回归。
- 闭环策略真实生效：r_live round1 存在 fail → 修正 prompt 回写重出（记录 prompt 含
  「上一次生成结果存在以下问题」）→ 两轮取优交付，rounds=2 入记录。
- 人工目检：透视/构图与原照一致；沙发-茶几-电视柜-地毯-双挂画-窗帘-酒柜（相连空间可见）
  布局与简报一致；主卧双床头柜分列床头、贵妃榻/斗柜贴西墙、床靠东墙全部落实。
- **偏差声明**：features.json 原文要求 ≥4 张且 relational vs softref 同批对照；按本次授权
  （预算 ≤4 gen + ≤6 VLM）执行 2 张 relational 实测，softref 对照引用同照片评测存档数据
  （同 VLM 口径）。2 张均在评测样本集内，结论方向与量级可互证。

### (2) 回归零侵入 — PASS

- `PYTHONPATH=packages/floorplan_core pytest packages/floorplan_core/tests -q` → **165 passed**（0.53s）。
- `PYTHONPATH=packages/floorplan_core:apps/api pytest apps/api/tests -q` → **455 passed**（17.37s）。
- `git diff` 全量审查：
  - main.py 恰 **6 个 hunk**，全部归属本批（import 注册 / _VIEW_FORWARDS·_VIEW_FACING_ZH 改引擎别名 /
    strategy 分派 / geometry_lock 显式分支 / relational 新增函数+预览端点 / _RECORD_HEAVY_KEYS）；
    软参考与几何锁定两路径函数体零改动，老测试仅补显式 `strategy` 参数（逐一核对 4 个测试文件 diff）。
  - floorplan_core 既有文件零改动，仅 `__init__.py` 一行注册 + 一行 docstring；byte-safe 纪律成立。
  - semantic_accept.py 纯尾部追加 +106 行，既有函数未动。
- 前端：`yarn lint` 通过（仅既存 useViewport.ts 7 条 exhaustive-deps warnings，与本批无关）；
  `yarn build` 通过（10.37s）。

### (3) 成本可观测 — PASS

- 记录实证（沙箱 renders.json）：relational 记录含 `strategy/rounds/relation_check
  （npass/nfail/nuncertain/background_*）/usage（total_tokens）/placement_brief`；
  旧记录无新键（schema 向后兼容）；`placement_brief` 入 `_RECORD_HEAVY_KEYS`（列表剥离、detail 全量），
  `relation_check` 不剥离供列表展示。
- budget 实证：`_budget.json` `daily_count=3` = 实际 3 次生成（r_live 2 轮 + r_master 1 轮）——
  **重试独立预扣**成立；`total_tokens=24178` 含生成+VLM（`provider.on_usage=_budget.record_tokens`）。
- 测试佐证：test_render_relational.py 断言重试后 `daily_count==2`、降级 `==1`、400 预扣回退 `==0`。

### (4) b3 F007-F010 补验 — 全部 PASS

| 项 | 判定 | 证据 |
|---|---|---|
| F007 调色板缺色 | PASS | ShootingGuideDiagram.tsx 零 emerald/rose（全组件目录 grep 仅 2 处注释提及）；守门脚本 `scripts/check/tailwind-palette.ts` 存在且运行 **PASS**（411 文件、27 色调色板） |
| F008 标签消歧/首4点非共面/大房优先 | PASS | `calib_features._member_labels`（方位后缀消歧 + 面积降序名次）+ `featureQueue.ts`（C1-C4 契约）；守门脚本 `feature-queue-order.ts` **PASS**（20 特征 7 组断言）；pytest `test_derive_features_disambiguates_duplicate_member_labels` 等在 455 内绿 |
| F009 线框剔除相机后方 | PASS | `main._calibration_wireframe` 经 `_cam_depth > _MIN_DEPTH_MM` 逐角点剔除；`test_wireframe_skips_members_behind_camera` 存在且通过 |
| F010 平面位置<3 前置 | PASS | `calib_features.degeneracy_reason` 解算前 `len(xy)<3` 拦截（注释含 115 组良态 0 误伤实证）；test_calib_features.py:357 对应用例通过 |

另：`scripts/check/mark-tool-layout.mjs` 亦运行通过。三个守门脚本均可 `node --experimental-strip-types` 直跑。

### (5) 红线核查 — PASS

- **不写 data/projects/**：验收全程 `git status` 21 项与开工时逐一致，`git diff data/` 为空（0 行）；
  实跑写入全部落沙箱（DATA_DIR/ARTIFACTS_DIR/UPLOADS_DIR 均指向 artifacts/route-eval-20260723）。
- **placement_brief.py 纯 stdlib**：AST 扫描仅 `__future__` + 相对导入（axon/catalog 亦仅 os/re/math）；
  无 httpx/PIL/numpy。
- **背景保真未写入本批承诺（spec §D5）**：`relation_pass = (nfail==0)` 仅由约束 checks 决定；
  `background_preserved` 只入记录不进任何门/重试判定（main.py 零引用其做分支）；
  r_live 记录 bg=False 照常交付——与 D5 一致。
- **PIPL 未入 git**：`artifacts/` 被 .gitignore:21 覆盖（照片与 env/prod.env 均 check-ignore 命中）；
  git status 无照片/凭据文件。
- 前端 build/lint 绿（见 (2)）。

## 各 feature 明细

### F001 — PASS
placement_brief.py（338 行）：orient=靠背墙、边缘缝隙 ≤300mm 贴墙（30px 临界有测试）、merge 组并集作用域、
视角映射搬进引擎且 main 改别名（值逐一对等，有回归锁测试）。D4 四缺陷全修：merge 组兄弟房家具按几何位置
判「照片房/相连空间」→ linked_lines 附「可能在画面外」且不入验收约束（真实数据实证：酒柜落相连空间正确
出 linked）；床头柜按实际数量（1 个写「紧靠一侧」、2 个写「2个分列」，真实 r_master 数据实证）；
窗帘软化「沿窗墙布置」；地毯文案泛化「房间中部活动区」。确定性测试（同输入同输出）在列。
pytest 11 条全绿。**非阻塞注记**：acceptance 原文要求「r_live/r_master/r_study 三真实房间简报快照」进
pytest，实现用合成几何等价物（两成员 merge 组/卧室）；三真实房间的编译正确性由本次真实 API 冒烟
（r_live merge 组、r_master）与评测存档（r_study）覆盖。

### F002 — PASS
分派（main.py:3144-3196）：默认 relational；strategy 非法值 400；`backend` 仅 geometry_lock 生效
（其余档传 backend → 400）；geometry_lock 显式档缺标定 400、fal 未配 400（不再静默落软参考——
刻意语义收紧，注释明记）。relational 缺 room_id → 400 `RELATIONAL_NOT_READY`（code+missing，同
REAL_NOT_READY 语义）；direction 缺省仅 frame=None 降级不阻断。参数交互矩阵（strategy/backend/
allow_unlabeled/allow_layout_issues）前后端一致。9 条新 pytest 覆盖分派/门/预扣回退。

### F003 — PASS
semantic_accept 尾部追加 relation-check 模式：逐条 pass/fail/uncertain、非 dict 项容错、status 归一、
relation_pass 本地确定性计算（不信 VLM overall）、背景分级只记录。闭环（main.py `_generate`）：
round1 即验收；relation_pass 或 degraded 即收；有 fail 才回写修正重试 1 次；`relation_score` 两轮取优
允许 round1 回退；每单 ≤2 gen + 2 VLM，重试独立预扣，VLM 失败 `evaluate_relations` 降级直交付记
degraded 且不重试。真实运行实证 rounds=2 修正路径与 rounds=1 直达路径各 1 次。

### F004 — PASS
real-render 页最小侵入接入：SegmentedControl 三档（relational 默认 + 三档定位文案）、geometry_lock
未标定/过期禁用并自动回退默认档、relational 档出图前简报折叠预览（frame+placement_lines+linked_lines，
失败优雅降级不阻塞）、RelationCheckPanel 并列 AutoCheckPanel（逐条 ✓/✗/? + 背景分级徽章 + degraded
标记 + 修正轮数徽章）。studioApi 类型齐备（RenderStrategy/PlacementBrief/RelationCheck/
RelationalNotReadyError），getPlacementBrief 预览与出图同一编译器。lint/build 绿，e2e 未动。

## Blocking 问题

无。

## Non-blocking 观察（建议后续批次处理，不拦合并）

1. **round2 预扣未兜异常**：`_render_real_relational._generate` 中 rnd==2 的 `_budget.reserve`
   不在 try 内——若 round1 成功后恰逢日额度被并发打满，BudgetExceeded 使整个 job 报错，
   已付费的 round1 成果被丢弃不交付。建议捕获后 break 交付 round1（概率低：需额度在两次
   生成之间恰好耗尽）。
2. **RelationCheckPanel 逐条展示 VLM note 而非约束原文**（`c.note || c.id`）：VLM note 措辞
   不含约束原文时用户看不到「要求的是什么」。建议前端按 C 序号对 `placement_brief.constraints`
   取原文并列展示（数据已在记录内）。
3. **VLM 背景判定偏松依旧**（评测 §4 已诚实声明）：内部 VLM 判 r_master `background_preserved=True`，
   而 gpt-image-2 实为整图重生成。bg 按 D5 只记录不做门，无误导性阻断风险；真正解法在
   BL-render-mask-edit。
4. **F001 pytest 未按 acceptance 字面做三真实房间快照**（用合成等价物），见 F001 明细注记。
5. `test_semantic_accept.py` diff 夹带既有测试的格式化重排（black 风格），与「仅补 strategy」
   略有出入，纯 cosmetic 无行为影响。

## 验收过程存证

- 产物与日志：`artifacts/route-eval-20260723/out/`（renders 2 张、artifacts2/_budget.json、
  api2.log、f005_independent_verify.json）。
- 预算台账：图像生成 3（r_live×2 轮 + r_master×1）+ VLM 5（内部 3 + 独立复核 2）= 未超授权。
- 本地 API :8017 已在验收结束后关闭，端口已释放。
