# calib-cure-b3 验收报告（verifying-1，隔离 evaluator fan-out）

> 执行：5 个隔离 evaluator subagent（每 feature 一个，fresh context）+ 4 个对抗复核 subagent（只对 FAIL/PARTIAL，只许证伪）。
> 编排：主上下文只做机械汇总，未改写、未筛选、未软化任何判定（harness-rules.md 铁律 12）。
> 日期：2026-07-20。分支 feat/calib-cure-b3。工作流 wf_212bfc29-5ad。

## 判定汇总

| feature | 判定 | 对抗复核 |
|---|---|---|
| F001 | **PARTIAL** | refuted=False → PARTIAL |
| F002 | **PARTIAL** | refuted=False → PARTIAL |
| F003 | **PASS** | （PASS 未进复核） |
| F004 | **PARTIAL** | refuted=False → PARTIAL |
| F005 | **PARTIAL** | refuted=False → PARTIAL |

合计：PARTIAL 4 / PASS 1

---

## F001 — PARTIAL

### 描述

F001 的**主目标成立且已实测证实**：正对墙/共面点位在解算前就被拦下并给出拍摄级「角落重拍」可行动提示，门未放宽，零回归。但 acceptance 明写的另一条「**非共面良态点集不误触**」在可测量的范围内**不成立**，且根因是一处**未申报的 acceptance 偏离**。

【关于「主动缩减/前提翻转」复核的表态】F001 的 features.json notes **未声明任何主动缩减或前提翻转**（generator_handoff 中申报的两处缩减均属 F004，不在本次范围）。但我在独立核查中**发现了一处未申报的缩减**：acceptance 原文要求的判据是「3D SVD s3/s1≈0 = 点共面，**结合**解出相机高度/hfov 极端」——即几何判据与相机极端的**合取**；且 acceptance 明确允许实装在「degeneracy_reason 或 **assess 层**」（assess 在解算后运行，说明合取是被预期且被许可的）。实装只保留了几何一半（calib_features.py:455 `np.ptp(P[:,2])>1.0 and s[2]/s[0]<0.08`），丢弃了「相机极端」这一半，commit message 与 notes 均未提及此偏离。我的判断：**该缩减不成立**（既无技术必要性，也确实造成了下述缺陷）。

【已达成的部分（真实且有价值）】
1. 真病例覆盖彻底：在**生产几何** data/projects/D/geometry.json 上，r_guest2 与 r_foyer 的全部 8 组「单面墙」选点，s3/s1 **精确等于 0.00000000**（世界坐标派生自户型图，共面是精确的而非边缘的）→ 全部命中「角落重拍」文案。我原先担心的 0.08~0.15 边缘带在生产中对该失效模式基本不可达。
2. 端到端可达：不只是单测通过——保存路径与 dry_run 预览路径**都**返回 HTTP 400 + 该文案，且在 solve 之前（真「早拦」，不烧预算、不落坏标定）。前端链路代码层完整（studioApi.ts:51-56 抛 body.error → FeaturePointCalibrator.tsx:296,546-548 NoticeBanner tone="error"）。
3. 门未放宽：F001 只**新增**拦截分支，未放宽任何阈值；solve_pnp/_solve_pnp_general/_refine/_pose_known_K/_project3/_rodrigues 经 AST 逐函数比对与基线**完全一致**。
4. 零回归：两套 pytest 全绿 0 skip（437 + 154），golden 逐字节测试**确实执行**（未 skip）；测试文件为纯新增（无删除/弱化）；data/ 与 packages/floorplan_core/ 净 diff 为空；commit tag `feat(calib-cure-b3-F001)` 映射 features.json F001（铁律 10 OK）；F001 的 acceptance 文本在实现过程中**未被改写**（仅 status pending→completed）。

【未达成的部分（判 PARTIAL 的依据）】
「非共面良态点集不误触」被证伪：**8.7%（10/115）**真·良态选点（经 3px 手点噪声蒙特卡洛验证仍能把相机解到 <300mm）收到了「正对一面墙拍的照片标不出来…请**重拍这张照片**」。误拦带 s3/s1 ∈ [0.0035, 0.049]。危害在于文案不只是拦——它把用户**赶去重拍一张本来没问题的照片**，而用户实际只需换选点；这恰是 F001 立项要消除的「白点/白跑」。作者的新单测只覆盖了一个手挑的良态样例（通过），未探近平面带，故未暴露此问题。

【构造性证据：acceptance 原定设计本可避免】对全部 12 例误拦样本，解出的相机**全部健康**（高 1370–1446mm、hfov 70–72°，接近真值），即「几何退化 AND 相机极端」的合取**可 100% 豁免这 12 例误拦**；同时对真共面样本仍拦下 9/11，漏下的 2 例中 r_guest2 y=1700 的 reproj 高达 110648px、r_foyer y=2500 实际解得正确（位置误差 205mm/reproj 0.5px，本就不该拦）——即合取 + 既有 reproj 门可**同时**保住全部真拦截并消除误拦。建议 fixing 轮把该诊断改挂到 assess 层（acceptance 已许可），或将文案在相机健康时降级为「请改选跨两面墙的点」而非「请重拍照片」。

### 复现步骤

复现误拦（判 PARTIAL 的核心证据），在仓库根执行：

PYTHONPATH=packages/floorplan_core:apps/api:apps/api/tests python3 - <<'EOF'
import json, itertools, numpy as np
from pathlib import Path
from aigc import calib_features as cf
from test_calibration_quality import _synthetic_cam
cam_true, project = _synthetic_cam(); C=-cam_true.R.T@cam_true.t
g=json.loads(Path('data/projects/D/geometry.json').read_text())
inf=lambda uv: 40<uv[0]<2008 and 40<uv[1]<1496
rng=np.random.default_rng(23); tot=blk=0
for rid in ['r_foyer','r_live']:
    feats,_=cf.derive_features(g,rid)
    vis=[f for f in feats if inf(project(tuple(f['world'])))]
    for n in (4,5):
      for c in itertools.combinations(vis,n):
        P=np.array([f['world'] for f in c],float); s=np.linalg.svd(P-P.mean(0),compute_uv=False)
        if s[0]<1e-9 or s[2]/s[0]<1e-9: continue
        ds=[]
        for _ in range(9):
            pts=[(tuple(f['world']),tuple(np.array(project(tuple(f['world'])))+rng.normal(0,3,2))) for f in c]
            try: r=cf.solve_pnp(pts,img_wh=(2048,1536)); ds.append(float(np.linalg.norm(-r.R.T@r.t-C)))
            except Exception: ds.append(float('inf'))
        if np.median(ds)>=300: continue          # 只看真·良态选点
        tot+=1
        m=cf.degeneracy_reason([f['world'] for f in c])
        if m and "同一面墙" in m: blk+=1
print(f"真良态选点 {tot} 组, 被『重拍这张照片』误拦 {blk} 组 = {100*blk/tot:.1f}%")
EOF

预期输出：真良态选点 115 组, 被『重拍这张照片』误拦 10 组 = 8.7%

端到端 400 拦截复现：把上文 evidence §5 的探针内容写入 apps/api/tests/test_zz_probe.py（从 test_calib_features 导入 _CAL/_upload_photo，用 client_fal fixture，POST mode=points 的北墙 4 角共面点），跑 `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests/test_zz_probe.py -q -s`，验完请删除。

### 证据

【实际运行的命令与输出要点】
1) 两套 pytest（当前 HEAD）：
   `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q` → **437 passed in 18.66s**（0 skip）
   `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs` → **154 passed in 0.53s**（0 skip，无 skip 原因输出）
   `-k baseline_byte_for_byte` → **2 passed, 152 deselected**（golden 逐字节测试确实执行，非 skip）

2) 基线对照（git worktree，dc9787f = b2 收口 HEAD）：
   基线 → **433 passed**；F001 commit 50950a7 → **434 passed**（净 +1 = 新测本身）；HEAD → 437。无回归。
   注：generator_handoff 称「基线 434」、F001 commit message 称「全 api 433 passed」——实测分别为 433 / 434，二者均差 1，属记账噪声非缺陷。

3) 红线核查：
   `git diff --stat dc9787f...HEAD -- data/` → 空；`-- packages/floorplan_core/` → 空
   `git diff dc9787f...HEAD -- apps/api/tests/*.py | grep "^-"` → **无输出**（测试纯新增，无删除/弱化）
   AST 逐函数比对基线 vs HEAD：solve_pnp / _solve_pnp_general / _refine / _pose_known_K / _project3 / _rodrigues **identical=True**；仅 degeneracy_reason(F001) 与 derive_features/_with_tier(F003) 变更。
   `git diff 56ac9be 50950a7 -- features.json` → F001 条目仅 `"pending"`→`"completed"`，acceptance/notes 一字未改。
   ruff：`python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py` → **All checks passed!**；main.py 的 1 条 I001 经 `git show dc9787f:apps/api/main.py` 提取后 `ruff check --isolated --select I` 复现 → **既有基线，非本批新增**。

4) 实装位置：apps/api/aigc/calib_features.py:453-459（新分支），判据在 :455
   `if float(np.ptp(P[:, 2])) > 1.0 and s[2] / s[0] < 0.08:`
   调用点 apps/api/main.py:985（位于 _validate_points_payload，main.py:944），端点 main.py:1196-1200 → `JSONResponse(status_code=400, ...)`，**在 solve_pnp(main.py:1214) 之前**。

5) 端到端探针（我临时写入 apps/api/tests/test_zz_evaluator_f001_probe.py，跑完已删除，工作区已复原）：
   [PROBE-A save] status=400 body={'error': '所选点几乎都在同一面墙上(共面) — 正对一面墙拍的照片标不出来。请站到房间角落, 让画面同时带到两面相邻墙 + 地面墙角和天花板转角, 再重拍这张照片。'}
   [PROBE-B dry_run] status=400（同一文案 → 预览路径同样早拦）
   [PROBE-C 良态角落点] status=200，quality.level=good，reproj=0.2（不误触）

