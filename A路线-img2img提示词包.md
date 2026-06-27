# A 路线 · AI 虚拟样板间（img2img）交付包

> 目标：在**真实底图**上摆软装，**不改硬装**，解决"臆造硬装"和"无真实尺度"两大问题。
> 配套底图：文件夹 `A路线-虚拟样板间底图/`（9 张，已按房间命名）。
> **房间命名与功能已对齐定稿平面（`平面布置图.svg`）**：东侧寝区为**书房**(原次卧一)+**次卧二**；**南向景观区(原生活阳台)已与客厅打通为一体**；以下提示词据此调整。

---

## 一、怎么用（按工具）

### 推荐工具（按效果/易用度排序）
1. **Gemini App / "Nano Banana"（Gemini 2.5/3 Flash Image）** ★最推荐
   - 上传对应底图 → 粘贴下方该房间提示词 → 直接生成"摆好家具"的版本。
   - 它是图像编辑模型，天然会保留原图结构，最省事。可多轮对话微调（"沙发换墨绿丝绒""地毯再大一点"）。
2. **虚拟样板间 SaaS**（virtualstagingai.app / applydesign.io / collov.ai 等）
   - 上传底图 → 选"按提示词/风格" → 出图。专为房产软装设计，保结构能力强。
3. **Stable Diffusion + ControlNet**（进阶/可批量）
   - ControlNet 用 **MLSD（直线）+ Depth（深度）** 双控锁结构；
   - **Inpaint 重绘**只圈地面以上的空白区域；**重绘幅度 denoising 0.40–0.55**（越低越保原图）。

### 通用设置原则
- **保结构**：用编辑/inpaint，不要用纯文生图；denoising 控低。
- **同机位**：不要让 AI 改变视角，保持底图透视=保持真实尺度感。
- **一次一个房间**，先出大件（沙发/床），满意后再加饰品。

---

## 二、通用"锁硬装"规则（每条提示词都已包含，附负向词）

**锁定不可改（Keep unchanged）**：地板材质与颜色、墙面材质与颜色、吊顶造型与灯带、门窗位置与黑框、中央空调风口、既有橱柜/石材/木饰面、房间结构与机位透视。

**负向提示词（Negative，通用）**：
```
do not change the floor, do not change flooring material or color, do not change wall color or material, do not move or add or remove windows or doors, do not change ceiling, do not alter room layout or perspective, no extra walls, no renovation of hard finishes, no distortion, no extra rooms, realistic scale
```

---

## 三、各房间提示词（中文版 + English）

### 01 客厅　底图：`01_客厅_…格栅墙+落地窗.jpg`
> 注：客厅与**南向景观区（原生活阳台已打通）**为同一连通空间，沙发组团面向东墙胡桃木影视墙，南窗侧设旋转椅+绿植的景观休闲角。
**中文**：在保持这张照片的洞石纹大理石地面、深胡桃木竖纹格栅墙、白色吊顶灯带、落地窗与城市景观全部不变的前提下，仅在房间内摆放软装：一组焦糖驼色半哑光真皮 L 型沙发（三人位+转角贵妃，面向胡桃木影视墙），米色大理石台面+古铜框的大小双茶几，靠胡桃木墙的低矮电视地柜与超薄壁挂电视，沙发区铺暖灰咖色羊毛地毯；**南窗侧（原阳台并入处）摆一对墨绿丝绒/驼色旋转休闲椅+小圆几+大型绿植，作晨咖赏景角**；古铜大理石落地灯，丝绒与棉麻抱枕、驼色针织盖毯。暖光2700K，杂志级实景摄影，保持原机位与透视。
**EN**: Keep the existing travertine marble floor, dark walnut fluted feature wall, white ceiling with cove lighting, floor-to-ceiling windows and city view EXACTLY as in the photo. Only add furniture: a caramel tan semi-matte leather L-shaped sofa (chaise toward window), a forest-green velvet lounge chair with champagne-gold legs, nested coffee tables with beige marble top and bronze frame, a low TV cabinet against the walnut wall with a slim wall-mounted TV, a warm taupe wool rug under the sofa, a bronze-and-marble floor lamp, velvet and linen cushions, a camel knit throw, a large fiddle-leaf fig plant. Warm 2700K light, photorealistic, same camera angle.

