#!/usr/bin/env bash
# 回滚到上一次健康通过的镜像 tag (.last_good_tag)。
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/
[ -f .env ] && set -a && . ./.env && set +a

: "${GHCR_OWNER:?需设 GHCR_OWNER}"
if [ ! -f .last_good_tag ]; then
  echo "[rollback] 无 .last_good_tag, 无法回滚" >&2
  exit 1
fi
TAG="$(cat .last_good_tag)"
export TAG GHCR_OWNER
COMPOSE="docker compose -f docker-compose.prod.yml"

echo "[rollback] 回滚到 TAG=$TAG"
$COMPOSE pull api web-static
$COMPOSE up -d
echo "[rollback] 完成 (TAG=$TAG)"
