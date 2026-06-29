#!/usr/bin/env bash
# VPS 部署: pull 指定 TAG 镜像 -> up -d (web-static 原子发布) -> 健康门禁 -> 失败回滚。
# 由 CI 经 SSH 调用: TAG=<git-sha> deploy.sh。VPS 永不构建, 只 pull。
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/
[ -f .env ] && set -a && . ./.env && set +a

: "${TAG:?需设 TAG=<git-sha>}"
: "${GHCR_OWNER:?需设 GHCR_OWNER}"
COMPOSE="docker compose -f docker-compose.prod.yml"
export TAG GHCR_OWNER

echo "[deploy] pull TAG=$TAG"
$COMPOSE pull api web-static

echo "[deploy] up -d (api 健康 + web-static 发布完成后再起 nginx)"
$COMPOSE up -d

echo "[deploy] 健康门禁 (绕 TLS+Basic, 容器内直探 api)"
ok=0
for i in $(seq 1 30); do
  if $COMPOSE exec -T api curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 2
done

if [ "$ok" != "1" ]; then
  echo "[deploy] 健康门禁失败 -> 回滚"
  ./scripts/rollback.sh
  exit 1
fi

echo "$TAG" > .last_good_tag
echo "[deploy] 成功, 记录 .last_good_tag=$TAG"
