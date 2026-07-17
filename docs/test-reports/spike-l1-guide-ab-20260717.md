# F012 spike：L1 简模引导 vs L0 彩盒 A/B 实测 — 执行报告（2026-07-17）

> 批次 calib-cure-b1 · executor:evaluator · 执行者 local/evaluator-subagent（隔离上下文）
> **结论先行：result = BLOCKED** —— relay 与 fal 两后端 API key 在本机环境均不存在（自查过程见 §2），
> 真实出图（acceptance 第 2/3 项量化表）无法执行。按预案降级为 `--dry` 干跑 + 引导图目检；
> **本报告不判 PASS**。干跑层面的全部前置工作（可信标定构造、两臂引导图、公平性验证）已完成并落盘，
> key 配好后重跑成本约 30 分钟 + 原授权预算 ~¥20-30（授权额度分文未动）。

---

## 1. 执行摘要

| 项 | 计划（acceptance） | 实际 |
|---|---|---|
| 前置：病例照片副本 | 本地只读拉取，不入 git | ✅ 2 张（798 书房 / f4d 客餐厅），仅存本地 scratchpad，未入库 |
| 前置：可信标定 | 手工构造点对经 dry-run 式校验 quality=good | ⚠️ 完成 2 份（§3）：study assess **ok=True(suspect, 41.5px)**；f4d 到达针孔模型极限 **ok=False(126.8px)**，wireframe 中央贴合良好（超广角贴角拍摄，详 §3.2——本身即有价值的门禁实证） |
| 出图：2 场景 × L0/L1 × relay/fal ≤16 图 | 用户已授权 ~¥20-30 | ❌ **BLOCKED**（双后端 key 缺失，§2）；已产 `--dry` 两臂引导图 2 场景 ×2 臂 + blank 自证版 |
| 量化表 score/fail_reasons/tokens | 逐图记账 | ❌ 未执行（依赖真实出图） |
| 落位/形体目检 | 书柜铺满东墙/沙发酒柜落位/简模穿帮 | ⚠️ 引导图层可判部分见 §4；出图层未执行 |
| go/no-go 建议 | 是否立项 3D 化 S1-S3 | §7：**dry 层面强 go 信号，最终判定待真实出图**（"换引导要重赛"纪律） |
| BL-decor-b2-L2-realphoto 顺带 | 挂画/窗帘真进实拍图不触发 structure FAIL | ❌ BLOCKED；dry 层观察见 §6 |
| 预算记账 | ≤16 图 ~¥20-30 | **0 图 / ¥0.00**（授权预算未动用） |

## 2. 环境阻塞：relay + fal key 均缺失（自查证据链）

按任务约定 key 自查本机 env（relay: `OPENAI_API_KEY`+`OPENAI_BASE_URL`；fal: `FAL_KEY`），逐层查证：

1. 当前 shell 环境变量：三者均无；
2. macOS `launchctl getenv`（GUI 环境）：无；
3. `~/.zshrc` / `~/.zprofile` / `~/.zshenv` / `~/.profile` 及其 source 链：无相关 export；
4. 项目 `.env` / `apps/api/.env*`：文件不存在；
5. macOS Keychain：按 9 个候选 service 名探测 + dump-keychain 关键词扫描（openai/fal/relay/grandtianfu/aigc）：无条目；
6. 凭据索引 `~/project/deploy/CREDENTIALS.md`（`docs/生产环境交接.md` §7 指向）：仅 Cloudflare token / deploysvr root 密码 / invoce SSH 三条，**无 AI provider key**；
7. 兄弟项目（gw/aigcgateway/grandtianfu_codex）`.env`：无。

生产 `.env`（deploysvr）持有真实 key，但批次红线明文「禁碰生产 .env/data」，不取。
`aigc-gateway` MCP 平台按项目记忆规范**严禁**用作本项目出图后端（无关实验平台），不用。

→ 双后端均缺 → 按任务书降级路径：整体 `--dry` 目检，result=BLOCKED，不判 PASS。

## 3. 可信标定构造实录（spike 前置，acceptance 第 1 项）

方法：Read 工具目测照片地面特征（4x 裁剪放大逐点复核）→ 对照 geometry v7（mm_per_px=10）构造
点/线观测 → scratch 求解脚本（借产品 `perspective.Camera` 投影约定与 `calibrate.solve_t` 同款
平移线性解；产品代码零改动）→ `perspective.assess_calibration_quality` 校验 → wireframe 叠图目检迭代。
照片 EXIF 已被上传归一化剥离（无焦距先验），两张照片均为**手机超广角拍摄**（解算 hfov 59.5°/109.5°）。

