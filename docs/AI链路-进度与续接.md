# 阅天府 AI 功能链路 — 进度与续接

> 续接文档(2026-06-30)。新会话从这里恢复上下文。配套自动记忆:`~/.claude/.../memory/grandtianfu-ai-pipeline.md`(更细)。**本文不含密钥**(凭据指针见 §6)。

## 1. 一句话现状
把单机原型工具产品化为多用户 SaaS,核心是"户型→多套家具方案→AI 出图"链路。**第 2 步(AI 摆家具多候选方案)与第 5 步(轴测→照片级效果图)均已代码完成并真实上线 design.vpanel.cc**;关键产品约束已落地:**一个户型支持多套候选家具方案,每套方案可独立推进后续编辑/画廊/render 工作流**。第 7 步(空房实拍+多图出图)待建。

## 2. 用户定稿的 7 步工作流 + 状态
| # | 步骤 | 状态 |
|---|---|---|
| 1 | 人工编辑定稿户型图 | ✅ 已有(几何编辑器) |
| 2 | **AI 根据空户型摆放家具** | ✅ **已上线**:LLM 受控选型 + deterministic layout + `/furnish` 异步生成多套 FurnitureScheme;prod 真 relay 冒烟通过 |
| 3 | 人工调整确认家具 | ✅ 已有(家具编辑器),已接入 `scheme_id` |
| 4 | 生成轴测方案图 | ✅ 已有(引擎 photo/shell SVG),已支持按 `scheme_id` 渲染 |
| 5 | **AI 据轴测图→照片级轴测效果图** | ✅ **已上线**(render 页 + /render-ai,prod 真跑通),按 `scheme_id` 归档 |
| 6 | 上传空房实拍照 | 🔨 后端上传端点已就位,前端待建 |
| 7 | **AI 据空房照+轴测方案→实拍效果图** | ⬜ 待建(Phase 4,需用户空房照) |

全程砍掉文生图(户型结构不可控)。所有 AI 出图走 **img2img**。

## 3. 技术决策(已定)
- **出图模型 = `gpt-image-2`,直连 OpenAI 兼容 relay**(网关不支持 img2img)。edits 端点支持多图(第 7 步:空房照+轴测参考)。备胎 fal/Gemini,provider 抽象层不锁死。
- **后端**:FastAPI 单体直接 import floorplan_core 引擎。AI 子系统 `apps/api/aigc/`:config(凭据缺失 ai_enabled=False 不崩主服务)/providers(/images/edits 单·多图)/budget(文件落盘原子预扣释放+张数硬闸)/jobs(进程内异步,生成 90-225s 提交即返 job_id 前端轮询)/artifacts(自托管+防穿越)/records(渲染历史)/raster(svg→png)。
- **生成 = 异步**(单 uvicorn worker,进程内 job;出图 90-225s,摆家具通常更快)。预算护栏 + 产物自托管(/api/artifacts)。
- **提示词**:prompt_gen 自动逐房 + `with_positions`(房内方位,Phase2 默认开;A/B 实测与 baseline 平手、无害)。**底图维持 original**(分类着色经评审否决:致材质偏色)。
- **第 2 步 = 混合**:LLM 选型 + 确定性落位 + 人精修(用户已同意)。LLM 不吐坐标。
- **多候选家具方案 = 核心模型**:Project 只有一份 `geometry.json`;家具升级为 `FurnitureScheme`,每套方案有独立 `furniture.json`/render history/artifacts。AI 摆家具永远创建新候选方案,不直接覆盖当前方案。规格见 `docs/多候选家具方案-实施规格.md`。
- **前端**:Horizon Tailwind React(Next15/React 钉 18.3.1/output:export 路A 静态导出);studio 工作台;同源 /api 不开 CORS;ChakraProvider 全站=0。

