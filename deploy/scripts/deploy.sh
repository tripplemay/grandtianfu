#!/usr/bin/env bash
# VPS 部署 (共享生产主机模型): GHCR 登录 -> pull 指定 TAG -> up -d -> loopback 健康门禁。
# 宿主 nginx/certbot 接管 TLS, 本脚本只管两容器 (api/web)。VPS 永不构建, 只 pull。
# 由 CI 经 SSH 调用: cd /opt/grandtianfu && TAG=<git-sha> ./scripts/deploy.sh
set -euo pipefail

cd /opt/grandtianfu
# CI/人工调用方显式传入的 TAG 必须优先于 .env 默认值；否则 .env 中 TAG=latest
# 会覆盖提交 SHA，导致部署不可追踪且 .last_good_tag 无法用于确定性回滚。
REQUESTED_TAG="${TAG-}"
[ -f .env ] && set -a && . ./.env && set +a
if [ -n "$REQUESTED_TAG" ]; then
  TAG="$REQUESTED_TAG"
fi

: "${TAG:?需设 TAG=<git-sha>}"
: "${GHCR_OWNER:?需设 GHCR_OWNER}"
COMPOSE="docker compose -f docker-compose.prod.yml"
export TAG GHCR_OWNER

# GHCR 只读登录 (私有镜像必需; GHCR_TOKEN 留空则跳过, 视镜像为公开)。
if [ -n "${GHCR_TOKEN:-}" ]; then
  echo "[deploy] docker login ghcr.io"
  echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:-$GHCR_OWNER}" --password-stdin
fi

echo "[deploy] pull TAG=$TAG"
$COMPOSE pull

echo "[deploy] up -d (api + web)"
$COMPOSE up -d

echo "[deploy] loopback 健康门禁 (宿主直探 api:8021, 绕 TLS+Basic)"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8021/api/health >/dev/null 2>&1; then
    ok=1; break
  fi
  sleep 2
done

if [ "$ok" != "1" ]; then
  echo "[deploy] 健康门禁失败 -> 回滚到 .last_good_tag"
  if [ -f .last_good_tag ]; then
    TAG="$(cat .last_good_tag)" $COMPOSE up -d
  fi
  exit 1
fi

echo "[deploy] default scene 校验门禁"
python3 - <<'PY'
import json
import sys
import urllib.request

url = "http://127.0.0.1:8021/api/projects/D/scene"
with urllib.request.urlopen(url, timeout=10) as res:
    body = json.loads(res.read().decode("utf-8"))
validation = body.get("validation") or {}
if not validation.get("ok"):
    print("[deploy] default scene validation failed", file=sys.stderr)
    for issue in validation.get("errors", [])[:20]:
        print(f"  - {issue.get('code')}: {issue.get('message')}", file=sys.stderr)
    raise SystemExit(1)
print(
    "[deploy] default scene ok "
    f"errors={len(validation.get('errors', []))} "
    f"warnings={len(validation.get('warnings', []))} "
    f"adjustments={len(validation.get('adjustments', []))}"
)
PY

echo "$TAG" > .last_good_tag
echo "[deploy] 成功, 记录 .last_good_tag=$TAG"