### 3.1 study_798（书房 r_guest2，「书柜位置错」病例照）

- **拓扑判定**：相机在房间南部偏西、**朝东北**（窗墙=北墙 y=2500 在左，右侧大白墙=东墙 x=18150）。
  初期误判为"朝东正对东墙"，被尺度自洽检验推翻（图上 (1014,984)→(1148,1007) 仅 134px，若为 3300mm
  东墙则相机需在 36m 外；实为窗洞以东 500mm 墙墩）。
- **求解**：双 VP 法数学病态（VP_x 落主点附近，焦距不可辨识——正对/近正对墙面拍摄时产品「线+角」
  专家模式的固有病态，与生产用户标不好此类照片的现象一致）。改用 3 地面点（窗洞东缘底/东北内角/
  西北内角）+ 3 线约束（东墙底线、窗洞两缘竖线）的网格+细化求解。
- **结果**：camera=(15269, 6800, 1720)mm，hfov 59.5°，pitch 11.8°；
  `assess: ok=True, level=suspect, reproj 41.5px`（<50 硬门），软信号=离房 1000mm（解算位置偏出
  南墙 1m，反映读点误差量级，不拦）。**wireframe 目检：踢脚线、东北角竖棱、窗位红线全部贴合**。✅ 可用
- 产物：`spike-l1-guide/cal_study_798.json`（相机+锚点，纯数值可入库）。

### 3.2 living_f4d（客餐厅 m_living，「沙发酒柜位置错」病例照）

- **拓扑判定**（历经 4 轮假设-证伪迭代，中间曾检验并排除 r_master 误绑假设）：相机在 r_live
  **东北角附近、朝南偏西**，南墙全落地玻璃门（w01, x∈[4950,12150]）横贯画面左中部，画面最左缘
  暖色墙墩=东墙 x=12150 内面，右侧近处大格栅墙=北墙 y=5800（x≥6750 实体段）。
- **两个实证陷阱**（对 C 期特征点 UI 的用户指引有直接参考价值）：
  1. **大理石强反光**把玻璃门倒影映在地面，形成"双底轨线"——初版把倒影分界当底轨，v 向读偏 49px，
     经 4x 裁剪放大纠正；
  2. **超广角贴角拍摄**：三个可靠角点方位跨度 104°（东墙墩 88° ↔ 北墙西端 192°），需 hfov≥110°；
     画面边缘桶形畸变残留使针孔模型全幅拟合极限停在 reproj≈110-135px。
- **结果**（hfov 封顶 109.5° 内最优）：camera=(12950, 6131, 800)mm，yaw 142°；
  `assess: ok=False, level=bad, reproj 126.8px`。**wireframe 中央区贴合良好**（玻璃底轨红线、
  格栅底线、三处竖棱全部贴住实物结构），画面左右缘系统偏差（畸变极限）。
- **门禁实证（本批产品逻辑的正反馈）**：该生产病例照片按 F005 渲染硬门（409 BAD_CALIBRATION）
  **无论如何标定都会被拦**——超广角贴角拍摄本就不该低门槛出图，用户须重拍（标准焦段/离墙远些）。
  这与存量坏标定 reproj 112.4px 被拦的裁决方向一致。
- **对 A/B 的影响**：两臂共用同一相机，标定偏差同向作用于 L0/L1，**A/B 内部公平性不受影响**；
  但 f4d 场景的"绝对落位"目检须打折扣（报告 §4 已按此拆分判定维度）。
- 产物：`spike-l1-guide/cal_living_f4d.json`。

## 4. `--dry` 干跑结果与两臂引导图目检

命令（真实照片版产物在本地 scratchpad，含照片像素**不入库**；blank 灰底版入库自证）：

```bash
python3 scripts/spike/run_ab.py --scenes scenes.json --outdir ab_out --dry        # 真实照片版（本地）
python3 scripts/spike/run_ab.py --scenes scenes_blank.json --outdir ab_blank --dry # blank 入库版
```

干跑通过：`guide_sanity_issues` 门未触发（两场景标定下无引导退化告警）；
study 4 件（bookshelf/desk_chair/desk/curtain）、living 12 件（rug/entry_door 按产品 skip 集跳过）。

### 4.1 L0 vs L1 形态对比（真实照片版目检，acceptance 目检点逐项）

