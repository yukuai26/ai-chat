#!/bin/bash
# /home/ubuntu/.openclaw/scripts/backup.sh
# 每天 23:59 执行，把关键数据备份到 backup 分支
# TODO: BK1 — 初始化 backup 分支
# TODO: BK2 — backup.sh 实现

set -e
REPO_DIR=${BACKUP_REPO_DIR:-/home/ubuntu/.openclaw/backup-repo}
DATE=$(date +%Y-%m-%d_%H%M)

# ---- 初始化 backup 分支（仅首次） ----
init_backup_branch() {
  if [ -d "$REPO_DIR/.git" ]; then
    echo "[backup] 备份仓库已存在，跳过初始化"
    return 0
  fi

  echo "[backup] 🔧 首次运行：初始化 backup 分支..."
  mkdir -p "$(dirname "$REPO_DIR")"

  # 尝试 clone backup 分支；不存在则创建
  git clone --branch backup --single-branch git@github.com:yukuai26/ai-chat.git "$REPO_DIR" 2>/dev/null || {
    git clone git@github.com:yukuai26/ai-chat.git "$REPO_DIR"
    cd "$REPO_DIR"
    git checkout --orphan backup
    git rm -rf . 2>/dev/null || true
    git commit --allow-empty -m "init backup branch"
    echo "[backup] ✅ backup 分支已创建 → push"
    git push -u origin backup
  }
}

init_backup_branch

cd "$REPO_DIR"

# ---- 清空工作区（保留 .git） ----
echo "[backup] 清理旧文件..."
find . -mindepth 1 -not -path './.git/*' -not -name '.git' -delete 2>/dev/null || true

# ---- rsync 同步 ----
echo "[backup] 📦 同步数据..."

# workspace-assistant（核心）
rsync -a --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' \
  --exclude 'media/inbound/' --exclude '*.log' --exclude '*.jsonl' \
  /home/ubuntu/.openclaw/workspace-assistant/{MEMORY.md,memory,projects,sops,system} \
  ./workspace-assistant/ 2>/dev/null || echo "[backup] ⚠️ workspace-assistant 部分路径不存在"

# workspace-build-cat（精简）
rsync -a /home/ubuntu/.openclaw/workspace-build-cat/{memory,logs} ./workspace-build-cat/ 2>/dev/null || echo "[backup] ⚠️ workspace-build-cat 部分路径不存在"

# user 数据
rsync -a /home/ubuntu/.openclaw/user-data/ ./user-data/ 2>/dev/null || echo "[backup] ⚠️ user-data 目录不存在"
rsync -a /home/ubuntu/.openclaw/user-sessions/ ./user-sessions/ 2>/dev/null || echo "[backup] ⚠️ user-sessions 目录不存在"
rsync -a --max-size=5M /home/ubuntu/.openclaw/user-files/ ./user-files/ 2>/dev/null || echo "[backup] ⚠️ user-files 目录不存在"

# web-app
rsync -a /var/www/chat/index.html ./web-app/ 2>/dev/null || echo "[backup] ⚠️ web-app 不存在"
rsync -a /home/ubuntu/.openclaw/gateway/scripts/fileserver.py ./web-app/ 2>/dev/null || true

# 服务器配置
mkdir -p ./server-config
cp /etc/nginx/sites-available/chat ./server-config/nginx-chat.conf 2>/dev/null || true
cp /etc/systemd/system/fileserver.service ./server-config/ 2>/dev/null || true

# ---- commit + push ----
echo "[backup] 📝 提交..."
git add -A

if git diff --cached --quiet; then
  echo "[backup] ℹ️ 无变更，跳过提交"
else
  git commit -m "backup: $DATE"
  echo "[backup] ✅ 提交完成: backup: $DATE"
fi

echo "[backup] 🚀 push..."
git push origin backup
echo "[backup] 🎉 备份完成！"
