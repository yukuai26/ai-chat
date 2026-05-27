#!/usr/bin/env bash
# setup-fileserver.sh — 安装依赖、部署 systemd 服务、启动 fileserver
# 用法: sudo bash deploy/setup-fileserver.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="$REPO_DIR/fileserver.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "=== BuildCat File Server Setup ==="
echo ""

# 1. 安装 Python 依赖
echo "[1/4] 安装 Python 依赖..."
pip3 install -r "$REPO_DIR/requirements-fileserver.txt"
echo "  依赖安装完成"
echo ""

# 2. 部署 systemd 服务文件
echo "[2/4] 部署 systemd 服务文件..."
cp "$SERVICE_FILE" "$SYSTEMD_DIR/fileserver.service"
chmod 644 "$SYSTEMD_DIR/fileserver.service"
echo "  服务文件已复制到 $SYSTEMD_DIR/fileserver.service"
echo ""

# 3. 重新加载 systemd 并启用服务
echo "[3/4] 启用服务（开机自启）..."
systemctl daemon-reload
systemctl enable fileserver
echo "  服务已启用"
echo ""

# 4. 启动服务
echo "[4/4] 启动服务..."
systemctl restart fileserver
sleep 2
systemctl status fileserver --no-pager
echo ""

# 验证健康检查
echo "=== 验证 ==="
if curl -sf http://127.0.0.1:5050/v1/files/health > /dev/null 2>&1; then
    echo "✅ 健康检查通过 — fileserver 运行正常"
else
    echo "⚠️  健康检查失败，查看日志: journalctl -u fileserver -f"
fi

echo ""
echo "=== 完成 ==="
echo "查看日志: journalctl -u fileserver -f"
echo "停止服务: systemctl stop fileserver"
echo "重启服务: systemctl restart fileserver"