6) 生产几何实证（只读 data/projects/D/geometry.json，未写入）：
   r_guest2 单墙选点 y=5700(n=6)/y=1700(n=4)/x=15150(n=10)/x=18150(n=4) → s3/s1 **0.00000000**，全部 BLOCKED(corner-guidance)
   r_foyer 单墙选点 y=4900(n=8)/y=2500(n=4)/x=4950(n=16)/x=6750(n=8) → s3/s1 **0.00000000**，全部 BLOCKED(corner-guidance)

7) 误拦定量（用仓库自带已知良好合成相机 test_calibration_quality._synthetic_cam，真值 C=[7500,6500,1400] focal 1450）：
   穷举 r_foyer/r_live 可见特征的 4/5 点组合，先用 3px 点击噪声 ×9 次蒙特卡洛筛出「真·良态」(中位位置误差<300mm) 共 **115 组**；其中被「同一面墙」文案拦下 **10 组 = 8.7%**，误拦带 s3/s1 min=0.0035 max=0.0490（门限 0.08）。
   噪声敏感性复核（对零噪声下被误拦的 8 组，各 30 次蒙特卡洛）：sigma=1px→中位 17mm(7/8 <300mm)；sigma=3px→中位 40mm(**8/8**)；sigma=5px→中位 63mm(7/8)。即这些组合**不是**病态条件数，抗真实点击噪声。
   合取可行性验证：12 例误拦样本解出相机高 1370–1446mm、hfov 70–72°，对照 perspective.CAMERA_Z_RANGE_MM=(800,2200)、HFOV_RANGE_DEG=(35,110) → **12/12 判定「不极端」**，故 acceptance 原定合取可全部豁免；对真共面样本合取仍拦下 9/11，漏下 2 例中 1 例 reproj=110648px（既有 assess reproj 门可拦）、另 1 例实际解得正确(位置误差 205mm/reproj 0.5px)。

8) 前端文案可达性（代码层，非目视）：apps/web/src/lib/studioApi.ts:51-56 `detail = body.error ...; throw new Error(detail)` → FeaturePointCalibrator.tsx:296 `setError(e.message)` → :546-548 `<NoticeBanner tone="error" title="标定失败">{error}</NoticeBanner>`。

9) 工作区复原确认：`git status --short` → 仅剩会话开始前既存的未追踪文档 docs/实拍效果图-几何锁定优化方案-20260717.md。未修改任何产品代码；临时探针与 worktree 均已清除。

### 未验证项（BLOCKED-NEEDS-USER）

以下项**必须由用户在真实浏览器人工操作/目视确认**，本轮未获当面配合，一律未验证——不臆测结果，既不因此判 PASS 也不因此判 FAIL（均属 F006 [L2] 范围，本次 F001 判定不依赖它们）：

1. [L2] BLOCKED-NEEDS-USER — 真实浏览器中，正对墙拍病例照 r_guest2（uploads/D/empty/472015c4…jpg）走完整点选流程后，「角落重拍」文案是否**目视可见、位置显眼、用户读得懂**。我只验证到代码链路完整（400 → studioApi 抛错 → NoticeBanner 渲染）与 API 层返回正确，**未做任何像素/视觉确认**。
2. [L2] BLOCKED-NEEDS-USER — 该引导是否真的实现了「不再白点」：即用户在**点满 4 点之前**能否得到预防性提示，还是必须点满 4 点提交后才撞到 400。按代码，degeneracy_reason 在 _validate_points_payload 内，**只在提交（含 dry_run 预览）时触发**，故用户仍需先点满 4 点；这是否满足用户对「不白点」的期待，需用户裁定。
3. [L2] BLOCKED-NEEDS-USER — 上文实测的 8.7% 误拦在**真实用户点选习惯**下的实际发生率。我的数字来自穷举组合，真实用户受 F003 priority 排序引导、倾向选铺开的结构角，实际率很可能低于 8.7%，但**具体多少未测**。
4. [L2] BLOCKED-NEEDS-USER — 误拦发生时的真实用户代价（用户是否真会照文案跑去重拍一张本来可用的照片）。

另需 Planner/用户裁决（非阻塞验收，属修复方向）：本 PARTIAL 是否进 fixing 轮。建议修法二选一：(a) 按 acceptance 原文把判据改为「几何退化 AND 解出相机极端(assess 层)」；(b) 保留解算前拦截，但在相机健康时把文案从「请重拍这张照片」降级为「请改选跨两面墙的点」。(a) 更贴 acceptance 且实测可 100% 消除误拦。

### 对抗复核

- refuted: **False** → final_result: **PARTIAL**

PARTIAL 成立, 但严重度被原报告高估约 4 倍。【复现】原脚本在系统 python3 上逐字复现 (115/10/8.7%); 两套 pytest 437+154 全绿 0 skip; 非环境误报。【非既有基线】git show dc9787f 确认基线 degeneracy_reason 无 s[2]/s[0] 分支, 该分支为 F001 commit 50950a7 新增, 归咎本批正确。【核心成立】calib_features.py:455 的新分支确实会在 solve 前 (main.py:985 _validate_points_payload -> 400, 早于 main.py:1214 solve_pnp) 拦下能解出健康相机的点集: 用真实 perspective.assess_calibration_quality 复核, 60/60 通过 (σ=1/3/5px), reproj 0.4-0.8px, camera_z 1392-1400mm, hfov 70.0-70.7° —— 即用户点完 4 个点后, 被一条『请重拍这张照片』赶去重拍一张本来没问题的照片, 正是 F001 立项要消除的白点/白跑。【可达性反而更强】误拦涉及的特征全是 tier=structural priority=0 (天花板角) 与 tier=opening priority=1 (门框), 恰是 F003 指示前端优先推荐的点。【原报告的量级错误 — 我的修正】(a) 原脚本 r_foyer/r_live 双重循环对同一组合重复计数 (10 行 = 6 个去重组合, 115 分母同样虚高); (b) 9 次试验 seed=23 的 median<300mm 良态判据 seed 脆弱, 把其中 2 组误判为良态 —— 60 次试验下位置误差实为 4237mm 与 7165mm, 属真退化, 拦得对。去重 + 以 assess.ok 为判据重算全部 316 个被拦组合: 301 组拦得对, 5 组边际, **仅 2 组为稳健良态误拦**, 且全部只发生在 4 点最低限, 无任何 n=5 组合被误拦。故真实误拦率远低于 8.7%。【根因诊断成立且被我强化】误拦点集根本不是墙面: 面法线与水平面夹角 16.7-35.1°、与相机主轴夹角 84.7-88.3° (近 edge-on), 由天花板角 z=2700 + 门头 z=2050 构成的近水平面; 平面 PnP 在焦距未知时仅当平面近 fronto-parallel 才退化, edge-on 平面可正常解出 f —— 而真正该拦的那组主轴夹角仅 29.2° (近 fronto-parallel)。故 acceptance 原文『s3/s1≈0 结合解出相机高度/hfov 极端』的合取是承重数学而非修辞, 相机侧那一半正是区分 fronto-parallel 与 edge-on 的判据; 实装只保留几何一半即误拦的成因, 且该偏离在 notes 与 commit message 中均未申报。【附加缺陷】对这些点集, 文案断言『所选点几乎都在同一面墙上』属事实错误 (点跨两个房间的天花板角 + 两扇不同的门), 处方『再重拍这张照片』亦错 —— 照片没问题, 只是选点不巧。【建议 fixing】加上相机侧合取 (acceptance 已许可挂 assess 层), 或在相机健康时把文案降级为『请改选跨两面墙的点』而非『请重拍照片』; 改动面小。【工作区】未修改任何产品代码, git status 仅剩会话前既存的未追踪文档; data/ 与 packages/floorplan_core/ 净 diff 为空。

---

## F002 — PARTIAL

### 描述

F002「拍摄/构图引导 UI(上传+标定入口)」实装了 acceptance 的上传入口一半, 且质量合格; 但 acceptance 明文点名的另一半「标定入口」只被部分覆盖, 且「简示意」完全缺失。

【已满足】(1) 上传入口 BaselinePhotosCard 加 NoticeBanner, 四条内容要点齐全(角落机位/两面相邻墙/地面墙角+天花板转角/避免正对单面墙), 真实无头浏览器实测渲染成功; (2) 复用设计系统 NoticeBanner, F002 自身零手写配色类; (3) dark: 成对完整; (4) 禁 bg-*-50 —— 渲染类含 bg-sky-50, 但它来自共享组件 status.tsx 的 NOTICE_TONE 且与 dark:bg-sky-900 成对, 非本批硬编码浅底, 判合规; (5) tsc/next lint 全绿; (6) 红线净空, commit tag 映射 features.json(铁律 10)。

【未满足 1 — 标定入口只覆盖一半】acceptance 原文是「在实拍照上传入口 **+ 标定入口**加拍摄指南: 角落机位 / 画面带两面相邻墙 / 地面墙角+天花板转角入画 / 避免正对单面墙」。F002 的 notes 把标定入口那一半委托给 b2 F006 既有 banner。**我独立复核该委托是否成立: 判定「仅部分成立」。** b2 F006 banner(FeaturePointCalibrator.tsx:343-356)确实覆盖「地面墙角+天花板转角入画」与「铺开到不同墙面」(≈两面墙, 措辞更弱), 但**完全不含「角落机位」与「避免正对单面墙」**——而这两条恰是 b2 L2 实证后 b3 批次赖以立项的核心新认知。全前端 grep 证实 "角落" 与 "正对一面墙" 二字仅存在于 BaselinePhotosCard 一处。标定入口处这两条只在 F001 后端 degeneracy_reason 触发时**反应式**出现(用户已经点完退化点集之后), 而非事前引导。实际危害有限(到标定入口时照片已拍完, 重拍指令由 F001 精准触发递送), 但 acceptance 措辞明确且未达成。

【未满足 2 — 简示意缺失】acceptance 写的是「拍摄指南(文字+简示意)」。两处 banner 均为纯文字, 无任何图示/SVG 示意。此项完全未实装。

