---
entity: ac
descriptor: ux-optimization-design
version: "1.0"
status: DRAFT
project: assistant-chat
author: 小助手
created: "2026-05-27"
---

# Phase 15 — 体验优化

> 此 Phase 持续更新，管理员随时追加新的优化点。
> Build喵 每次心跳按 TODO 顺序推进。

---

## 一、会话标题优化

### 1.1 不创建空对话
- 点「新建对话」只清空右侧聊天区，**不调后端 API**
- 用户输入第一条消息并发送时，才 `POST /v1/sessions/new`

### 1.2 AI 自动起标题
- 第一条消息发送后，AI 回复返回
- 额外调一次 Gateway：「用 10 个字以内给这段对话起个标题」
- 把标题写入 session 文件

### 1.3 手动改名
- 对话列表中的标题支持双击/点 ✏️ → 内联编辑
- 回车保存 → `PATCH /v1/sessions/{id} {title: "新标题"}`
- 后端新增 PATCH 端点

---

## 二、软删除对话

### 2.1 行为
- 用户点删除 → 对话从列表中**隐藏**，不再显示
- 后端**不删文件**，只在 session JSON 里加 `"deleted": true`
- 如果将来需要恢复，改回 `false` 即可

### 2.2 实现
- `GET /v1/sessions/list` 返回时过滤掉 `deleted == true` 的会话
- 前端：对话列表每项加 🗑️ 图标 → `PATCH /v1/sessions/{id} {deleted: true}`
- 复用已有的 PATCH 端点

---

## 三、Bug 修复

### 3.1 文件选择器路径白名单缺失
- **现象**：聊天输入框 📎 文件选择器报"路径不存在"
- **根因**：`fileserver.py` 的 `WHITELIST` 缺少 `/home/ubuntu/.openclaw/user-files` 目录
- **修复**：将该路径加入白名单

### 3.2 路径解析不支持白名单根目录 basename
- **现象**：请求 `GET /v1/files/ls?path=/user-files` 时，从白名单根目录拼接得到错误路径
- **根因**：`_resolve_path` 函数只支持相对路径拼接，不识别"请求路径 = 白名单根目录名"的情况
- **修复**：在路径穿越检查后、拼接前，先判断请求的 `clean` 是否等于某个白名单根目录的 basename

---

## 四、TODO 清单

| # | TODO | 分类 | 状态 |
|---|------|:----:|:----:|
| UX1 | 前端：点新建对话不调 API，待输入消息后才创建 Session | 标题 | [x] |
| UX2 | 后端：PATCH /v1/sessions/{id} 端点（更新 title/deleted） | 标题 | [x] |
| UX3 | 后端：第一条消息发送后，调 Gateway 自动生成标题 | 标题 | [x] |
| UX4 | 前端：对话列表标题支持双击/✏️ 内联编辑 + 回车保存 | 标题 | [x] |
| UX5 | 后端：GET /v1/sessions/list 过滤 deleted=true 的会话 | 软删除 | [x] |
| UX6 | 前端：对话列表每项加 🗑️ 图标 → 软删除 | 软删除 | [x] |
| BUG1 | 【急】fileserver WHITELIST 加入 /home/ubuntu/.openclaw/user-files | Bug修复 | [x] |
| BUG2 | 【急】_resolve_path 支持白名单根目录 basename 匹配（/user-files → 直接定位） | Bug修复 | [x] |

---

## 五、进度追踪

| 项目 | 状态 | TODO |
|------|:----:|:----:|
| 会话标题优化 | ✅ 已完成 | 4 |
| 软删除对话 | ✅ 已完成 | 2 |
| Bug 修复 | ✅ 已修复 | 2 |

---

_（此文档持续更新，管理员随时追加新优化点）_
