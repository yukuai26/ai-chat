---
entity: ac
descriptor: changes
version: "1.0"
status: ACTIVE
created: "2026-05-26"
---

# 变更记录

## 2026-05-26 架构调整：Canvas → nginx
- **变更内容**：聊天网页托管从 Gateway Canvas 改为 nginx
- **变更原因**：Canvas 路由对所有非本地请求要求认证（返回 401），无法公开访问
- **影响范围**：部署流程、网页访问路径、Tunnel 代理目标端口（18789 → 8080）
- **确认人**：管理员

## 2026-05-26 架构调整：GitHub Pages → 同源方案
- **变更内容**：取消 GitHub Pages 托管，改为同源方案
- **变更原因**：GitHub Pages 跨域请求 Gateway API 被 CORS 拦截
- **影响范围**：网页部署方式
- **确认人**：管理员

## 2026-05-26 推理模式启用
- **变更内容**：thinkingDefault 设为 "high"
- **变更原因**：管理员要求启用推理模式
- **影响范围**：DeepSeek V4 Pro 回复质量提升
- **确认人**：管理员

## 2026-05-26 初始搭建
- **变更内容**：Cloudflare Tunnel + Gateway API + nginx + 网页
- **变更原因**：项目启动
- **影响范围**：全部新功能
- **确认人**：管理员

## 2026-06-09 修复：恢复 Dashboard 卡片页指令输入框
- **问题**：`#tab-daily` 内的 `dashboard-command-bar`（与卡片喵对话的指令框）HTML 元素被误删（疑似 6/2~6/9 改股票/量化卡片时），CSS 与 JS 完好仅缺 DOM
- **修复**：补回 8 行 HTML（cmdHint/cmdAttachBtn/cmdInput/cmdSend），位置在 cmdFileTags 之后
- **设计一致性**：本次为回归修复，使代码重新对齐既有设计基线（命令栏本就是设计的一部分），无新增设计
- commit: 30e40fa