### 02 客餐厅大开间　底图：`02_客餐厅大开间_…灯带.jpg`
**中文**：保持洞石大理石地面、暗藏灯带吊顶、黑框玻璃移门、开放式格局不变；在餐厅区摆放：1800×950 岩板长餐桌+6 把焦糖皮/米绒餐椅（4+2 主人椅），胡桃木+岩板餐边柜，长形古铜艺术吊灯；远处客厅区放置焦糖皮沙发与地毯。暖光，保持原机位透视，实景摄影。
**EN**: Keep the marble floor, cove-lit ceiling, black-framed glass sliding door and open plan unchanged. Add in the dining zone: a 1800×950 sintered-stone dining table with 6 chairs (caramel leather + 2 host chairs in beige), a walnut + stone sideboard, a long bronze art pendant light; in the far living zone add a caramel leather sofa and rug. Warm light, same perspective, photorealistic.

### 03 厨房　底图：`03_厨房_…黑框玻璃门.jpg`
**中文**：保持既有浅灰橱柜、白色石英石台面、黑框玻璃移门、大理石地面、暗藏灯带全部不变；仅增加台面软装小物：成套刀架、香槟金调味罐组、砧板、一束小绿植、防滑地垫。不改任何硬装与橱柜。实景摄影。
**EN**: Keep the existing light-grey cabinets, white quartz countertop, black-framed glass door, marble floor and cove lighting unchanged. Only add countertop styling: a knife block, champagne-gold spice jar set, cutting board, a small herb plant, an anti-slip mat. Do not change any hard finishes or cabinetry. Photorealistic.

### 04 主卧（候选A）　底图：`04_卧室A_暖木地板+角窗….jpg`
**中文**：保持暖橡木地板、米色墙面、落地角窗与栏杆、吊顶不变；摆放主卧软装：1.8m 焦糖色真皮软包大床配宽矮床头板，一对胡桃木+香槟金圆角床头柜，一对古铜暖光床头壁灯，焦糖皮床尾凳，奶咖羊毛地毯，燕麦色长绒棉床品多层叠搭与针织盖毯，角落奶咖单人休闲椅+落地灯+小圆几，陶艺花器绿植。暖光2700K，保持原机位透视，实景摄影。
**EN**: Keep the warm oak floor, beige walls, corner floor-to-ceiling window with railing and ceiling unchanged. Add master-bedroom furnishings: a 1.8m caramel leather upholstered bed with a wide low headboard, a pair of walnut + champagne-gold rounded nightstands, a pair of bronze warm-light wall sconces, a caramel leather bench at the foot, an oatmeal wool rug, oatmeal long-staple cotton bedding layered with a knit throw, a corner lounge chair + floor lamp + side table, ceramic vases with greenery. Warm 2700K, same camera angle, photorealistic.

### 05 书房 STUDY（定稿=书房，原次卧一）　底图：`05_卧室B_暖木地板+落地角窗.jpg`
> 定稿功能为**书房（兼留宿）**：书桌靠北窗、整墙书柜靠侧墙、靠墙双人沙发床、阅读角。
**中文**：保持地板、墙面、落地角窗不变；按**书房**布置：靠窗双人书桌 2050×660+2 把藏木色真皮工学椅，整墙胡桃木开放+封闭书柜，靠墙焦糖色双人沙发床（留宿用），暖灰短绒地毯，台灯与阅读落地灯，奶咖单人阅读椅+小圆几，书籍与艺术摆件、绿植。暖光，保持机位透视，实景摄影。
**EN**: Keep floor, walls and corner window unchanged. Stage as a STUDY: a 2050×660 double desk by the window with 2 walnut-toned leather ergonomic chairs, a full-wall walnut open+closed bookshelf, a caramel leather sofa-bed against the wall (for occasional guests), a warm-grey low-pile rug, a desk lamp and reading floor lamp, a lounge reading chair + side table, books, art objects and plants. Warm light, same perspective, photorealistic.

### 05b 次卧二 GUESTROOM 2（如有第二间卧室底图可复用本提示词）
**中文**：保持地板、墙面、落地角窗不变；按**次卧**布置：1.5–1.8m 软包床（床头靠实墙）+一对床头柜与台灯，南墙整体衣柜，梳妆/书桌靠窗，燕麦色床品叠搭、奶咖地毯、绿植。暖光，保持机位透视，实景摄影。
**EN**: Stage as a guest bedroom: a 1.5–1.8m upholstered bed (headboard against the solid wall) + paired nightstands and lamps, a full wardrobe on the south wall, a dresser/desk by the window, oatmeal bedding, a warm rug and plants. Warm light, same perspective, photorealistic.