## 4. 分支 / 提交
- **Phase 3 运行时代码验证提交 = `9e3aa17`**(prod `.last_good_tag=9e3aa17`;当前 `main` 后续可能有纯文档提交):Phase 1(AI 基础设施)+ 1.5b(提示词方位)+ Phase 2(render-ai + render 页)+ Phase 5(部署接线)+ 多候选 FurnitureScheme + Phase 3(AI 摆家具 LLM/落位生成)+ `CHAT_MODEL`/`IMAGE_MODEL` 分离修正。
- **`feat/ai-furnish` 已合入 `main`**:`feat/ai-furnish` 与 `main` 同步到 `6739c4e` 后,`main` 追加 `9e3aa17` 修正 chat 默认模型。
- 部署模型:**push `main` 即部署**(CI 构建 api/web 镜像→GHCR→SSH VPS deploy.sh 只 pull+up)。**deploy.sh 用 VPS 上的 compose/.env,repo 不自动同步到 VPS**——改 compose/.env/nginx 须手动 SSH 同步。

## 5. 完成情况(Phase 视角)
- **Phase 0** 命门 spike ✅:gpt-image-2 img2img(第5步)+ 多图(第7步机制)真图验证 PASS。
- **Phase 1** AI 基础设施 ✅:`aigc/` 包,40 测试,经 18 项多智能体对抗评审修复。
- **Phase 1.5b** 提示词方位 ✅:opt-in,A/B 平手无害,默认开。
- **Phase 2** 第5步 ✅:`/render-ai`(后端真 relay e2e)+ render 页(build 绿)。**已上线**。
- **Phase 5** 部署 ✅:relay key 注入 prod .env(600)、artifacts/uploads bind 挂载 chown 10001、relay 从 VPS 直连 200 无需代理、nginx 无需改。prod `/api/ai/status` enabled:true,真实在线生成验证通过。
- **Phase 1.5a** 第2步地基 ✅:`floorplan_core/catalog.py`(25 软装件目录+默认外观)+ `room_brief.py`(逐房简报:尺寸 mm/门窗匹配 N·S·E·W 墙/可选家具)。22 测试。
- **Phase 2.5** 多候选家具方案规格 ✅:`docs/多候选家具方案-实施规格.md`。目标:一个 Project 支持多个 `FurnitureScheme`,后续编辑/画廊/render/空房实拍都按 `scheme_id` 推进。
- **Phase 3** 第2步 AI 摆家具 ✅ **已上线并生产真跑通**:后端 `POST /api/projects/{id}/furnish` 异步 job;`aigc.providers.chat_json()` 调 relay chat JSON mode(默认 `CHAT_MODEL=gpt-5.5`,与 `IMAGE_MODEL=gpt-image-2` 分离);`apps/api/furnish.py` 做 room_brief prompt、受控校验、warnings;`floorplan_core/layout.py` 确定性落位;`catalog.expand()` 补外观;前端 `/scheme` 页可输入风格、选择数量/base scheme、生成候选并沿 scheme 进入 editor/gallery/render。
- **生产事故**:画廊全黑(悬挂家具 room_id→render 500)已修(引擎跳过悬挂件 + 数据重映射 r_liveext→r_live)。**线上 D 数据已与仓库分叉(线上 22 房/仓库 20 房),勿假设相等**。

## 6. 凭据 / 访问(指针,**值不在本文**)
- **relay**:OpenAI 兼容,base `https://co.ghgame.cn:18065/v1`,模型 gpt-image-2 + gpt-5.5/5.4。key 在 **本地 scratchpad/ai.env** 与 **prod `/opt/grandtianfu/.env`**(600)。⚠️ **该 key 曾在聊天明文出现,建议轮换**(热替换:`cd /opt/grandtianfu && docker compose up -d api`)。
- **SSH VPS**:当前本机可用 `ssh aigc-prod`(tripplezhou@34.180.93.185,key `~/.ssh/id_ed25519`,nopasswd sudo + docker 组);旧记忆可能写 `ssh kolmatrix`。
- **prod 站点**:design.vpanel.cc,Basic Auth(凭据见自动记忆 grandtianfu-deployment)。
- **GitHub**:tripplemay/grandtianfu,`gh` CLI 可用。

