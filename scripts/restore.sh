#!/bin/bash
# /home/ubuntu/.openclaw/scripts/restore.sh [日期/commit]
# 从 backup 分支恢复到指定日期的备份
# TODO: BK3 — restore.sh 实现

set -e
REPO_DIR=${BACKUP_REPO_DIR:-/home/ubuntu/.openclaw/backup-repo}
TARGET=${1:-""}

usage() {
  echo "用法: restore.sh <日期|commit-hash>"
  echo "示例: restore.sh 2026-05-27"
  echo "      restore.sh abc1234"
  echo ""
  echo "可用备份:"
  cd "$REPO_DIR" 2>/dev/null && git log --oneline --since="2026-01-01" 2>/dev/null | head -20 || echo "  （备份仓库未初始化）"
  exit 1
}

[ -z "$TARGET" ] && usage

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "❌ 备份仓库不存在: $REPO_DIR"
  echo "   请先执行 backup.sh 初始化"
  exit 1
fi

cd "$REPO_DIR"

echo "[restore] 🔄 拉取最新备份..."
git fetch origin backup
git checkout backup
git pull origin backup 2>/dev/null || true

# 查找匹配的 commit
COMMIT=$(git log --oneline --grep="$TARGET" --format="%H" | head -1)
if [ -z "$COMMIT" ]; then
  COMMIT=$(git rev-parse "$TARGET" 2>/dev/null || echo "")
fi

if [ -z "$COMMIT" ]; then
  echo "❌ 找不到备份: $TARGET"
  echo "可用列表:"
  git log --oneline --since="2026-01-01" | head -20
  exit 1
fi

echo "[restore] 📋 即将恢复:"
echo "    commit: $COMMIT"
echo "    描述:   $(git log -1 --format='%s' "$COMMIT")"
echo "    日期:   $(git log -1 --format='%ci' "$COMMIT")"
echo ""
echo "⚠️  警告：此操作将覆盖当前数据！"

# 非交互式时通过 RESTORE_CONFIRM 环境变量确认
if [ "${RESTORE_CONFIRM:-}" = "yes" ]; then
  echo "[restore] 自动确认（RESTORE_CONFIRM=yes）"
else
  read -p "    确认恢复? [y/N] " CONFIRM
  if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "[restore] 已取消"
    exit 0
  fi
fi

git checkout "$COMMIT"

echo "[restore] 📥 恢复中..."

# rsync 恢复到源目录
rsync -a ./workspace-assistant/ /home/ubuntu/.openclaw/workspace-assistant/ 2>/dev/null || true
rsync -a ./workspace-build-cat/ /home/ubuntu/.openclaw/workspace-build-cat/ 2>/dev/null || true
rsync -a ./user-data/   /home/ubuntu/.openclaw/user-data/ 2>/dev/null || true
rsync -a ./user-sessions/ /home/ubuntu/.openclaw/user-sessions/ 2>/dev/null || true
rsync -a ./user-files/  /home/ubuntu/.openclaw/user-files/ 2>/dev/null || true
rsync -a ./web-app/     /var/www/chat/ 2>/dev/null || true

# 恢复服务器配置
cp ./server-config/nginx-chat.conf /etc/nginx/sites-available/chat 2>/dev/null || true
cp ./server-config/fileserver.service /etc/systemd/system/ 2>/dev/null || true

# 重启服务
echo "[restore] 🔄 重启服务..."
systemctl restart fileserver 2>/dev/null || true
systemctl reload nginx 2>/dev/null || true

echo "[restore] ✅ 已恢复到 $(git log -1 --format='%s (%ci)')"
