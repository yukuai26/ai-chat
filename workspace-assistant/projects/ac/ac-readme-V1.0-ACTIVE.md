---
entity: ac
descriptor: readme
version: "1.0"
status: ACTIVE
project: assistant-chat
manager: 管理员
created: "2026-05-26"
---

# Assistant Web Chat — 项目总览

| 字段 | 值 |
|------|-----|
| 项目名 | assistant-chat (小助手 Web Chat) |
| 负责人 | 管理员 |
| 创建时间 | 2026-05-26 |
| 状态 | 🟢 开发中 |
| 当前阶段 | Phase 0.2 — 稳定性加固 |
| 预计完成 | 2026-06-03 |
| 实际上线 | 2026-05-26 (MVP) |
| 最新部署 | 2026-05-26 17:33 |

## 项目目标
构建可公开访问的 Web AI 聊天系统，管理员和受信任用户无需飞书即可对话。

## 当前待完成
- [ ] cloudflared systemd 服务（高优先级）
- [ ] 购买域名绑定
- [ ] Gateway restart 卡住排查
- [ ] 安全加固（rate limiting）
- [ ] 健康监控脚本
- [ ] 会话历史 localStorage

## 项目文件索引
| 文件 | 用途 |
|------|------|
| `ac-project-plan-V1.0-ACTIVE.md` | 完整项目规划 |
| `ac-risk-register-V1.0-ACTIVE.md` | 风险评估 |
| `ac-issues-V1.0-ACTIVE.md` | 问题追踪 |
| `ac-work-log-V1.0-ACTIVE.md` | 工作日志 |
| `tech/ac-architecture-V1.0-ACTIVE.md` | 系统架构 |

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-05-26 | 初始创建，继承原 README.md 内容 |
