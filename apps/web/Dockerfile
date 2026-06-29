# 阅天府 web 镜像 (路A: Next 静态导出 -> nginx 托管)。
# 构建上下文 = monorepo 根 (docker build -f apps/web/Dockerfile .)。
# 两阶段: builder 在容器内 yarn build:export 出 out/; publisher 把 out/ 原子发布到
# web_static 卷的 /<sha> 并翻转 current 软链 (绝不 rm 活 docroot), 保留近 3 版防改版后旧 chunk 404。

# ---- builder ----
# node:22 (部分传递依赖如 @mapbox/jsonlint-lines-primitives 要求 engine node>=22)。
FROM node:22-bookworm-slim AS builder
WORKDIR /app
# 先装依赖 (lockfile 已存在, 利用层缓存)。
COPY apps/web/package.json apps/web/yarn.lock ./
RUN yarn install --frozen-lockfile
COPY apps/web/ ./
# 路A 静态导出 -> out/ (NEXT_OUTPUT_EXPORT=1 触发 next.config output:'export')。
RUN NEXT_OUTPUT_EXPORT=1 yarn build:export

# ---- publisher: 原子发布到 /<sha>, 翻转 current 软链, 保留旧版供在途会话/回滚 ----
FROM alpine:3.20 AS publisher
COPY --from=builder /app/out /out
ENV SHA=dev
# 发布器为一次性容器: 复制产物到 /web_static/<sha>, 原子 mv -T 翻 current 软链, 淘汰第 4 版起的旧目录。
# current 用【相对】软链 (-> $SHA, 非 /web_static/$SHA): nginx 把同一卷挂到
# /usr/share/nginx/html, 绝对软链 /web_static/$SHA 在 nginx 容器内不可解析 -> 404;
# 相对软链 current->smoke 在任意挂载点都正确解析。
CMD ["sh", "-c", "\
  D=/web_static/$SHA; rm -rf \"$D\"; mkdir -p \"$D\"; cp -a /out/. \"$D\"/; \
  ln -sfn \"$SHA\" /web_static/.current.tmp && mv -Tf /web_static/.current.tmp /web_static/current; \
  ls -1dt /web_static/*/ 2>/dev/null | grep -v '/current/' | tail -n +4 | xargs -r rm -rf; \
  echo published $SHA"]
