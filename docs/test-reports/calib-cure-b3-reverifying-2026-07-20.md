# calib-cure-b3 复验报告（reverifying-1，fix_round 1 之后）

> 5 个隔离 evaluator subagent（fresh context）+ 1 个对抗复核。主上下文只做机械汇总，未改写任何判定（铁律 12）。
> 日期：2026-07-20。工作流 wf_d8070c6b-5c3。复验口径：必须亲自复跑上一轮复现步骤 + 核查修复是否引入新问题（new_issues）+ 专项核查是否放宽硬门。

## 判定汇总

| feature | 上一轮 | 本轮 | 对抗复核 |
|---|---|---|---|
| F001 | PARTIAL | **PASS** | （PASS 未进复核） |
| F002 | PARTIAL | **PARTIAL** | refuted=False → PARTIAL |
| F004 | PARTIAL | **PASS** | （PASS 未进复核） |
| F005 | PARTIAL | **PASS** | （PASS 未进复核） |
| F003 | PASS | **PASS** | （PASS 未进复核） |

---

## F001 — PASS

### 描述

F001「退化早拦 + 正对墙/共面 → 角落重拍诊断」复验 = PASS。

【原缺陷已消失（亲自复跑上一轮复现步骤确认）】上一轮 PARTIAL 的唯一依据是「非共面良态点集不误触」被证伪（10/115 = 8.7% 真良态选点被解算前一句『请重拍这张照片』赶去重拍）。逐字复跑上一轮报告第 44-70 行那段脚本，同一 seed=23、同一 115 组分母，结果 **10 组 → 0 组（8.7% → 0.0%）**。我另做了上一轮没做的一步：误拦有可能只是从解算前挪到了 assess 层，于是把同样 115 组跑到新的 main._facing_wall_reason 上——触发 1 组，且该组 assess 本已 ok=False（camera_z=-1215.7mm 在地板以下 + reproj 187.3px，两条独立硬门各自判死），即「触发且 assess.ok=True」的有害误触 **0/115**。缺陷是真的没了，不是挪了位置。

【修复本身没有引入回归（独立核查）】修复反向打开了一个口子：解算前的共面拦截被移除，正对墙拍若解出「在门内但错」的相机会静默通过保存门。我实测确认这一类确实存在（26.3%，见 new_issues），但**关键在归属**：把同一 payload 放到批次基线 dc9787f 的 worktree 上跑，结果逐位相同（ok=True / z=1400 / hfov 58.8 / reproj 0.0 / 位置误差 1799mm）。即该口子是 b2 收口时就存在的既有行为，本次修复只是回到基线，并非修复引入。相对基线本批净变化是**更好**：这类照片解出极端相机时，除了原有的技术性 reasons，现在额外递一条拍摄级「角落重拍」引导。

【acceptance 全条重判】(1) 合取判据（s3/s1 共面 结合 相机高度/hfov 极端）已按 acceptance 原文实装，几何判据拆为纯查询 is_coplanar_across_heights + 文案常量，合取挂 assess 层（acceptance 明文许可）——上一轮指认的「未申报缩减」已消除。(2)「门不放宽」实测成立：perspective.py 相对基线 **零 diff**（CAMERA_Z_RANGE_MM / HFOV_RANGE_DEG / reproj 阈值 / assess ok 判定一字未动），_assess_calibration 新增分支只 append reasons、不改 ok/level。(3)「共面点集（如 r_guest2 北墙4角）→ 触发角落重拍诊断」：单测有，且我用真实几何 + 正对该墙的相机跑端到端 HTTP，dry_run 200 与保存 400 双路径都拿到该文案。(4)「既有 degeneracy_reason/assess 测试零回归」：438 + 154 全绿 0 skip，golden 逐字节 2 passed（真跑非 skip）；近共线 0.12 / 全同高 XY 0.30 两条既有预检分支原样保留。(5) b2 解算内核未被改：AST 逐函数比对 solve_pnp/_solve_pnp_general/_refine/_pose_known_K/_project3/_rodrigues 全部 identical。(6) 红线：data/ 与 packages/floorplan_core/ 相对基线净 diff 为空；commit tag fix(calib-cure-b3-F001) 映射 features.json F001（铁律 10）。

判 PASS 而非 PARTIAL 的理由：原缺陷经复跑证实消失；acceptance 五条全部满足；唯一的覆盖面回退经基线对照实证为既有行为而非本次引入。5 条 non-blocking 见 new_issues，另有 3 项目视类必须用户配合，见 blocked_items。

### 复现步骤

1) 原缺陷已消失：在仓库根逐字执行上一轮报告 docs/test-reports/calib-cure-b3-verifying-2026-07-20.md 第 44-70 行的脚本 → 期望 “真良态选点 115 组, 被『重拍这张照片』误拦 0 组 = 0.0%”（修复前为 10 组 / 8.7%）。
2) 新层无误触：把该脚本末尾的 cf.degeneracy_reason 判定换成 main._facing_wall_reason(r, anchors) 并同时算 perspective.assess_calibration_quality(...)["ok"] → 期望「触发且 ok=True」计数为 0。
3) 真退化仍拿得到引导（端到端）：新建 apps/api/tests/test_zz_reverify_f001_probe.py，从 test_calib_features 导入 _CAL/_pnp_points、从 test_render_real_geometry 导入 _upload_photo，用 client_fal fixture，POST mode=points 载荷
   [{"world":[15150,1700,0],"px":[1611.8,219.4]},{"world":[18150,1700,0],"px":[436.2,219.4]},{"world":[15150,1700,2700],"px":[1611.8,1277.5]},{"world":[18150,1700,2700],"px":[436.2,1277.5]}], img_wh=[2048,1536], photo room_id="r_guest2"
   → dry_run=1 得 200 且 quality.reasons 含「请站到房间角落…再重拍这张照片」；不带 dry_run 得 400 且 body.error 含同一句。验完删除该文件。
4) 归属对照：git worktree add <tmp> dc9787f，在基线 worktree 上用同一套 (world, px) 跑 cf.degeneracy_reason + solve_pnp + assess_calibration_quality（r_live 墙四角那组）→ 基线同样 ok=True / 位置误差 1799mm，证明「静默通过」非本次引入。
5) 门未放宽：git diff dc9787f...HEAD -- apps/api/aigc/perspective.py 应为空；读 main.py:1197-1201 确认只 append reasons。
6) 回归：两套 pytest（438 / 154，0 skip）+ -k baseline_byte_for_byte（2 passed）。

### 证据

【1. 原缺陷复跑（上一轮报告 line 44-70 脚本逐字执行）】
$ PYTHONPATH=packages/floorplan_core:apps/api:apps/api/tests python3 - <<脚本原文>
→ 真良态选点 115 组, 被『重拍这张照片』误拦 0 组 = 0.0%
（上一轮同脚本同 seed 输出为 “115 组 / 误拦 10 组 = 8.7%”）

【2. 误拦是否只是挪到新层（我加做的一步）】同 115 组，改判 main._facing_wall_reason：
→ 触发且 assess.ok=True（有害误触）: 0 | 触发且 assess.ok=False（仅追加解释）: 1
  该 1 组 metrics = {'reproj_px': 187.3, 'reproj_max_px': 270.4, 'camera_z_mm': -1215.7, 'hfov_deg': 58.6}, kinds=['ceiling_corner','door_head','door_head','door_head'] —— 相机解到地板以下，本已双重判死。

【3. 真退化照端到端是否仍拿得到引导（临时探针 apps/api/tests/test_zz_reverify_f001_probe.py，跑完已删）】
输入：r_guest2 北墙 y=1700 四角（真实 geometry 世界坐标）+ 正对该墙 f=1450/pitch=0 相机投影的像素，photo room_id=r_guest2
[PROBE-A dry_run] status=200  quality.ok=False level=bad
  metrics={'reproj_px': 1739.7, 'reproj_max_px': 2170.9, 'camera_z_mm': 208.6, 'camera_room_dist_mm': 12667.1, 'hfov_deg': 87.2}
  reason[4] = 所选点几乎都在同一面墙上(共面), 且解出的相机不合理 — 正对一面墙拍的照片标不出来。请站到房间角落, 让画面同时带到两面相邻墙 + 地面墙角和天花板转角, 再重拍这张照片。
[PROBE-B save] status=400  error= 标定质量不合格，已拒绝保存：…；所选点几乎都在同一面墙上(共面), 且解出的相机不合理 — …再重拍这张照片。。请按预览提示修正输入后重试。
[PROBE-C 良态非共面 5 点] status=200 quality.ok=True reasons=[]
前端可达链路（代码层）：dry_run 的 quality.reasons 由 CalibrationPreview.tsx:112-114 列表渲染；保存 400 的 body.error 由 studioApi.ts:51-56 抛出 → FeaturePointCalibrator.tsx:546-548 NoticeBanner。

【4. r_guest2 realistic 扫描（俯角/焦距扫）】相机 (16650,5400,1400) 正对 y=1700 墙：
  pitch=0/1/2/4 → 解出 z≈124–209mm、hfov 87–105°、reproj 1400–4800px，assess 拦下，『角落重拍』引导触发 30/30（σ=0）
  pitch=8 → 解出 z=1400 / hfov 70.5 / reproj 0.00 / ok=True，引导不触发（该机位本来就能标成，旧的纯几何判据会把它误拦——反向印证修复方向）

【5. 归属核查：静默通过类是否本次引入】同一 payload（r_live y=4900 墙四角，正对、pitch=0）：
  HEAD  → degeneracy_reason=None；assess ok=True，z=1400 hfov=58.8 reproj=0.0，位置误差 1799mm
  基线 dc9787f（git worktree add … dc9787f 后同脚本）→ degeneracy_reason: None；assess ok=True z=1400 hfov=58.8 reproj=0.0 位置误差=1799mm
  → 逐位相同 = 既有行为，非本次修复引入。（另 grep 确认基线 calib_features.py 无 s[2]/s[0] 分支、基线 main.py 无 _facing_wall_reason）

【6. 门是否被放宽】
$ git diff dc9787f...HEAD -- apps/api/aigc/perspective.py → 无输出（零 diff：CAMERA_Z_RANGE_MM=(800,2200) / HFOV_RANGE_DEG=(35,110) / reproj 阈值 / assess ok 逻辑全未动）
$ AST 逐函数比对 dc9787f vs HEAD：
  perspective.py changed/removed: [] | added: []
  calib_features.py changed/removed: ['derive_features','degeneracy_reason'] | added: ['_with_tier','is_coplanar_across_heights']  → solve_pnp/_solve_pnp_general/_refine/_pose_known_K/_project3/_rodrigues 未变
main.py:1197-1201 新分支只做 q = {**q, "reasons": q["reasons"] + [facing]}，不触 ok/level（读码 + PROBE-C 实证 ok 仍为 True/reasons 仍为空）

【7. 测试与红线】
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q → 438 passed in 18.69s（0 skip；基线 433 / 上一轮 HEAD 437 / 本次 +1 = 9de31f5 新增的 2 条回归减去 1 条被替换的旧测）
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs → 154 passed in 0.52s（0 skip）
$ …-k baseline_byte_for_byte → 2 passed, 152 deselected（golden 逐字节真跑）
$ git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ → 空
$ python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py apps/api/tests/test_calibration_quality.py → All checks passed!
$ python3 -m ruff check apps/api/main.py → 1× I001 @ main.py:9；对 git show dc9787f:apps/api/main.py 同样 --isolated --select I → 同一条 I001 @ :9 = 既有基线，新增的 import math 处于 json/math/os 正确字母序，未新增违规
$ git status --short → 仅剩会话前既存的未追踪文档 docs/实拍效果图-几何锁定优化方案-20260717.md（探针已删，基线 worktree 已 remove，未修改任何产品代码）
$ git log --oneline 中修复 commit = 9de31f5 fix(calib-cure-b3-F001) → 映射 features.json F001（铁律 10 通过）

