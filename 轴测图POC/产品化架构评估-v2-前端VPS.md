# 整合方案:阅天府软装工具产品化(前端=Horizon Next.js,部署=单台公网 VPS)

> 本方案在三视角(前端嵌入 / VPS 部署 / 路线骨架)基础上,吸收 36 条对抗结论做了**取舍裁定与内部一致性修正**。凡三视角互相矛盾处(SSR 真伪、Postgres 时机、网络隔离、CSP、健康门禁等),下面给出**唯一定稿**,并标注修了哪条对抗项。最高优先级修正前置为"Phase 0 三道 gating spike",未过不写任何业务代码。

---

## ⓿ 先决裁定:三个会让整盘计划报废的前置 gating(对抗 #1/#2/#3/#27)

这三项**必须在写第一行业务代码前完成**,因为它们各自能单独否决"用 Horizon"这个硬约束本身:

1. **许可证(对抗 #3,法律级)**:模板无 LICENSE 文件,Creative Tim/Horizon Pro 分档授权,基础档**禁止用于对外付费用户访问的 SaaS**。→ 动作:找出购买回执确认档位是否覆盖"对外付费 SaaS + 计划的开发者/end-product 数";不足则升级 Extended/SaaS 档,或换一个 MIT 模板。**法务/授权未确认前,不投入前端工程。**

2. **依赖可复现 + Chakra/React19 可构建性(对抗 #1/#2/#27/#28,技术级)**:
   - 模板**无 lockfile**,`react: ^19.0.0-rc.1` 的 caret 今天会解析到 **React 19 stable**(模板作者没测过的运行时);Chakra v2 + @emotion 11 + framer-motion 7 官方只支持 React 18,且它们就在**承重外壳** `admin/layout.tsx` / `Configurator` 里(9 个文件),不是可删的示例页。
   - → 动作(顺序固定):(a) `yarn install` 一次,**commit 生成的 `yarn.lock`**,把 `react`/`react-dom`/`@types/react` 钉成**一组协调的精确版本**(决策:React 18.3 stable + types 18,还是 RC + types 19——二选一,不要 runtime19+types18 长期共存);(b) 删 `preinstall: npx npm-force-resolutions`(yarn 原生认 `resolutions`,且 npx 不固定版本会污染 docker build 出网,对抗 #7);(c) **`yarn build`(加 `output:'standalone'`)+ 运行期冒烟 `admin/layout.tsx`**,作为"SSR 容器拓扑成立"的唯一门禁。
   - **失败分支预案**:若 Chakra v2 在 React 19 下崩 → 优先 pin React 18.3(代价:验证 Next15+模板在 18 下可跑);其次纯 Tailwind 重写外壳(真实工作量,需单独排期);最次 Chakra v3 迁移(大改,不推荐)。

3. **商业价值(沿用评估 doc 红线,Phase 0.5)**:极薄内部工具对 3–5 真实客户手工交付 #1/#7 验证价值。**不通过,不上公网 VPS 正式环境。**

---

## ① 更新后目标架构

### 文字架构图

```
                         公网
                          │  (仅 80/443;建议 Cloudflare 橙云,见下)
                          ▼
        ┌─────────────────────────────────────────────┐
        │  VPS 单机  (Docker Compose,Ubuntu + ufw)     │
        │                                               │
   edge │   ┌────────┐                                  │
  ──────┼──▶│ nginx  │  TLS 终止 / realip / 限流 / CSP   │
        │   └───┬────┘  /→web   /api→api               │
        │       │                                       │
        │  ┌────┴─────┐         ┌──────────────────┐    │
        │  │ web      │         │ api (FastAPI)     │    │
        │  │ Next 15  │         │  import 引擎       │    │
        │  │ (见下:   │  /api   │  /derive /validate │    │
        │  │ 静态导出  │◀───────▶│  /render(SVG字符串)│   │
        │  │ 或 node)  │         │  /save* /tasks    │    │
        │  └──────────┘         └───┬───────┬───────┘    │
        │                          │入队    │同步线程池   │
        │                     ┌────▼───┐  (CPU:derive/   │
        │                     │ redis  │   小图光栅)      │
        │                     │ queue  │ noeviction      │
        │                     │ +cache │ allkeys-lru(分) │
        │                     └────┬───┘                 │
        │                     ┌────▼─────┐               │
        │                     │ rq worker│ rasterize/ai  │
        │                     │ rsvg+CJK │ 队列分离       │
        │                     └────┬─────┘               │
        │                          │ 出站 443            │
        │  ┌──────────┐            ▼ (egress bridge)     │
        │  │ postgres │      外部 AI: AIGC网关/fal/Replicate
        │  │(P2才上;  │                                   │
        │  │ MVP=SQLite│   卷: artifacts(可重算/TTL)      │
        │  └──────────┘       uploads(不可重算/优先备份)  │
        └─────────────────────────────────────────────┘
```

### 同步 / 异步边界(定稿)

- **同步(进程内 import,~20ms 热路径)**:`/derive`、`/validate`、`/save-geometry`(先 validate 再落盘)、`/save-furniture`、**小尺寸 SVG→PNG**。
  - ⚠ 修对抗 #14:`derive` 端点用 **`def`(非 `async def`)** 让 FastAPI 自动丢线程池;`geometry.derive` 是 GIL 下的同步 CPU 纯函数,写成 `async def` 会阻塞事件循环,2 个并发实时编辑就排队。gunicorn worker 数按 **≈核数**(CPU 密集),非 IO 的 `2*cores+1`。压测门禁:N 并发 `/derive` 的 p95 < 200ms。
- **异步(RQ,两条独立队列)**:`rasterize`(大图 PNG@3200,CPU 短尖峰)、`ai`(#4 chat / #6 img2img / #7 inpaint,IO 等外部 API)。两队列分开避免 CPU 任务被 IO 任务挤队。

### 一次"实时编辑"请求时序

```
浏览器(受控SVG编辑器)
  │ 拖动房间→200ms debounce
  ▼ POST /api/derive  (同源,经 nginx)
nginx ──proxy──▶ api(def derive→线程池)
  │ geometry.derive(G)  纯函数 ~20ms
  ◀── {walls,doors,windows,dims,conflicts,warns}
浏览器:用返回数据重绘 inline <svg> 派生层 + 红/黄冲突提示
  (拖拽期走 ref 直改 transform,松手才 setState — 对抗#6 性能)
```

### 一次"成品效果图 #6"时序(异步)

```
浏览器 POST /api/projects/{id}/renders
  → api:① 原子预扣预算(Redis INCR / DB行锁,对抗#16 防TOCTOU)
        ② 入队 ai 队列 → 返回 {task_id}
  → worker:调 fal/Replicate(egress bridge 出站,对抗#11)
        → 失败回滚预算;成功生成大图 + 缩略图(对抗#9)→ artifacts
  → 浏览器轮询/SSE GET /api/tasks/{task_id} → result_url
```

---

## ② 前端落地(Horizon)

### 路由结构(定稿:`/studio` 顶层段,对抗 #31)

**现在就定 `/studio`,不要先建 `/admin/editor` 再迁**——否则 layout、routes 菜单、middleware matcher、auth 跳转全要返工。骨架第一页直接写在 `/studio` 下。

```
src/app/studio/
├── layout.tsx                 # 复制 admin/layout.tsx,换 routes.studio 源
├── projects/page.tsx          # 项目台(react-table)
└── projects/[id]/
    ├── editor/page.tsx        # 双模编辑器(核心长极)
    ├── gallery/page.tsx       # 轴测/效果图画廊(缩略图网格)
    ├── style/page.tsx         # #4 风格对话
    └── catalog/page.tsx       # 家具/素材库
```

- `routes.studio.tsx` 独立文件(不污染原 `routes.tsx`);约定"建页必改菜单"(模板双轨:menu 数组 ≠ 文件路由)。
- 项目内 editor/gallery/style/catalog 用**页面内 Tab**(依赖 `[id]`,放全局侧栏会产生无 id 死链)。

### 编辑器 React 重建拆分(对抗 #6:这是项目最长极,单独时间盒 spike)

把 647 行 `editor.html` 当**需求规格**,重建为受控 SVG + 纯函数。**明确的 spike 成功标准:拖房间→吸附→跨space越界回弹→自动重派生,40 件家具下 60fps。** 与项目台/画廊/catalog(相对琐碎)分开排期。

```
components/studio/editor/
├── FloorplanEditor.tsx   状态容器:mode/G/ITEMS/选中
├── EditorStage.tsx       <svg viewBox> + bg image + 两图层 + pointer 分发
├── geometry/ RoomRect / ResizeHandles / OpeningMarker / DerivedWalls / GeometrySidePanel
└── furniture/ FurnitureLayer(@dnd-kit) / FurnitureItem / FurnitureSidePanel

lib/floorplan/ geometry.ts(移植 rectsOverlap/crossSpaceOverlap/snapEdge/bestSnap/hostExtent/roomAt)
               coords.ts(ORIGIN 读 G.meta.origin,禁硬编码)/ types.ts / colors.ts
```

**必须保留的非显而易见逻辑**:① ORIGIN 从 `G.meta.origin` 读(多户型会变);② 跨space重叠保持上一合法值(回弹);③ `hostExtent` 开洞夹取;④ `bestSnap`(邻边优先 SNAP=8,退网格 GRID=5,Alt 关);⑤ 几何模式家具层半透只读;⑥ **派生(实时内存)/校验保存(落盘,有 ERROR 返 400 不落盘)二分**。

承载方式裁定:**受控 inline SVG**(对齐评估 doc"不上 Pyodide/WASM");>200 家具掉帧才把家具层下沉 `react-konva`,几何层始终 SVG。拖拽期 ref 直改 DOM transform、松手 setState(对抗 #6 性能关键)。

### 上传 / 库 / 数据层 / 鉴权选型

- **上传(#1/#7)**:`react-dropzone`(模板 `DropZonefile.tsx` 已有模式)。前端校验 MIME/尺寸/张数;异步拿 `task_id`。**#1 文案"AI草稿需描摹"、#7 文案"风格化氛围参考非精确可视化"**;#7 必须有 **PIPL 跨境单独同意**组件(见对抗 #17,gating)。
- **库**:`@tanstack/react-table` v8(模板 `ComplexTable` 模式)。家具表与编辑器共享同一 ITEMS state,行内改尺寸 ↔ 画布双向同步。
  - ⚠ 对抗 #36 硬前置:**家具复合键 `room:"living:180,250"` → `{room_id,dx,dy}` 相对坐标迁移,必须排在家具层/家具表之前**(否则 #2 改尺寸后家具静默错位),先做 point-in-rect 人工复核。
- **数据层**:新增 `swr` + `axios`(模板未自带)。**同源 `/api`**——dev 用 Next `rewrites` 把 `/api` 代理到 api,**全程 baseURL 常量 `/api`,CORS 永远关**(对抗 #33,避免 `*` 安全味 + 双 baseURL 返工)。统一信封 `{success,data,error}`;前端不信任 derive 几何,服务端 validate 为唯一真值。
- **鉴权**:评估 doc"起步可托管/暂无"。`src/middleware.ts` 拦 `/studio/**` 未登录跳 `/auth/sign-in`。**注意这与对抗 #4/#34 的部署决策耦合**(见下)。

### React19-RC + Next15 注意与授权说明(对抗 #1/#2/#4/#5/#8/#26)

| 项 | 现状 | 定稿动作 |
|---|---|---|
| lockfile | **无** | 生成并 commit yarn.lock,精确钉版本 |
| react/types 配对 | runtime19 + types18 | 选**一组协调对**(见⓿) |
| preinstall hook | `npx npm-force-resolutions` 未固定 | **删**(yarn 原生 resolutions) |
| `next.config.js` | 有 `swcMinify`(Next15已移除)、`images.domains`(已弃用)、`export`/`gh-pages` 脚本 | 删 `swcMinify`;`domains`→`remotePatterns`(对抗#5,别用 Plan1 §8.3 的 domains);加 `output:'standalone'`(若走 node 容器);删/改 `export`/`gh-pages` 避免误用 |
| SSR 真伪 | 全树 `dynamic(ssr:false)`,实际 client-only | **见②尾部部署决策** |
| `'use client'` | App Router 默认 Server Component | 编辑器/表格/dropzone 必加 |
| 授权 | 见⓿ #1 | gating |

**SSR 决策(对抗 #4/#34,定稿)**:模板整树 `ssr:false`,**没有 SSR 价值**(零 SEO、白屏首绘),唯一服务端能力是 middleware 鉴权。两条路明确二选一:
- **路 A(推荐 MVP)**:`output:'export'` 静态导出 → nginx 直接托管静态文件,**砍掉 web node 容器**,鉴权下沉到 nginx + api(token)。更省内存、更简单,正好是 standalone build 失败时的天然回退(对抗 #27)。
- **路 B**:保留 middleware 鉴权 → 必须 node 容器 + `output:'standalone'`。
- ⚠ 不要像三视角那样"按 SSR 给 VPS 配内存"却跑无 SSR 壳。**先 `yarn build` 探针,据结果定 A/B。**

### 保留 / 裁剪清单

- **裁**:`admin/nfts/**`、`rtl/**`、大部分 `ecommerce`(留 dropzone 后删)、`mapbox-gl`/`react-map-gl`、`@fullcalendar`(EOL);`export`/`gh-pages` 脚本。
- **留复用**:admin layout + Sidebar + Navbar + ConfiguratorContext 外壳(⚠ 这套含 Chakra,受⓿ #2 gating 约束)、card/fields/checkbox/radio、`ComplexTable`、kanban 的 dnd-kit 用法、`react-tabs`。
- **apexcharts**(2022,window 依赖,未测 React19)**保持可选、不进 MVP 关键路径**(对抗 #10)。

---

## ③ VPS 部署

### 服务清单(定稿:MVP 与完整两档,对抗 #29)

**MVP / Walking Skeleton = 3 服务**(nginx + web + api,SQLite + 文件,无 redis/worker/postgres)——评估 doc 红线"价值优先于平台",SQLite 双写冲突是"加了 worker 才有"的自找问题。**只有当异步 #6 真正落地才加 redis+worker;Postgres 推到 Phase 2(有重复付费客户)。**

完整拓扑(异步 AI 落地后):nginx / web / api / **rq-worker** / **redis** / (Phase2)postgres + 一次性 certbot profile。

### compose 关键修正(三视角 YAML 有内部矛盾,这里是定稿)

- **网络(对抗 #11,最严重)**:三视角 YAML 把 api/worker 只挂 `internal:true` 网 → 出站被切断,**所有 AI 功能首次部署即静默失败**。定稿落地"方案 A 双网卡":`db/redis` 留 `internal`;`api/worker` 同时挂 `internal`(访 DB/redis)+ `egress`(非 internal,出站 AI)。本地 gating:`docker compose exec api curl https://api.fal.ai` 通。
- **Redis(对抗 #12)**:队列绝不能 `allkeys-lru`(会驱逐 RQ job payload → 付费任务静默丢失)。队列 redis 用 **`noeviction` + AOF**;缓存若要 LRU 另起实例。maxmemory 按队列峰值重估。
- **资源上限(对抗 #13)**:每服务设 `mem_limit`(web 1g / api 768m / worker 1g / postgres 1g / redis 640m),postgres 给保护性 `oom_score_adj`,Next 设 `NODE_OPTIONS=--max-old-space-size`;宿主配 2–4G **swap** 兜底。
- **端口**:仅 nginx 暴露 80/443;db/redis/api/web **零宿主端口映射**(比依赖 ufw 更可靠,Docker 绕过 ufw 改 iptables)。
- **卷**:`artifacts`(可重算/TTL 清理/缩略图)、`uploads`(不可重算/优先备份/短 TTL 合规)分离;`pg_data`、`redis_data`、`certbot_certs`。
- **健康门禁(对抗 #20)**:`deploy.sh` 不要 `curl https://localhost`(证书 CN 不匹配必失败→每次误判回滚)。用 `curl http://api:8000/healthz`(绕 TLS)或 `--resolve $DOMAIN:443:127.0.0.1`;healthz 做真实依赖探活(DB/redis 可达)。

### 镜像要点(rsvg + CJK)

- **api/worker 共用镜像**:`python:3.12-slim` + `librsvg2-bin` + `fonts-noto-cjk` + `fonts-noto-cjk-extra` + `fc-cache -f`;非 root 运行。构建上下文取 monorepo 根(`COPY packages/floorplan_core`)。
- **镜像层 gating**:`fc-list | grep -i "Noto.*CJK"` 非空 + 含中文房名 SVG→PNG 与 baseline 像素 diff 一致(房名不豆腐块)。把这项**提前到"本次"**做(对抗 #35,廉价隔离 de-risk)。
- **web**:若走路 B,`output:'standalone'` 多阶段(镜像 ~200M);若路 A,无 web 容器,nginx 托管静态。**CI 构建,VPS 只 pull**(4G VPS 跑 `next build` 会 OOM)。

### 安全基线

**必须做(上线 gating)**:
1. ufw 默认拒入站,仅 22(限源)/80/443;db/redis 零端口映射。
2. SSH:`PermitRootLogin no`、仅密钥。
3. **CSP 修正(对抗 #21)**:`default-src 'self'` 会打碎 emotion/Chakra(运行时注入 inline style)+ apexcharts + 跨域图。定稿:`style-src 'self' 'unsafe-inline'`;`img-src 'self' data: <对象存储域>`;`connect-src 'self'`;`script-src` 按 Next 内联加 nonce。上线前浏览器 console 实测 0 violation。
4. **TLS 冷启动(对抗 #22)**:首签用 HTTP-only 引导 server 块(只 listen 80 + webroot),签到后切 443。证书到期监控(剩<21天告警)**升为必须做**;续期后 `nginx -t` 再 reload,失败告警。
5. 应用鉴权:所有 `/api/*` 必须带 token(否则 `/derive` 成公网免费算力)。
6. nginx 限流 + `client_max_body_size 15m` + 安全头;fail2ban。
7. **Cloudflare 橙云与 realip(对抗 #15,二者必须配套)**:若上 CF,nginx 必须 `set_real_ip_from <CF段>` + `real_ip_header CF-Connecting-IP`(否则限流/fail2ban 按 CF IP 误封全体用户);源站 ufw 仅放 CF IP 段(防绕 CF 直打源站)。**CF 上/不上明确二选一,别两个都标"必须"。**

**应该做**:上传防护(剥 SVG 脚本防存储型 XSS、魔术字节校验、独立 uploads 卷经 api 鉴权下发);**artifacts TTL 清理 + 内容哈希去重升为必须做 + 磁盘 >75% 告警 >90% 自动清(对抗 #19,磁盘满是单机头号宕机源)**;凭据修正(对抗 #23:`docker login --password-stdin`,redis 密码走配置文件/ACL 不上命令行);Sentry + Uptime Kuma。

### AI 花钱闸门(对抗 #16,生存级)

单层 app 内 `PER_USER_DAILY_AI_BUDGET` 不够。多层:① **provider/网关侧硬月额度 + 熔断**(AIGC 网关 `get_balance`/`get_usage_summary` 接告警);② 预算检查与扣减**原子化**(Redis INCR / DB 行锁),**入队时预扣、失败回滚**,不在执行时才查(防 TOCTOU 并发入队);③ 限流按**账户**非 IP(换 IP 即重置)。

### 资源规格

- **不要 4G 跑全栈**(对抗 #13)。MVP 3 服务可 4G;完整拓扑**起步即 8G**:4 vCPU / 8G / **≥100G NVMe**(artifacts 增长快)。CPU 尖峰=rsvg 光栅(队列削峰);AI 步骤不吃本机 CPU(IO 等外部),worker 队列分离。

### CI/CD + 备份 + 可用性

- CI 构建+推 GHCR,VPS `compose pull` + `deploy.sh`(先跑**向后兼容** migration → `--no-deps` 滚动 → 健康门禁)。回滚 = `TAG=<上个sha> up -d`。**不用 watchtower**(无门禁/无 migration 编排)。
- **备份(对抗 #18)**:夜间 pg_dump 的 RPO≈24h 对"设计师数小时方案"不可接受。定稿:DB WAL 归档/物理复制把 RPO 压到分钟级(或 Phase2 提前用托管 PG);uploads 写穿即同步 R2;**备份加密密钥独立托管(不在 VPS/仓库)**;上线前完整 restore 演练记 RTO。
- **可用性(对抗 #25)**:单 VPS 无冗余。同机加 **staging compose project**(不同端口/库)先验 migration+镜像冒烟再 prod;明确 **SLA(非 24/7,给维护窗口)+ status page**;前端对 5xx 做乐观重试 + **本地草稿缓存**(api 重启不丢未保存编辑);migration 强制 expand-contract(只加不删)。

### 成本量级(对抗 #24,三视角缺失)

| 项 | 月度量级 |
|---|---|
| VPS 4C/8G NVMe | Hetzner ~€15 / DO·Vultr ~$48 |
| 对象存储 + 出口流量 + 备份存储 | ~$5–20 |
| 域名 + Sentry/监控(免费档) | ~$2 |
| **固定基础设施小计** | **~$25–70/月** |
| **AI 变动成本(真正大头)** | 每户多张图可达**每户数美元**(#4 chat + #6 img2img + #7 inpaint × provider 单价),直接挂钩 `PER_USER_DAILY_AI_BUDGET` 与定价毛利 |

**结论**:固定成本不是问题,**AI 单户变动成本是毛利生死线**,必须在定价前算"每功能调用次数 × 单价",并定"单 VPS 撑多少并发户 → 何时被迫上第二台/托管 DB"的规格阶梯。

---

## ④ 修订迁移路线

### Phase 0 — 三道 gating spike + 去硬编码 + 内核库化 + 全栈骨架(1–2 周,纯重构)

- **gating(⓿)**:许可证确认 / `yarn.lock`+React-Chakra 可构建 spike / 商业价值(0.5)。**任一不过即停。**
- 后端:去硬编码绝对路径(`SRC_DEFAULT`/`HOUSE="D"`/根路径→env)→ 抽 `packages/floorplan_core` →(对抗 #30)**先 snapshot 当前 render 输出为 golden baseline,再** 把 `render()` 改返回字符串,断言一致 → verify_golden 升 pytest + 补家具渲染快照。
- 前端:`git init` monorepo,Horizon 拷入 `apps/web`(先不裁),新增 axios+SWR 数据层。
- 部署:`docker-compose.dev.yml`(仅 web+api),api 第一版 `sys.path` import 现引擎(零搬迁)。
- 验收:Walking Skeleton S1(见⑤)。**风险**:Chakra/React19(已 gating)、render 字符串化(已先补快照)。

### Phase 0.5 — 商业验证(评估 doc 红线,前端/部署不加码)

极薄内部工具手工交付 #1/#7 给 3–5 真实客户。**不通过不上公网 VPS。**

### Phase 1 — 单用户 MVP + 单机 VPS 上线(3–5 周)

- 后端:FastAPI import 引擎 + (#6 落地时)1 RQ worker + redis;**MVP 用 SQLite/文件**;覆盖 #2/#3/#5 完整、#4(网关 chat)、#6(直连 img2img);#1 走"AI 草稿+描摹"非关键路径;**家具复合键迁移(#36)排在家具层之前**。
- 前端:Horizon 落地全部页面(项目台/双模编辑器/画廊/风格对话);编辑器作**独立时间盒长极**(对抗 #6)。
- 部署:`docker-compose.prod.yml` 上单台公网 VPS(网络双网卡、redis noeviction、资源上限、CSP、TLS 冷启动、AI 多层预算、staging 冒烟、备份)。
- 风险:编辑器移植量(最长极)、#6 一致性、CJK 镜像(已 gating)、单点+无 staging(已加 staging project)。

### Phase 2 — 规模化(有重复付费客户后)

Postgres(JSONB 版本快照,WAL/PITR)+ 对象存储(MinIO/R2,artifacts 提前迁出)+ worker 横扩(rasterize/ai 拆服务)+ 配额/计费/限流 + Grafana/Loki 或托管 APM + #7 合规前置 + GPU 自建则**拆第二台机**(不与公网 Web 同机)。

---

## ⑤ 下一步可执行清单(本次就开始)

> 红线:**不移动** `geometry.py`/`svg2geometry.py`/`平面布置图-无家具.svg`/`geometry-D户型.json`/`verify_golden.py`;API import 现引擎不搬文件。

### 本次动作(每步带验证)

**步骤 0 — 三道 gating(写代码前,对抗 #1/#2/#3/#27)**
- (a) 查 Creative Tim 购买回执确认授权档位覆盖对外付费 SaaS。验证:留存授权证明。
- (b) 在模板目录 `yarn install` → **commit `yarn.lock`** → 精确钉 react/react-dom/@types/react 一组协调版本 → 删 `preinstall` hook → `next.config.js` 改(删 swcMinify、domains→remotePatterns、加 output 视路A/B)→ **`yarn build`**。验证:build 绿 + 起 `admin/layout.tsx` 运行期无 Chakra/forwardRef 报错。失败→走 React18 pin 或静态导出回退。
- (c) 决策 SSR 路 A(静态导出,推荐)/ 路 B(node 容器),据 build 结果定。

**步骤 1 — monorepo scaffold**
```
git init; mkdir -p apps/api apps/web packages/floorplan_core deploy
# .gitignore: node_modules .next __pycache__ artifacts/ *.png .env yarn-error.log
```
验证:`git status` 干净,`轴测图POC/` 未动。

**步骤 2 — Horizon 拷入 apps/web**(已含步骤 0b 的 lockfile)。验证:`yarn dev` 起 `localhost:3000/admin/dashboards/default`。

**步骤 3 — apps/api 最小 FastAPI(import 现引擎)**
- `ENGINE_DIR` 走 env(勿硬编码进逻辑),`sys.path.insert` import `geometry`。
- 端点:`GET /api/health`、`GET /api/projects/D/geometry`、**`def derive(...)`**(非 async,对抗 #14)调 `geometry.derive`。
- 验证:`curl /api/health` → ok;`curl -XPOST /api/derive -d @geometry-D户型.json` walls 非空,且与 `python serve.py` 结果一致(回归对齐)。

**步骤 4 — 前端骨架页(定 `/studio`,对抗 #31)**
- `apps/web/src/app/studio/projects/[id]/editor/page.tsx`(`'use client'`)+ `components/studio/editor/FloorplanPreview.tsx`(SWR 取几何 → POST /derive → 受控 inline SVG 画 walls,mm→px;移植 `grender` 雏形)。
- **数据层同源**:Next `rewrites` 把 `/api` 代理到 api,axios `baseURL='/api'`,**不开 CORS**(对抗 #33)。
- `routes.studio.tsx` 加菜单项。
- 验证:`localhost:3000/studio/...editor` 在 Horizon 暗色布局渲出 D 户型 2D 线框;改墙坐标→重 POST→SVG 实时更新。

**步骤 5 — Walking Skeleton 验收 + 廉价 de-risk**
- S1(读+derive,3 服务,web 本地跑非容器内 yarn install,对抗 #32):一条命令起 api 容器 + 本地 `yarn dev`,走通线框实时预览。
- **S1.5(对抗 #35)**:加薄写路径 `POST /save → 文件 → 读回`,给持久化设计早期信号(别只验最低风险纯函数路径)。
- **CJK 镜像 de-risk 提前(对抗 #35)**:本地 build api 镜像,`fc-list | grep CJK` 非空 + 中文房名 SVG→PNG 不豆腐块。

### 下次动作(Phase 0 正式 + S2)
1. 去硬编码 → 抽 `floorplan_core`(迁五个金测耦合文件前先去硬编码再迁再复跑)→ **先 snapshot 当前 render → 再字符串化 → 断言一致**(对抗 #30)+ 家具渲染快照。验证:`pytest --cov` 几何+渲染绿,api 改 `import floorplan_core` 后 /derive 回归一致。
2. S2:`GET /api/render` 返 SVG 字符串;`/studio/.../gallery` 显示轴测图;PNG 走 CJK 镜像。
3. 家具复合键 `{room_id,dx,dy}` 迁移(对抗 #36,家具层/表的硬前置)→ 家具层 dnd-kit → 双向同步。
4. 裁剪 Horizon(nfts/map/calendar)→ `yarn build` 绿。
5. prod compose 草案:nginx(realip+CSP+TLS 冷启动)+ redis(noeviction)+ worker(双网卡 egress)+ 资源上限 + staging project + 备份 cron。验证:自签证书 `https://localhost` 走通反代,`exec api curl https://api.fal.ai` 出站通。

---

## 关键取舍一览(供决策)

| 决策 | 定稿 | 对抗依据 |
|---|---|---|
| 三道 gating 前置 | 许可证/Chakra-build/价值,任一不过即停 | #1#2#3#27 |
| SSR | 路 A 静态导出(MVP 推荐)/ 路 B node 容器,据 build 定 | #4#34 |
| MVP 服务数 | 3(nginx+web+api,SQLite),异步落地才加 redis/worker,PG 到 P2 | #29 |
| derive 端点 | `def`(线程池),非 async | #14 |
| 网络 | 双网卡:db/redis internal + api/worker egress | #11 |
| 队列 redis | noeviction(绝不 LRU) | #12 |
| Cloudflare | 上则配 realip + ufw 仅放 CF 段;不上则接受源站暴露(二选一) | #15 |
| AI 预算 | provider 硬额度 + 原子入队预扣 + 按账户限流 | #16 |
| 路由段 | 现在定 `/studio` | #31 |
| 数据层 | SWR+axios,同源 /api,无 CORS | #33 |
| 编辑器 | 独立时间盒长极,家具键迁移硬前置 | #6#36 |

**残留需你确认**:① SSR 路 A/B(等步骤 0b build 结果);② Cloudflare 上不上(决定源站暴露面);③ #7 PIPL 跨境合规(法务确认前不上线,VPS 区域纳入合规);④ AI 单户毛利模型(定价前必算);⑤ React pin RC 还是 18 stable(Chakra spike 结果决定)。

**相关绝对路径**:评估 doc `/Users/yixingzhou/project/grandtianfu/轴测图POC/产品化架构评估.md`;引擎 `/Users/yixingzhou/project/grandtianfu/轴测图POC/{geometry.py,轴测引擎.py,serve.py,editor.html,build.py,geometry-D户型.json,furniture-D户型.json}`;模板源 `/Users/yixingzhou/project/db4rDjuaSCqaEFW9XcFo_horizon-tailwind-react-nextjs-pro-3.0.0/horizon-tailwind-react-nextjs-pro-main`(`cp -R`→`/Users/yixingzhou/project/grandtianfu/apps/web`);骨架落点 `/Users/yixingzhou/project/grandtianfu/{apps/api,apps/web,packages/floorplan_core,deploy/,docker-compose.dev.yml}`。