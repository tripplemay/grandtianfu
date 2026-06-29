验证完成。关键事实已确认:`apps/web/yarn.lock` 存在(273KB,Design1/2的"缺lockfile"阻塞为**假**);`next.config.js` remotePatterns **含 fbcdn 第三主机**;`main.py` save_geometry(L406)/save_furniture(L307)/create_project(L237) 全是 `open("w")+json.dump` **非原子**;delete_project(L263) `rmtree` **不受 GEOM_READONLY 约束**;create-project CTA `router.push(/studio/projects/${created.id}/editor)`(L72)在路A下必 404;当前 `apps/api/Dockerfile` 仍用 `ENGINE_DIR=/engine` **未装 floorplan_core**(照现状 build 必崩)。下为最终计划。

---

# 阅天府 studio — 单台公网 VPS 部署实施计划(MVP·最终版)

> 范围:**只设计/规划,不执行**。不跑 docker build、不动 dev 服务。MVP = nginx + web静态 + api **3 服务**;redis/rq-worker/postgres/egress双网卡 **全部分期**(AI #4/#6/#7 落地再加)。所有路径为绝对路径,配置可照抄。本计划已整合 3 视角并消解 25 条对抗发现的全部冲突与事实错误。

---

## ① 架构定稿

### 拓扑(文字)
```
公网 (TCP 80/443)
   │  仅 nginx 暴露端口;api/web 不映射宿主端口
   ▼
[nginx:1.27-alpine]  反代+静态+TLS+BasicAuth+限流+安全头
   ├─ location /        → 静态(命名卷 web_static 的 current/ 软链,路A 导出产物)
   ├─ location /api/    → http://api:8000  (同源,无 CORS,透传 no-store,DELETE 边缘拦截)
   └─ location=/api/health → api:8000 (auth_basic off, 供探活)
   ▼ (docker 内网 internal bridge)
[api: FastAPI uvicorn]  内置 floorplan_core;非root uid10001
   └─ bind mount /srv/grandtianfu/data/projects → /data/projects (DATA_DIR, 活数据)
[web-static: 一次性发布器]  把 out/ 原子发布到 web_static 卷的 /<sha> 并翻转 current 软链后退出
[certbot: profile 手动/续期]  webroot 签发,与 nginx 共享 certs/webroot 卷
```

### 定稿要点
- **web 走路 A(静态导出 → nginx 托管)**。工程已就绪(`build:export` + `output:'export'`,导出态自动关 rewrites,正好同源 /api 归 nginx);整树 `dynamic(ssr:false)` 无 SSR 价值,路 B 纯白养进程。
- **同源 /api + TLS**:443 终止 TLS,`/api/` 反代 api:8000(保留 `/api` 前缀,`proxy_pass http://api:8000;` 末尾不带 `/`),`connect-src 'self'`,无 CORS(红线)。
- **数据持久卷用 bind mount**(`/srv/grandtianfu/data/projects`,**不用命名卷**)——这是消解"备份脚本路径与卷类型不一致"(对抗#9)和"卷属主非 10001 致 save 403"(对抗#4)两个问题的统一选择:宿主目录可直接 `chown 10001`、可直接被 backup.sh tar、可直接灌种子。
- **分期边界(MVP 不引入)**:redis / rq-worker / postgres / egress 双网卡 / WAL-PITR / Grafana-Loki / 上传防护。异步 AI(#6)落地后再加(届时 redis 用 noeviction+AOF,api/worker 挂独立 egress 网出站)。

---

## ② 文件清单(deploy/ 下新建 + 必改代码)

> 本节定义"部署时落盘什么";本工作流**不创建**这些文件。

### 必改的现有代码(MVP 部署前置 gating,非可选)
| 文件 | 改动 | 来源对抗项 |
|---|---|---|
| `/Users/yixingzhou/project/grandtianfu/apps/api/main.py` | **落盘改原子写**:save_geometry/save_furniture/create_project 三处 `open("w")+json.dump` → 写同目录 `*.tmp` + `flush()/os.fsync()` + `os.replace(tmp,path)`;覆盖前留 `.bak` 单步回退 | #8 #16(critical) |
| 同上 | **/api/health 升级真实探活**:检查 DATA_DIR 存在且可写(写临时文件)+ `import floorplan_core` 成功,否则返 503;返回体加 `{"ok":true,"readonly":<GEOM_READONLY>}` | #11 #15 |
| `/Users/yixingzhou/project/grandtianfu/apps/api/Dockerfile` | **改写**(详见下) | #(现状) |
| `/Users/yixingzhou/project/grandtianfu/apps/web/src/app/studio/projects/page.tsx` | **MVP D-only**:隐藏/禁用「＋新建项目」与「删除」按钮(否则创建后 `router.push(.../E/editor)` 落 404,且 DELETE 无纵深) | #1 #10 |
| `/Users/yixingzhou/project/grandtianfu/apps/api/main.py` delete_project | **软删**:`rmtree` 前先 `mv` 到 `{DATA_DIR}/.trash/<id>-<ts>`(保留 N 天) | #10 |

### deploy/ 新建文件
| 路径 | 职责 | 关键片段/要点 |
|---|---|---|
| `deploy/docker-compose.prod.yml` | 3 服务编排 + bind/卷/网络/restart/mem_limit/healthcheck | 见 §下方 |
| `deploy/nginx/conf.d/00-bootstrap.conf` | TLS 冷启动仅 80+ACME(签发期临时) | 见 ③/④ |
| `deploy/nginx/conf.d/grandtianfu.conf` | 正式 80→443 + 443 站点 | 见下方 |
| `deploy/nginx/snippets/tls-params.conf` | Mozilla intermediate ssl 参数 | TLSv1.2/1.3 + OCSP + resolver 127.0.0.11 |
| `deploy/nginx/snippets/security-headers.conf` | CSP/HSTS/X-* | **必须在每个含 add_header 的 location 里 include**(#18 继承陷阱) |
| `deploy/nginx/htpasswd` | Basic Auth(`htpasswd -B`) | **不入仓**,VPS 上生成,权限 600 |
| `deploy/tls/init-letsencrypt.sh` | 冷启动一次性引导(自签占位→certbot→reload) | #3 #24 |
| `deploy/scripts/deploy.sh` | pull→up→健康门禁→失败回滚 | http /api/health,绕 TLS |
| `deploy/scripts/rollback.sh` | `TAG=$(cat .last_good_tag) up -d` | 镜像按 git sha |
| `deploy/scripts/backup.sh` | tar `/srv/.../data/projects` → 异地推送(强制) | #9 #12 |
| `deploy/scripts/restore-test.sh` | 真恢复 + `diff -r`,记 RTO | #12 #21 |
| `deploy/scripts/bootstrap-vps.sh` | 首次主机加固:ufw/sshd/swap/chown数据目录 | #4 |
| `deploy/systemd/grandtianfu-backup.{service,timer}` | 备份调度(每6h) | Persistent=true |
| `deploy/fail2ban/jail.d/nginx-studio.local` | sshd + nginx-http-auth + limit-req | [应做] |
| `deploy/.env.example` | env 模板(入仓);真 `.env` 不入仓 600 | GEOM_READONLY 留空注释 |
| `/Users/yixingzhou/project/grandtianfu/.dockerignore` | 收缩上下文 + 防泄密 | **递归** `**/.env` 等(#14),注释独占行(#7) |
| `/Users/yixingzhou/project/grandtianfu/apps/web/Dockerfile` | 路A 多阶段:builder 出 out/ → 发布器 | #2 原子发布 |
| `/Users/yixingzhou/project/grandtianfu/.github/workflows/deploy.yml` | CI 出镜像→GHCR→SSH 调 deploy.sh | 避 4G VPS OOM |

### api Dockerfile(改写,构建上下文=monorepo 根)
```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        librsvg2-bin fonts-noto-cjk fonts-noto-cjk-extra curl \
    && fc-cache -f && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 10001 appuser
WORKDIR /app
# 引擎库内置(现 main.py: from floorplan_core import ...;旧 ENGINE_DIR 思路已废弃)
COPY packages/floorplan_core /opt/floorplan_core
RUN pip install --no-cache-dir /opt/floorplan_core
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY apps/api/ /app/
ENV DATA_DIR=/data/projects HOUSE=D GEOM_READONLY=
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
# MVP 单用户先 1 worker(配合 mem_limit,避免 2 worker×渲染峰值 OOM);压测后再调
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","1"]
```

### web Dockerfile(原子发布,消解 #2 的 rm -rf 活卷)
```dockerfile
# ---- builder ----
FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY apps/web/package.json apps/web/yarn.lock ./
RUN yarn install --frozen-lockfile          # yarn.lock 已存在(对抗#6/13/23: 无需"补")
COPY apps/web/ ./
RUN NEXT_OUTPUT_EXPORT=1 yarn build:export   # 产物 out/
# ---- publisher: 原子发布到 /<sha>, 翻转 current 软链, 保留旧版供在途会话/回滚 ----
FROM alpine:3.20 AS publisher
COPY --from=builder /app/out /out
ENV SHA=dev
CMD ["sh","-c","\
  D=/web_static/$SHA; rm -rf $D; mkdir -p $D; cp -a /out/. $D/; \
  ln -sfn $D /web_static/.current.tmp && mv -Tf /web_static/.current.tmp /web_static/current; \
  ls -1dt /web_static/*/ | grep -v current | tail -n +4 | xargs -r rm -rf; \
  echo published $SHA"]
```
> nginx `root /usr/share/nginx/html/current;`(current 是软链)。发布=原子 `mv -T` 翻软链,**绝不 rm 活 docroot**;保留最近 3 个 sha 目录,在途会话仍能取旧 `_next/static` 指纹 chunk(消解"改版后旧 chunk 404",对抗#2)。SHA 由 compose 传入。

### docker-compose.prod.yml(MVP 3 服务)
```yaml
name: grandtianfu
services:
  api:
    image: ghcr.io/${GHCR_OWNER}/grandtianfu-api:${TAG:-latest}
    restart: unless-stopped
    environment:
      DATA_DIR: /data/projects
      HOUSE: D
      GEOM_READONLY: ""          # 生产必须空=可写(红线;#15)
    volumes:
      - /srv/grandtianfu/data/projects:/data/projects   # bind(#4 chown / #9 备份对齐)
    networks: [internal]
    expose: ["8000"]
    mem_limit: 1g                # 先给余量;压测渲染 p99 后定(#11 #22 不拍脑袋)
    memswap_limit: 1g
    healthcheck:
      test: ["CMD","curl","-fsS","http://127.0.0.1:8000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
  web-static:
    image: ghcr.io/${GHCR_OWNER}/grandtianfu-web:${TAG:-latest}
    environment: { SHA: "${TAG:-dev}" }
    restart: "no"
    volumes: [ "web_static:/web_static" ]
    networks: [internal]
  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    depends_on:
      web-static: { condition: service_completed_successfully }
      api: { condition: service_healthy }
    ports: ["80:80","443:443"]
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/snippets:/etc/nginx/snippets:ro
      - ./nginx/htpasswd:/etc/nginx/htpasswd:ro
      - web_static:/usr/share/nginx/html:ro
      - certbot_certs:/etc/letsencrypt:ro
      - certbot_webroot:/var/www/certbot
      - ./logs/nginx:/var/log/nginx          # 供宿主 fail2ban 读
    networks: [internal]
    mem_limit: 256m
  certbot:
    image: certbot/certbot:latest
    profiles: ["certbot"]
    volumes:
      - certbot_certs:/etc/letsencrypt
      - certbot_webroot:/var/www/certbot
networks: { internal: { driver: bridge } }
volumes: { web_static: {}, certbot_certs: {}, certbot_webroot: {} }
```

### nginx grandtianfu.conf(正式块,已含全部对抗修正)
```nginx
limit_req_zone  $binary_remote_addr zone=api_rl:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=api_conn:10m;

server {                                   # 80 → 跳 443,放行 ACME
    listen 80; server_name studio.example.com;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl; http2 on; server_name studio.example.com;
    ssl_certificate     /etc/letsencrypt/live/studio.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/studio.example.com/privkey.pem;
    include /etc/nginx/snippets/tls-params.conf;

    root /usr/share/nginx/html/current;     # current 软链(原子发布)
    index index.html;
    client_max_body_size 15m;

    auth_basic "grandtianfu"; auth_basic_user_file /etc/nginx/htpasswd;

    location = /api/health {                # 探活放行(#20),否则 401 误判 DOWN
        auth_basic off;
        proxy_pass http://api:8000;
    }
    location /api/ {                         # 同源,保留 /api 前缀,透传 no-store
        limit_req zone=api_rl burst=20 nodelay; limit_conn api_conn 20;
        limit_except GET POST PUT OPTIONS { deny all; }   # MVP 边缘拦 DELETE(#10)
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s; proxy_buffering off;
        include /etc/nginx/snippets/security-headers.conf;   # #18 每 location 重复
    }
    location /_next/static/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        include /etc/nginx/snippets/security-headers.conf;   # #18
        try_files $uri =404;
    }
    location / {
        try_files $uri $uri.html =404;      # #5 真 404,不再 200 兜底
        add_header Cache-Control "no-store, must-revalidate";
        include /etc/nginx/snippets/security-headers.conf;   # #18
    }
    error_page 404 /404.html;
    location = /404.html { internal; include /etc/nginx/snippets/security-headers.conf; }
}
```

### security-headers.conf(CSP 统一,#5 #18 #19)
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options nosniff always;
add_header X-Frame-Options SAMEORIGIN always;
add_header Referrer-Policy strict-origin-when-cross-origin always;
add_header Content-Security-Policy "default-src 'self'; \
script-src 'self' 'unsafe-inline'; \
style-src 'self' 'unsafe-inline'; \
img-src 'self' data: blob: https://images.unsplash.com https://i.ibb.co https://scontent.fotp8-1.fna.fbcdn.net; \
font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'" always;
```
- `script-src` 统一 `'self' 'unsafe-inline'`(路A 无 nonce,#19);`style-src 'unsafe-inline'` 必留(Chakra/emotion)。
- `img-src` **补 fbcdn 第三主机**(next.config 实含,#5);上线前浏览器 console 实测 0 violation。

### .dockerignore(#7 #14 修正)
```
.git
.venv
**/.venv
**/node_modules
**/.next
**/out
**/__pycache__
**/*.pyc
**/*.egg-info
**/.DS_Store
**/.env
**/.env.*
**/*.env
*.mp4
*.png
*.jpeg
archive
轴测图POC
docs
两段式效果图
软装概念板
data
deploy/nginx/htpasswd
```
> 注释独占行(Docker 不支持行尾注释);`.env` 用 `**/` 递归(否则 `apps/api/.env` 不被排除,会烤进镜像层不可撤)。

---

## ③ 安全基线 + 鉴权 + 备份 + restart + CI/CD + 监控 + Cloudflare

- **网络**:compose 零宿主端口(仅 nginx 80/443);ufw default deny incoming + 仅放 22/80/443;Docker 直写 iptables 绕 ufw,故不靠 ufw 兜底容器端口。22 有固定 IP 则限源,无则仅密钥+fail2ban(Tailscale 为 [应做] 更优)。
- **SSH**:`PermitRootLogin no` + `PasswordAuthentication no` + 专用 `deploy` 用户(docker 组);确认密钥可登再 reload sshd。
- **鉴权(MVP 最小可上线)**:**nginx 全站 HTTP Basic(`htpasswd -B` bcrypt)**,零改 api 代码、同源凭据自动随 fetch 带上;`/api/health` carve-out。**显式说明**:Basic 是单一共享口令(3-5人),只限"谁能访问",不防"进程被 kill 当场损毁数据"——数据安全靠**原子写 + 实测备份**,不是靠鉴权(#25)。DELETE 在 MVP 由 nginx 边缘拦截 + 代码软删双保险。token/托管鉴权(Authelia)= 分期。
- **GEOM_READONLY**:生产必须空=可写(红线);值暴露到 /api/health,误置 1 由监控告警(#15)。
- **备份(红线,#9 #12 #21)**:`backup.sh` tar `/srv/grandtianfu/data/projects` → **异地对象存储(R2/S3)推送为 MVP 必需**,`BACKUP_REMOTE` 缺失则**报错退出+告警**(不静默跳过);桶开版本化/对象锁防勒索。systemd timer 每 6h(设计师数小时方案,RPO≤6h)。**加密 age 降为 [应做]**(右尺寸:两个小 JSON;若启用则密钥托管 runbook 强制,因私钥不在 VPS=无法自动恢复)。`restore-test.sh` 真恢复+`diff` 进 timer 链路,记录 RTO,**作为 MVP gate**。
- **restart 策略(根治掉线,#11)**:三件套 `restart: unless-stopped` + healthcheck(真实探活)+ `systemctl enable docker`(宿主重启自拉起)。**补**:监控 docker `OOMKilled`/restart 次数,识别"崩溃-重启循环";`mem_limit` 由压测 render p99 +50% 定,**不拍脑袋**;MVP `--workers 1` 避 2worker×渲染峰值 OOM。宿主配 2-4G swap 兜底。
- **CI/CD(避 OOM,#2)**:GitHub Actions(runner 内存足,`next build` 不 OOM)→ build api+web 镜像按 `git sha` tag → 推 GHCR(private)→ SSH 调 `deploy.sh`:`compose pull` → `up -d`(传 `TAG=sha`,web-static 原子发布)→ **健康门禁**(`exec -T api curl http://localhost:8000/api/health`,绕 TLS+Basic,#8)→ 失败 `TAG=$(cat .last_good_tag) up -d` 自动回滚。VPS 全程只 pull,永不构建。GHCR 登录 `--password-stdin`。CI 加 gitleaks secret 扫描(#14)。
- **监控(轻量)**:Uptime Kuma 监控 `https://$DOMAIN/api/health` + TLS 证书<21天告警;`df` systemd timer >75% 告警(单机头号宕机源);Sentry 免费档前后端异常 [应做]。
- **Cloudflare:MVP 不上**(单一建议)。源站直连 + LE certbot,链路最短、无需 realip/ufw 收紧。**若上**(隐藏源站/免费WAF):同时改三处否则误封——nginx `set_real_ip_from <CF段>` + `real_ip_header CF-Connecting-IP`、ufw 80/443 仅放 CF IP 段、CF SSL 设 Full(strict) 源站仍装 LE。进 ⑤ 决策清单。
- **成本量级**:VPS 4C/8G(MVP 4G 可跑,8G 给编辑器+pull 余量)Hetzner ~€15 / DO·Vultr ~$24-48;域名 ~$1-2;异地备份 <$1;监控 $0。**MVP ~$20-50/月**。AI 变动成本本次不涉及。

---

## ④ 分阶段步骤(每步验收)

**阶段 0 — 代码前置 gating(本地,部署前必须完成)**
1. main.py 原子写改造(save_geometry/save_furniture/create_project + .bak)。验收:本地 `kill -9` 渲染中进程后,geometry.json 仍是完整旧版,不被截断。
2. main.py /api/health 升级真实探活(DATA_DIR 可写 + import floorplan_core + readonly 字段)。验收:`curl /api/health` 返 `{"ok":true,"readonly":false}`;手动设只读目录返 503。
3. main.py delete_project 软删到 `.trash`。验收:删除后文件进 `.trash`,可恢复。
4. web page.tsx MVP D-only(隐藏新建/删除)。验收:首页无创建/删除入口,无法 push 到 E/editor。
5. 改写 api Dockerfile + 新建 web Dockerfile + `.dockerignore`。验收:`docker build` 上下文 < 10MB 且不含 .env/mp4(本地干跑,不在 VPS)。

**阶段 1 — 本地 compose 冒烟(本地,不动 dev)**
6. 用临时端口起 compose(避开 dev),seed 一份 D 数据到本地 bind 目录并 `chown 10001`。验收:① 浏览器 `/studio/projects/D/editor` 可开;② **真做一次 save-geometry,确认文件 mtime 变化**(验证 uid10001 可写,#4);③ `/_next/static` 长缓存、HTML no-store、curl -I 看到 CSP+HSTS(#18);④ console 0 CSP violation(含 fbcdn 图,#5);⑤ kill api → 自动重启 → 端到端恢复。

**阶段 2 — VPS 首次部署**
7. `bootstrap-vps.sh`:创建 deploy 用户+公钥、ufw、sshd 加固、swap、`mkdir -p /srv/grandtianfu/data/projects && chown -R 10001:10001`。验收:仅密钥可登、`ufw status` 仅 22/80/443。
8. seed D 数据到 `/srv/grandtianfu/data/projects` 并 `chown 10001`;CI 推镜像到 GHCR;VPS `docker login --password-stdin` + `deploy.sh`(暂用 bootstrap conf,无 TLS)。验收:`exec -T api curl http://localhost:8000/api/health` 通过。

**阶段 3 — TLS 冷启动(#3 #24)**
9. `init-letsencrypt.sh`:先在 `live/<domain>` 放**自签占位证书**让 nginx 带 443 块正常启动 → `--profile certbot` webroot **先 --dry-run** 再正式签发 → 删占位换真证书 → `nginx -t && nginx -s reload`。续期:**唯一机制** = 宿主 systemd timer `certbot renew --deploy-hook 'nginx -t && nginx -s reload'`(丢弃 sidecar loop / nginx command 覆盖)。验收:`curl -fsS --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/api/health` 200;SSL Labs ≥A。

**阶段 4 — 上线核对 checklist**
10. ☐ GEOM_READONLY 为空(/api/health readonly:false);☐ save-geometry 线上真写成功;☐ DELETE 经 nginx 返 403/405;☐ Basic Auth 生效且 /api/health 放行;☐ 备份 timer 跑通且**异地有对象**;☐ **restore-test 真恢复+diff 通过并记录 RTO**;☐ 限流生效;☐ console 0 CSP violation;☐ deploy.sh 健康门禁+回滚演练过一次;☐ 证书到期监控告警接通。

---

## ⑤ 用户须提供/须决策清单

**阻塞执行(必须先给):**
1. **VPS**:规格(建议 8G/≥80G NVMe;4G 可跑)、IP、root/sudo 初始访问方式。
2. **域名**:`studio.example.com` 实际域名(填 server_name/证书)+ DNS A 记录指向 VPS。
3. **GHCR**:GitHub owner/仓库名 + GHCR token(填 compose image: 与 CI secrets `VPS_HOST/VPS_SSH_KEY`)。
4. **异地备份目标**:R2/S3 bucket + rclone 凭据(MVP 必需,缺则备份不达标)。
5. **certbot 邮箱**:LE 到期通知。

**须决策(影响配置,非全阻塞):**
6. **是否鉴权**:建议 MVP 用 nginx Basic(默认采纳);需多用户/审计则升 Authelia(分期)。提供 Basic 口令或由部署方生成。
7. **Cloudflare 上不上**:建议**不上**;若要隐藏源站/免费 WAF 则上,需补 realip+ufw 仅放 CF 段+SSL Full strict。
8. **22 是否限源**:有固定管理 IP 则限源;无则仅密钥+fail2ban 或 Tailscale。
9. **create/delete 取舍**:MVP 默认 D-only 隐藏入口;若必须支持多项目创建,需改路 B(node 容器,真动态 [id])或把 editor 改单一非动态路由+query 取 id(分期决策)。
10. **age 备份加密**:启用则须确认私钥托管方案(私钥不上 VPS)。

---

## ⑥ 风险 + 复杂度 + 不必做

**风险(残留,均已给缓解):**
- [Med] mem_limit 是未压测的估值 → 上线前压 render p99 校准;监控 OOMKilled。
- [Med] 路A 下 create/delete 已隐藏,但 API 仍可达 → nginx 边缘拦 DELETE + 代码软删兜底。
- [Med] Basic 单口令=全量删改权 → 配套原子写+实测备份;文档化口令轮换。
- [Low] CSP `unsafe-inline` 是路A 固有弱化 → 转路B 才能收 nonce(分期);上线前 console 实测 0 violation。
- [Low] 多户型深链 404 = 路A 边界 → MVP D-only 规避。

**复杂度:整体 Med。** api Dockerfile 改写 + compose/nginx = Low-Med;原子写/软删/health 代码改 = Low(但 gating);TLS 冷启动 = Med(易踩,已脚本化);CI/CD = Med。

**不必做 / 暂不做(防过度,严守不引入未需组件):**
- 多机 / k8s / 负载均衡(单 VPS 单点即满足 MVP)。
- redis / rq-worker / postgres / egress 双网卡 / WAL-PITR(AI #6 落地再加)。
- 自建 AI / 模型服务(#4/#6/#7 未实现,本次不涉及)。
- Grafana/Loki/Prometheus 全栈监控(Uptime Kuma+Sentry+df 足够 MVP)。
- 上传防护(剥 SVG 脚本/魔术字节/独立 uploads 卷)= 上传功能落地再做。
- CSP nonce 收紧、staging 环境、OCSP must-staple(分期)。

---

**等用户确认本计划、并提供 ⑤ 中阻塞项(VPS / 域名 / GHCR / 异地备份目标 / certbot 邮箱)后,再进入实际落盘与部署执行。本工作流到此只产出计划,未执行任何 build/部署、未改动 dev 服务。**

相关绝对路径(待创建/待改):`/Users/yixingzhou/project/grandtianfu/apps/api/{Dockerfile,main.py}`、`/Users/yixingzhou/project/grandtianfu/apps/web/{Dockerfile,src/app/studio/projects/page.tsx}`、`/Users/yixingzhou/project/grandtianfu/.dockerignore`、`/Users/yixingzhou/project/grandtianfu/.github/workflows/deploy.yml`、`/Users/yixingzhou/project/grandtianfu/deploy/**`(compose/nginx/tls/scripts/systemd/fail2ban/.env.example)。