【非阻断观察】(a) banner 实测位于「上传照片」按钮**下方**(实测 y: 按钮 590, banner 643), 与 commit message 自称的「前置于上传」在 DOM/视觉顺序上不符——同卡片内紧邻, 用户在触发文件选择前仍能看到, 影响轻微; (b) NoticeBanner 组件内部已带 mb-3(status.tsx:299), F002 又外套一层 <div className="mb-3">, 双重下边距, 纯外观。

结论: 主体可用且质量达标, 但两条明文 acceptance 项未达成, 修复成本很小(标定入口 banner 补两句 + 加一张 inline SVG 示意), 故判 PARTIAL 而非 PASS。

### 复现步骤

1. cd /Users/yixingzhou/project/grandtianfu/apps/web
2. npx tsc --noEmit                                     # 期望 exit 0
3. npx next lint --file src/components/studio/baseline/BaselinePhotosCard.tsx   # 期望 no warnings
4. 复现上传入口 banner(自动化): 在 apps/web/e2e/ 放一个临时 spec, goto '/studio/projects/D/baseline',
   断言 getByText('拍摄建议（直接影响能否标定/精准落位）') 可见, 并核对 body innerText 含
   站在房间角落 / 两面相邻的墙 / 地面墙角 / 天花板转角 / 避免正对一面墙平拍;
   npx playwright test <spec> --reporter=list  (webServer 自动起沙箱 api:8010 + web:3100, 不碰 data/projects)
   跑完删除该 spec 与 .e2e-sandbox/
5. 复现「标定入口缺两条要点」: 
   grep -rn "角落" apps/web/src --include="*.tsx" --include="*.ts"   # 仅 BaselinePhotosCard 命中
   再实读 apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx:341-357 对照 b2 F006 banner 原文
6. 复现「简示意缺失」: 实读 BaselinePhotosCard.tsx:322-338, banner children 无 <svg>/<img>
7. 红线: git show c0687de --stat; git diff --stat 56ac9be..c0687de -- data/ packages/floorplan_core/

建议修复(供 Generator 参考, 均为小改):
 (a) FeaturePointCalibrator 构图 banner 补两句「站房间角落拍 / 避免正对一面墙平拍」, 与 F001 后端文案口径一致;
 (b) 加一张 inline SVG 简示意(俯视: 相机在角落 -> 视锥罩住两面相邻墙 = ✓ / 相机正对单墙 = ✗), 上传与标定两处复用同一组件;
 (c) 可选: 去掉 BaselinePhotosCard.tsx:325 外层 mb-3(NoticeBanner 自带), 并把 banner 移到卡片头部行之上以真正「前置于上传」。

### 证据

【1. 真实无头浏览器实测(自建临时 Playwright spec, 沙箱数据, 跑完即删)】
$ cd apps/web && npx playwright test tmp-b3f002-check --reporter=list
  ✓ 1 e2e/tmp-b3f002-check.spec.ts › F002: 基线页上传入口出现拍摄引导 banner (8.6s)  1 passed
输出要点:
  BANNER_TEXT >>> 拍摄建议（直接影响能否标定/精准落位） | 请站在房间角落拍,让画面同时带到两面相邻的墙 + 地面墙角 + 天花板转角;避免正对一面墙平拍——正对单面墙的照片在几何上无法标定,需要重拍。
  BANNER_CLASS mb-3 rounded-xl border p-3 text-sm border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900 dark:text-sky-200
  BANNER_BOX {"x":683,"y":643,"width":525,"height":20}
  UPLOAD_BTN_BOX {"x":1129.8,"y":590,"width":91.2,"height":28}   <- banner 在按钮下方
五条关键词逐条 assert 通过: 站在房间角落 / 两面相邻的墙 / 地面墙角 / 天花板转角 / 避免正对一面墙平拍
元素级截图(深色主题)目视: 深蓝底 + 浅蓝字, 对比度良好, 无白底突兀。

【2. 标定入口覆盖度 — 源码级判定证据(强于页面 innerText)】
$ grep -rn "角落" apps/web/src --include="*.tsx" --include="*.ts"
  apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx:323  (代码注释)
  apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx:330  请<span className="font-semibold">站在房间角落</span>
$ grep -rn "正对" apps/web/src --include="*.tsx" --include="*.ts"
  BaselinePhotosCard.tsx:322/334/335 (本批新增) + real-render/page.tsx:188 与 BaselinePhotosCard.tsx:70 (皆为「窗正对」窗朝向枚举, 无关)
=> 全前端仅 BaselinePhotosCard 一处。FeaturePointCalibrator / PerspectiveCalibrator 均无。
实读 apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx:341-357 (b2 F006 banner 原文):
  「点位尽量铺开到不同墙面、并覆盖不同高度(地面墙角 + 天花板转角/门窗框顶)...拍摄时也尽量让画面同时拍到地面墙角与天花板转角。」
  -> 含「地面墙角+天花板转角入画」「不同墙面」; 不含「角落机位」「避免正对单面墙」。
实读 apps/web/src/components/studio/real-render/PerspectiveCalibrator.tsx:412-444: 专家模式警告 + roomMissing/几何错误 banner, 无拍摄构图引导。
角落重拍文案的唯一来源是后端 F001(反应式): apps/api/aigc/calib_features.py:458
  "请站到房间角落, 让画面同时带到两面相邻墙 + 地面墙角和天花板转角, 再重拍这张照片。"
  经 FeaturePointCalibrator.tsx:546-550「标定失败」banner / CalibrationPreviewPanel 透出。

【3. 简示意缺失】实读 BaselinePhotosCard.tsx:322-338 与 FeaturePointCalibrator.tsx:341-357 全文, 两处 banner children 均为纯文本 + <span className="font-semibold">, 无 <svg>/<img>/图示组件。

【4. 设计系统合规溯源】apps/web/src/components/studio/ui/status.tsx:275-307
  NOTICE_TONE.info = 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900 dark:text-sky-200' (共享组件, 三组均成对)
  NoticeBanner 自带 className 前缀 'mb-3 rounded-xl border p-3 text-sm' -> 与 F002 外层 <div className="mb-3">(BaselinePhotosCard.tsx:325) 构成双重下边距。

【5. 静态检查】
$ cd apps/web && npx tsc --noEmit ; echo TSC_EXIT=$?   ->  TSC_EXIT=0 (无输出)
$ npx next lint --file src/components/studio/baseline/BaselinePhotosCard.tsx  ->  ✔ No ESLint warnings or errors

【6. 红线与铁律 10】
$ git show c0687de --stat
  apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx | 20 +++++++-  |  features.json 2 +-  |  progress.json 4 +-
  (3 files changed, 22 insertions(+), 4 deletions(-)) -> 未碰 data/projects/, 未碰 packages/floorplan_core/, 未碰 golden
$ git diff --stat 56ac9be..c0687de -- data/ packages/floorplan_core/   -> 空输出
$ git status --short data/ packages/floorplan_core/ apps/web/e2e/       -> 空输出(临时 spec 与 .e2e-sandbox 已清理)
commit tag feat(calib-cure-b3-F002) 映射 features.json F002 ✓

【7. 上传入口唯一性核查(确认 BaselinePhotosCard 就是「实拍照上传入口」)】
$ grep -rn "uploadBaselinePhoto" apps/web/src
  BaselinePhotosCard.tsx:219 (空房实拍照, 无 purpose)
  editor/geometry/UnderlayControls.tsx:33  purpose:'underlay'      (底图描摹, 非实拍照)
  editor/geometry/WallPhotoControls.tsx:54 purpose:'wall_material' (墙面材质, 非实拍照)
=> 实拍照上传入口唯一, F002 落点正确。
readOnly 门控 (BaselinePhotosCard.tsx:324) 由 baseline/page.tsx:191 readOnlyPhotos = status==='superseded' || isHistorical 驱动, 语义合理(历史/已废版本不引导拍摄)。

### 未验证项（BLOCKED-NEEDS-USER）

【BLOCKED-NEEDS-USER】以下项必须真实用户/真实浏览器人工参与, 本轮未获授权, 未执行, 不臆测结果:
1. 引导文案的**实际行为效力**——真实用户读到该 banner 后是否确实改用角落机位重拍、重拍照片是否随后标定成功。此为 F006 [L2] 范围(「正对墙拍照片 -> 不再白点」「角落机位照片 -> 能标成功」), 需用户当面操作真实浏览器 + 只读重拉 PIPL 病例照。本轮仅证明 banner 存在且文案内容齐全, **不代表已证明其解决用户报障**。
2. 「简示意」的视觉设计取舍需用户/设计裁决(是否要图、画成什么样), 我只客观记录其当前缺失, 不代替裁决。
3. 移动端/窄屏下该 banner 的排版与可读性未做多视口目视确认(本轮仅 1280x720 桌面视口 + 深色主题)。

【本轮 L2 未阻断的部分】上传入口 banner 的渲染存在性、文案内容、dark: 配色、位置关系, 均已由本地沙箱无头浏览器自动化实测取得客观证据, 不属 blocked。

### 对抗复核

- refuted: **False** → final_result: **PARTIAL**

PARTIAL 判定成立，非环境误报，非归咎既有基线。独立复现（全部在 HEAD 上做，已含 F003/F004 对 FeaturePointCalibrator 的后续修改）：

【证伪尝试 1 — acceptance 被软化/陈旧 checklist】失败。F002 acceptance 在规划 commit 56ac9be 与 HEAD 逐字节相同，原文含「上传入口 + 标定入口加拍摄指南(文字+简示意)」；docs/specs/calib-cure-b3-spec.md §D2 独立同述。两项要求真实且未被改写。