## 7. Phase 3 上线验证记录
实现流程:
```
风格意向(scheme 页) → room_brief 喂 LLM → LLM(relay gpt-5.5, chat json_mode)
按风格从 catalog 逐房选型(受控,只选该房 furniture_options)
→ 落位引擎(MVP 启发式:贴墙+避门+间距,出可用草稿)
→ catalog.expand 补外观 → 写入 1..N 个 FurnitureScheme 候选
→ 用户选择某套方案进入编辑器精修 → 该 scheme 继续走第4/5/7步
```
已验证:
- `PYTHONPATH=packages/floorplan_core:apps/api .venv/bin/python -m pytest apps/api/tests -q` → 68 passed,5 skipped。
- `PYTHONPATH=packages/floorplan_core .venv/bin/python -m pytest packages/floorplan_core/tests -q -k 'not render_string_matches_baseline_byte_for_byte'` → 23 passed,3 deselected。
- `cd apps/web && yarn build` → 通过,仅既有 FullCalendar/React warning。
- GitHub Actions deploy run `28438555199` → success,head `9e3aa17`。
- VPS `TAG=9e3aa17 ./scripts/deploy.sh` → pull/up/loopback health gate 通过,`.last_good_tag=9e3aa17`。
- prod `/api/health` → `{"ok":true,"readonly":false}`;`/api/ai/status` → `enabled:true,model:gpt-image-2`。
- prod `/studio/projects/D/scheme` loopback web → 200 HTML。
- prod `POST /api/projects/D/furnish`(style=现代轻奢,count=1,base=`default`) → job `cba860007211464fb67622b4bf53b20f` done;新增 `scheme_ai_20260630_105220_01_2780`,name=`现代轻奢软装方案`,source=`ai`,base=`default`,家具 71 件,warnings:`房间 r_live 类型 chair 数量过大,已降级`。
- prod `GET /api/projects/D/schemes/{scheme_id}/render?mode=plan2d` → 200 `image/svg+xml`,28388 bytes,XML/SVG 前缀正常。
- prod default 方案仍 56 件,AI 新方案 71 件;确认未覆盖根级 default furniture。

## 8. 下一步:Phase 1.5c+4(第7步)
第 7 步:轴测按房切片 + 空房照上传打 `room_id` 标签 + 多图 staging,需用户提供真实空房照;PIPL 跨境合规用户已接受,加授权提示/可删除存储。

## 8b. 效果图删除(2026-07-07 上线)
用户可删单张效果图(实拍 real-photo + 写实 axon-photoreal 两页历史)。
- 后端 `schemes.remove_render`(方案级 renders.json,`_RENDERS_LOCK`)+ `RenderLog.remove`(legacy 账本);`DELETE /api/projects/{house}/schemes/{scheme_id}/renders/{render_id}`:先摘记录(default 双账本防 `_list_default_renders` 合并复活)→ 404 若无 → 后 `_unlink_render_files` 删该记录自有 4 文件(url/base_url/thumb_url/preview_url,经 `_artifacts.resolve` 防穿越),**显式保留共享 photo_url**(空房照归 baselines/其它 render 共享)。先记录后文件(崩溃只留孤儿,gc.sh 兜底)。
- 前端 `real-render`/`render` 两页历史卡 + 最新大图加删除按钮,`useConfirm` 确认,删后 `reload()` 重算 latest。
- 字节安全:render 记录/文件不进 golden(与 layout 同理);删图不回退配额(累计口径)。测试 `test_render_delete.py` 6 条。3-agent 对抗审查 0 confirmed。

## 9. 红线 / 坑(务必守)
- 活数据 `data/projects/` 只读不污染:测试写接口用沙箱 DATA_DIR 或 `GEOM_READONLY=1`;**测试 save 会污染 D furniture,提交前 `git checkout` 还原**。
- golden/`.phase0-baseline` 字节级不动;改引擎(axon/prompt_gen)默认行为前先确认 golden 绿。
- AI 摆家具不可覆盖现有 `furniture.json`;必须创建新 `FurnitureScheme`。`default` 方案兼容旧数据,非 default 方案不写项目根级 `furniture.json`。
- ChakraProvider 全站=0;React 钉 18.3.1;`output:export` 路A(AI 调用全走 /api 无 Next route)。
- dev 跑着时**绝不**在宿主 `yarn build`(污染共享 .next 致 chunk 404);web 构建走 docker builder。
- `GEOM_READONLY` 生产必须空(红线;置 1 会拦 save-geometry)。
- 改 prod compose/.env/nginx 须手动 SSH 同步到 VPS(CI 不同步)。
- judge 类 workflow 给 agent Read 大图(>1MB×3)会 stall → 先缩图。