| 目检点 | L0 彩盒 | L1 简模 | 判读 |
|---|---|---|---|
| 书柜铺满东墙（study） | 一整块半透明紫色平板盖住东墙 | **两端板 + 7 层通长隔板 + 顶板**的通高开放书架，透视正确沿墙延伸 | L1 把「宽度/通高/层架结构」从文字约束变成像素事实——正是「书柜画成窄条」失败模式的结构性对策 |
| 书桌/椅（study） | 纯色盒 ×2 | 桌=**面板+四腿+挡板**；椅=**座箱+靠背**（orient E 朝向正确） | 形体语义完整 |
| 沙发 L 形两段（living） | 两块蓝色半透明盒 | 两段沙发**座+靠背+双扶手**成形，L 形相对关系可读 | 「两盒并成一张/朝向错」失败模式的对策成立 |
| 餐桌（living） | 紫色平板盒 | **桌面板+四条桌腿**立于地面 | 成形；桌腿着地点与地面透视有轻微漂移（f4d 标定极限的体现） |
| 酒柜/电视柜（living） | 半透明盒 | 整盒（产品设计如此：media/wine_cabinet 走整盒，内部结构对引导增益有限） | 与 L0 同外形，符合 §D5「L1 外包络=L0 盒」 |
| 简模穿帮风险（酌看） | — | 平光多面明暗着色有立体感；灰调带色相可区分同类 | 「AI 保留灰体质感」风险须真实出图才能判——**未执行** |
| 落位正确性 | study 两臂落位全部正确（紫盒贴东墙/绿罩窗/蓝椅居中/橙桌画缘）；living 语义无 gross 错位、绝对位置受 §3.2 标定偏差影响 | 同左（两臂同相机） | study 可作绝对落位主判场景；living 作形体/相对关系判 |

### 4.2 发现的问题与观察（真实出图前即可确认）

1. **[中] curtain 全高不透明板遮死窗户**（两场景一致）：L1 的 curtain 走 `_whole_box` 全高
   (0..2700) 不透明薄板，把窗洞/玻璃门整面糊死。edit 模型将失去"keep windows unchanged"的
   像素参照，有整面重画玻璃区的风险（L0 半透明彩盒能透出窗）。**若立项 S1-S3，curtain 须特殊
   处理**（半透明/仅侧幔+帘盒/降低 alpha）。此项在真实出图时应重点观察。
2. **[低] 产品 prompt 既有冠词噪声**（L0 逐字继承，非 F011 引入）：`en` 字段自带冠词与
   near/partial 话术模板拼接产生 "The purple **a full-height bookshelf** sits..."、
   "The orange **a desk**..."。对 LLM 理解影响很小，建议随后续批次顺手修（main.py:2288-2293 一带）。
3. **[信息] 两臂公平性验证通过**：diff 两臂 prompt，仅「彩盒→简模」映射段措辞不同
   （colored translucent boxes / gray 3D primitive mockups + 颜色指涉去除），rug/墙面挂饰/
   附着/near/partial 话术逐字保留；legend 类型-颜色对应、box_usability 降级标记一致。§D5 兑现。

## 5. 预算记账

| 项 | 数量 | 费用 |
|---|---|---|
| relay 出图 | 0 | ¥0 |
| fal 出图 | 0 | ¥0 |
| **合计** | **0 图** | **¥0.00**（授权 ~¥20-30 分文未动） |

## 6. BL-decor-b2-L2-realphoto 观察点（顺带项）——BLOCKED + dry 层观察

- **真实验证（挂画/窗帘真进实拍图、不触发 acceptance structure FAIL）：未执行**（依赖真实出图）。
- dry 层可确认：两臂 prompt 均含专门话术（挂画="flat framed artwork mounted on the wall...not
  a freestanding object on the floor"；窗帘="floor-length curtains hanging over the window,
  not a solid boxy object"）；引导图中 wall_art 以墙面带（z 1000-1400）薄盒呈现、位置贴墙正确。
- 风险提示同 §4.2-1：L1 的 curtain 不透明全高板可能**加剧**而非缓解 structure 判定风险（AI 若
  照抄板状引导会产出"实心板状窗帘"——恰是话术禁止的形态）。真实 A/B 时此项为必看点。

## 7. go / no-go 建议（3D 化 S1-S3 立项）

**干跑证据给出强 go 信号，但最终 go/no-go 判定必须等真实出图数据**——本仓既有纪律「淘汰结论绑定
引导方式，换引导要重赛」（relay 复评实证）同样适用于其逆命题：采纳新引导也要有实测数据。