【证伪尝试 2 — 标定入口换措辞已覆盖】失败。将 grep 从「角落/正对」扩到「两面|相邻墙|平拍|单面墙|转角处|房间角|对着一面」全量扫 apps/web/src：除 BaselinePhotosCard.tsx:322-335 外，仅命中 fieldStyles.ts 注释与 PerspectiveCalibrator.tsx:591 的 aria-label「地面角 N 对应房间角」（无关）。实读标定入口全链：real-render/page.tsx:876-905（透视标定按钮+说明）无拍摄引导；page.tsx:1395-1413 模态包装未传引导；FeaturePointCalibrator.tsx:341-358（b2 F006 + F003 追加）覆盖「铺开到不同墙面」「地面墙角+天花板转角」，但确实不含「角落机位」与「避免正对单面墙」。委托 b2 F006 仅部分成立，原判定准确。

【证伪尝试 3 — 简示意存在于别处】失败。grep「示意|图示」全 src 零命中；calib/baseline 内 4 处 <svg>/<img> 均为照片叠加层（CalibrationWireframeOverlay / y 线 / 缩略图 / 标定照本体），非构图示意；决定性证据：git diff --stat 56ac9be..HEAD -- apps/web/public/ 为空，本批未交付任何图示资源。

【证伪尝试 4 — 环境误报】不适用且已排除。两条未满足项均为源码存在性事实，不受依赖缺装/版本漂移/测试隔离影响。工具链仍实跑：npx tsc --noEmit exit 0（Node v25.7.0，项目 pin 22，未产生假失败）；npx next lint --file BaselinePhotosCard.tsx → No ESLint warnings or errors。

【最强反驳角度的处理】acceptance 内「开工前查现有引导位避免与 b2 F006 重复」可被读作授权省略标定入口——予以驳回：「避免重复」不等于「省略」，且缺失的两条恰是 b2 L2 实证（正对墙拍几何退化）后 b3 赖以立项的新认知，b2 F006 不可能已含。更关键：「简示意」在两处入口均缺失且无任何委托理由，故即便按最宽松读法 F002 亦不能达 PASS。未放宽口径。

【红线与铁律】git diff --stat 56ac9be..HEAD -- data/ packages/floorplan_core/ apps/web/public/ 空；commit tag feat(calib-cure-b3-F002) 映射 features.json F002（铁律 10 ✓）。

【非阻断】NoticeBanner 自带 mb-3（status.tsx:299）与 BaselinePhotosCard.tsx:325 外层 mb-3 构成双重下边距，纯外观。

【L2】F002 两条缺口均可静态判定，不依赖用户人工浏览器操作，无需 BLOCKED-NEEDS-USER 项，判定亦未以「未验证」为由定 FAIL。

本次验证未修改任何产品代码、测试或状态文件。

---

## F003 — PASS

### 描述

F003「特征供给稳健化（结构角优先，窗特征按 wtype 置信度降级/可跳过）」逐条 acceptance 均以实物证据满足，判 PASS。

【notes 声明的调查结论 / 主动缩减，独立复核结论】
(1) 「wtype 是人工标注的几何数据，非现场推导」——**成立**。我独立取证三条互不依赖的证据链：(a) 编辑器 GeometrySidePanel.tsx:411-415 是一个 `options={['normal','full','high']}` 的下拉，用户可随手改；(b) floorplan_core/axon.py:75 与 :923 从 SVG `data-wtype="..."` 正则解析/回写，tests/svg2geometry.py:262 亦以 `gv("data-wtype","normal")` 读取；(c) apps/web/src/lib/floorplan/geometry.ts:698 直插窗时硬写 `wtype:'normal'` 默认值。全链路无任何一处从照片/现场推导 wtype。故 `wtype=='full'` 只代表"图纸标为落地窗"，该批把窗特征降级为存疑点的前提站得住。
(2) 「后端 id 字典序排序契约刻意不动，轮候顺序交前端按 priority 排」——**设计成立，但实际行为增量被 commit message 高估（non-blocking）**。成立的部分：derive_features 的唯一后端消费者是 main.py:1334 的 features 端点，无第二处依赖顺序的消费方，故"数据层给事实、呈现层定顺序"正交拆分是自洽的，且保住了既有 binding/UI 的 id 引用零回归。被高估的部分：我在真实生产几何 data/projects/D/baselines/v1 上对**全部 20 个房间**实算，id 字典序与 priority 序**完全一致**（id 前缀恰好 ceilcorner/corner < door/doorhead < winhead/window），即前端 `byPriority` 在当前数据上是**行为空操作**。F003 对用户真实可见的增量是「辅助·可跳过」徽章 + caveat 文案 + banner 一句话，不是队列重排。这不构成 acceptance 失败（priority 契约显式且对未来 id 变更有防御价值，测试也钉死了 priority 严格单调），但 commit message 里"队列按 priority 轮候（结构角先、存疑窗点垫后）"的表述超出了实测可观察到的变化。

【给 F006 的关键前提提醒】spec §4.2(c) 的 L2 检查项「窗几何失配不再产生无对应物的必点项」**无法在 acceptance 点名的 r_guest2 / r_foyer 上验证**——我实算这两个房间 derive_features 产出 0 个 optional 窗特征（该二室无 wtype=='full' 的窗）。可实际验证该项的房间是 r_garden(8 个 optional)/r_liveext(8)/r_master(6)/r_bed_g(6)/r_bath_g(6)/r_vest(4)/r_balc(4)。F006 若沿用 r_guest2/r_foyer 会得到"看不到窗特征"的空验证。

【红线核查全部通过】data/projects 净 diff 为空；packages/floorplan_core 净 diff 为空；golden 逐字节测试实跑通过（非 skip）；F003 单 commit 只碰 5 个文件且全在 batch_scope.allowed_paths 内；b2 解算内核（solve_pnp/_solve_pnp_general/assess）不在 diff hunk 范围内，门阈值一字未改；commit tag `feat(calib-cure-b3-F003)` 映射 features.json F003（铁律 10 满足）。我未修改任何产品代码，未在仓库落任何文件。

### 复现步骤

全部命令在 /Users/yixingzhou/project/grandtianfu (branch feat/calib-cure-b3, HEAD f0f8e33) 下执行：

# 1. 两套 pytest（0 skip）
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q --ignore=apps/api/tests/test_zz_evaluator_f001_probe.py
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs

# 2. golden 逐字节实跑（确认 passed 而非 skipped）
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -k "byte_for_byte or baseline" -v

# 3. 零回归节点 id 差分
git worktree add -f --detach /tmp/wt-parent b6c555c
git worktree add -f --detach /tmp/wt-f003 459c438
PYTHONPATH=/tmp/wt-parent/packages/floorplan_core:/tmp/wt-parent/apps/api python3 -m pytest /tmp/wt-parent/apps/api/tests -q --collect-only 2>&1 | grep "::" | sed "s|.*/apps/api/tests/||" | sort > /tmp/base_ids.txt
PYTHONPATH=/tmp/wt-f003/packages/floorplan_core:/tmp/wt-f003/apps/api python3 -m pytest /tmp/wt-f003/apps/api/tests -q --collect-only 2>&1 | grep "::" | sed "s|.*/apps/api/tests/||" | sort > /tmp/f003_ids.txt
comm -23 /tmp/base_ids.txt /tmp/f003_ids.txt   # 期望空 = 零回归
comm -13 /tmp/base_ids.txt /tmp/f003_ids.txt   # 期望恰好 2 条 F003 新测

# 4. 真实几何实算（只读，复现 priority 序 == id 序 与 optional 分布）
PYTHONPATH=packages/floorplan_core:apps/api python3 -c "
import json
from aigc import calib_features
G=json.load(open('data/projects/D/baselines/v1/geometry.json'))
for r in G['rooms']:
    f,_=calib_features.derive_features(G,r['id'])
    idord=[x['id'] for x in f]
    priord=[x['id'] for x in sorted(f,key=lambda z:(z['priority'],z['id']))]
    print(r['id'],'n=',len(f),'optional=',sum(1 for x in f if x['optional']),'id==pri:',idord==priord)
"

# 5. 静态门
cd apps/web && npx tsc --noEmit
cd apps/web && npx next lint --file src/components/studio/real-render/FeaturePointCalibrator.tsx --file src/components/studio/real-render/PerspectiveCalibrator.tsx --file src/lib/studioApi.ts
python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py

# 6. ruff format 偏差属既有基线（对照法）
git show dc9787f:apps/api/aigc/calib_features.py > /tmp/base_cf.py
python3 -m ruff format --check --config ruff.toml /tmp/base_cf.py   # 基线同样 would reformat

# 7. 红线
git diff --stat dc9787f...HEAD -- data/projects/ data/ packages/floorplan_core/   # 期望空
git show --name-only --format= 459c438                                            # 期望 5 文件全在 allowed_paths

### 证据

【1. 两套 pytest 全绿 0 skip（实跑）】
- `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q --ignore=apps/api/tests/test_zz_evaluator_f001_probe.py` -> `437 passed in 18.01s`（0 skip；--ignore 见第 6 条并发说明）
- `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs` -> `154 passed in 0.58s`（0 skip）
- golden 逐字节实跑：`pytest packages/floorplan_core/tests -q -k "byte_for_byte or baseline" -v` -> `2 passed, 152 deselected`，来自 test_render_snapshot.py，**passed 非 skipped**（.phase0-baseline 存在且比对通过）

【2. 零回归硬证据（worktree 节点 id 逐条对照）】
- 干净 worktree @dc9787f(b2 基线) -> `433 passed`
- 干净 worktree @b6c555c(F003 之父，含 F001/F002) -> `434 passed`
- 干净 worktree @459c438(F003 本体) -> `436 passed`
- 节点 id 集合差分（父 vs F003）：`comm -23 base_ids f003_ids` = **空**（无任何既有测试被删/改名）；`comm -13` = 恰好 2 条：
  `test_calib_features.py::test_derive_features_tiers_structural_first_and_downgrades_windows`
  `test_calib_features.py::test_derive_features_tier_fields_present_on_every_feature`
- `git show --numstat 459c438` -> `60  0  apps/api/tests/test_calib_features.py`（纯新增 0 删除，既有 derive_features 测试原封）
- 注：commit message 自称"基线 434"是 off-by-one（真实 b2 基线 433，434 是 F001 之后），F003 自身数字 436/+2 正确。non-blocking 文档瑕疵。