### 06 主卫　底图：`06_主卫_…金棕大理石台面+浴缸.jpg`
**中文**：保持微水泥灰墙、金棕大理石双台盆台面、独立浴缸、LED灯镜、灰色地砖全部不变；仅增加软装：成套棉麻浴巾（燕麦色）、石质托盘+扩香、一株散尾葵/龟背竹绿植、防滑地垫、托盘上的香薰蜡烛与护肤瓶器。不改硬装。实景摄影。
**EN**: Keep the micro-cement grey walls, gold-brown marble double vanity, freestanding bathtub, LED mirror and grey floor tiles unchanged. Only add soft items: oatmeal linen towel set, a stone tray with a diffuser, a palm/monstera plant, an anti-slip mat, scented candle and skincare bottles on the tray. Do not change hard finishes. Photorealistic.

### 07 主卧·格栅墙　底图：`07_主卧_奶咖木饰面格栅背景墙.jpg`
**中文**：保持奶咖色木饰面竖格栅背景墙、暖橡木地板、吊顶不变；以格栅墙为床头背景，摆放焦糖皮软包大床、宽矮床头板、一对圆角床头柜与古铜壁灯、焦糖皮床尾凳、奶咖地毯、燕麦床品。暖光，保持机位透视，实景摄影。
**EN**: Keep the cream-beige fluted wood feature wall, warm oak floor and ceiling unchanged. Use the fluted wall as the headboard backdrop; add a caramel leather upholstered bed with wide low headboard, a pair of rounded nightstands with bronze sconces, a caramel leather bench, an oatmeal rug and oatmeal bedding. Warm light, same perspective, photorealistic.

### 08 客厅·景观区（原南阳台，已与客厅打通）　底图：`08_南阳台_…城市中庭景观.jpg`
> 注：此处已**并入客厅**为一体（非独立封闭阳台），按"室内客厅延伸的景观休闲角"布置，材质与客厅连续。
**中文**：保持地面、玻璃栏杆、灰咖墙、城市与中庭景观不变；按**客厅景观延伸角**布置：一对墨绿丝绒/驼色旋转休闲椅+脚凳，小圆茶几，与客厅同系的羊毛/短绒地毯，几盆室内绿植（橄榄树/散尾葵），暖色落地灯，与室内客厅材质色调连续统一。营造晨咖赏景角。保持机位透视，实景摄影。
**EN**: Keep the micro-cement floor, glass railing, greige wall and city/courtyard view unchanged. Add outdoor lounge furnishings: a pair of weather-resistant rattan/aluminium lounge chairs with ottoman, a small round coffee table, an outdoor rug, several weatherproof plants (olive tree/areca palm), a warm outdoor floor lamp — a morning-coffee view corner. Same perspective, photorealistic.

### 09 卫生间（公卫/次卫）　底图：`09_卫生间_微水泥+玻璃淋浴+浴缸.jpg`
**中文**：保持微水泥墙、玻璃淋浴隔断、洁具、地砖不变；仅加软装：浅色棉麻毛巾、置物托盘、小绿植、香薰、防滑地垫。不改硬装。实景摄影。
**EN**: Keep the micro-cement walls, glass shower partition, sanitary ware and floor tiles unchanged. Only add: light linen towels, a tray, a small plant, a diffuser, an anti-slip mat. Do not change hard finishes. Photorealistic.

---

## 四、使用顺序建议
1. 先做 **01 客厅** 与 **07/04 主卧** 两张主图，确认风格方向；
2. 满意后再批量做其余房间；
3. 每张可多轮微调（换色/换款/加饰品），最终用于和客户/施工方沟通。
4. 若某张 AI 仍轻微改了硬装，把"通用负向提示词"整段加到 prompt 末尾，并把 denoising 调更低（0.4 以下）。

> 注：本环境的网关工具不支持传入底图（只能文生图），故 A 路线需在上述外部工具中执行；底图与提示词均已备好，复制即用。

---

## 五、Gemini / Nano Banana 实操步骤（手把手）

> Nano Banana = Google 的 **Gemini 2.5 Flash Image** 图像编辑模型，最适合本任务（天然保留原图结构）。

**入口（任选其一，都需 Google 账号）：**
- **Google AI Studio** `aistudio.google.com` → 新建 Chat → 模型选 **"Gemini 2.5 Flash Image"（Nano Banana）** → 上传底图 → 粘贴提示词。（最推荐，控制力强）
- **Gemini App** `gemini.google.com`（或手机 App）→ 点 **＋ 上传图片** → 选底图 → 输入提示词。（最省事）

**关键：用"编辑指令"措辞，模型才会保留原图。** 每条提示词建议以这句开头：

