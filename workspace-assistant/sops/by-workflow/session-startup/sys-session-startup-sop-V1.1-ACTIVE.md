---
entity: sys
descriptor: session-startup-sop
version: "1.1"
status: ACTIVE
author: 小助手
created: "2026-05-26"
updated: "2026-05-26"
trigger: "每次新 session 启动"
---

# sys-session-startup-sop — Session 启动标准操作流程

## 目的
确保每次新 session 都能快速恢复上下文，知道之前干了什么、还需要干什么、用了什么规范。

## 启动步骤

### 步 1：读身份（红色 — OpenClaw 系统文件）
```
SOUL.md  → User.md → MEMORY.md
```
- 确认角色和行为准则
- 确认管理员偏好
- 加载长期记忆（项目架构、核心教训、TODO）

### 步 2：读近期日记（红色）
```
memory/YYYY-MM-DD.md（今天）
memory/YYYY-MM-DD.md（昨天）
```
- 了解最近 48 小时干了什么

### 步 3：读工作流规范（红色）
```
WORKFLOW.md
```
- 确认更新/Review/部署的标准流程

### 步 4：读心跳规则（红色）
```
HEARTBEAT.md
```
- 确认自动检查项和触发条件

### 步 5：读项目状态（绿色文件）
```
projects/ac/ac-readme-V1.0-ACTIVE.md
```
- 当前阶段
- 待完成 TODO
- 最近变更

### 步 6：快速扫教训索引（绿色文件）
```
lessons/_index.md
```
- 最近犯了什么错、有什么规则需要记住
- 不需要深入读每个 lesson，扫标题即可

### 步 7：扫描可用 Skill（系统注入）
- 检查当前 session 的 `<available_skills>` 列表
- 确认哪些 skill 可用（code-analyzer, project, librarian-mastery 等）

### 步 8：向管理员汇报
```
简洁汇报三点：
1. 当前项目状态（如 Phase 0.2 — 稳定性加固）
2. 待完成事项（优先级 top 3）
3. 建议下一步
```

## 读文件优先级（Token 预算意识）

```
必读（完整）：
  SOUL.md, USER.md, MEMORY.md
  memory/今天.md, memory/昨天.md
  WORKFLOW.md

快速读（扫结构）：
  ac-readme（看 TODO 列表）
  lessons/_index.md（扫标题）
  HEARTBEAT.md（已有通常不会变）

按需读（干活时才深入）：
  具体的 SOP
  具体的 lesson
  ac-project-plan, ac-risk-register
```

## 质量标准
- 5 分钟内完成上下文恢复（或更快）
- 向管理员汇报不超过 3 条核心信息
- 不重复说已经知道的

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.1 | 2026-05-26 | 补全 8 步启动流程，区分必读/快读/按需读 |
| V1.0 | 2026-05-26 | 初始创建 |