【3. acceptance 逐条对应的实现位置（读码）】
- apps/api/aigc/calib_features.py:42-77 `_KIND_TIER` 映射 + `_with_tier()`：wall_corner/ceiling_corner->(structural,0,False,None)；door_jamb->(opening,1,False,None)；door_head->(opening,1,False,_DOOR_HEAD_CAVEAT)；window_floor/window_head->(uncertain,2,**True**,caveat)。未知 kind 保守回落 opening（不误判存疑）。
- calib_features.py:197-200 `return sorted((_with_tier(f_) for f_ in feats), key=lambda f_: f_["id"]), members` —— id 字典序契约保留。
- apps/web/src/lib/studioApi.ts:317-323 `CalibrationFeature` 增 tier/priority/optional/caveat_zh 类型契约。
- FeaturePointCalibrator.tsx:64-65 `byPriority`；:170 `queue = [...features].sort(byPriority)`；:158-160 currentTarget 改从 queue 取。
- FeaturePointCalibrator.tsx:343-348 `{currentTarget.optional && <Badge tone="amber" size="xs">辅助·可跳过</Badge>}`；:365-369 `{currentTarget.caveat_zh && <span className="... text-amber-700 dark:text-amber-400">⚠ {caveat}</span>}`；:324-330 banner 补"墙角与天花板转角最可信"。
- PerspectiveCalibrator.tsx:366-370 伪特征点补齐分级字段（恒 structural），保证全量契约。

【4. wtype 来源独立取证（我自己 grep，非采信叙述）】
- apps/web/src/components/studio/editor/geometry/GeometrySidePanel.tsx:411-415 `<SelectRow label="wtype" options={['normal','full','high']} onChange={(v)=>props.onSetOp('wtype', v)} />`
- packages/floorplan_core/floorplan_core/axon.py:75 `re.search(r'data-wtype="(\w+)"', s)`；:923 写 `data-wtype="%s"`
- packages/floorplan_core/tests/svg2geometry.py:262 `wtype = gv("data-wtype","normal")`
- apps/web/src/lib/floorplan/geometry.ts:698 `wtype: 'normal'`（直插默认）

【5. 真实几何实算（只读 data/projects，未写）】
`PYTHONPATH=... python3 -c "derive_features(v1_geometry, rid)"`：
- r_guest2: n=14，optional=**0**，tiers={structural,opening}，id 序 == priority 序
- r_foyer: n=32，optional=**0**，tiers={structural,opening}，id 序 == priority 序
- 全 20 房间扫描：有 optional 的仅 r_garden(16/8)、r_vest(20/4)、r_balc(12/4)、r_liveext(16/8)、r_bed_g(16/6)、r_bath_g(18/6)、r_master(18/6)；**每一间 `id-order == priority-order` 均为 True**
- 窗 wtype 分布 `Counter({'full':8,'normal':3,'high':2})` —— derive 只对 full 出特征，故"按 wtype 置信度差异化降级"无可差异化对象，统一降级与之等价

