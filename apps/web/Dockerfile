# 阅天府 web 镜像 (共享生产主机模型: Next 静态导出 -> 烤进 nginx:alpine, 镜像即版本)。
# 构建上下文 = monorepo 根 (docker build -f apps/web/Dockerfile .)。
# 两阶段: builder 在容器内 yarn build:export 出 out/; runtime 把 out/ 直接 COPY 进
# nginx:alpine, 自带最小 nginx.conf (listen 8080)。镜像内 nginx 仅服静态、不反代 /api
# (/api 由宿主 nginx 路由到 api 容器)。回滚 = 换 tag, 不再用 publisher/软链方案。

# ---- builder ----
# node:22 (部分传递依赖如 @mapbox/jsonlint-lines-primitives 要求 engine node>=22)。
FROM node:22-bookworm-slim AS builder
WORKDIR /app
# 先装依赖 (lockfile 已存在, 利用层缓存)。
COPY apps/web/package.json apps/web/yarn.lock apps/web/.npmrc ./
RUN yarn install --frozen-lockfile
COPY apps/web/ ./
# 静态导出 -> out/ (NEXT_OUTPUT_EXPORT=1 触发 next.config output:'export';
# 前端数据层 API_BASE='/api' 同源相对路径, 不烤死 origin, 由宿主 nginx 路由)。
RUN NEXT_OUTPUT_EXPORT=1 yarn build:export

# ---- runtime: 静态产物烤进 nginx:alpine ----
FROM nginx:alpine
# 替换默认站点 (默认 listen 80; 本镜像只服静态、listen 8080, 由宿主 nginx 反代)。
RUN rm -f /etc/nginx/conf.d/default.conf
COPY apps/web/nginx.conf /etc/nginx/conf.d/web.conf
COPY --from=builder /app/out /usr/share/nginx/html
EXPOSE 8080
# nginx:alpine 默认 CMD 已是 nginx -g 'daemon off;'
