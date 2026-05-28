---
entity: sys
descriptor: session-startup-sop
version: "1.0"
status: ACTIVE
author: 小助手
created: "2026-05-26"
trigger: "每次新 session 启动"
---

# sys-session-startup-sop — Session 启动标准操作流程

## 目的
确保每次新 session 都能快速恢复上下文，知道之前干了什么、还需要干什么。

## 步骤

### 1. 读取身份文件（必需）
```
按序读取：SOUL.md → USER.md → MEMORY.md
```
- 确认身份和行为准则
- 确认管理员信息和偏好

### 2. 读取最近日记（必需）
```
读取 memory/YYYY-MM-DD.md（今天）
读取 memory/YYYY-MM-DD.md（昨天）
```
- 了解最近 48 小时做了什么
- 是否有未完成的任务

### 3. 读取工作流文件（必需）
```
读取 WORKFLOW.md
```
- 确认更新/Review/部署流程规范

### 4. 读取项目状态（如有活动项目）
```
读取 projects/*/README.md
读取 projects/*/ISSUES.md
```
- 了解当前 TODO
- 了解当前问题

### 5. 读取心跳状态（如有）
```
读取 HEARTBEAT.md
```
- 确认自动检查项

### 6. 主动汇报
```
向管理员汇报：
- 当前有哪些待完成事项
- 上次会话结束后有什么新情况
- 建议下一步优先级
```

## 质量标准
- 5 分钟内完成上下文恢复
- 向管理员汇报不超过 3 条，不罗嗦