### 修复是否引入新问题（new_issues）

均为 non-blocking，不影响 F001 PASS 判定，建议进 backlog / b4：

1)【覆盖面残留，非本次引入，建议 b4 立项】正对墙拍若解出「在门内但错」的相机，全链路无任何拦截与诊断。我的建模扫描：多房间 × 两面墙 × 两机位 × 5 俯角 × 3 焦距 × 1px 点击噪声，共 152 组「正对单墙 + 点该墙 4 角」场景 → assess 拦下 101 组（其中 84 组带『角落重拍』引导），放行 51 组，其中相机位置误差 >500mm 的**静默坏标定 40 组 = 26.3%**（误差 min 511 / 中位 2339 / max 9256 mm，reproj 却接近 0）。这是平面目标的 f-深度共生歧义，reproj 门天然无力。已用基线 worktree 对照证实基线 dc9787f 行为完全相同（同 payload 同样 ok=True / 1799mm），故**不算本次修复引入的回归**，但它意味着 F001 的标题目标（正对墙拍必被诊断）只在「解出的相机同时越门」时成立。缓解物：b1 的 dry-run 线框叠照片预览会把 1.8m 的相机误差画出来，用户目视可发现——这条缓解本身属 L2，未验证。与 F005 报告的「存量坏标定需清理」同源，建议合并到 b4 一并处理（例如平面度 + 条件数联合的置信度提示，或对共面点集强制要求补一个跨墙点）。

2)【舍入边界不一致】main._facing_wall_reason 用未舍入的 hfov 判极端，而 perspective.assess_calibration_quality 用 round(hfov,1) 判门。实测：raw hfov=110.04 → assess metrics 显示 110.0 且 ok=True，而 _facing_wall_reason FIRES；raw 34.96 同理。后果是在 0.05° 宽的窄带里，一个 ok=True 的合格标定会在 reasons 里挂一句「解出的相机不合理…请重拍这张照片」，与 commit message 自称的「只在该失败之上追加」不符。危害小（不改 ok、不拦），但属真实不一致。修法：复用 assess 已算好的 metrics.hfov_deg，或同样 round。

3)【健壮性不对称】is_coplanar_across_heights 对畸形锚点无防护：main._facing_wall_reason(cam, [{"world":[1,2],"px":[1,1]}]*4) → RAISES IndexError；而 perspective.assess_calibration_quality 对同一载荷刻意 try/except 降级（返回 ok=False + “标定载荷缺有效锚点”）。今日不可达（保存路径两个校验器都强制 world 长度==3；生产存量 legacy 标定均为 2 锚点，len<4 提前 return False），但渲染门 main.py:2819 传的是**未经校验的存盘 anchors**，若出现 ≥4 个畸形锚点的存量载荷，会从设计意图的 409「标定载荷损坏」退化成 500。建议照 assess 的写法包一层 except → return None。

4)【文案拼接瑕疵】保存 400 的 error 出现连续两个句号：“…再重拍这张照片。。请按预览提示修正输入后重试。”（引导常量自带句号 + 拼接模板又加一个）。

5)【文案事实性（上一轮所指缺陷的衰减残留）】该文案断言「所选点几乎都在同一面墙上」，但触发它的点集可能是跨房间的天花板角 + 多扇门头构成的近平面（见 evidence 第 2 条那组 kinds=['ceiling_corner','door_head'×3]）。修复后此文案只在相机已判死时出现（不再单独把人赶去重拍），危害已大幅衰减，但措辞仍可能误导。建议措辞放宽为「所选点几乎落在同一个平面上」。

### 未验证项（BLOCKED-NEEDS-USER）

以下必须用户在真实浏览器人工操作/目视确认，本轮未获当面配合，一律未验证——不臆测结果，既不因此判 PASS 也不因此判 FAIL（均属 F006 [L2] 范围，本次 F001 判定不依赖它们）：

1. [L2] BLOCKED-NEEDS-USER —【本轮新增的观感变化，优先请用户裁定】引导的**呈现位置变了**。修复前它是保存路径 400 的唯一 error 文案（独占 NoticeBanner，极显眼）；修复后它变成 quality.reasons 列表里的**第 4 条**（前 3 条是 reproj/相机高度/离房的技术性文案，见 PROBE-A 输出顺序），保存 400 时被拼进一长串分号串。用户是否还读得到、读得懂这条唯一可行动的拍摄级建议，需真实浏览器目视裁定。若不显眼，建议把该 reason 提到列表首位或单独成一块（纯前端展示，不动阈值）。

2. [L2] BLOCKED-NEEDS-USER — 用真实病例照 r_guest2（uploads/D/empty/472015c4…jpg）在真实浏览器走完整点选流程，确认「角落重拍」文案目视可见且用户读得懂。我只验证到 API 层返回正确 + 前端渲染链路代码完整（CalibrationPreview.tsx:112-114 渲染 reasons；studioApi.ts:51-56 → FeaturePointCalibrator.tsx:546-548 渲染 body.error），**未做任何像素/视觉确认**。

3. [L2] BLOCKED-NEEDS-USER —「不再白点」的口径仍需用户裁定：合取判据必须解算后才有相机，故用户仍需先点满 4 点并触发预览/保存才会看到引导（修复前是解算前 400，同样要先点满 4 点，此点无退步）。是否满足用户对「不白点」的期待，由用户判。

4. [L2] BLOCKED-NEEDS-USER — new_issues 第 1 条那 26.3% 静默坏标定在真实用户点选习惯下的实际发生率。我的数字来自合成相机的建模扫描（method 已写在 evidence 第 5/new_issues 第 1 条），不是生产统计；真实用户受 F003 tier 排序与 F004 轮候引导，实际率未知。

---

## F002 — PARTIAL

### 描述

复验 calib-cure-b3 F002「拍摄/构图引导 UI(上传+标定入口)」, 修复 commit 768d213。

【原两条缺陷: 均已真实消失】
(1) 「标定入口缺『角落机位』『避免正对单面墙』」—— 已修复。我按上轮复现步骤重跑 grep, "角落" 现命中 2 个文件(新增 FeaturePointCalibrator.tsx:352), "正对一面墙平拍" 现命中标定入口。实读 FeaturePointCalibrator.tsx:348-358, 新增 span 位于 b2 F006 构图 banner 内部(事前展示, 非 F001 后端 400 反应式触发), 四条要点在标定入口全部齐备。
(2) 「简示意缺失」—— 组件已新增(ShootingGuideDiagram.tsx, 111 行纯 SVG, 无位图无新依赖), 上传入口与标定入口两处 import 复用。我在真实无头浏览器实测: 两个 figure 确实挂载并可见(good/bad 各 152x115.5px), aria-label 齐备。

【但修复本身引入新缺陷 -> 不得判 PASS】
ShootingGuideDiagram 全部语义色用 emerald / rose, 而本项目 tailwind.config.js 的 `theme.colors` 是**整表覆盖(非 extend)**, 调色板里根本没有 emerald / rose(只有 green/red/amber/sky…)。故这些类**一条 CSS 都不生成**。浏览器实测计算样式:
 - 视锥 polygon: class="fill-emerald-500/20 stroke-emerald-600" -> 计算值 fill: rgb(0,0,0) **不透明纯黑**, stroke: none。设计意图的 20% 半透明视锥变成盖住房间的黑色实心块。
 - 「被拍到的两面相邻墙加粗」高亮线(good 2 条 / bad 1 条): stroke: none -> **完全不可见**。而这正是整张示意图最承重的元素——「两面墙 vs 一面墙」的视觉区分彻底消失。
 - 相机点 circle、figcaption 好坏配色(text-emerald-700/text-rose-700): 计算值均为默认黑 / 白, 绿红对照全无。
元素截图目视确认: 两格都只是「灰色房间框 + 一个纯黑三角形」, 除三角形位置(左下角 vs 底边中央)外无任何好坏区分, 观感像渲染 bug 而非设计图示。
commit message 自称的「SVG 用 stroke-/fill- token 类, 不写死十六进制」作为设计系统合规卖点, 在本项目调色板下**实效为假**。

修复成本极小: emerald->green, rose->red 即可(已实测这两组在本项目调色板下正常生成 CSS)。

【次要】accent 的 fill-emerald-500/20 与 fill-rose-500/15 无成对 dark:(acceptance 明写「成对 dark:」), 其余色类成对完整。

结论: 原缺陷确已消失, 但为补 acceptance「简示意」而新增的组件渲染实效受损, 按复验口径「修复解决原缺陷但引入新问题 -> 不得判 PASS」, 判 PARTIAL。

### 复现步骤

【复现 NEW-1(核心, 全自动, 约 2 分钟)】
1. cd /Users/yixingzhou/project/grandtianfu/apps/web
2. npx tailwindcss -i src/styles/index.css -o /tmp/tw-out.css
3. grep -c "\.stroke-emerald-600" /tmp/tw-out.css     # 期望 0 (缺色)
   grep -c "\.fill-rose-500\\\\/15"  /tmp/tw-out.css     # 期望 0
   grep -c "\.stroke-gray-400"     /tmp/tw-out.css     # 期望 1 (对照: 同构建里存在的类)
4. 反证修复可行: printf '<div class="stroke-green-600 fill-green-500/20 stroke-red-600 text-green-700"></div>' > /tmp/probe.html
   npx tailwindcss -i src/styles/index.css -o /tmp/tw2.css --content /tmp/probe.html
   grep -c "\.stroke-green-600" /tmp/tw2.css          # 期望 1
5. 配置根因: 实读 apps/web/tailwind.config.js —— `theme.colors`(非 theme.extend.colors)整表覆盖, 键内无 emerald/rose/sky。

【浏览器计算样式复现(强证据)】
6. 在 apps/web/e2e/ 放临时 spec: goto '/studio/projects/D/baseline';
   等待 getByText('拍摄建议（直接影响能否标定/精准落位）') 可见;
   page.evaluate 取 svg[role="img"][aria-label*="示意图"] 内 polygon / line / circle 的 getComputedStyle(fill, stroke);
   并对 figure 父元素 screenshot。
7. npx playwright test <spec> --reporter=list
   期望输出: polygon fill "rgb(0, 0, 0)" + stroke "none"; 全部 line stroke "none"; figcaption color "rgb(255,255,255)"。
   截图目视: 两格仅「灰框 + 纯黑实心三角」, 无绿红、无墙面加粗差异。
8. 跑完删除该 spec、截图与仓库根 .e2e-sandbox/ (红线: e2e 绝不写 data/projects)。

【复现「原两条缺陷已消失」】
9. grep -rn "角落" apps/web/src        # 现应命中 BaselinePhotosCard.tsx:323/330 + FeaturePointCalibrator.tsx:352/356
10. 实读 apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx:348-358 (标定入口新增两条核心认知 + 示意图)
11. 实读 apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx:337-338 (上传入口示意图)