【6. 静态门 / 设计系统 / 红线】
- `cd apps/web && npx tsc --noEmit` -> 退出码 0，无输出
- `npx next lint --file FeaturePointCalibrator.tsx --file PerspectiveCalibrator.tsx --file studioApi.ts` -> `✔ No ESLint warnings or errors`
- `python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py` -> `All checks passed!`
- `ruff format --check` 对这两文件报 "Would reformat" —— 我把 **dc9787f 的同名文件抽到 scratchpad 单独跑 ruff format --check，同样报 2 files would be reformatted**，证实为 b1/b2 既有基线偏差，**非本批新增**
- Badge tone="amber" 是设计系统合法 tone：ui/status.tsx:204 `BadgeTone` 含 'amber'，:208 `bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200`（成对 dark:）。新增文案 `text-amber-600/700 dark:text-amber-400` 亦成对
- 新增行无 `bg-*-50`：changed 文件里唯一命中是 PerspectiveCalibrator.tsx:448 `bg-brand-50`，`git log -L 448,448` 溯源到 **b8344f1(calib-cure-b1 #87)**，非本批
- `git diff --stat dc9787f...HEAD -- data/projects/` -> **空**；`-- data/ packages/floorplan_core/` -> **空**
- `git show --name-only 459c438` -> 5 文件，全部落在 progress.json.batch_scope.allowed_paths 内，无夹带

【7. 环境干扰记录（非产品问题，供编排者知悉）】
验收期间有并行 evaluator subagent 在同一工作树落测试探针：`apps/api/tests/test_zz_evaluator_f001_probe.py`(01:43 创建, +2 test) 与 `apps/web/e2e/tmp-b3f002-check.spec.ts`(01:45)，导致我第一次全量跑 437、第二次变 439。已用 `--ignore` 隔离并用干净 worktree 复算确认真实数为 437。另 scratchpad 下 `wt-base` 被同侪 evaluator 占用且其中 `apps/api/tests/test_calibration_quality.py` 被注入了 F004 的 RED 探针 —— 我未触碰该 worktree，另建 wt-f003* 三个干净 worktree 取数，用完已 `worktree remove`。

### 未验证项（BLOCKED-NEEDS-USER）

无阻塞项影响 F003 判定 —— F003 自身 acceptance 全部为 L1（派生层逻辑 + pytest + 静态门），已在本地全部实测完毕，不含需用户人工操作的条目。

[BLOCKED-NEEDS-USER] 以下与 F003 相关但归属 F006(L2) 的条目未验证，我不臆测其结果：
1. spec §4.2(c)「窗几何失配不再产生无对应物的必点项」—— 需真实浏览器目视确认「辅助·可跳过」徽章与 caveat 文案在标定页实际渲染、跳过按钮对 optional 点确实可用、用户不再被迫瞎点。我只能静态确认渲染分支与类型契约正确（FeaturePointCalibrator.tsx:343-348, :365-369），**无法替代目视**。
2. 该项若在 F006 沿用 acceptance 点名的 r_guest2 / r_foyer 会得到空验证（实算 optional=0，该二室无 wtype=='full' 窗）。**F006 须改用 r_master / r_garden / r_liveext / r_bed_g / r_bath_g / r_vest / r_balc 之一**，否则该 L2 项无法被真实行使。

---

## F004 — PARTIAL

### 描述

F004「对应关系 UX 加固」实装质量总体扎实，但**其自称"最直击 b2 L2 病灶"的旗舰交付物（天花板角↔地面孪生联动）在出厂默认轮候顺序下对天花板角永不触发**，即在它唯一针对的场景里是死代码。故判 PARTIAL。

**一、对 notes 声明的两处"前提翻转/主动缩减"的独立复核结论**

(1)「v_i↔yaw 未实证已过时」→ **成立**。我独立核到 b625012a（`feat(calib-cure-b1-F010)`, 2026-07-17）确实引入 `_VIEW_FORWARDS` 并带生产交叉验证（f4d v1→SW / 798 v3→NE），且经 b8344f1(PR#87) 已投产。spec §D4 的「b1 §D7 声明未实证」确系过时表述。因映射可用，acceptance 里那条**条件式**退路（"映射不可用则退到…"）不触发，未走退路判定正确。方位表自洽性我也校了：X=东+/Y=南+ 下 v0(-1,-1)=西北、v1=西南、v2=东南、v3=东北，与 main.py:1109-1112 既有注释及前后端两张表逐项一致。

(2)「照片侧目标区域高亮（粗相机先验）结构性不可行，主动缩减」→ **成立**，且我拿到了量化证据（不止接受其说辞）。我用标定前系统真正拥有的全部先验（direction 象限 + 生产门 CAMERA_Z_RANGE_MM(800,2200) + HFOV_RANGE_DEG(35,110) + 房内任意机位 + 保守收窄的 ±12° pitch）做蒙特卡洛，测同一个天花板角的投影像素散布：P5-P95 达画幅宽的 **18.5 倍**，即便四分位距仍有画幅宽 2.7 倍 / 高 1.8 倍，且只有 **5.8%** 的先验相容相机能把该点投进画幅内。任何据此画出的"目标区域框"都是凭空捏造，缩减判断成立。我另核实 `_camera_zone_phrase`(main.py:2415-2439) 确实只产出定性中文短语、从不产像素区域，且那是给已知合成相机的轴测用，与实拍标定前无关。

**二、实证发现的缺陷（判 PARTIAL 的唯一理由）**

孪生联动的实现本身是对的（planId 前缀映射覆盖全部三类异面点；异面点与地面孪生同 (x,y) 由 derive_features 构造保证，我在 calib_features.py:119-136 / 181-196 逐行核实；竖线渲染几何正确）。但它被 F003（前一个 commit 459c438）的轮候排序卡死：`byPriority` 同 priority 时按 id 的 localeCompare 兜底，而 `wall_corner` 与 `ceiling_corner` **同为 priority 0**，`ceilcorner:` 的 'ce' < `corner:` 的 'co' —— 于是全部天花板角排在全部地面角**之前**。我模拟出厂队列确认：位次 1-4 全是天花板角，此时地面孪生一个都没放，`twinPlaced` 恒为 null，提示文案与琥珀参考线均不渲染。而 `MIN_POINTS = 4`，典型用户放满 4 点就结束，全程停留在天花板角区段。点选顺序是**强制**的（onPickPoint 恒把点位赋给 currentTarget，用户只能跳过不能改序），所以这不是"用户换个顺序就好了"。该提示只在门框顶(#10)/窗框顶(#12)触发，而窗特征已被 F003 降级为 priority 2 + optional + 可跳过。

结论：commit message 与 features.json notes 里"最直击 b2 L2 病灶（天花板角被点到窗户半高）"这一自我定性，在出厂配置下不成立。修复应属 F003/F004 交界（如 byPriority 增加按 world z 升序的次级键让地面孪生先行），需按铁律 10 挂 feature 号，我不实施。

**三、通过项**：两处后端改动确为纯文案（`_direction_mismatch_reason` 阈值/判定逻辑逐字未动，main.py:1125-1141），可行动文案端到端抵达用户可见的 400 响应；朝向锚定 banner 指向的「户型基线·实拍照」视角选择器确实存在（BaselinePhotosCard.tsx:408-410），引导非死路；设计系统复用与 dark: 成对合规。

**四、次要非阻断观察**：`VIEW_FACING[photo.direction ?? '']` 对 legacy 方位值（后端 main.py:1127 明确承认 N/S/E/W legacy 存在）取不到值，会落到"还没标注拍摄视角"的 warn banner —— 陈述失实（其实标了，只是 legacy），但引导动作（去重选 v0..v3）恰好是正确补救。仓库 seed 数据中未见任何 direction 值，生产是否存在 legacy 值未验。

### 复现步骤

复现「孪生联动对天花板角不可达」（无需浏览器，纯逻辑，可在 CI 钉死）：

1. 取任一有 ≥4 个存活墙角的房间（如 r_guest2），调 GET /api/projects/D/baselines/{v}/photos/{pid}/calibration-features，
   得到的 features 中 wall_corner 与 ceiling_corner 的 priority 均为 0（calib_features.py:67-74）。
2. 前端按 byPriority 排序（FeaturePointCalibrator.tsx:66-67）：同 priority 时 'ceilcorner:...'.localeCompare('corner:...') === -1
   （'ce' < 'co'），故全部 ceilcorner:* 排在全部 corner:* 之前。
3. 打开特征点标定，观察轮候队列前 4 位 —— 全为「…顶角(天花板)」。
4. 依次点前 4 点：每一步 twinPlaced 均为 null（其 planId 孪生 'corner:{mid}:{cname}' 尚未进入 placed），
   故「↑ 它就在你已放的第 N 点…正上方」文案与琥珀竖线**始终不出现**。
5. MIN_POINTS=4 已满足，用户此时即可解算并退出，全程未见过该提示一次。
6. 对照组：一路点/跳到第 10 位 doorhead:d1:a 时提示正常出现 —— 证明实现本身无 bug，纯粹是排序顺序把它锁在了触发条件之外。

建议修复方向（属 F003/F004 交界，须按铁律 10 挂 feature 号，我不实施）：
byPriority 增加次级键按 world[2] 升序（地面孪生先于其异面孪生），或在 twinPlaced 为 null 且孪生排在队列更后时，改提示"请先放它正下方的地面墙角"。修复后应补一条钉死"每个异面点在队列中必晚于其地面孪生"的回归测试。

### 证据

【测试】
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q --ignore=apps/api/tests/test_zz_evaluator_f001_probe.py
  -> 437 passed in 20.93s (0 skip)
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q
  -> 154 passed in 0.69s (0 skip)
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests/test_render_snapshot.py -q -rs
  -> 5 passed；且 /Users/yixingzhou/project/grandtianfu/.phase0-baseline 存在 => golden 逐字节比对**实际执行**未 skip
注：apps/api/tests/test_zz_evaluator_f001_probe.py 为**并发运行的另一位 F001 evaluator** 会话中新写入的未追踪探针（我首次跑全量时尚不存在，collect 由 437->439）。非我产物，我未删改。

【新测非同义反复 — RED-before 实证】
$ git worktree add <scratch>/wt-base dc9787f  (批次基线 = 首个 commit 56ac9be 之前的 HEAD)
$ cp apps/api/tests/test_calibration_quality.py <scratch>/wt-base/... && pytest -k actionable
  -> FAILED test_direction_mismatch_reason_is_actionable
     AssertionError: assert ('镜像' in '解算相机朝向与照片标注的拍摄视角 (v0) 近乎相反 — 锚点/特征点可能整体标反, 或照片的视角标注有误')
  在 HEAD 上同测 PASS => 真 RED->GREEN。

【可行动文案端到端抵达 HTTP 400（evaluator 探针，跑在一次性 worktree，未入用户工作树）】
$ git worktree add <scratch>/wt-head HEAD; 追加断言后 pytest -k evaluator_probe -s
  -> 1 passed，[REASONS] 实际输出含：
     "...解算相机朝向与照片标注的拍摄视角 (v0, 镜头大致朝西北) 近乎相反 —— 特征点很可能整体左右点反了(镜像): 画面左侧的角被点成了右侧的角。请点「重来」清空, 先找一个无歧义的特征(如门框)认准画面的左右..."
  两个 worktree 已 git worktree remove --force 清理。

【缩减(2) 独立量化复核 — 脚本 <scratch>/coarse_prior_spread.py，用生产门常量】
$ PYTHONPATH=... python3 coarse_prior_spread.py
  门参数: CAMERA_Z_RANGE_MM=(800.0, 2200.0) HFOV_RANGE_DEG=(35.0, 110.0)
  样本 20000, 目标在镜头前方 10623 例, 真正落在画幅内 1169 例 = 5.8%
  P5-P95 像素包络: u -73683..947 (画幅宽 4032 的 18.5 倍) | v -37463..962 (画幅高 3024 的 12.7 倍)
  P25-P75 像素包络: u -11948..-867 (2.7 倍宽) | v -5487..35 (1.8 倍高)
  => 粗相机先验下像素级高亮框 = 伪精度，缩减成立。
诚实边界：该蒙特卡洛在可行集上取均匀先验（真实拍摄者会聚集），但即便 IQR 仍超 1.8 个画幅高，结论不因先验形状改变。

【前提翻转(1) 复核】
$ git show --stat b625012a -> "feat(calib-cure-b1-F010): 专家模式动态文案 + direction 交叉校验"，
  commit body 原文："v0..v3↔朝向映射实证 (轴测'近角看向里角'+_VIEW_TURNS 旋转; 生产 f4d(v1→SW)/798(v3→NE) 构图交叉验证)"
$ git log --oneline -S"_VIEW_FORWARDS" -- apps/api/main.py -> b8344f1(PR#87 已投产) 引入, 52dd41c 本批扩表
  main.py:1108-1113 注释与 :1115 _VIEW_FACING_ZH 一一对应；FeaturePointCalibrator.tsx:69-79 前端表与之逐项相同。

【缺陷实证 — 孪生联动对天花板角不可达】
apps/api/aigc/calib_features.py:67-74  _KIND_TIER: wall_corner=(structural,0,...) 与 ceiling_corner=(structural,0,...) **同 priority 0**
apps/web/.../FeaturePointCalibrator.tsx:66-67  byPriority = a.priority-b.priority || a.id.localeCompare(b.id)
apps/web/.../FeaturePointCalibrator.tsx:180-190 twinPlaced: 仅当 isElevated(currentTarget) 且其 planId 孪生**已在 placed 中**才非 null
apps/web/.../FeaturePointCalibrator.tsx:244-260 onPickPoint 恒 setPlaced(featureId: currentTarget.id) => 顺序强制，用户不可改序（只能跳过）
apps/web/.../FeaturePointCalibrator.tsx:88 MIN_POINTS = 4
$ node <模拟出厂队列，ids 取自 derive_features 真实格式 + _CORNER_NAMES=("西北","东北","东南","西南")>
   1 ceilcorner:r_guest2:东北  [异面] 孪生提示✗ (地面孪生尚未放)
   2 ceilcorner:r_guest2:东南  [异面] 孪生提示✗
   3 ceilcorner:r_guest2:西北  [异面] 孪生提示✗
   4 ceilcorner:r_guest2:西南  [异面] 孪生提示✗
   5-8 corner:r_guest2:*       [地面]
  10 doorhead:d1:a             [异面] 孪生提示✅ -> door:d1:a
  12 winhead:w1:a              [异面] 孪生提示✅ -> window:w1:a
  => 位次 1-4（即 MIN_POINTS 全部预算）无一触发；仅门框顶/窗框顶可触发，而窗特征已被 F003 降级为 optional 可跳过。

【红线核查 全部通过】
$ git diff --stat dc9787f...HEAD -- data/                      -> 空
$ git diff --stat dc9787f...HEAD -- packages/floorplan_core/    -> 空
$ git diff --stat dc9787f...HEAD -- apps/api/aigc/perspective.py -> 空（solve_pnp/_solve_pnp_general/assess 数学零改动；F004 的 mismatch 仅在 main.py:1169-1171 于 assess 结果之上叠加 reasons，未改内核）
$ git show --name-only --format="" 52dd41c -> apps/api/main.py / apps/api/tests/test_calibration_quality.py / apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx（3 文件全在 batch_scope.allowed_paths 内，无夹带）
铁律 10: commit tag "feat(calib-cure-b3-F004)" 对应 features.json 实有条目 F004 ✅

【lint / 类型】
$ cd apps/web && npx tsc --noEmit -> exit 0
$ npx next lint --file src/components/studio/real-render/FeaturePointCalibrator.tsx -> "✔ No ESLint warnings or errors"
$ python3 -m ruff check apps/api/main.py apps/api/tests/test_calibration_quality.py -> 仅 1 条 I001 (main.py:9 import block)
$ git show dc9787f:apps/api/main.py > <scratch>/base/main.py && ruff check 之 -> 同样 1 条 I001 => **既有基线，非本批新增** ✅
设计系统: NoticeBanner/Badge 自 components/studio/ui/status（tone 联合类型 'info'|'warn'|'error'，两处用法合法）；新增色均成对 dark:（text-amber-700 dark:text-amber-400）；
$ git show 52dd41c | grep '^+' | grep -E 'bg-(gray|blue|amber|red|green|brand|navy)-50\b' -> 无命中 ✅

【我未修改任何产品代码】所有写入均在 scratchpad 与两个一次性 worktree（已删）。

### 未验证项（BLOCKED-NEEDS-USER）

以下项必须真实浏览器人工目视，本轮未获用户当面配合，一律 BLOCKED-NEEDS-USER，我不臆测其结果（既不据此判 PASS 也不据此判 FAIL）：

1. [L2] 琥珀色孪生参考线在**真实照片、真实宽高比**下的落位正确性。代码用 pctX/pctY 相对自然像素取百分比（FeaturePointCalibrator.tsx:310-311, 506-508），与既有已放点标记同一套换算，静态读码看不出新增偏差；但 img 为 `block w-full` + 覆盖层 `absolute inset-0`，实际渲染盒是否与自然尺寸严格同比需目视。注：即便此项验过，也不改变上面「天花板角场景下该线根本不渲染」的判定。

2. [L2] 朝向锚定 banner（"镜头大致朝X…确认左右"）对真实用户是否真的降低 r_guest2 那类整组镜像错误 —— 属行为效果，代码层不可证。

3. [L2] 生产照片记录中是否真实存在 legacy direction 值（N/S/E/W）。后端 main.py:1127 明确承认该 legacy 分支存在，若命中则前端会错误显示"还没标注拍摄视角"。仓库 seed data/projects 中 grep 不到任何 direction 字段，故生产侧未知。

4. [L2] F004 acceptance 中"朝向**锁定**"的强度：实装为非阻断提示 banner + 失败后文案，并无任何"先点 1 个无歧义特征"的交互式锁。是否满足用户对"锁定"的预期，需用户裁决（spec §D4 标注"按需/可分期"、§3 标注"按 D4 调查定深度"，我倾向认为文本级锚定在 spec 授权范围内，故未据此扣分）。

### 对抗复核

- refuted: **False** → final_result: **PARTIAL**

独立复现成立，且比原报告更强。(1) 排序断言经真实后端数据验证：用 derive_features 对 data/projects/D/geometry.json 的 5 个房间派生真实特征，再用真实 Node localeCompare 跑 byPriority/twinPlaced/planId 的忠实移植——wall_corner 与 ceiling_corner 同为 priority 0，全部 ceilcorner:* 严格排在全部 corner:* 之前，故天花板角的地面孪生恒在队列更后，twinPlaced 对天花板角在任意位次均为 null。孪生提示首次触发位次：r_guest2=12、r_study=12、r_master=11、r_foyer/r_live=25，MIN_POINTS=4 预算内无一触发。(2) 排除环境误报：localeCompare 在 default/en/zh-CN/zh-Hans-CN/de 及 ignorePunctuation/sensitivity:base/numeric 下一律返回 -1（区分字符 e<o 为基本拉丁字母，各 locale 主权重一致），非 Node 版本或 locale 漂移。(3) 排除既有基线归咎：git show dc9787f 的 FeaturePointCalibrator.tsx 无 sort/queue/twin，排序(F003 459c438)与孪生联动(F004 52dd41c)均为本批新增。(4) 排除测试隔离问题：437+154 全绿 0 skip（前评者提到的 test_zz_evaluator_f001_probe.py 已不存在，collect 回到 437），tsc --noEmit exit 0。(5) 红线复核通过：data/、packages/floorplan_core/、apps/api/aigc/perspective.py 净 diff 为空；_direction_mismatch_reason 阈值 cosang < -0.7071 逐字未动，仅 docstring 与文案变更，故"纯文案"PASS 项成立；BaselinePhotosCard.tsx 确有 VIEWS=['v0'..'v3'] 选择器，banner 引导非死路。【一处对原报告的修正，但不改变判定】存在原报告遗漏的逃生路径：找回已跳过 = setSkippedIds([])，用户若先跳过 4 个天花板角、放完 4 个地面角、再点找回，孪生提示可正常触发（模拟实证 ✅->#1..#4），故"结构性永不可达"表述过强。但该路径需 8 次放置 + 一个仅在跳过后才出现的按钮，且与 F003 自身 banner「墙角与天花板转角最可信,优先点它们」的在屏指引直接相反，UI 无任何提示，MIN_POINTS=4 内仍不可达。acceptance 字面命名的正是「天花板角与地面孪生联动提示」，而天花板角恰是引导流程中唯一永不触发的那一类。判定维持 PARTIAL。修复方向属 F003/F004 交界（byPriority 增 world[2] 升序次级键 + 钉死"异面点必晚于其地面孪生"的回归测试），须按铁律 10 挂 feature 号，我未实施，未修改任何产品代码。

---

## F005 — PARTIAL

### 描述

F005（3D/简模引导路线评估 spike）核心交付达标且质量高，但 acceptance 明文点名的一项内容缺失，且付费臂全部量化结论在仓库内无任何可核证据。

【达标项 — 已独立核实】
1. 研究码非产品、不 import main.py：`scripts/spike/` 全目录 grep，`main.py` 仅出现在注释里；`_product.py` 只经 importlib 读入 `aigc.*` 子模块。本批 0 行 spike 代码变更（即字面「复用 b1 工具」）。F005 commit f0f8e33 未触碰任何 `apps/` 或 `packages/` 文件。
2. 两臂公平性可核：`run_ab.py` 的 L0 prompt 自称逐字复制自产品 `_geometry_lock_prompt`，我做了字面量级 diff — 48 vs 41 条中差异**全部是注释与类型标注**，指令文本零漂移。（唯一瑕疵：注释引用的行号 `main.py:2263-2353` 已过期，现址 2638。）
3. **NO-GO 的承重机制被我独立复现（零成本、零 PIPL）**：我用仓库内 committed 标定 + repo seed geometry + `photo=blank` 跑 `run_ab.py --dry`，产出的 L0/L1 引导图在几何与构图上**完全一致地崩坏**，仅表面着色不同。这正面支持报告 §2 的论点——引导表示法的丰富度救不了错误的投影，失败由上游（相机/世界几何）决定。此判断我不依赖任何生产数据即可确认。
4. PIPL 红线：全批次 git 历史无任何 jpg/png/heic/二进制新增。
5. 报告位置/命名/自述性质（第 3 行明示「研究产物，非产品 signoff」）、go/no-go、b4 三条建议——齐备，§7 诚实边界写得罕见坦率。
6. 铁律 10：F001-F005 commit tag 全部映射 features.json 实际条目。

【未达标项 — 判 PARTIAL 的依据】
A. acceptance 原文要求「成本依赖（**承接 b1 spike 4 条 GO 条件: VLM 形体评分 / 样本 / curtain 简模**）」。报告实际只承接 2 条（跨后端/fal 悬空、n 极小），对 **VLM 形体评分**与 **curtain 简模**的关键词命中数均为 **0**。这对 curtain 尚属遗漏，对 VLM 则有实质后果：报告 §4 自己发现了度量失效，并向 b4 提了一个**新**检测器（足迹 mask 重叠度），却未与 b1 早已议定的「须配 VLM/人工形体评分器」条件做接续或取代说明——b4 有重复推导或丢弃既有结论的风险。（NO-GO 使 b1 GO 条件部分失效这一辩解可能成立，但报告未作此表述。）
B. 付费臂**零可核证据**。§3/§4 的全部量化结论（score 1.0 / 0.85 / 0.917、19077 tokens、4/4、139-179s）在仓库内无任何产物支撑。关键在于：b1 已确立先例——`docs/test-reports/spike-l1-guide/rows.json` 与 `summary.md` 是**纯文本**（我核过内容：只有 legend/件数/文件名/分数，无照片像素），完全可在 PIPL 红线内保留。b3 却连这类文本记录也一并删除。后果是本批最有产品后果的新发现（§4「auto_check 判反」，已被写进 b4 待办）**任何独立方都无法复核**。
C. §3「落位是否跟随引导」为执行者本人目视自判、无留存产物。§7 已诚实声明，单独看可接受；与 B 叠加后，付费臂整体不可审计。

【关于 notes 中的「前提翻转」— 我的独立表态：**部分成立，但 handoff 措辞过头**】
features.json/generator_handoff 写「L2 前提**已被 F005 推翻**，勿沿用」；报告 §5 自己写的是「该前提仍**未验证**，Evaluator 必须实测」。**报告的措辞正确，handoff 的措辞不正确。** 可核实的一半我已在代码中确认：`apps/api/aigc/perspective.py:587` `CAMERA_Z_RANGE_MM = (800.0, 2200.0)`，判定在 `:663`——故若 r_foyer 存档相机高确为 399mm，它确实过不了高度门（该行注释本身即记「生产病例 f4d 解出 399mm(膝下) 即此翻车」）。但不可核实的一半是数值本身（需 deploysvr 只读，未授权）。更重要的是逻辑：该存档是**门禁上线前的 legacy 2 锚点专家模式**标定，它失败**不能推出**用 b1/b2 新特征点模式重标也会失败。故正确结论是「前提未验证」，不是「前提被推翻」。F006 必须实测，且**不得因此预判 FAIL**。

### 复现步骤

复现我的独立零成本验证（无需生产访问、无 PIPL、无费用）：

1. 准备沙箱场景（只读消费仓库内数据，不写 data/）：
   mkdir -p /tmp/spike && cd /tmp/spike
   cp <repo>/docs/test-reports/spike-l1-guide/cal_study_798.json .
   cp <repo>/data/projects/D/geometry.json .
   cp <repo>/data/projects/D/furniture.json .
   写 scenes.json：
   [{"id":"g2","photo":"blank","calibration":"cal_study_798.json",
     "geometry":"geometry.json","furniture":"furniture.json",
     "rooms":["r_guest2"],"style":"modern light-luxury"}]

2. 干跑（零成本，不调 provider）：
   cd <repo> && PYTHONPATH=packages/floorplan_core:apps/api \
     python3 scripts/spike/run_ab.py --scenes /tmp/spike/scenes.json \
     --outdir /tmp/spike/out --dry --force

3. 目视对比 /tmp/spike/out/g2_L0_guide.png 与 g2_L1_guide.png：
   两臂几何/构图逐件重合，仅着色不同 → 复现报告 §2「失败由相机决定，不由引导表示法决定」。
   再对照 <repo>/docs/test-reports/spike-l1-guide/study_798_blank_L1_guide.png（同标定 + 生产 v7 geometry）：完全成形且落地 → 隔离出「崩坏来自上游不匹配」。

4. 覆盖度核查（A 项缺口）：
   grep -c "curtain\|VLM\|形体评分" docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md   # 均为 0
   对照 docs/test-reports/spike-l1-guide-ab-20260717.md:152-166 的 4 条 GO 条件。

5. 回归与红线：
   PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q      # 439 passed
   PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q # 154 passed
   git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/                      # 空

### 证据

【实际运行的命令与输出要点】

1) spike 隔离性（acceptance「不 import main.py」）
$ grep -rn "import main|from main|load_main" scripts/spike/
→ 仅 4 处，全部在注释/docstring 中（_product.py:4,9；run_ab.py:60；calib_solve/solver.py:12）。无一处为真实 import。
$ grep -n "def load_|import_module" scripts/spike/_product.py
→ :65 `importlib.import_module(f"aigc.{mod_name}")`，只读入 aigc 包。

2) 我自己跑的零成本干跑（独立复现 NO-GO 承重机制）
$ PYTHONPATH=packages/floorplan_core:apps/api python3 scripts/spike/run_ab.py \
    --scenes <scratchpad>/spike/scenes.json --outdir <scratchpad>/spike/out --dry --force
→ [dry] g2_suspect41px L0: 5 件 / L1: 5 件；live_bad127px L0: 6 件 / L1: 6 件；summary.md 已写
输入全部来自仓库内（docs/test-reports/spike-l1-guide/cal_study_798.json、data/projects/D/geometry.json、furniture.json，photo=blank），零成本、零 PIPL、未写 data/。
目视产物 g2_suspect41px_L0_guide.png vs _L1_guide.png：**两图家具位置/尺寸/出画方式逐件重合，仅半透明彩盒 vs 不透明简模的着色不同**。对照 b1 留存的 docs/test-reports/spike-l1-guide/study_798_blank_L1_guide.png（同一标定 + 生产 v7 geometry）则是完全成形的书桌/椅/书架且全部落地——证明崩坏来自上游世界/相机不匹配，而非引导表示法。这正是报告 §2「失败由相机决定，不由引导表示法决定」。

3) 两臂公平性（L0 prompt 与产品是否同源）
自写脚本对 apps/api/main.py `_geometry_lock_prompt`（现址 :2638，非注释所称 :2263）与 run_ab.py 同名函数做字面量 diff：
→ product-only 12 条 / spike-only 4 条，**逐条检视全部为注释文本与类型标注差异**，无一条指令文本差异。
$ git diff dc9787f...HEAD -- apps/api/main.py
→ 本批只改 _VIEW_FACING_ZH / _direction_mismatch_reason（F004），未碰 prompt，故拷贝未因本批而失效。

4) acceptance「承接 b1 4 条 GO 条件」覆盖度
$ for k in curtain 窗帘 VLM 形体评分 成本 依赖 样本 fal; do grep -c "$k" docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md; done
→ curtain=0, 窗帘=0, VLM=0, 形体评分=0, 成本=2, 依赖=2, 样本=1, fal=2
b1 四条件原文见 docs/test-reports/spike-l1-guide-ab-20260717.md:152-166（1 后端依赖 / 2 须配形体评分器 / 3 样本仍小 / 4 curtain 简模须特殊处理）。命中 1、3；缺 2、4。

