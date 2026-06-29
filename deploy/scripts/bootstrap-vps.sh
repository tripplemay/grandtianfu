#!/usr/bin/env bash
# VPS 首次主机加固 (#4): deploy 用户 + ufw + sshd 加固 + swap + 数据目录 chown 10001。
# 以 root 运行一次。确认密钥可登再 reload sshd (否则可能把自己锁外)。
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
DATA_DIR="${DATA_DIR:-/srv/grandtianfu/data/projects}"
SWAP_GB="${SWAP_GB:-2}"

echo "[1/6] 创建 deploy 用户 (docker 组)"
id "$DEPLOY_USER" &>/dev/null || useradd -m -s /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER" || true
echo ">>> 请手动把部署公钥写入 /home/$DEPLOY_USER/.ssh/authorized_keys 并 chmod 600"

echo "[2/6] ufw: default deny incoming, 放行 22/80/443"
if command -v ufw >/dev/null; then
  ufw --force default deny incoming
  ufw --force default allow outgoing
  ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp
  ufw --force enable
  ufw status
fi

echo "[3/6] sshd 加固 (PermitRootLogin no / PasswordAuthentication no)"
SSHD=/etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' "$SSHD"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD"
echo ">>> 确认 $DEPLOY_USER 可用密钥登录后, 手动执行: systemctl reload sshd"

echo "[4/6] swap ${SWAP_GB}G (兜底渲染峰值 OOM)"
if [ ! -f /swapfile ]; then
  fallocate -l "${SWAP_GB}G" /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

echo "[5/6] 数据目录 + chown 10001 (与容器 appuser uid 对齐, 保证 save 可写)"
mkdir -p "$DATA_DIR"
chown -R 10001:10001 "$DATA_DIR"

echo "[6/6] docker 开机自启 (宿主重启自动拉起栈)"
systemctl enable docker || true

echo "完成。reload sshd 前请务必确认密钥登录可用。"
