#!/usr/bin/env bash
# 备份活数据 (#9 #12 #21): tar /srv/grandtianfu/data/projects -> 异地对象存储 (R2/S3, MVP 必需)。
# BACKUP_REMOTE 缺失 -> 报错退出 + 非零码 (不静默跳过, 否则"以为有备份"是最危险的假象)。
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/
[ -f .env ] && set -a && . ./.env && set +a

DATA_DIR="${BACKUP_SRC:-/srv/grandtianfu/data/projects}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE 未配置 (如 r2:grandtianfu-backup); MVP 异地备份必需, 拒绝静默跳过}"

TS="$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
ARCHIVE="$WORK/grandtianfu-data-$TS.tar.gz"

echo "[backup] 打包 $DATA_DIR -> $ARCHIVE"
tar -czf "$ARCHIVE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"

echo "[backup] 校验本地归档可解 (防坏包)"
tar -tzf "$ARCHIVE" >/dev/null

echo "[backup] 推送异地: $BACKUP_REMOTE"
# rclone 需预配置 remote (桶开版本化/对象锁防勒索)。
rclone copy "$ARCHIVE" "$BACKUP_REMOTE/" --no-traverse

echo "[backup] 完成: $(basename "$ARCHIVE") -> $BACKUP_REMOTE"
