# 备份系统设计文档

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

防止 AI 发癫删数据，所有用户数据 + 记忆 + 配置每天自动备份到 Git。

- **备份仓库**：`yukuai26/ai-chat` 的 `backup` 分支
- **频率**：每天 23:59
- **两个脚本**：`backup.sh`（存） + `restore.sh`（取）

## 二、备份内容

| 数据 | 路径 | 备份 |
|------|------|:--:|
| 用户 Dashboard 数据 | `/home/ubuntu/.openclaw/user-data/` | ✅ |
| 用户会话 | `/home/ubuntu/.openclaw/user-sessions/` | ✅ |
| 用户文件 | `/home/ubuntu/.openclaw/user-files/` | ⚠️ ≤5MB |
| 管理员记忆 | `workspace-assistant/MEMORY.md` | ✅ |
| 每日日记 | `workspace-assistant/memory/` | ✅ |
| 设计文档 | `workspace-assistant/projects/` | ✅ |
| SOP + 注册表 | `workspace-assistant/sops/`, `system/` | ✅ |
| Build喵 工作区 | `workspace-build-cat/`（精简） | ✅ |
| 网页源码 | `/var/www/chat/` | ✅ |
| 服务器配置 | nginx + systemd | ✅ |
| API Token / 密钥 | — | ❌ 不进 git |
| node_modules / venv | — | ❌ 可重建 |

## 三、脚本一：backup.sh（储存备份）

```bash
#!/bin/bash
# /home/ubuntu/.openclaw/scripts/backup.sh
# 每天 23:59 cron 执行，把数据提交到 backup 分支

set -e
REPO_DIR=/home/ubuntu/.openclaw/backup-repo
DATE=$(date +%Y-%m-%d_%H%M)

# 初始化（仅首次）
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone --branch backup --single-branch git@github.com:yukuai26/ai-chat.git "$REPO_DIR" 2>/dev/null || {
    git clone git@github.com:yukuai26/ai-chat.git "$REPO_DIR"
    cd "$REPO_DIR"
    git checkout --orphan backup
    git rm -rf .
    git commit --allow-empty -m "init backup branch"
    git push -u origin backup
  }
fi

cd "$REPO_DIR"

# 清空工作区（保留 .git）
find . -mindepth 1 -not -path './.git/*' -not -name '.git' -delete

# rsync 同步
rsync -a --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/'   --exclude 'media/inbound/' --exclude '*.log' --exclude '*.jsonl'   /home/ubuntu/.openclaw/workspace-assistant/{MEMORY.md,memory,projects,sops,system}   ./workspace-assistant/

rsync -a /home/ubuntu/.openclaw/workspace-build-cat/{memory,logs} ./workspace-build-cat/
rsync -a /home/ubuntu/.openclaw/user-data/   ./user-data/
rsync -a /home/ubuntu/.openclaw/user-sessions/ ./user-sessions/
rsync -a --max-size=5M /home/ubuntu/.openclaw/user-files/ ./user-files/
rsync -a /var/www/chat/index.html ./web-app/
rsync -a /home/ubuntu/.openclaw/gateway/scripts/fileserver.py ./web-app/ 2>/dev/null || true

# nginx + systemd 配置
mkdir -p ./server-config
cp /etc/nginx/sites-available/chat ./server-config/nginx-chat.conf 2>/dev/null || true
cp /etc/systemd/system/fileserver.service ./server-config/ 2>/dev/null || true

# commit + push
git add -A
git diff --cached --quiet || git commit -m "backup: $DATE"
git push origin backup
```

## 四、脚本二：restore.sh（切到某天备份）

```bash
#!/bin/bash
# /home/ubuntu/.openclaw/scripts/restore.sh [日期/commit-hash]
# 恢复到指定日期的备份

set -e
REPO_DIR=/home/ubuntu/.openclaw/backup-repo
TARGET=${1:-""}

if [ -z "$TARGET" ]; then
  echo "用法: restore.sh <日期|commit>"
  echo "示例: restore.sh 2026-05-27"
  echo "      restore.sh abc1234"
  echo ""
  echo "可用备份:"
  cd "$REPO_DIR" && git log --oneline --since="2026-01-01" | head -20
  exit 1
fi

cd "$REPO_DIR"
git fetch origin backup
git checkout backup
git pull origin backup

# 查找匹配日期的 commit
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

git checkout "$COMMIT"

echo "⚠️  即将恢复到备份: $(git log -1 --format='%s')"
echo "    日期: $(git log -1 --format='%ci')"
read -p "    确认恢复? [y/N] " CONFIRM

if [ "$CONFIRM" != "y" ]; then
  echo "已取消"
  exit 0
fi

# rsync 恢复到源目录
rsync -a ./workspace-assistant/ /home/ubuntu/.openclaw/workspace-assistant/
rsync -a ./workspace-build-cat/ /home/ubuntu/.openclaw/workspace-build-cat/
rsync -a ./user-data/   /home/ubuntu/.openclaw/user-data/
rsync -a ./user-sessions/ /home/ubuntu/.openclaw/user-sessions/
rsync -a ./user-files/  /home/ubuntu/.openclaw/user-files/
rsync -a ./web-app/     /var/www/chat/
cp ./server-config/nginx-chat.conf /etc/nginx/sites-available/chat 2>/dev/null || true
cp ./server-config/fileserver.service /etc/systemd/system/ 2>/dev/null || true

# 重启受影响的服务
systemctl restart fileserver 2>/dev/null || true
systemctl reload nginx 2>/dev/null || true

echo "✅ 已恢复到 $(git log -1 --format='%s (%ci)')"
```

## 五、定时任务

```
cron: 59 23 * * * → /home/ubuntu/.openclaw/scripts/backup.sh
```

## 六、安全保护

- `backup` 分支与 `main` 完全独立，不影响网页部署
- `force push` 只有 backup.sh 触发，我不直接操作 backup 分支
- `restore.sh` 需要手动确认才能执行
- Token/密钥不进备份

## 七、TODO

| # | TODO | 状态 |
|---|------|:----:|
| BK1 | 初始化 backup 分支：`git checkout --orphan backup` | [x] |
| BK2 | 实现 backup.sh（rsync + git commit + push） | [x] |
| BK3 | 实现 restore.sh（按日期查 commit + 确认恢复） | [x] |
| BK4 | 设置 cron 每天 23:59 执行 backup.sh | [x] |
| BK5 | 测试备份-恢复完整流程 | [x] |

## 八、进度追踪

| 项 | 状态 |
|----|:--:|
| 备份系统 | ✅ 已完成 |
