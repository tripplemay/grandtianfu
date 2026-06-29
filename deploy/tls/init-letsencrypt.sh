#!/usr/bin/env bash
# 冷启动一次性引导 TLS (#3 #24): 自签占位 -> nginx 带 443 起 -> certbot webroot 签发 -> 换真证书 reload。
# 仅在 VPS 首次部署运行一次; 续期由宿主 systemd timer `certbot renew` 负责 (非本脚本)。
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/

: "${DOMAIN:?需设 DOMAIN=studio.example.com}"
: "${CERTBOT_EMAIL:?需设 CERTBOT_EMAIL=you@example.com}"
STAGING="${STAGING:-1}"   # 默认先 staging dry-run, 确认通了再 STAGING=0 正式签

COMPOSE="docker compose -f docker-compose.prod.yml"

echo "[1/5] 生成自签占位证书 (让 nginx 443 块能启动)"
$COMPOSE run --rm --entrypoint "\
  sh -c 'mkdir -p /etc/letsencrypt/live/$DOMAIN && \
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
      -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
      -subj /CN=$DOMAIN'" certbot

echo "[2/5] 用 bootstrap conf 起 nginx (仅 80, 放行 ACME)"
# 启用 bootstrap, 暂停正式 conf, 避免 server_name 冲突。
mv -f nginx/conf.d/grandtianfu.conf nginx/conf.d/grandtianfu.conf.disabled 2>/dev/null || true
$COMPOSE up -d nginx

echo "[3/5] certbot 签发 (STAGING=$STAGING)"
STAGING_FLAG=""
[ "$STAGING" = "1" ] && STAGING_FLAG="--staging"
$COMPOSE run --rm certbot certonly --webroot -w /var/www/certbot \
  $STAGING_FLAG --email "$CERTBOT_EMAIL" --agree-tos --no-eff-email \
  --force-renewal -d "$DOMAIN"

echo "[4/5] 切回正式 conf (含 443)"
rm -f nginx/conf.d/grandtianfu.conf.disabled || true
git checkout -- nginx/conf.d/grandtianfu.conf 2>/dev/null || true
mv -f nginx/conf.d/00-bootstrap.conf nginx/conf.d/00-bootstrap.conf.disabled 2>/dev/null || true

echo "[5/5] reload nginx"
$COMPOSE up -d nginx
$COMPOSE exec nginx nginx -t
$COMPOSE exec nginx nginx -s reload

echo "完成。若 STAGING=1 验证通过, 重跑 STAGING=0 获取受信任证书。"