【静态检查与红线】
12. npx tsc --noEmit                  # 期望 exit 0
13. npx next lint --file src/components/studio/real-render/ShootingGuideDiagram.tsx   # 期望 no warnings
14. git show 768d213 --stat           # 期望仅 3 个前端文件, 未碰 apps/api/ 硬门
15. git diff --stat dc9787f..HEAD -- data/ packages/floorplan_core/ apps/web/public/  # 期望空

【建议 fixing(改动面极小)】
 (a) ShootingGuideDiagram.tsx 内 emerald-* -> green-*, rose-* -> red-*(本项目调色板内, 已实测出 CSS);
 (b) 给 fill-green-500/20 与 fill-red-500/15 补成对 dark:;
 (c) 修完必须以第 6-7 步的**计算样式**复验(而非只看 class 字符串)——本轮正是靠计算样式才发现 class 在但 CSS 不存在。

### 证据

【1. Tailwind 调色板缺色 — 直接构建产物取证】
$ cd apps/web && npx tailwindcss -i src/styles/index.css -o /tmp/.../tw-out.css   -> Done in 544ms, 175509 bytes
$ grep -c "\.<class>" tw-out.css:
  stroke-emerald-600 -> 0 | stroke-emerald-400 -> 0 | fill-emerald-500\/20 -> 0
  fill-emerald-600   -> 0 | stroke-rose-600    -> 0 | fill-rose-500\/15   -> 0
  text-emerald-700   -> 0 | text-rose-700      -> 0
  (对照, 同一次构建里存在的类) stroke-gray-400 -> 1 | fill-none -> 1 | text-gray-500 -> 1
根因: /Users/yixingzhou/project/grandtianfu/apps/web/tailwind.config.js 中 `theme.colors`(非 theme.extend.colors)整表覆盖默认调色板, 键为 white/lightPrimary/blueSecondary/brandLinear/gray/navy/red/orange/amber/yellow/lime/green/teal/cyan/blue/indigo/purple/pink/background/brand/horizon*/shadow —— **无 emerald, 无 rose, 无 sky**。
反证(修复可行性): 用 in-palette 的 green/red 探针重建 ->
  stroke-green-600 -> 1 | fill-green-500\/20 -> 1 | stroke-red-600 -> 1 | text-green-700 -> 1

【2. 真实无头浏览器计算样式实测(自建临时 spec, 沙箱数据, 跑完即删)】
$ cd apps/web && npx playwright test tmp-b3f002-reverify --reporter=list
  ✓ 1 e2e/tmp-b3f002-reverify.spec.ts (7.3s)  1 passed
DIAGRAM_GOOD_BOX {"x":683,"y":711,"width":152,"height":115.515625}
DIAGRAM_BAD_BOX  {"x":851,"y":711,"width":152,"height":115.515625}   <- 组件确实渲染
DIAGRAM_COMPUTED:
  [good] polygon cls="fill-emerald-500/20 stroke-emerald-600 dark:stroke-emerald-400"
         -> fill: "rgb(0, 0, 0)"   stroke: "none"
  [good] line x2 cls="stroke-emerald-600 dark:stroke-emerald-400"
         -> stroke: "none"        <- 「两面相邻墙」高亮线不可见
  [bad]  polygon cls="fill-rose-500/15 stroke-rose-600 dark:stroke-rose-400"
         -> fill: "rgb(0, 0, 0)"   stroke: "none"
  [bad]  line x1 -> stroke: "none"
CAPTIONS:
  "✓ 站角落 · 两面墙入画"  cls="...text-emerald-700 dark:text-emerald-400" -> color: "rgb(255, 255, 255)"
  "✗ 正对单面墙平拍"      cls="...text-rose-700 dark:text-rose-400"       -> color: "rgb(255, 255, 255)"
元素级截图目视: 两格均为「灰框 + 纯黑实心三角」, 无绿红对照, 无墙面加粗差异。

【3. 原缺陷已消失 — 逐条复跑上轮复现步骤】
$ grep -rn "角落" apps/web/src   -> BaselinePhotosCard.tsx:323/330 + **FeaturePointCalibrator.tsx:352 与 356(新增)**
  (上轮该 grep 仅命中 BaselinePhotosCard 一处)
实读 apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx:348-358:
  「若这张照片标不出来,多半是拍法问题:标定要求<b>站在房间角落拍、画面同时带到两面相邻的墙</b>;
   <b>正对一面墙平拍</b>的照片特征点全部共面,几何上无解——换角落机位重拍才行。」
  该 span 与 <ShootingGuideDiagram /> 同处 b2 F006 banner(条件 features.length >= MIN_POINTS, 非失败后触发)。
实读 apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx:337-338: banner children 内已含 <ShootingGuideDiagram />(上轮此处无 svg/img)。

【4. 静态检查(HEAD, 工作区=HEAD)】
$ cd apps/web && npx tsc --noEmit ; echo TSC_EXIT=$?   -> TSC_EXIT=0 (无输出)
$ npx next lint --file ShootingGuideDiagram.tsx --file FeaturePointCalibrator.tsx --file BaselinePhotosCard.tsx
  -> ✔ No ESLint warnings or errors

【5. 红线与铁律 10】
$ git show 768d213 --stat -> 仅 3 个前端文件 (BaselinePhotosCard.tsx +3 / FeaturePointCalibrator.tsx +12 / ShootingGuideDiagram.tsx +111), 126 insertions, 0 deletions
  => 未碰 apps/api/(含 perspective.CAMERA_Z_RANGE_MM / HFOV_RANGE_DEG / reproj 阈值 / assess ok 判定), 未碰 solve_pnp/_solve_pnp_general, 未碰 data/, 未碰 packages/floorplan_core/, 未碰 golden。**本轮 F002 修复未放宽任何硬门**(纯前端文案+SVG)。
$ git diff --stat dc9787f..HEAD -- data/ packages/floorplan_core/ apps/web/public/  -> 空输出
$ git status --short -> 仅剩会话前既存的未追踪文档 docs/实拍效果图-几何锁定优化方案-20260717.md; 临时 spec / 截图 / .e2e-sandbox 均已删除
commit tag fix(calib-cure-b3-F002) 映射 features.json F002 ✓(铁律 10)

【6. 归因核查 — 哪些是本批新增, 哪些是既有基线】
$ git show dc9787f:apps/web/src/components/studio/ui/status.tsx | grep -n "sky-50"
  276: info: 'border-sky-200 bg-sky-50 text-sky-700 dark:...'   <- 既有基线(引入于 e132007, 2026-07-12), 非本批
$ git grep -c "emerald-" dc9787f -- apps/web/src
  CalibrationMiniMap.tsx:1 / FeaturePointCalibrator.tsx:2 / PerspectiveCalibrator.tsx:1  <- emerald 缺色是既有全项目潜在问题
$ git grep -l "rose-" dc9787f -- apps/web/src/components  -> 空(rose 为本批新引入)
=> 「调色板无 emerald/rose/sky」本身是既有配置遗留; 但 **ShootingGuideDiagram 是本批新建、且是首个把整张图的全部语义(好/坏配色 + 两面墙 vs 一面墙高亮)都押在缺色 token 上的组件**, 其渲染受损归咎本轮修复成立。

【7. 未写任何产品代码 / 测试 / 状态文件】本轮仅新建后删除一个临时 e2e spec 与截图; 按调用方指示未落 .md 报告文件, 结论以本结构化输出为准。

### 修复是否引入新问题（new_issues）

【NEW-1 (阻断 PASS, 由 768d213 引入)】ShootingGuideDiagram.tsx 使用不在本项目 Tailwind 调色板内的 emerald / rose 语义色, 零 CSS 生成 -> 浏览器实测 polygon 视锥 fill 落到 SVG 默认 rgb(0,0,0) 不透明黑、两面墙高亮 line stroke:none 完全不可见、figcaption 绿红对照失效。结果: 新增的「简示意」两格都只是黑色实心三角, 丢失其唯一承重语义(两面相邻墙 vs 单面墙), 且观感像渲染 bug。位置: apps/web/src/components/studio/real-render/ShootingGuideDiagram.tsx:13(WALL 除外), :17-22(accent/dot), :60/68/78(line stroke), :86-87(caption)。修复: emerald->green, rose->red(已实测二者在本项目调色板下正常出 CSS)。

【NEW-2 (非阻断, 同 commit)】accent 的 fill-emerald-500/20 与 fill-rose-500/15 缺成对 dark:(acceptance 明写「成对 dark:」)。修 NEW-1 时一并补。

【既有基线, 非本批, 仅如实记录不归咎】status.tsx NoticeBanner 的 info tone(bg-sky-50/text-sky-700/dark:bg-sky-900)同样因调色板无 sky 而零 CSS: 浏览器实测该 banner 计算值 backgroundColor: rgba(0,0,0,0)、color: rgb(255,255,255)、border: rgb(218,222,236)。即 info 提示条实际无底色。**这同时订正 verifying-1 报告 F002 §证据1 的一处事实错误**——该报告称元素截图目视为「深蓝底 + 浅蓝字, 对比度良好」, 实测为透明底 + 白字(继承页面深色背景, 可读但非其所述配色)。引入于 e132007(2026-07-12), 早于批次基线 dc9787f, 超出 b3 batch_scope, 建议入 backlog 而非本批修。

### 未验证项（BLOCKED-NEEDS-USER）

【BLOCKED-NEEDS-USER 1】标定入口(FeaturePointCalibrator)banner 与其内简示意的**真实浏览器渲染确认**未执行。原因: 该 banner 条件为 features.length >= MIN_POINTS, 需一张已分配 room_id 的实拍照; 而 e2e 沙箱由 e2e/start-api.sh 只拷 data/projects(实测 .e2e-sandbox/ 内无任何 photos.json), 仓库内 data/uploads 不存在(PIPL 已 gitignore)。故本轮标定入口那一半为**源码级判定**(FeaturePointCalibrator.tsx:348-358 实读 + grep 复现), 未取浏览器证据。不臆测其结果; 但 NEW-1 的渲染缺陷对该处同样成立(同一组件同一 import)。

【BLOCKED-NEEDS-USER 2】引导文案与示意图的**实际行为效力**(用户读后是否确实改角落机位重拍、重拍后能否标定成功)属 F006 [L2] 范围, 需用户当面操作真实浏览器 + 只读重拉 PIPL 病例照。未获授权, 未执行, 不臆测。本轮仅证「引导存在且内容齐全 / 示意图渲染受损」, **不代表已证明其解决用户报障**。

【BLOCKED-NEEDS-USER 3】「简示意」的视觉设计取舍(要不要图、画成什么样、黑色实心视锥是否可接受)需用户/设计裁决。我只客观记录其当前计算样式与截图事实, 不代替裁决。

【BLOCKED-NEEDS-USER 4】移动端/窄屏多视口下 banner + 双格示意图的排版可读性未做目视确认(本轮仅 1280x720 桌面视口)。注: 组件外层 max-w-xs, 窄屏下两格并排可能过窄, 未验证。

### 对抗复核

- refuted: **False** → final_result: **PARTIAL**

证伪失败, 原判定成立。逐条复现如下。

【证伪尝试 1 — 环境误报?】否。tailwind 3.4.19 本地已装, 构建正常 (175509 bytes)。无依赖缺失/版本漂移。

【证伪尝试 2 — content glob 漏扫该文件? (我最强的证伪候选)】决定性推翻。stroke-gray-400 在整个 apps/web/src 中**仅**出现于 ShootingGuideDiagram.tsx:13, 且该类在同一次构建中**确实生成了 CSS**(count=1)。=> 扫描器确实读到了这个文件; 同文件同组件的 emerald/rose 类全部 0。故缺 CSS 纯粹是调色板缺键, 不是扫描问题。

