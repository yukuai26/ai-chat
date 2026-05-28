---
entity: sys
descriptor: web-deploy-sop
version: "1.0"
status: ACTIVE
created: "2026-05-26"
---

# sys-web-deploy-sop — Web Chat 部署标准操作流程

## 触发条件
- 修改聊天网页 HTML/CSS/JS
- 更新 nginx 配置
- 更新 Gateway 配置

## 步骤

### A. 网页更新

1. 修改源文件：`canvas/index.html`
2. 本地测试：`python3 -m http.server 9999` → 浏览器检查
3. 部署：`sudo cp canvas/index.html /var/www/chat/index.html`
4. 验证：`curl -sI http://localhost:8080/`
5. 验证 Tunnel：`curl -sI https://xxx.trycloudflare.com/`

### B. nginx 配置更新

1. 修改：`/etc/nginx/sites-available/chat`
2. 语法检查：`sudo nginx -t`
3. 重载：`sudo systemctl reload nginx`
4. 验证：`curl -sI http://localhost:8080/`

### C. Gateway 配置更新

1. 修改：`~/.openclaw/openclaw.json`
2. JSON 语法检查：`python3 -c "import json; json.load(open('...'))" print('OK')`
3. 重启：`openclaw gateway restart`
4. **如果 restart 失败**：改用 `openclaw gateway status` 诊断，不要重试
5. 验证 API：`curl -X POST localhost:18789/v1/chat/completions ...`

### D. 部署后检查清单
- [ ] nginx 返回 200
- [ ] API 返回 200
- [ ] Tunnel 域名可访问
- [ ] 网页加载正常
- [ ] 对话功能正常
- [ ] 更新 WORK_LOG.md 记录变更
- [ ] 如有故障，记录到 lessons/