5) 可复现性缺口（B 项）
$ head -c 900 docs/test-reports/spike-l1-guide/rows.json
→ b1 留存的运行记录为纯文本（scene/arm/dry/drawn/guide_file/legend/min_in_frame），**不含任何照片像素**，且已入 git。b3 对应产物（rows.json / summary.md / prompt txt）在仓库中不存在：
$ git log --name-only --pretty=format: dc9787f..HEAD | grep -iE "\.(jpg|jpeg|png|heic)$" → NONE
$ git show --name-only f0f8e33 → 仅 docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md + features.json + progress.json
故 §3/§4 的 score 1.0 / 0.85 / 0.917、19077 tokens 无任何仓内支撑。

6) 「前提翻转」的可核一半
apps/api/aigc/perspective.py:587 `CAMERA_Z_RANGE_MM = (800.0, 2200.0)  # 人手持高度; 生产病例 f4d 解出 399mm(膝下) 即此翻车`
apps/api/aigc/perspective.py:663-668 高度门判定 → 399mm 确在门外。
但 399mm 这一测量值本身出自报告 §5（生产只读盘点），本地不可核。

7) 红线与回归
$ git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ → 空（无输出）
$ git diff --name-only dc9787f...HEAD → 12 个文件，无 data/、无 floorplan_core/、无二进制
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q → **439 passed in 20.45s**（0 skip；commit message 称 437，实测多 2，两者皆绿，非阻断）
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q → **154 passed in 0.58s**（0 skip，与声明一致）
$ git log ... | grep -oE "calib-cure-b3-F[0-9]+" → F001-F005，全部映射 features.json（铁律 10 通过）
本次验收未修改任何产品代码；我的产物只落在 scratchpad。

