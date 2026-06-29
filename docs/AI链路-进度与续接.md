# 阅天府 AI 功能链路 — 进度与续接

> 续接文档(2026-06-30)。新会话从这里恢复上下文。配套自动记忆:`~/.claude/.../memory/grandtianfu-ai-pipeline.md`(更细)。**本文不含密钥**(凭据指针见 §6)。

## 1. 一句话现状
把单机原型工具产品化为多用户 SaaS,核心是"户型→AI 出图"链路。**第 5 步(轴测→照片级效果图)已代码完成并真实上线 design.vpanel.cc**;第 2 步(AI 摆家具)地基已就位,主体待建;第 7 步(空房实拍)待建。

## 2. 用户定稿的 7 步工作流 + 状态
| # | 步骤 | 状态 |
|---|---|---|
| 1 | 人工编辑定稿户型图 | ✅ 已有(几何编辑器) |
| 2 | **AI 根据空户型摆放家具** | 🔨 地基完成(catalog+room-brief),主体待建(Phase 3) |
| 3 | 人工调整确认家具 | ✅ 已有(家具编辑器) |
| 4 | 生成轴测方案图 | ✅ 已有(引擎 photo/shell SVG) |
| 5 | **AI 据轴测图→照片级轴测效果图** | ✅ **已上线**(render 页 + /render-ai,prod 真跑通) |
| 6 | 上传空房实拍照 | 🔨 后端上传端点已就位,前端待建 |
| 7 | **AI 据空房照+轴测方案→实拍效果图** | ⬜ 待建(Phase 4,需用户空房照) |

全程砍掉文生图(户型结构不可控)。所有 AI 出图走 **img2img**。

## 3. 技术决策(已定)
- **出图模型 = `gpt-image-2`,直连 OpenAI 兼容 relay**(网关不支持 img2img)。edits 端点支持多图(第 7 步:空房照+轴测参考)。备胎 fal/Gemini,provider 抽象层不锁死。
- **后端**:FastAPI 单体直接 import floorplan_core 引擎。AI 子系统 `apps/api/aigc/`:config(凭据缺失 ai_enabled=False 不崩主服务)/providers(/images/edits 单·多图)/budget(文件落盘原子预扣释放+张数硬闸)/jobs(进程内异步,生成 90-225s 提交即返 job_id 前端轮询)/artifacts(自托管+防穿越)/records(渲染历史)/raster(svg→png)。
- **生成 = 异步**(单 uvicorn worker,进程内 job;90-225s 故必异步)。预算护栏 + 产物自托管(/api/artifacts)。
- **提示词**:prompt_gen 自动逐房 + `with_positions`(房内方位,Phase2 默认开;A/B 实测与 baseline 平手、无害)。**底图维持 original**(分类着色经评审否决:致材质偏色)。
- **第 2 步 = 混合**:LLM 选型 + 确定性落位 + 人精修(用户已同意)。LLM 不吐坐标。
- **前端**:Horizon Tailwind React(Next15/React 钉 18.3.1/output:export 路A 静态导出);studio 工作台;同源 /api 不开 CORS;ChakraProvider 全站=0。

## 4. 分支 / 提交
- **`main` = `b33f136`**(= origin/main)**已上线 prod**:Phase 1(AI 基础设施)+ 1.5b(提示词方位)+ Phase 2(render-ai + render 页)+ Phase 5(部署接线)。画廊 hotfix `dcd62f9` 也在 main。
- **`feat/ai-furnish` = `e4b3c39`**(领先 main 1 commit,**第 2 步工作分支**):Phase 1.5a(catalog + room-brief + schema 拆分)。
- 部署模型:**push `main` 即部署**(CI 构建 api/web 镜像→GHCR→SSH VPS deploy.sh 只 pull+up)。**deploy.sh 用 VPS 上的 compose/.env,repo 不自动同步到 VPS**——改 compose/.env/nginx 须手动 SSH 同步。