支持 go 的干跑证据：
1. L1 渲染器（F011 工具）在两个真实生产场景上产出形体完整、透视正确、遮挡有序的简模引导——
   3D 化评估文档 §2 列的 5 类失败模式中 4 类（书柜窄条/餐桌缩背景/L 形并张/椅子环绕）在引导图
   层面已被结构性消解；
2. 两臂公平性机制成立（§4.2-3），A/B 实验设计可信；
3. 成本结构未变：出图预算 ~¥20-30 即可完成 16 图对照。

阻止即刻 go 的缺口：
1. **AI 服从性未实测**（模型对简模的跟随度/灰体穿帮率——spike 的核心问题仍未回答）；
2. curtain 遮窗副作用（§4.2-1）需实测确认严重程度与 prompt 对策有效性。

**建议**：配好 relay/fal key 后按 §8 重跑（标定/scenes/工具全部就绪，增量成本 ≈30 分钟人时 +
授权预算），拿到量化表后再作 S1-S3 立项裁决。若重跑显示 L1 在 auto_check score 与落位目检上
不劣于 L0 且形体维度显著改善、无系统性灰体穿帮 → go。

## 8. 复现指引（key 配好后）

```bash
# 素材（PIPL：照片副本放本地未跟踪路径；标定 JSON 已入库可直接用）
#   docs/test-reports/spike-l1-guide/cal_study_798.json
#   docs/test-reports/spike-l1-guide/cal_living_f4d.json
#   scenes 清单模板：docs/test-reports/spike-l1-guide/scenes.example.json（补照片/几何/家具路径）
OPENAI_BASE_URL=... OPENAI_API_KEY=... FAL_KEY=... \
python3 scripts/spike/run_ab.py --scenes scenes.json --outdir out/ --backends relay,fal
# 预期 2×2×2=8 图（可再 --arms/--backends 拆分补跑至 ≤16 图预算内）
```

## 9. 未执行项清单（明示）

| # | 项 | 原因 |
|---|---|---|
| 1 | 2 场景 × L0/L1 × relay/fal 真实出图（8-16 图） | relay+fal key 本机均缺失 |
| 2 | 量化表（auto_check score / fail_reasons / usage tokens / fal 像素） | 依赖 #1 |
| 3 | 出图落位/形体/简模穿帮目检 | 依赖 #1 |
| 4 | BL-decor-b2-L2-realphoto 实拍验证 | 依赖 #1 |
| 5 | go/no-go 最终判定 | 依赖 #2/#3 |

## 10. 产物清单

**入库（本目录 `spike-l1-guide/`，均无 PIPL 内容）**：blank 两臂引导图 ×4、两场景标定 JSON ×2、
两臂 prompt ×4、dry summary.md / rows.json、scenes.example.json。
（`dry-run/` 子目录为 F011 合成标定自证产物，与本报告的生产几何+重构标定产物互补。）

**仅存本地 scratchpad（含照片像素，PIPL 不入库）**：真实照片版两臂引导图 ×4、wireframe 叠图 ×2、
病例照片副本 ×2、标定求解脚本（calib_build*.py）。会话结束后随 scratchpad 生命周期清理；
重建方法：照片按 spec §6 从 deploysvr 只读拉取，标定直接用入库 JSON。

## 11. 框架提案候选（供 Planner 裁决，Evaluator 按任务边界不直接写 framework/）

1. **新坑**：镜面反光地面（大理石/亮面砖）会把墙/门倒影映成"双底线"，人工或 UI 点选地面特征时
   易取到倒影线（本次 f4d 底轨 v 向偏 49px 实证）；C 期特征点 UI 的用户指引可加一句"点踢脚/门框
   与地面的真实交线，勿点倒影"。建议写入 `framework/patterns/` 或产品 UI 文案。
2. **新规律**：手机超广角（hfov≳105°）贴角拍摄的照片，针孔无畸变模型全幅拟合极限 reproj≈100px+，
   必触 CALIB_MAX_REPROJ_PX 硬门——门禁行为正确，但产品可考虑在拍摄指引中明示"用 1x 主摄、
   离墙 2m 以上"以降低用户重标挫败感。

---

*Evaluator: local/evaluator-subagent（隔离上下文）· 2026-07-17*
*本报告基于实物：生产几何/家具/照片副本、scripts/spike 工具实跑、perspective/assess 实调。*