### 未验证项（BLOCKED-NEEDS-USER）

1. [BLOCKED-NEEDS-USER] 报告 §5 生产标定盘点（7 份 legacy 2 锚点、r_guest2 reproj 2353.4px、r_foyer camera_z 399mm、r_garden hfov 3.5°）——需 deploysvr 只读访问，属外部生产读取，未获授权。我只能确认其**条件成立**（门为 [800,2200]mm，399mm 必然不过），无法确认**测量值本身**。不臆测其真伪。

2. [BLOCKED-NEEDS-USER] 4 张付费出图（relay，19077 tokens）的**用户预算授权**：报告第 4 行与 commit message 均声称「用户 2026-07-20 授权」，我无法独立验证。请用户确认该授权确实发生（若未发生则属流程违规，与 F005 技术结论无关但需另行处理）。

3. [BLOCKED-NEEDS-USER] 报告 §3/§4 付费臂的全部观察（落位是否跟随引导、auto_check 分数判反）——原始产物已随沙箱销毁，无法复核。若用户认为 §4「auto_check 判反」这一将进入 b4 的产品缺口需要可核依据，建议按 b1 先例补跑并保留**纯文本** rows.json/summary.md（不含像素，不违反 PIPL）。

4. [不阻断，但须传达给 F006] handoff 与报告对 r_foyer 前提的措辞不一致（「已被推翻」vs「仍未验证」）。以报告措辞为准：**未验证**。F006 必须真实浏览器实测重标，既不得因 calib=True 判其成功，也不得因存档 legacy 标定不过门而预判失败。

### 对抗复核

- refuted: **False** → final_result: **PARTIAL**

复现确认，非环境误报。【A 项成立且为唯一承重依据】acceptance 明文要求 `成本依赖(承接 b1 spike 4 条 GO 条件: VLM 形体评分/样本/curtain 简模)`。我独立复跑 grep：curtain=0、窗帘=0、VLM=0、形体评分=0、评分器=0。对照 b1 四条件原文(docs/test-reports/spike-l1-guide-ab-20260717.md:152-166)，报告实际承接 2/4——条件1(后端依赖)见报告 line 33/119、条件3(样本)见 line 120；条件2(VLM/人工形体评分器)与条件4(curtain 简模)完全缺失，即 acceptance 明文点名的 3 项只落 1 项。acceptance 于 2026-07-19 lock、次日执行，非陈旧 checklist。最强辩解(NO-GO 使 GO 条件失效)对条件 2 不成立：报告 §4 自证该度量缺口仍是活的，§6.2 却向 b4 提了一个**新**检测器(足迹 mask 重叠度)且与 b1 已议定的 VLM/人工评分器零接续，重复推导/丢弃既有结论的风险真实。【B/C 事实成立但超出 acceptance 口径】scripts/spike/run_ab.py:492-494 确会自动写 summary.md + rows.json，故该纯文本记录由构造即存在而被一并删除；b1 的 rows.json / ab-rows-real.json 我逐条读过，确为纯文本(scene/arm/score/tokens/elapsed/fail_reasons，无任何照片像素)且已入 git，先例成立。但 F005 acceptance 只要求报告含 go/no-go + b4 建议 + 成本依赖，并明写「研究产物非产品 signoff」，未要求留存运行产物；C 项 §7 已诚实声明且 §4 已论证现有量化指标不可用于此。故 B/C 应记为 non-blocking 建议，不单独构成 PARTIAL。【核心交付独立佐证(支持实质达标)】我用仓库内 committed 标定 + repo seed geometry + photo=blank 自行零成本干跑并目视两图：L0/L1 家具盒位置/尺寸/出画方式逐件重合，仅着色不同(半透明 vs 不透明)，两臂同等崩坏、无一件落地——报告 §2「失败由相机决定不由引导表示法决定」成立。spike 隔离性成立：scripts/spike/ 全目录 4 处 main.py 命中全在注释/docstring，_product.py:65 只 importlib 读 aigc.*。【已知误报筛查全部排除】(1) main.py I001 在基线 dc9787f 同样存在(我对 git show dc9787f:apps/api/main.py 跑了 ruff)，未被误归本批；(2) 红线净空：git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ 空，apps/api/aigc/perspective.py 零改动(b2 解算内核完整)，批次无二进制/图片新增；(3) 前提翻转可核一半确认：perspective.py:587 CAMERA_Z_RANGE_MM=(800.0,2200.0)、判定在 :663，399mm 确在门外——原发现对 handoff 措辞的订正(应为「未验证」而非「已推翻」)正确，F006 不得预判 FAIL。【原发现的一处失准(不影响判定)】其称 439 passed；我实测 437 passed / 437 collected，与 commit message 完全一致，工作树干净(仅 1 个 20260717 既有未跟踪文档)、stash 为空 —— 故「commit message 称 437，实测多 2」是其自身环境漂移，非 commit message 有误；两者皆绿 0 skip，非阻断。【结论】PARTIAL 维持，但仅由 A 项承重。补救成本极低且无需预算：在 §6/§7 补一段处置 b1 条件 2 与 4(声明 curtain 简模因 NO-GO 失效；§6.2 足迹 mask 检测器对 b1 VLM/人工形体评分器取代或互补)。