## 5. 完成情况(Phase 视角)
- **Phase 0** 命门 spike ✅:gpt-image-2 img2img(第5步)+ 多图(第7步机制)真图验证 PASS。
- **Phase 1** AI 基础设施 ✅:`aigc/` 包,40 测试,经 18 项多智能体对抗评审修复。
- **Phase 1.5b** 提示词方位 ✅:opt-in,A/B 平手无害,默认开。
- **Phase 2** 第5步 ✅:`/render-ai`(后端真 relay e2e)+ render 页(build 绿)。**已上线**。
- **Phase 5** 部署 ✅:relay key 注入 prod .env(600)、artifacts/uploads bind 挂载 chown 10001、relay 从 VPS 直连 200 无需代理、nginx 无需改。prod `/api/ai/status` enabled:true,真实在线生成验证通过。
- **Phase 1.5a** 第2步地基 ✅:`floorplan_core/catalog.py`(25 软装件目录+默认外观)+ `room_brief.py`(逐房简报:尺寸 mm/门窗匹配 N·S·E·W 墙/可选家具)。22 测试。
- **生产事故**:画廊全黑(悬挂家具 room_id→render 500)已修(引擎跳过悬挂件 + 数据重映射 r_liveext→r_live)。**线上 D 数据已与仓库分叉(线上 22 房/仓库 20 房),勿假设相等**。

## 6. 凭据 / 访问(指针,**值不在本文**)
- **relay**:OpenAI 兼容,base `https://co.ghgame.cn:18065/v1`,模型 gpt-image-2 + gpt-5.5/5.4。key 在 **本地 scratchpad/ai.env** 与 **prod `/opt/grandtianfu/.env`**(600)。⚠️ **该 key 曾在聊天明文出现,建议轮换**(热替换:`cd /opt/grandtianfu && docker compose up -d api`)。
- **SSH VPS**:`ssh kolmatrix`(tripplezhou@34.180.93.185,key `~/.ssh/kolmatrix_deploy`,nopasswd sudo + docker 组)。
- **prod 站点**:design.vpanel.cc,Basic Auth(凭据见自动记忆 grandtianfu-deployment)。
- **GitHub**:tripplemay/grandtianfu,`gh` CLI 可用。

## 7. 下一步:Phase 3(第2步 AI 摆家具)— 待建
在 `feat/ai-furnish` 上继续。流程:
```
风格意向(scheme 页) → room_brief 喂 LLM → LLM(relay gpt-5.5, chat json_mode)
按风格从 catalog 逐房选型(受控,只选该房 furniture_options)
→ 落位引擎(MVP 启发式:贴墙+避门+间距,出可用草稿)
→ catalog.expand 补外观 → 写 furniture(经 save-furniture 校验)
→ 用户编辑器精修 → 再走第4/5步
```
要建:① **chat 客户端**(扩展 `aigc/providers.py` 或新 `aigc/llm.py`:relay /chat/completions + json_object);② **选型逻辑**(room_brief+风格→每房类型清单,受控校验);③ **落位引擎** `floorplan_core/layout.py`(启发式,确定性,出草稿);④ 后端 `POST /api/projects/{id}/furnish`(异步 job);⑤ 前端 scheme 页(风格输入 + 生成草稿 + 跳编辑器)。落位野心 = MVP 启发式(人精修兜底,已与用户对齐)。
之后:**Phase 1.5c+4**(第7步:轴测按房切片 + 空房照上传打 room_id 标签 + 多图 staging,需用户提供真实空房照;PIPL 跨境合规用户已接受,加授权提示/可删除存储)。

## 8. 红线 / 坑(务必守)
- 活数据 `data/projects/` 只读不污染:测试写接口用沙箱 DATA_DIR 或 `GEOM_READONLY=1`;**测试 save 会污染 D furniture,提交前 `git checkout` 还原**。
- golden/`.phase0-baseline` 字节级不动;改引擎(axon/prompt_gen)默认行为前先确认 golden 绿。
- ChakraProvider 全站=0;React 钉 18.3.1;`output:export` 路A(AI 调用全走 /api 无 Next route)。
- dev 跑着时**绝不**在宿主 `yarn build`(污染共享 .next 致 chunk 404);web 构建走 docker builder。
- `GEOM_READONLY` 生产必须空(红线;置 1 会拦 save-geometry)。
- 改 prod compose/.env/nginx 须手动 SSH 同步到 VPS(CI 不同步)。
- judge 类 workflow 给 agent Read 大图(>1MB×3)会 stall → 先缩图。
