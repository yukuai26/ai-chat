---
entity: ac
descriptor: architecture
version: "1.0"
status: ACTIVE
created: "2026-05-26"
---

# ac-architecture — 系统架构文档

## 整体架构

```
┌──────────────────────────────────────────────────────────┐
│                        用户浏览器                          │
│                   (https://域名)                           │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTPS
                       ▼
┌──────────────────────────────────────────────────────────┐
│                Cloudflare Tunnel (trycloudflare)           │
│                出站隧道，无需开端口                          │
└──────────────────────┬───────────────────────────────────┘
                       │
                       ▼  localhost:8080
┌──────────────────────────────────────────────────────────┐
│                        nginx                              │
│  ├── /              → /var/www/chat/index.html (公开)     │
│  └── /v1/*          → proxy_pass 127.0.0.1:18789 (需Token) │
└──────────┬───────────────────────────────────────────────┘
           │
           ▼  127.0.0.1:18789
┌──────────────────────────────────────────────────────────┐
│                  OpenClaw Gateway                          │
│  HTTP API: /v1/chat/completions                           │
│  Auth: Token (e0fb40ce...)                                │
│  Model: openclaw:assistant → DeepSeek V4 Pro              │
│  Thinking: high                                           │
└──────────────────────────────────────────────────────────┘
```

## 认证流

```
1. 用户打开网页 → nginx 返回 index.html（无认证）
2. 用户在页面输入 Token → 存储在浏览器 localStorage
3. 用户发消息 → 页面 fetch /v1/chat/completions
4. nginx 透明转发 → Gateway（携带 Authorization: Bearer TOKEN）
5. Gateway 验证 Token → 执行 Agent → 返回结果
6. nginx 透传结果 → 浏览器
```

## 关键配置

| 组件 | 配置 |
|------|------|
| Gateway | 127.0.0.1:18789, auth.mode=token |
| nginx | 0.0.0.0:8080, sites-available/chat |
| cloudflared | --url http://localhost:8080 --no-autoupdate |
| Token | e0fb40cef753818c92577e3c8fe2af53 |

## 依赖的 OpenClaw 配置

| 文件 | 用途 |
|------|------|
| `~/.openclaw/openclaw.json` | Gateway 配置（端口、认证、agents） |
| `~/.openclaw/agents/assistant/agent/models.json` | 模型定义 |
| `~/.openclaw/agents/assistant/agent/SOUL.md` | Agent 角色 |

## 网络流

```
出站：cloudflared → Cloudflare Edge → 用户
入站：无（所有请求通过出站隧道回传）
安全组：无需改动（只开放 SSH 22）
```

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-05-26 | 初始架构文档 |
