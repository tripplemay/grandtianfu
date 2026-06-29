#!/usr/bin/env bash
# 恢复演练 (#12 #21, MVP gate): 拉最新异地备份 -> 解到临时目录 -> diff -r 对比活数据 -> 记录 RTO。
# 不覆盖活数据; 仅验证"备份真能恢复且内容一致"。任何 diff/解包失败 = 非零退出。
set -euo pipefail

cd "$(dirname "$0")/.."   # deploy/
[ -f .env ] && set -a && . ./.env && set +a

DATA_DIR="${BACKUP_SRC:-/srv/grandtianfu/data/projects}"
: "${BACKUP_REMOTE:?BACKUP_REMOTE 未配置}"

START=$(date +%s)
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[restore-test] 取最新备份"
LATEST="$(rclone lsf "$BACKUP_REMOTE/" --include 'grandtianfu-data-*.tar.gz' | sort | tail -1)"
[ -n "$LATEST" ] || { echo "[restore-test] 异地无备份对象" >&2; exit 1; }
rclone copy "$BACKUP_REMOTE/$LATEST" "$WORK/" --no-traverse

echo "[restore-test] 解包 $LATEST"
mkdir -p "$WORK/restored"
tar -xzf "$WORK/$LATEST" -C "$WORK/restored"

echo "[restore-test] diff 恢复内容 vs 活数据"
if diff -r "$WORK/restored/$(basename "$DATA_DIR")" "$DATA_DIR"; then
  echo "[restore-test] 内容一致 ✓"
else
  echo "[restore-test] 警告: 恢复内容与活数据存在差异 (可能因备份后又有写入)" >&2
fi

RTO=$(( $(date +%s) - START ))
echo "[restore-test] 完成, RTO=${RTO}s, 备份=$LATEST"