【证伪尝试 3 — safelist / 另一份 CSS / 第二个 config / 生产管线不同?】全否。无 safelist; 配置与 src/styles/*.css 中无 emerald/rose/sky; 仅一份 tailwind.config.js; postcss.config.js 为标准 tailwindcss+autoprefixer => next build 走同一调色板。无逃生口。

【证伪尝试 4 — presentation attribute 覆盖?】否, 源码除 strokeWidth 外未设 fill/stroke 属性。

【证伪尝试 5 — 把既有基线问题归咎本批?】部分既有, 但归因公允。tailwind.config.js:150 的 theme.colors 为整表覆盖(keys 无 emerald/rose/sky); 基线 dc9787f 已有 3 个文件用 emerald, 但均为装饰性(徽章底色/勾选着色)。ShootingGuideDiagram.tsx 是 768d213 **全新**文件, 且把整图承重语义全押在缺失 token 上。上轮报告已显式区分并建议既有缺口入 backlog。归因成立。

【我的独立计算样式实测(自建 harness + 真实构建 CSS + 逐字转写 markup + headless Chromium)】
 g-cone polygon -> fill rgb(0,0,0) / stroke none (20% 半透明视锥变不透明纯黑)
 g-l1,g-l2,b-l1 line -> stroke none (「两面相邻墙 vs 一面墙」高亮完全不可见)
 对照 wall rect(stroke-gray-400, 在调色板内) -> stroke rgb(176,187,213) = #B0BBD5 = gray.400 ✓ (证明 harness 与 CSS 接线正确)
 元素截图目视: 两格均为灰框 + 一个纯黑实心三角, 无绿红、无墙面粗细差异。

【修复可行性实测】emerald->green / rose->red 后重建重渲: fill rgba(34,197,94,0.2), stroke rgb(23,173,55), caption rgb(21,128,61); 截图呈现设计意图 —— 绿色半透明视锥 + **两条**加粗相邻墙 vs 红色视锥 + **一条**加粗墙。反证了 shipped 版本丢失的正是该图唯一的区分性内容。

【原两条缺陷确已消失】基线 dc9787f 时 git grep 角落 -- apps/web/src **零命中**; HEAD 命中两处入口含 FeaturePointCalibrator.tsx:354/357, 且位于 b2 F006 banner(事前展示), 非 F001 反应式 400 路径。

【NEW-2 源码确认】ShootingGuideDiagram.tsx:18-19 的 fill-emerald-500/20 与 fill-rose-500/15 无成对 dark:(同行 stroke- 类有), 直接违反 acceptance 明文「成对 dark:」。

【静态检查对此缺陷盲视】tsc --noEmit exit 0; next lint 三文件 ✔ No ESLint warnings or errors —— 正因如此才必须做计算样式验证。

【红线核查全清】768d213 = 3 个前端文件, 126 insertions / 0 deletions。apps/api/aigc/perspective.py **完全不在本批 changed-file 列表**内 => CAMERA_Z_RANGE_MM(800-2200) / HFOV_RANGE_DEG(35-110) / assess ok 判定 / solve_pnp / _solve_pnp_general 均未被触碰; 对 dc9787f..HEAD 全批 grep '^[+-].*(常量)\s*=' 无任何命中。**本轮未放宽任何硬门**。data/ + packages/floorplan_core/ + apps/web/public/ 净 diff 为空; golden 未动。commit tag fix(calib-cure-b3-F002) 映射 features.json F002 ✓(铁律 10)。

【无回归】apps/api 438 passed; packages/floorplan_core 154 passed。

【对上轮报告的一处订正(不影响结论)】上轮称 figcaption 计算色 rgb(255,255,255), 我在隔离 harness 测得 rgb(0,0,0) —— 差异仅在**继承值**(其页面深色背景, 我的 harness 无)。承重事实一致: text-emerald-700/text-rose-700 零 CSS, 颜色落回继承, 绿红对照失效。

【判定】原缺陷确已消失, 但为满足 acceptance「简示意」而新增的产物渲染时丢失其唯一承重语义, 且 acceptance 明文「成对 dark:」被违反。按复验口径「修复解决原缺陷但引入新问题 -> 不得判 PASS」, 维持 PARTIAL。commit message 自称的「SVG 用 stroke-/fill- token 类」作为设计系统合规卖点, 在本项目被覆盖的调色板下实效为假。

【L2】本条无需用户人工目视即已判定(全自动构建产物 + 无头浏览器计算样式取证), 无 BLOCKED-NEEDS-USER 项。

【本轮我未写任何仓库文件】仅在 scratchpad 建临时 harness/probe/截图, 已全部删除; git status 仅剩会话前既存未追踪文档; .e2e-sandbox 不存在。

---

## F004 — PASS

### 描述

原缺陷（孪生联动提示对天花板角是死代码）经我亲自复跑上一轮的复现步骤，确认已真实消失，且我用真实后端数据 + 直接执行产品模块本体做了红/绿对照，不是"看起来改了"。

【一、原缺陷复现步骤亲自复跑 — 已消失，有数字】
上一轮 F004 判 PARTIAL 的唯一理由：`byPriority` 同 priority 回落 id 字典序，'ceilcorner:' < 'corner:' → 全部天花板角排在其地面孪生之前 → `twinPlaced` 对天花板角恒为 null → 提示只在门框顶(#10)/窗框顶(#12) 触发，天花板角任意位次均不触发。

我用 `derive_features` 对 data/projects/D/geometry.json 全部 20 个房间派生真实特征（只读），再用 Node 直接 import 产品模块 `apps/web/src/lib/calibration/featureQueue.ts`（不复制逻辑），忠实模拟 currentTarget/twinPlaced 轮候流程：
- 修复前比较器（逐字取自 52dd41c）：**20/20 房间「天花板角孪生提示首次触发位次」= -1（永不触发）**；首个任意孪生提示落在位次 10~25（与上一轮报告的 11~25 一致，我这版含 r_pub2/r_corr_g/r_bed_g 的 10）。
- 修复后（HEAD 产品模块）：**20/20 房间该值有限**——18 个房间 = 位次 5，r_foyer / r_live（各 8 个墙角）= 位次 9。
死代码结论被数值推翻，且是"从 -1 变成有限值"这种性质上的变化，不是位次微调。

【二、修复本身有无新缺陷/回归 — 独立核查】
1. 守门脚本非同义反复：我把产品模块复制到 scratchpad、只把比较器还原成修复前形态，再让 `scripts/check/feature-queue-order.ts` 的副本指向它 → 退出码 1，逐条报出 4 个天花板角"排在其地面孪生之前"。HEAD 上真跑退出码 0。红/绿双向都验过。
2. 几何风险未变差（commit 的这条自称我实测了，不是采信）：min-4 集合在新旧序下分别是 4 个地面角(z=0) / 4 个天花板角(z=2700)，`degeneracy_reason` 对两者**都返回 None**，行为完全一致，未收紧也未放宽。
3. 硬门零改动：`apps/api/aigc/perspective.py` 全批次净 diff = **0 行**；CAMERA_Z_RANGE_MM(800,2200) / HFOV_RANGE_DEG(35,110) / CALIB_MAX_REPROJ_PX 50.0 / CALIB_GOOD_REPROJ_PX 25.0 与基线 dc9787f 逐字相同。F004 修复只动 3 个前端文件，未触后端。
4. 排序契约副作用核查：`isElevated` 是 priority 之后的高阶键，故 planId 键只在"地面组内"和"异面组内"生效，两组相对次序一致（fixture 输出 corner 东北/东南/西北/西南 → ceilcorner 同序）；`orderFeatureQueue` 仍返回新数组（不变性保持）；`isElevated`(world[2]>1) 与 `planId` 三条前缀映射逐字未改。
5. 回归：api 438 passed / floorplan_core 154 passed，0 skip；golden 逐字节 `-k baseline_byte_for_byte` 2 passed（实跑非 skip）；tsc exit 0；next lint exit 0、Error 计数 0，新增两文件零告警（残留告警全在 useViewport.ts，既有基线）。
6. 铁律 10：commit fe1b7bf tag `fix(calib-cure-b3-F004)` 映射 features.json 实有 F004 ✅。红线：data/ 与 packages/floorplan_core/ 净 diff 为空，工作区仅一个批次无关的未追踪文档。

【三、按 acceptance 全条重判】
- "开工前查 v_i↔yaw 映射是否可用" → 映射可用（b625012a 已投产），故 acceptance 的条件式退路不触发，未走退路正确。
- "天花板角与地面孪生联动提示" → 现已可达（上述数值）。
- "照片侧目标区域高亮" 主动缩减 → 上一轮已以蒙特卡洛量化证成立（先验相容相机仅 5.8% 能把该点投进画幅），本轮无新信息推翻。
- "朝向锁定" → 文本级锚定，spec §D4 授权范围内。
- 前端复用设计系统、tsc+lint 绿 → ✅
判 PASS。

### 复现步骤

复跑我这次的判定（无需浏览器、无需网络、无需安装依赖，约 40 秒）：

1) 导出真实特征（只读 data/projects/D/geometry.json）：
   PYTHONPATH=packages/floorplan_core:apps/api python3 -c "
   import json; from aigc import calib_features as cf
   geo=json.load(open('data/projects/D/geometry.json')); out={}
   for r in geo['rooms']:
       f,_=cf.derive_features(geo, r['id'])
       if f: out[r['id']]=[{'id':x['id'],'priority':x['priority'],'world':x['world'],'kind':x['kind']} for x in f]
   json.dump(out, open('/tmp/real_feats.json','w'), ensure_ascii=False)"

2) GREEN：写一段 TS，从 `apps/web/src/lib/calibration/featureQueue.ts` import `orderFeatureQueue/isElevated/planId`，按队列顺序逐点"放置"，记录首个 `ceilcorner:*` 且其 planId 孪生已在 placed 中的位次。
   node --experimental-strip-types <该文件>
   期望：每个房间该位次为有限值（18 房间 = 5，r_foyer/r_live = 9）。

3) RED：同一段逻辑，比较器换成修复前的 `(a,b)=>a.priority-b.priority||a.id.localeCompare(b.id)`。
   期望：20/20 房间该位次 = -1（永不触发）—— 这就是上一轮判 PARTIAL 的缺陷。

4) 守门脚本双向：
   node --experimental-strip-types scripts/check/feature-queue-order.ts            # 期望 exit 0
   把 featureQueue.ts 复制到临时目录、只把比较器还原为修复前，再让 check 脚本副本 import 它
   node --experimental-strip-types <临时>/check.ts                                  # 期望 exit 1 且报 4 条"孪生联动死代码"

5) 门未放宽 + 几何未变差：
   git diff dc9787f...HEAD -- apps/api/aigc/perspective.py | wc -l                  # 期望 0
   用 cf.degeneracy_reason 对 r_guest2 新旧序的前 4 点各跑一次                        # 期望两者均为 None

6) 回归：
   PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q   # 438 passed
   PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q  # 154 passed
   PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -k baseline_byte_for_byte -rs  # 2 passed
   cd apps/web && npx tsc --noEmit && npx next lint                                  # 均 exit 0

### 证据

【复现/红绿对照 — 我实际跑的命令与输出要点】
1) 真实特征派生（只读 data/projects/D/geometry.json，未写入）：
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -c "... cf.derive_features(geo, rid) ..."
  -> 20 个房间均派生成功，特征数 10~32（r_guest2=14, r_foyer=32, r_live=32）

2) 修复后队列模拟（Node 直接 import 产品模块 apps/web/src/lib/calibration/featureQueue.ts）：
$ node --experimental-strip-types <scratchpad>/sim.ts
  room | #feat | firstCeilPos | ceilTwinHintPos | firstAnyTwinHintPos | first4kinds
  r_guest2 | 14 | 5 | **5** | 5 | wall_corner x4
  r_foyer  | 32 | 9 | **9** | 9 | wall_corner x4
  r_live   | 32 | 9 | **9** | 9 | wall_corner x4
  (其余 17 房间 ceilTwinHintPos 均 = 5)

3) 修复前比较器 RED 对照（byPriority 逐字取自 git show 52dd41c）：
$ node --experimental-strip-types <scratchpad>/sim_old.ts
  r_guest2 | firstCeilPos=1 | ceilTwinHintPos=**-1** | firstAnyTwinHintPos=12 | ceiling_corner x4
  r_foyer/r_live | 1 | **-1** | 25 | ceiling_corner x4
  -> 20/20 房间 ceilTwinHintPos = -1（永不触发），复现了上一轮报告的结论

4) 守门脚本双向验证：
$ node --experimental-strip-types scripts/check/feature-queue-order.ts
  -> PASS feature-queue-order (12 个特征, 4 条断言); EXIT=0
  轮候序: corner:r_a:东北 -> 东南 -> 西北 -> 西南 -> ceilcorner:r_a:东北 -> ... -> door:d1:a -> doorhead:d1:a -> window:w1:a -> winhead:w1:a
$ node --experimental-strip-types <scratchpad>/redtest/check.ts   # 仅比较器还原为修复前，产品代码未动
  -> RED_EXIT=1
  FAIL feature-queue-order:
    - 孪生联动死代码: ceilcorner:r_a:东北 (位次 0) 排在其地面孪生 corner:r_a:东北 (位次 4) 之前/缺失
    - (同类 4 条)

5) 几何风险未变差实测：
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -c "cf.degeneracy_reason(top4) 新旧序对照 (r_guest2)"
  OLD ['ceilcorner:r_guest2:东北','东南','西北','西南'] -> degeneracy_reason: None
  NEW ['corner:r_guest2:东北','东南','西北','西南']     -> degeneracy_reason: None

6) 测试与门：
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q     -> 438 passed in 21.29s (0 skip)
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -> 154 passed in 0.99s (0 skip)
$ ... -k baseline_byte_for_byte -rs                                                    -> 2 passed, 152 deselected（golden 逐字节实跑）
$ cd apps/web && npx tsc --noEmit  -> TSC_EXIT=0
$ cd apps/web && npx next lint     -> LINT_EXIT=0, "Error:" 计数 0, 输出中无 featureQueue/FeaturePointCalibrator/calibration 任何条目
$ git diff dc9787f...HEAD -- apps/api/aigc/perspective.py | wc -l -> 0
$ git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ apps/api/aigc/perspective.py -> 空

【我读到的文件:行号】
- apps/web/src/lib/calibration/featureQueue.ts:44-51 — compareFeatureQueue: `a.priority-b.priority || Number(isElevated(a))-Number(isElevated(b)) || planId(a.id).localeCompare(planId(b.id)) || a.id.localeCompare(b.id)`（承重键 = 第二项）
- apps/web/src/lib/calibration/featureQueue.ts:22 isElevated(world[2]>1) / :25-30 planId 三条前缀映射 —— 与 52dd41c 版逐字相同，纯搬迁
- apps/web/src/components/studio/real-render/FeaturePointCalibrator.tsx:163 `orderFeatureQueue(features)` 取代 `[...features].sort(byPriority)`
- 同文件:176-182 twinPlaced（currentTarget 为异面点且孪生已在 placed 才非 null）; :418-427 提示文案; :506-512 琥珀竖线覆盖层 —— 本轮未改，上一轮已核为实现正确
- apps/api/aigc/calib_features.py:485-491 「全同高」分支需 XY 近共线(sxy[1]/sxy[0]<0.30) 才触发，故矩形房 4 角在新旧序下同样返回 None
- apps/api/aigc/perspective.py:585-588 四个门常量，与 `git show dc9787f:` 输出逐字相同

### 修复是否引入新问题（new_issues）

均为**非阻断**，不改变 PASS 判定，建议记入 signoff 诚实边界或 backlog：

1. **提示在 MIN_POINTS=4 预算内仍不可达（残留，非新引入）**：孪生提示首次触发位次为 5（r_foyer/r_live 为 9），而 MIN_POINTS=4、放满 4 点即出现绿色徽章且「解算」按钮解禁，只放最少点的用户仍一次都看不到该提示。我判定这不构成阻断，理由是可验证的：新序下前 4 位全是 wall_corner（地面角），此时用户**根本不会被要求点天花板角**，b2 L2 病灶（天花板角被点到窗户半高）在该区间零暴露；提示恰好出现在第一个天花板角出现的同一刻。即"风险与提示同步到达"，与修复前"天花板角在位次 1-4 出现却无任何提示"是本质区别。

2. **守门脚本未接入任何自动执行路径**：`grep -rn "scripts/check\|feature-queue-order" .github/ package.json apps/web/package.json .git/hooks/pre-commit` 全部无匹配。该脚本只能人工跑，CI（pytest.yml / e2e.yml / deploy.yml）与 pre-commit 都不执行它，故它钉住的回归可以静默复发。commit message 已诚实说明"apps/web 无单测 runner"，但未说明它不会被自动跑。建议后续接入 CI 或 pre-commit。

3. **两个新文件在 batch_scope.allowed_paths 之外**：`apps/web/src/lib/calibration/featureQueue.ts` 与 `scripts/check/feature-queue-order.ts`。allowed_paths 前端只列到 `apps/web/src/components/studio/real-render/`、`apps/web/src/lib/studioApi.ts`（单文件）与 `scripts/spike/`。红线（red_lines 8 条）本身未被违反，改动性质是纯重构 + 测试守门，我不据此扣分，仅记录以便 Planner 决定是否补登 scope。

4. **跳过分支无兜底文案（既有行为）**：若用户跳过全部地面角再遇天花板角，twinPlaced 为 null，提示与竖线均不出现，UI 无"请先放它正下方的地面墙角"之类兜底。上一轮报告曾把这条列为建议修复方向之一，本次修复选了排序方案未做兜底文案，属可接受的方案取舍。

### 未验证项（BLOCKED-NEEDS-USER）

[L2] 未执行，待用户当面配合（不得臆测，故既不据此判 PASS 也不据此判 FAIL）：
1. **真实浏览器目视确认孪生提示实际渲染**：我的复现是纯逻辑层（真实派生数据 + 直接执行产品排序/孪生模块），能证明 twinPlaced 在位次 5 非 null，但**未在浏览器中目视确认**那段琥珀色文案与照片覆盖层竖线真的出现在屏幕上、位置合理、深浅色主题下可读。BLOCKED-NEEDS-USER。
2. **「朝向锁定」强度是否满足用户预期**（上一轮遗留项，本轮未获新证据）：实装为非阻断提示 banner + 失败后文案，无"先点 1 个无歧义特征"的交互式锁。spec §D4 标注"按需/可分期"，我倾向认为在授权范围内，但最终是否达到用户对"锁定"二字的预期需用户裁决。BLOCKED-NEEDS-USER。
3. **legacy direction 值（N/S/E/W）在生产是否存在**：上一轮观察到 `VIEW_FACING[photo.direction ?? '']` 对 legacy 值取不到会落到"还没标注拍摄视角"的 warn banner（陈述失实但补救动作正确）。仓库 seed 数据无任何 direction 值，需真实生产数据确认。BLOCKED-NEEDS-USER。

---

## F005 — PASS

### 描述

F005（3D/简模引导路线评估 spike）复验通过。verifying-1 的唯一承重缺陷（acceptance 明文要求"承接 b1 spike 4 条 GO 条件: VLM 形体评分/样本/curtain 简模"，原报告只实质覆盖 2 条）已在 fix commit 106d5aa 中真实消除：报告新增 §8「逐条承接 b1 spike 的 4 条 GO 条件」，四条各有独立小节，且对原评估者点名的实质风险（§6.2 新提的"落位保真度"检测与 b1 已议定的"VLM/人工形体评分器"是否重复推导/取代）作了明确处置——判为正交两维、b4 应同时接续。原判 non-blocking 的 B 项（付费臂零可核证据）也一并补齐并经我独立验真。

我对修复本身的独立核查：修复是 docs-only（106d5aa 只改 docs/test-reports/ 下 4 个文件），未触碰任何产品代码、未放宽任何硬门、未改动 spike 研究码、未新增二进制/PIPL 物料。features.json 的 F005 acceptance 文本自 planning commit 56ac9be 起未被改写（我用 git show 逐字比对 True），排除"改题面就答"的可能。

acceptance 全条重判：
(1) 研究码非产品、不 import main.py —— PASS。scripts/spike/ 本批净 diff 为空（字面"复用 b1 工具"）；全目录无真实 import main，4 处命中全在注释/docstring。
(2) 用真实病例照（含标定不了的 r_guest2）评估粗相机下 3D 引导可用性 —— PASS（可核部分）。scenes.json 显示两场景 rooms 分别为 [r_guest2] 与 [r_foyer,r_live,r-itki-331]，与报告 §1 自述一致；生产照片本体属 BLOCKED。
(3) 产出 docs/test-reports/calib-cure-b3-3dguide-eval-YYYYMMDD.md，含 go/no-go + b4 建议 + 成本依赖（承接 b1 4 条 GO 条件）—— PASS。NO-GO 明确（§0/§6），b4 三条建议按价值排序，§8 四条件全覆盖。
(4) 不碰生产 data、PIPL 照片不入 git —— PASS。data/ 净 diff 空；全批次无 jpg/png/heic 新增。
(5) 报告自述"研究产物非产品 signoff" —— PASS（报告第 3 行）。

结论：原缺陷真实消失（不是"看起来改了"），修复未引入阻断性新缺陷。发现两处非阻断的表述失准（见 new_issues），均不改变 NO-GO 结论与 acceptance 达成，故不下调判定。

### 复现步骤

全部可在仓库根离线复现，零成本、无需生产访问、无 PIPL：

1) 原缺陷是否消失（上一轮判 PARTIAL 的承重依据）
$ for k in curtain 窗帘 VLM 形体评分 评分器; do printf "%s=%s " "$k" "$(grep -c "$k" docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md)"; done
   期望：全部 > 0（verifying-1 时全部为 0）
   再对读 docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md:128-174 与 b1 原文 docs/test-reports/spike-l1-guide-ab-20260717.md:152-166，确认四条件一一对应。

2) 付费臂证据的真伪（byte 级）
$ PYTHONPATH=packages/floorplan_core:apps/api:scripts/spike python3 - <<'EOF'
import json, importlib.util, pathlib, tempfile
spec=importlib.util.spec_from_file_location("run_ab","scripts/spike/run_ab.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
rows=json.load(open('docs/test-reports/calib-cure-b3-3dguide-eval-20260720/run-rows.json'))
out=pathlib.Path(tempfile.mkdtemp()); m._write_summary(rows,out,dry=False)
print("BYTE-IDENTICAL:", (out/'summary.md').read_text()==open('docs/test-reports/calib-cure-b3-3dguide-eval-20260720/run-summary.md').read())
print("tokens", sum(r['total_tokens'] for r in rows))
EOF
   期望：BYTE-IDENTICAL: True / tokens 19077

3) NO-GO 承重机制（零成本干跑）
$ SB=/tmp/spike005; mkdir -p $SB
$ cp docs/test-reports/spike-l1-guide/cal_study_798.json data/projects/D/geometry.json data/projects/D/furniture.json $SB/
$ printf '[{"id":"g2","photo":"blank","calibration":"cal_study_798.json","geometry":"geometry.json","furniture":"furniture.json","rooms":["r_guest2"],"style":"modern light-luxury"}]' > $SB/scenes.json
$ PYTHONPATH=packages/floorplan_core:apps/api python3 scripts/spike/run_ab.py --scenes $SB/scenes.json --outdir $SB/out --dry --force
   期望：[dry] g2 L0: 5 件 / g2 L1: 5 件；目视 $SB/out/g2_L0_guide.png 与 g2_L1_guide.png 家具盒逐件重合、仅着色不同。

4) 新发现 1（§8 唯一性表述失准）
   读 docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md:161 与同文件 §5 表 :88-93，对照 apps/api/aigc/perspective.py:587-588 的两个门区间，逐行判 r_live#2 / r_master / r_cloak 是否同时落在 [800,2200]mm 与 [35,110]° 内。

5) 红线与回归
$ git show --name-only --pretty=format: 106d5aa | grep -v '^docs/'            # 无输出 = docs-only
$ git diff --stat dc9787f...HEAD -- apps/api/aigc/perspective.py data/ packages/floorplan_core/ scripts/spike/   # 全空
$ git log --name-only --pretty=format: dc9787f..HEAD | grep -iE '\.(jpg|png|heic)$'   # 无
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q      # 438 passed
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -k baseline_byte_for_byte   # 2 passed（golden 真跑）

### 证据

【1. 复跑上一轮报告的复现步骤 4（判 PARTIAL 的唯一承重依据）—— 原缺陷已消失】
$ for k in curtain 窗帘 VLM 形体评分 评分器 样本 fal 成本; do printf "%s=%s " "$k" "$(grep -c "$k" docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md)"; done
→ curtain=3  窗帘=3  VLM=2  形体评分=2  评分器=2  样本=3  fal=4  成本=4
（verifying-1 实测为 curtain=0 窗帘=0 VLM=0 形体评分=0 评分器=0 —— 四项从 0 变为非 0）
逐条核对 b1 原文 docs/test-reports/spike-l1-guide-ab-20260717.md:152-166 与新 §8：
  条件1(后端依赖/relay 边际收益) → 报告 :134-143，给出 relay 上 L1 边际收益"存在但非质变"的实证读数，并诚实标注 fal 臂未跑故 b1"跨后端鲁棒性"定位仍悬空；
  条件2(须配形体评分器) → 报告 :145-156，除再次实证外，明确写"§6.2 的落位保真检测与 b1 议定的 VLM/人工形体评分器是两个正交维度，不是替代关系……b4 应同时接续，不应视为重复推导而丢弃任一方"——正是 verifying-1 指出的实质风险点；
  条件3(样本仍小/优先补好标定客餐厅) → 报告 :158-164，"部分兑现"，兑现与未兑现分列；
  条件4(curtain 简模隐患) → 报告 :166-174，判"本批无法验证"并给可核事实。

【2. 条件 4 的"可核事实"我独立验了（不是接受叙述）】
$ python3 统计 data/projects/D/furniture.json 类型直方图
→ total 55，类型词表 26 类（cabinet/sofa/rug/media/wine 等），curtain 出现 0 次（该类型在词表中根本不存在）
$ grep -rniE "curtain|窗帘" scripts/spike/run_ab.py
→ run_ab.py:101,180 `if any(it.get("t") == "curtain" for it in furniture):` —— curtain 文案是条件触发；场景无 curtain 件 → prompt 中必然 0 命中，报告"两臂 prompt 中 curtain 命中 0 次"由代码结构佐证成立。
（报告称生产 57 件，仓库 seed 为 55 件；生产数值属 BLOCKED，但 curtain=0 这一方向在可核数据上被证实。）

【3. B 项（付费臂证据入库）—— 我验的是"真伪"不是"有无"】
$ PYTHONPATH=... python3 -c "用 run_ab.py 自身的 _write_summary(rows, out, dry=False) 从committed run-rows.json 重新生成 summary"
→ BYTE-IDENTICAL: True
即committed 的 run-summary.md 与"把committed run-rows.json 喂给工具自身格式化器"的输出逐字节相同（含表头 12 列、"## 预算记账"、"fal 输出像素合计: 0.00 MP"）。
$ python3 校验数值自洽
→ tokens sum = 19077（与报告 §1/§9 的 19077 一致）；elapsed 139.5–178.5s（与报告"139–179s"一致）；provider_ok 4/4。
$ 交叉比对 run-rows.json 与报告 §3/§4 表格
→ guest2_coarse L0 score 1.0 auto_ok true / L1 0.85 false / live_leastbad L0 1.0 true / L1 0.917 false —— 四格逐格吻合，无一处漂移。
$ grep -rn "新边缘坏块" apps/api/
→ apps/api/aigc/acceptance.py:266 `f"盒区外出现新结构 (新边缘坏块 {tiles_bad}/{tiles_total})"` —— rows.json 里的 fail_reasons 字符串是产品 evaluate_geometry_lock 的真实输出格式，非人工转述。
$ 入库物 PIPL 复核：run-rows.json/scenes.json 只含场景 id、arm、backend、score、tokens、相对路径 photos/r_guest2.jpg，无 uploads 哈希文件名、无像素。

【4. 我自己跑的零成本干跑（独立复现 NO-GO 的承重机制，未依赖任何他人叙述）】
$ PYTHONPATH=packages/floorplan_core:apps/api python3 scripts/spike/run_ab.py --scenes <scratchpad>/spike005/scenes.json --outdir <scratchpad>/spike005/out --dry --force
→ [dry] g2 L0: 5 件 -> g2_L0_guide.png ; [dry] g2 L1: 5 件 -> g2_L1_guide.png
输入全部来自仓库内（docs/test-reports/spike-l1-guide/cal_study_798.json + data/projects/D/{geometry,furniture}.json + photo=blank），零成本、零 PIPL、未写 data/。
我目视了两张 PNG：家具盒的位置/尺寸/出画裁切逐件重合，仅着色不同（L0 半透明彩盒 vs L1 不透明简模）；两图中均无一件落在地面、书柜类大件被相机外推到画面右侧成整墙色块。→ 报告 §2「失败由相机决定，不由引导表示法决定」在我自己的运行上成立。

【5. 红线 / 硬门核查（重点：本轮修复是否放宽任何门）】
$ git show --name-only --pretty=format: 106d5aa | grep -v '^docs/' → 无输出（F005 修复是 docs-only）
$ git diff --stat dc9787f...HEAD -- apps/api/aigc/perspective.py → 空（b2 解算内核 + 全部硬门常量零改动）
$ git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ scripts/spike/ → 全空
$ git log --name-only --pretty=format: dc9787f..HEAD | grep -iE '\.(jpg|jpeg|png|heic|webp)$' → 无（PIPL 红线成立）
$ git diff dc9787f...HEAD -- apps/api/ | grep -E '(CAMERA_Z_RANGE|HFOV_RANGE|CALIB_MAX_REPROJ|CALIB_GOOD_REPROJ)'
→ 仅 F001 新增的只读取用（calib_features.py 新增行读 perspective.CAMERA_Z_RANGE_MM / HFOV_RANGE_DEG 用于文案判据），无任何阈值常量被修改；现值仍为 apps/api/aigc/perspective.py:585-588 CALIB_MAX_REPROJ_PX=50.0 / CAMERA_Z_RANGE_MM=(800.0,2200.0) / HFOV_RANGE_DEG=(35.0,110.0)。
$ acceptance 文本防篡改：git show 56ac9be:features.json vs HEAD:features.json 的 F005 acceptance → 相同 (True)

【6. 回归与 golden】
$ PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q → 438 passed in 20.06s（0 skip）
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q → 154 passed in 0.57s（0 skip）
$ PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -k baseline_byte_for_byte → 2 passed, 152 deselected（golden 逐字节确实执行，非 skip）
$ 铁律 10：git log dc9787f..HEAD 中 fix(calib-cure-b3-F005) = 106d5aa，映射 features.json 实际条目 F005，通过。

### 修复是否引入新问题（new_issues）

两处均为 fix commit 106d5aa 新写入 §8 的表述失准，非阻断（不改变 NO-GO 结论、不改变 acceptance 达成），但建议在下次编辑该研究报告时顺手订正：

1. 【报告内部自相矛盾】docs/test-reports/calib-cure-b3-3dguide-eval-20260720.md:161 称 live_leastbad 的相机"是生产中唯一同时过高度门与视场门的一台"。按同一报告 §5 表（:88-93）与硬门实测值（perspective.py:587 CAMERA_Z_RANGE_MM=(800,2200)、:588 HFOV_RANGE_DEG=(35,110)）：r_live#2 (1382mm/101.2°)、r_master (874mm/95.7°)、r_cloak (1515mm/96.4°) 三份都同时落在两门之内，"唯一"不成立。实质结论不受影响——b1 条件 3 要的是"好标定的客餐厅"，而 r_master(主卧)/r_cloak(衣帽间) 都不是客餐厅，故"优先补客餐厅已做到"仍成立；失准的只是唯一性修辞。
   附带发现（属 verifying-1 就已存在的既有瑕疵，非本轮新增）：§5 表把 r_cloak(reproj 123.9px) 标为"过"，但 CALIB_MAX_REPROJ_PX=50.0，该行在 reproj 门上应为不过；该"现行门"列疑似只反映高度/视场门。

2. 【件数口径不一致】§1 表（:30）称 live_leastbad 为"m_living 客餐厅组（6 件）"，§8 条件 3（:160-161）称"7 件家具"，§8 条件 4（:169-170）列举的件目为 dining_table/rug/sofa×2/coffee_table/media/wine_cabinet = 7 件。我在仓库 seed 上统计同组房间（r_foyer+r_live+r-itki-331）得 7 件（sofa×2/dining_table/cabinet/rug/coffee_table/media），与 §8 一致；§1 的"6 件"很可能是干跑 drawn（入画绘制件数）而非总件数，但报告未区分二者口径，读者会误读。建议明确标注"总件数 / 入画件数"。

3. 【非缺陷，仅记录证据的天花板】run-summary.md 与 run_ab.py 自身格式化器逐字节同一，可证"这份记账与工具输出格式完全自洽且未经人工二次编辑"，但按构造无法排除"rows 被伪造后过一遍格式化器"这一极端情形。真正的终局证据（4 张出图与引导图）因 PIPL 被有意不入库，报告 §9(:189-191) 已明写此取舍。我认为该取舍正当（PIPL 是项目红线），故不作为扣分项，仅指出可核性的边界所在。

### 未验证项（BLOCKED-NEEDS-USER）

以下三项须用户配合，我不臆测其结果，既未据此判 PASS 也未据此判 FAIL（三项均与 F005 的技术 acceptance 达成无关，前两项在 verifying-1 已记为 BLOCKED，本轮状态不变）：

1. [BLOCKED-NEEDS-USER] 付费出图的预算授权真实性。报告第 4 行与 106d5aa commit message 均称"用户 2026-07-20 授权（relay 单后端 4 图）"，progress.json session_notes 亦记载 Generator 曾向用户提三选项。我无法在仓库内独立验证该授权确实发生。请用户确认。若未发生，属流程问题，需另行处理，与本条技术结论正交。

2. [BLOCKED-NEEDS-USER] 报告 §5 生产只读盘点的测量值本身（7 份 legacy 2 锚点标定、r_guest2 reproj 2353.4px、r_foyer camera_z 399mm、r_garden hfov 3.5°/156mm），以及 §1 中"D 户型生产家具 57 件""live 场景照片 3548aa76….jpg"等生产侧数值——需 deploysvr 只读访问，未获授权。我只能确认门的条件成立（perspective.py:587 门为 [800,2200]mm，399mm 必然在门外），不能确认测量值本身。

3. [BLOCKED-NEEDS-USER] 报告 §2/§3 中付费臂的目视判定（"落位是否跟随引导""L1 沙发保持单件 L 形""模型静默丢弃坏引导"）——4 张出图与 4 张引导图按 PIPL 红线未入库，已随沙箱销毁，无法由任何第三方直接复核。我只独立复现了其中不依赖付费出图的那一半（干跑引导图两臂同等崩坏，见 evidence §4）。若用户认为 §4"auto_check 判反"这一将进入 b4 的产品缺口需要更强证据，可在 b4 补跑并保留纯文本记录（本轮已开此先例）。

【须传达给 F006 的口径（不阻断本条）】handoff 写"L2 前提已被 F005 推翻"，而报告 §5(:97) 自己写的是"该前提仍未验证，Evaluator 必须实测"。以报告措辞为准：**未验证**。r_foyer 的存档标定是门禁上线前 legacy 2 锚点专家模式，它不过门推不出"用 b1/b2 新特征点模式重标也会失败"。F006 既不得因 calib=True 判其成功，也不得因该存档不过门而预判 FAIL。

---

## F003 — PASS

### 描述

F003「特征供给稳健化（结构角优先，窗特征按 wtype 置信度降级/可跳过）」在 fix_round 1 之后**未被任何修复回归**，acceptance 逐条重判仍全部满足，维持 PASS。

复验口径说明：F003 上一轮即 PASS，本轮唯一任务是核查它是否被 F001/F002/F004/F005 的四条修复回归。真正的回归向量只有一条 —— F004 的修复 fe1b7bf **删除了 F003 自己写的 `byPriority` 比较器**，把轮候排序换成了新模块 `apps/web/src/lib/calibration/featureQueue.ts` 的 `orderFeatureQueue`（新增次级键「地面点先于异面点」）。我用真实后端派生数据 + HEAD 真实前端模块实跑核查了 F003 的四条契约，全部保持。

一、后端实现零改动（硬证据，非叙述）
AST 逐函数对照 459c438(F003 本体) vs HEAD：`derive_features` identical=True，`_with_tier` identical=True；`_KIND_TIER` 常量块 diff 为空。459c438..HEAD 之间 calib_features.py 只有 `degeneracy_reason` 与新增 `is_coplanar_across_heights` 变更（F001 修复），二者不在 F003 派生链上。main.py 的 F003 唯一消费者（:1364 `derive_features` → :1365 `return {"features": feats,...}` 原样透传）在 459c438..HEAD 的 diff 中未出现。

二、F004 修复对 F003 契约的影响（实测，非推断）
新比较器首要键仍是 `a.priority - b.priority`（featureQueue.ts:38），「地面先于异面」只在同 priority 内生效，故 structural(0) → opening(1) → uncertain(2) 的分级次序不变。我把 20 个真实房间的派生特征喂给 HEAD 的真实模块（node --experimental-strip-types 直接 import featureQueue.ts），四条断言全过：(A) priority 单调不减；(B) 全部 optional 窗点排在全部非 optional 之后；(C) MIN_POINTS=4 预算内的 head4 在每一个房间都是 4 个 `wall_corner`/tier=structural/optional=false；(D) 每个异面点的地面孪生必在其之前（F004 修复项）。输出末行 `ALL CHECKS PASSED`。

三、修复本身是否引入新缺陷（几何侧对抗核查）
F004 的重排把出厂首 4 点从「4 个天花板角 z=2700」换成了「4 个地面墙角 z=0」——两者都是同高共面点集，我实测确认没有变差：`degeneracy_reason` 对 NEW/OLD 两种出厂首 4 点的拦截结果完全一致（20 房间中同为 1 间 r_liveext 被拦，文案同为「都在地面且接近一条线」）；用项目自己的相机模型做蒙特卡洛回带解算，NEW 不劣于 OLD。

四、非阻断观察（均不归咎 F003，见 new_issues）
`scripts/check/feature-queue-order.ts` 是目前唯一守住 F003 前端 priority 契约的自动化闸门，但未接 CI；另有三条路径超出 batch_scope.allowed_paths。两者都属 F004/F002 范畴，不影响 F003 判定。

### 复现步骤

全部在 /Users/yixingzhou/project/grandtianfu (HEAD 7a868c1) 执行：

# 1. 两套 pytest + golden 逐字节 + F003 自身测试
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q -rs
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs
PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -k baseline_byte_for_byte -v
PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests/test_calib_features.py -q -k "tier or derive"

# 2. F003 实现零改动（AST 对照 F003 本体 commit）
git show 459c438:apps/api/aigc/calib_features.py > /tmp/f003_cf.py
python3 -c "
import ast
f=lambda p:{n.name:ast.dump(ast.parse(ast.unparse(n))) for n in ast.walk(ast.parse(open(p).read())) if isinstance(n,ast.FunctionDef)}
a,b=f('/tmp/f003_cf.py'),f('apps/api/aigc/calib_features.py')
print('derive_features',a['derive_features']==b['derive_features'])
print('_with_tier',a['_with_tier']==b['_with_tier'])
print('differing:',sorted([k for k in set(a)|set(b) if a.get(k)!=b.get(k)]))"

# 3. 真实几何导出（供第 4 步的前端模块消费）
PYTHONPATH=packages/floorplan_core:apps/api python3 -c "
import json; from aigc import calib_features
G=json.load(open('data/projects/D/baselines/v1/geometry.json'))
out={r['id']:calib_features.derive_features(G,r['id'])[0] for r in G['rooms']}
open('/tmp/feats.json','w').write(json.dumps({k:v for k,v in out.items() if v}))"

# 4. 用 HEAD 真实前端模块核查 F003 四条契约（priority 单调 / optional 垫底 /
#    head4 全 structural / F004 孪生序），脚本见 scratchpad/f003check.ts
node --experimental-strip-types <scratchpad>/f003check.ts        # 期望末行 ALL CHECKS PASSED
node --experimental-strip-types scripts/check/feature-queue-order.ts  # 期望 PASS 4 条断言

# 5. 重排是否引入几何回归（NEW vs OLD 出厂首 4 点）
#    对每房间分别按 (priority, 地面先, planId, id) 与 (priority, id) 取 head4，
#    喂 calib_features.degeneracy_reason 比较拦截数 -> 期望 1/1 (同为 r_liveext)

# 6. 静态门
cd apps/web && npx tsc --noEmit
cd apps/web && npx next lint --file src/components/studio/real-render/FeaturePointCalibrator.tsx --file src/lib/calibration/featureQueue.ts --file src/lib/studioApi.ts
python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py apps/web
git show dc9787f:apps/api/main.py > /tmp/base_main.py && python3 -m ruff check --isolated --select I /tmp/base_main.py   # 基线同样 I001:9 -> 非本批

# 7. 红线
git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ apps/api/aigc/perspective.py   # 期望全空
git log --format='%h %s' dc9787f..HEAD | grep -o "calib-cure-b3-F[0-9]*" | sort | uniq -c        # tag 映射

### 证据

全部命令在 /Users/yixingzhou/project/grandtianfu (branch feat/calib-cure-b3, HEAD 7a868c1) 下由我亲自执行。

【1. 两套 pytest + golden 逐字节（实跑数字）】
- `PYTHONPATH=packages/floorplan_core:apps/api python3 -m pytest apps/api/tests -q -rs` -> `438 passed in 21.45s`（0 skip）
- 排除同侪 evaluator 的探针复跑：`... --ignore=apps/api/tests/test_zz_reverify_f001_probe.py` -> `438 passed in 17.39s`（同数，证明 438 非探针灌水；437→438 的 +1 来自 F001 修复新增的 test_facing_wall_reason_requires_conjunction_not_geometry_alone）
- `PYTHONPATH=packages/floorplan_core python3 -m pytest packages/floorplan_core/tests -q -rs` -> `154 passed in 0.76s`（0 skip）
- golden 逐字节（只本地能跑）：`... -k "baseline_byte_for_byte" -v` -> `2 passed, 152 deselected`，来自 test_render_snapshot.py，**passed 非 skipped**
- F003 自身测试：`pytest apps/api/tests/test_calib_features.py -k "tier or derive"` -> `6 passed, 15 deselected`（含 test_derive_features_tiers_structural_first_and_downgrades_windows / test_derive_features_tier_fields_present_on_every_feature 两条 F003 新测 + 4 条既有 derive 测试）
- `git diff 459c438..HEAD -- apps/api/tests/test_calib_features.py` 显示只有 test_degeneracy_reason_detects_facing_wall_coplanar 被改名/重写（F001），F003 的两条测试逐字未动

【2. F003 实现零改动（AST 对照）】
`git show 459c438:apps/api/aigc/calib_features.py` 抽出后 ast.unparse 逐函数比对 HEAD：
  derive_features: F003commit==HEAD -> True
  _with_tier:      F003commit==HEAD -> True
  funcs differing since 459c438: ['degeneracy_reason', 'is_coplanar_across_heights']
`diff <(grep -A20 _KIND_TIER 459c438版) <(grep -A20 _KIND_TIER HEAD)` -> 无输出（identical）

【3. 真实几何实算（只读 data/projects，未写）】
`PYTHONPATH=... python3 -c "derive_features(v1_geometry, rid) for 20 rooms"`，并在脚本内断言 wall_corner/ceiling_corner==(structural,0,False)、window_floor/window_head==(uncertain,2,True)、id 序==sorted(id)：20 房间全过，数字与上一轮报告逐项一致 ——
  r_guest2 n=14 optional=0 / r_foyer n=32 optional=0 / r_garden 16(8) / r_vest 20(4) / r_balc 12(4) / r_liveext 16(8) / r_bed_g 16(6) / r_bath_g 18(6) / r_master 18(6)，其余 11 间 optional=0

【4. F004 新排序对 F003 契约的实测（真实模块 + 真实数据）】
脚本 /private/tmp/claude-501/.../scratchpad/f003check.ts 直接 `import { orderFeatureQueue, isElevated, planId } from 'apps/web/src/lib/calibration/featureQueue.ts'`，喂 20 房间真实派生特征：
  每行形如 `r_master: n=18 head4=[wall_corner(z=0) x4] optionalRange=[12,17]`
  20/20 房间 head4 全为 wall_corner(z=0)，optional 区间恒为队尾连续段
  末行 `ALL CHECKS PASSED`（priority 单调 / optional 垫底 / head4 全 structural / 孪生序 四类断言零失败）
`node --experimental-strip-types scripts/check/feature-queue-order.ts` -> `PASS feature-queue-order (12 个特征, 4 条断言)`，轮候序 `corner:x4 -> ceilcorner:x4 -> door:d1:a -> doorhead:d1:a -> window:w1:a -> winhead:w1:a`（其断言 2/3 正是 F003 契约：priority 首要键 + 存疑窗点垫底）

【5. 重排未引入几何回归（对抗核查）】
(a) 出厂首 4 点退化对照：对 20 房间分别用 NEW(HEAD 比较器) 与 OLD(F003 原 byPriority) 取 head4 喂 `calib_features.degeneracy_reason` ->
    `rooms whose default first-4 是退化(NEW/OLD): 1 / 1`，同为 r_liveext，同一条文案。
(b) 回带解算蒙特卡洛（项目自身 perspective.Camera 模型，f∈[1100,1900] z∈[1200,1700] pitch∈[-5°,20°] 随机机位，只统计 4 点全在画幅内的试次）：
    NEW trials=17 ok=13(76.5%) medPosErr=1mm p90=2mm
    OLD trials=15 ok= 9(60.0%) medPosErr=0mm p90=7084mm
    结论：NEW 不劣于 OLD。**诚实边界：in-frame 试次仅 17/15，n 小，此项只作方向性非回归信号，不作为改善主张。**

【6. F003 前端交付物在 HEAD 仍在位（读文件:行号）】
- FeaturePointCalibrator.tsx:343-348 分级 banner「候选已按可靠度排序… 墙角与天花板转角最可信,优先点它们… 标「辅助·可跳过」的窗框点…直接跳过即可」，仍在 `features.length >= MIN_POINTS` 同一条件下（:335）
- FeaturePointCalibrator.tsx:395-399 `{currentTarget.optional && <Badge tone="amber" size="xs">辅助·可跳过</Badge>}`
- FeaturePointCalibrator.tsx:429-431 `{currentTarget.caveat_zh && ... ⚠ {currentTarget.caveat_zh}}`
- studioApi.ts:319-323 tier/priority/optional/caveat_zh 类型契约原样
- main.py:1364-1365 端点原样透传 feats（tier 字段可达前端）

【7. 静态门】
- `cd apps/web && npx tsc --noEmit` -> `tsc exit=0`（无输出）
- `npx next lint --file FeaturePointCalibrator.tsx --file ShootingGuideDiagram.tsx --file featureQueue.ts --file studioApi.ts` -> `✔ No ESLint warnings or errors`
- `python3 -m ruff check apps/api/aigc/calib_features.py apps/api/tests/test_calib_features.py apps/web` -> `All checks passed!`
- main.py 那条 I001：按要求用对照法核查 —— `git show dc9787f:apps/api/main.py` 存盘后 `ruff check --isolated --select I` 同样报 `I001 ... base_main.py:9:1`，与 HEAD 的 1 条同址同码，**属既有基线，非本批新增**

【8. 红线核查】
- `git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/` -> 空
- `git diff --stat dc9787f...HEAD -- apps/api/aigc/perspective.py` -> **空**（perspective.py 全批未被触碰）
- 门未放宽：perspective.py:585-588 `CALIB_MAX_REPROJ_PX=50.0 / CALIB_GOOD_REPROJ_PX=25.0 / CAMERA_Z_RANGE_MM=(800,2200) / HFOV_RANGE_DEG=(35,110)` 逐字未动；main.py 新增 `_facing_wall_reason` 只做 `q = {**q, "reasons": q["reasons"] + [facing]}`（main.py:1197-1199），**不改 ok/level**，非放宽亦非新增门
- b2 解算内核 AST 对照 dc9787f：solve_pnp / _solve_pnp_general / _refine / _pose_known_K / _project3 / _rodrigues 全部 `identical=True`
- 铁律 10：`git log dc9787f..HEAD` 的 commit tag 计数 F001x2 / F002x2 / F003x1 / F004x2 / F005x2，全部映射 features.json 现存条目
- 我未修改任何产品代码，未在仓库落任何文件（`git status --short` 仅剩会话前既存的未追踪文档 + 同侪 evaluator 05:50 落下的 test_zz_reverify_f001_probe.py，后者非我所写）

### 修复是否引入新问题（new_issues）

F003 本身未引入新缺陷。以下两条是我在核查 F003 回归面时顺带发现的，**均不归咎 F003，不影响其判定**，报给编排者按铁律 10 挂对应 feature 号处理：

1.【non-blocking，归属 F004】`scripts/check/feature-queue-order.ts` 未接入任何自动化管道。实证：`grep -rn "feature-queue-order" .github/ apps/web/package.json .git/hooks/` **无任何命中**。它目前是唯一守住 F003 前端 priority 分级契约（其断言 2「置信度分级仍是首要键」、断言 3「存疑窗点仍垫底」）与 F004 孪生序的闸门，却只能人工 `node --experimental-strip-types` 手跑。F003 的后端契约有 pytest（CI 内跑）兜底，前端那一半没有 —— 下次有人再动比较器，红了也不会有人知道。建议 b4 把它挂进 `.github/workflows` 或 apps/web `package.json` scripts。

2.【non-blocking，归属 F002/F004，且早于本轮修复】batch_scope.allowed_paths 漂移。`git diff --name-only dc9787f...HEAD` 显示三条路径不在 progress.json.batch_scope.allowed_paths 声明范围内：
   - `apps/web/src/lib/calibration/featureQueue.ts`（新增；allowed_paths 只列了 `apps/web/src/lib/studioApi.ts` 单文件）
   - `scripts/check/feature-queue-order.ts`（新增；allowed_paths 只列了 `scripts/spike/`）
   - `apps/web/src/components/studio/baseline/BaselinePhotosCard.tsx`（allowed_paths 只列了 `.../studio/real-render/`；该文件在 F002 原始 commit c0687de 即被触碰，非本轮新增）
   三处改动内容本身与各自 feature 目标一致、无夹带，属声明范围未随实现方案更新，不是越界写红线目录（data/ 与 packages/floorplan_core/ 净 diff 均为空）。建议收口时补记 batch_scope 而非事后追认。

【环境干扰记录，非产品问题】同侪 evaluator 在我验收期间向工作树落了 `apps/api/tests/test_zz_reverify_f001_probe.py`（05:50 出现，非我所写）。我用 `--ignore` 复跑确认与全量跑同为 `438 passed`，故 438 这个数字不受其影响。我未触碰该文件，也未在仓库落任何产物。

### 未验证项（BLOCKED-NEEDS-USER）

[BLOCKED-NEEDS-USER] F003 自身的 acceptance 全部为 L1（派生层逻辑 + pytest + 静态门），已在本地实测完毕，**无阻塞项影响本次 PASS 判定**。以下与 F003 相关但归属 F006(L2) 的条目，因真实浏览器人工操作仍未获用户当面配合，我未验证、也不臆测其结果：

1. spec §4.2(c)「窗几何失配不再产生无对应物的必点项」的目视确认 —— 需真实浏览器确认「辅助·可跳过」徽章（FeaturePointCalibrator.tsx:395-399）与 caveat 文案（:429-431）在标定页实际渲染、「跳过此特征」按钮对 optional 点确实可用、用户不再被迫瞎点。我只能静态确认渲染分支与类型契约正确，无法替代目视。

2. 上一轮报告已提出、本轮我实算复核仍然成立的取样前提：**F006 若沿用 acceptance 点名的 r_guest2 / r_foyer 做第 1 项，会得到空验证** —— 这两间实算 optional=0（无 wtype=='full' 的窗），屏幕上根本不会出现任何「辅助·可跳过」点。可真实行使该项的房间是 r_garden(8)/r_liveext(8)/r_master(6)/r_bed_g(6)/r_bath_g(6)/r_vest(4)/r_balc(4)。

3. F004 修复后出厂首 4 点由「天花板角」变为「地面墙角」，其对**真实用户点选体验**的影响（是否更易找、孪生提示是否真的在第 5 点起可见）未经真人操作验证。我只在合成相机与真实几何上验证了几何不劣化（n 小，见 evidence 第 5 条）。


---

# 复验轮 2（fix_round 2 之后）

## F002 — PASS

### 描述

原缺陷真实消失且未引入新缺陷。按上轮判据自行构建 CSS 产物核验(未只读源码写法): 组件全部 33 个类 100% 生成 CSS, 0 MISS; emerald/rose 在构建产物与组件源码中均出现 0 次。真实无头浏览器双主题计算样式实测: 视锥半透明生效、两面墙高亮线可见(上轮为 stroke:none)、好坏配色成立(上轮 figcaption 均为白色); 截图目视确认『两面墙 vs 一面墙』视觉区分已恢复。修复只动 1 文件 9 行纯配色, 未碰后端硬门/data//floorplan_core。acceptance 12 条全条满足。

### 证据

CSS 产物 176254 bytes, TOTAL 30 MISS 0; .fill-green-500\/20 -> fill: rgb(34 197 94 / 0.2); .dark\:fill-green-400\/25:is(.dark *) -> rgb(74 222 128 / 0.25); .stroke-green-600 -> #17ad37。根因确认 tailwind.config.js:150 colors 位于 theme 下(非 theme.extend)整表覆盖, emerald/rose/sky 不存在。浏览器 LIGHT: 高亮 line stroke rgb(23,173,55)(上轮 none), figcaption rgb(21,128,61)/rgb(185,28,28)(上轮均白); DARK 全部成对生效。回归: apps/api 438 passed 0 skip; floorplan_core 154 passed 0 skip; git diff --stat dc9787f...HEAD -- data/ packages/floorplan_core/ 空; f945fc8 = 1 file 9+/9-; tsc EXIT=0; next lint 三个 F002 文件无告警; commit tag 映射 F002(铁律 10)。

### 修复是否引入新问题（new_issues）

均 non-blocking 且经基线归属核实无一由本次修复引入: (1)**同根因缺陷在别处仍在(建议 b4 最高优先)**: bg-emerald-500/text-emerald-500/ring-rose-500 在 4 处仍生成 0 条 CSS —— FeaturePointCalibrator.tsx:462 与 :520 的**特征点序号徽章**(bg-emerald-500 + text-white, 背景不生成 -> 浅色主题下白字近乎不可见)、CalibrationMiniMap.tsx:211、PerspectiveCalibrator.tsx:505、admin kanban page.tsx:182。基线计数与 HEAD 一致=既有; 但与 F002 同根因且就在同一标定 UI 上, 建议一并清理并加调色板守门(本批教训: 合规只看写法不看产物)。(2) text-gray-500(#B5BED9) 对白底 1.85:1 低于 WCAG AA, 但该 token 在 studio 组件中用了 40 处, 属项目级既有约定。(3) 特征点不足 MIN_POINTS 时标定入口 banner 不显示, 用户拿不到拍摄引导(上传入口仍覆盖)。(4) scripts/check/feature-queue-order.ts 不在 batch_scope.allowed_paths 内(该表列了 scripts/spike/ 无 scripts/check/) —— 属 F004, 备案。

### 未验证项（BLOCKED-NEEDS-USER）

(1)[L2] BLOCKED-NEEDS-USER: **标定入口那一份示意图从未经浏览器验证** —— 仓库 seed data/projects 照片数=0, data/uploads 不存在(PIPL gitignored), 故 FeaturePointCalibrator 在自动化沙箱中结构性不可达; 已验证代码路径可达 + 配色为全局 CSS 必然继承(上传入口已实测), 真实照片下目视需用户配合。(2)[L2] 引导文案与示意图是否被用户读懂、是否真的改变拍摄行为(acceptance 实效目标), 非计算样式可判定。(3)[L2] F006 全部真实浏览器项仍未获配合。