> 「这是一张室内实景照片。**请保持照片中的地面、墙面、吊顶灯带、门窗与黑框、窗外景观、既有橱柜/石材/木饰面全部不变**，只在房间里**添加/摆放**以下软装家具：……（粘贴该房间的中文提示词）。保持原机位与透视、真实尺度，杂志级实景摄影，暖光 2700K。」

**逐张操作：**
1. 选一张底图（从 `A路线-虚拟样板间底图/`，如 `01_客厅…jpg`）。
2. 上传 → 粘贴上面的开头句 + 对应房间提示词（本文件第三节）。
3. 生成。先只放**大件**（沙发/床/餐桌），满意后再追加饰品。
4. **多轮微调**（直接对话）：如「沙发换成墨绿丝绒」「地毯再大一点、压住沙发」「加一盏古铜落地灯」「灯光更暖」。
5. 若 AI 改了硬装：回复「**你改动了地面/墙面，请还原成原照片的硬装，只保留我要的家具**」，或把第二节《通用负向提示词》整段附在末尾。
6. 满意后下载，按房间命名归档。

**建议顺序：** 先出 **01 客厅** 与 **07 主卧（格栅墙）** 两张主图定方向 → 满意后批量出其余（02 餐厅、03 厨房、05 书房、06 主卫、08 客厅景观区、09 卫生间、05b 次卧二）。

**对照表（底图 → 提示词）：**
| 底图文件 | 用第三节哪条 |
|---|---|
| 01_客厅… | 01 客厅 |
| 02_客餐厅大开间… | 02 客餐厅 |
| 03_厨房… | 03 厨房 |
| 04_卧室A… | 04 主卧（候选A）/ 07 主卧格栅 |
| 05_卧室B… | 05 书房（或 05b 次卧二） |
| 06_主卫… | 06 主卫 |
| 07_主卧_格栅… | 07 主卧·格栅墙 |
| 08_南阳台… | 08 客厅·景观区 |
| 09_卫生间… | 09 卫生间 |

> 备选工具：房产软装 SaaS（virtualstagingai.app / collov.ai 等，上传底图选风格出图）；或 Stable Diffusion + ControlNet（MLSD+Depth 锁结构，inpaint 重绘地面以上空白，denoising 0.40–0.55）。

---

## 六、多角度实景底图（从交付视频补充，覆盖更全）

> 文件夹：`A路线-虚拟样板间底图-多角度/`（19 张，已按"房间-角度-时间码"命名，房间多角度，逐张 img2img 后拼起来≈全屋实景）。原始空间为**毛坯/空房**，img2img 直接往空房里加家具，最干净可靠。

**底图 ↔ 房间 ↔ 提示词 对照：**
| 底图文件 | 房间 | 用第三节提示词 |
|---|---|---|
| 客餐厅_白大理石墙A_48s / B_51s | 客餐厅大开间 | 02 客餐厅（餐厅区按 餐厅 提示，含 3.0×1.1m 长餐桌 8 椅） |
| 客厅_落地窗景观角_93s | 客厅 | 01 客厅 |
| 客厅景观区_南向A_90s / B_12s | 客厅·景观区 | 08 客厅·景观区 |
| 入户花园_15s | 入户花园 | （加绿植景观组合+地灯，硬装不变） |
| 厨房_75s | 厨房 | 03 厨房 |
| 生活阳台_87s | 生活阳台 | （嵌洗烘塔+收纳+晾衣，硬装不变） |
| 次卧二_角A_105s / B_120s / C_126s | 次卧二 | 05b 次卧二 |
| 主卧_角A_159s / B_156s | 主卧 | 04 主卧 / 07 主卧·格栅墙 |
| 主卧衣帽间_168s | 主卧衣帽间 | （U 型衣柜+中岛+穿衣镜+坐凳，硬装不变） |
| 主卫_角A_144s / B_141s | 主卫 | 06 主卫 |
| 公卫_129s | 公卫 | 09 卫生间 |
| 次卧套房_33s | 次卧套房·多功能 | （1.8床/沙发床+影音柜+休闲椅，F01-F03） |
| 次卫_39s | 次卫 | 09 卫生间 |

> ⚠ **书房**：空房状态下与次卧二难以区分，本批 19 张未单独标到清晰的书房角度。两个办法：① 直接复用任一**次卧二/卧室角度底图**，套用 **05 书房** 提示词出图（空房通用，效果一致）；② 若要书房本体角度，告诉我，我再从视频里定位书房时间段补 2–3 帧。
