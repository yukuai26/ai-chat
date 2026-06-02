---
entity: ac
descriptor: design-code-audit
version: "1.0"
status: DRAFT
author: doc-reader (代码审查子Agent)
created: "2026-06-01"
baseline: ac-design-baseline-V1.0-ACTIVE.md
---

# AC 设计↔代码审查报告 V1.0

> 审查基准：`ac-design-baseline-V1.0-ACTIVE.md`（2026-06-01 管理员确认版）
> 后端代码：`/var/www/chat/fileserver.py`（6134 行）
> 前端代码：`/var/www/chat/index.html`（9852 行）
> 审查时间：2026-06-01 19:40 CST

---

## 问题汇总表

| 编号 | 模块 | 差异描述 | 类型 | 严重度 |
|------|------|----------|------|--------|
| B3-1 | 聊天·文件上下文 | fileserver 注入格式与 OpenClaw Gateway/飞书格式不一致 | b | **高** |
| C3-1 | 文件浏览器·端口 | 设计要求端口 5001，实际为 5050 | b | **高** |
| C2-1 | 文件浏览器·白名单 | 白名单多出 user-files 目录（设计仅提 assistant + build-cat） | c | 低 |
| K-1 | 备份 | 23:59 cron 备份脚本未注册到系统 crontab | a | **高** |
| E2-1 | 用户系统·注册 | 代码实现了注册功能（含邀请码），设计说"当前不需要注册" | c | 低 |
| H-1 | WebSocket·JWT字段 | WS 认证解析 `payload.sub`，JWT 签发用的是 `payload.user` | b | 中 |
| D4-1 | Dashboard·@前缀 | @前缀分发代码仍完整存在（设计已废弃，但基线注明不判违规） | c | 低 |

---

## A. 整体架构 / 访问与认证

### A1 — 账号密码登录后即可使用

**设计要求：** 用户用账号密码登录后即可使用。

**代码现状：** ✅ 已实现
- `fileserver.py:315` — `POST /v1/api/auth/login` 端点，接收 username/password，bcrypt 校验
- `fileserver.py:206` — `make_token()` 签发 JWT（HS256，24h/7d 过期）
- `fileserver.py:220-245` — `auth_required` 装饰器，解析 Bearer JWT
- `fileserver.py:567-616` — `require_token` 双模式认证（JWT 优先 + 旧 API Token 回退）
- `index.html:3432-3582` — 完整登录页 UI（用户名/密码输入 + 记住我 + 错误提示）

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### A3 — 架构（浏览器→CF Tunnel→nginx→Gateway+fileserver）

**设计要求：** 浏览器 → Cloudflare Tunnel → nginx → Gateway(127.0.0.1:18789) + fileserver(127.0.0.1:5001)

**代码现状：** ⚠️ 部分偏差
- Gateway URL: `fileserver.py:156` — `GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"` ✅
- fileserver 端口: `fileserver.py:6132` — `port = int(os.environ.get("PORT", 5050))` ❌（见 C3-1）
- systemd service: `Environment=PORT=5050` ❌
- nginx 配置: `proxy_pass http://127.0.0.1:5050` — 实际运行在 5050

**差异类型：** b（行为偏差）
**严重度：** 高（端口不符设计，见 C3-1 统一记录）

---

## B. 💬 聊天 + 会话

### B1 — 会话存储 + 分组

**设计要求：** 会话存储 `user-sessions/{id}.json`，左侧列表按 今天/昨天/更早 分组。

**代码现状：** ✅ 已实现
- `fileserver.py:158` — `SESSION_DIR = "/home/ubuntu/.openclaw/user-sessions"`
- `fileserver.py:763` — 文件为 `{session_id}.json`
- `index.html:5477-5490` — 前端分组逻辑：`groups = { '今天': [], '昨天': [], '更早': [] }`

**差异类型：** 无
**严重度：** —

### B2 — 端点

**设计要求：** 端点：`/v1/sessions/new|list|{id}|{id}/chat`，DELETE 删除。

**代码现状：** ✅ 已实现
- `fileserver.py:777` — `POST /v1/sessions/new`
- `fileserver.py:834` — `GET /v1/sessions/list`
- `fileserver.py:871` — `GET/PATCH /v1/sessions/{id}`
- `fileserver.py:1345` — `POST /v1/sessions/{id}/chat`
- `fileserver.py:936` — `DELETE /v1/sessions/{id}`

额外端点（不在设计中，类型 c）：
- `POST /v1/sessions/{id}/title` — 自动生成标题
- `POST /v1/sessions/{id}/messages` — 追加消息

**差异类型：** 无（核心端点完全一致；额外端点属 c 类低优先级）
**严重度：** —

### B3 — 【核心审查点】文件传输·上下文注入格式

**设计要求：** 当带文件发送消息时，后端拼装给 Gateway 的 prompt 上下文格式，要与"飞书对话中发送文件时"的注入格式保持一致。

**代码现状：** ❌ 格式不一致

#### fileserver.py 的文件注入格式

位置：`fileserver.py:1160-1224`（`_build_gateway_messages` + `_parse_file_attachment`）

**文本文件注入结构（fileserver.py:1128-1134）：**
```python
# _parse_file_attachment 返回 summary:
result["summary"] = (
    f"📄 文件: {file_path.name} ({mime_desc})\n"
    f"```\n{content}\n```"
)
```

**注入 messages 的方式（fileserver.py:1219-1223）：**
```python
# 新消息的文件附件
if new_files:
    summaries = [_parse_file_attachment(f)["summary"] for f in new_files]
    messages.append({
        "role": "system",
        "content": "用户选择了以下文件:\n\n" + "\n---\n".join(summaries),
    })
messages.append({"role": "user", "content": new_message})
```

最终发送给 Gateway 的实际格式：
```json
[
  {"role": "system", "content": "用户选择了以下文件:\n\n📄 文件: example.py (text/x-python)\n```\nimport os\nprint('hello')\n```"},
  {"role": "user", "content": "帮我看看这段代码"}
]
```

#### OpenClaw Gateway/飞书 的文件注入格式

位置：`~/.npm-global/lib/node_modules/openclaw/dist/reply-Deht_wOB.js:1093-1393`

**OpenClaw 的 `applyMediaUnderstanding` 流程：**
1. 媒体文件下载到本地磁盘（`saveMediaBuffer`）
2. 通过 `extractFileContentFromSource` 提取文本内容
3. 通过 `extractFileBlocks` 生成 XML 格式块
4. 通过 `appendFileBlocks` 追加到 `ctx.Body`（即用户消息体）

**实际注入格式（reply-Deht_wOB.js:1318-1325）：**
```xml
<file name="example.py" mime="text/x-python">
import os
print('hello')
</file>
```

**关键差异（汇总）：**

| 维度 | fileserver.py | OpenClaw Gateway（飞书） |
|------|---------------|--------------------------|
| 格式 | 纯文本 + markdown 代码块 | XML `<file>` 标签 |
| 角色 | 独立 `system` 消息 | 拼接到 `user` 消息 Body 中 |
| 文件元信息 | `📄 文件: name (mime)` 前缀文本 | `<file name="..." mime="...">` XML 属性 |
| 内容包裹 | ` ```\ncontent\n``` ` | 无额外包裹，直接放 `<file>` 标签内 |
| 多文件分隔 | `\n---\n` | 多个 `<file>` 块用 `\n\n` 连接 |
| 大文件处理 | 截断 4000 字符 + 提示 | 由 `limits.maxChars` 控制（配置化） |
| 非文本文件 | `📎 文件: name | 类型: mime | 大小: size | 路径: path` | 依赖 media-understanding（图片描述/音频转录） |

**差异类型：** b（行为偏差）
**严重度：** **高**
**建议：** 将 fileserver.py 的文件注入格式改为与 OpenClaw 一致的 `<file name="..." mime="...">content</file>` XML 格式，并将文件内容追加到 user 消息内容中（而非独立 system 消息）。具体改造：
1. `_parse_file_attachment` 的 summary 改为 `<file name="{name}" mime="{mime}">\n{content}\n</file>`
2. 注入位置从独立 system message 改为拼接到 user content 末尾

---

## C. 📁 文件浏览器

### C1 — 端点

**设计要求：** 端点：`/v1/files/ls|read|write|upload|mkdir|download|health`

**代码现状：** ✅ 已实现
- `fileserver.py:623` — `GET /v1/files/health`
- `fileserver.py:648` — `GET /v1/files/ls`
- `fileserver.py:674` — `GET /v1/files/read`
- `fileserver.py:700` — `GET /v1/files/download`
- `fileserver.py:1437` — `POST /v1/files/write`
- `fileserver.py:1478` — `POST /v1/files/upload`
- `fileserver.py:1556` — `POST /v1/files/mkdir`

**差异类型：** 无
**严重度：** —

### C2 — 安全（白名单 + 防穿越）

**设计要求：** 登录认证 + 路径白名单（assistant + build-cat 两个 workspace）+ 防 `..` 穿越 + 拒绝绝对路径绕过。

**代码现状：** ⚠️ 基本符合，白名单多一项
- `fileserver.py:113-116` — 白名单：
  ```python
  WHITELIST = [
      "/home/ubuntu/.openclaw/workspace-assistant",
      "/home/ubuntu/.openclaw/workspace-build-cat",
      "/home/ubuntu/.openclaw/user-files",  # ← 设计未提及
  ]
  ```
- `fileserver.py:464-508` — `_resolve_path()` 防穿越：检查 `..` 段 + resolve 后围栏检查
- 所有 `/v1/files/*` 端点使用 `@require_token` 认证

**差异类型：** c（代码多出 user-files，设计仅提 assistant + build-cat）
**严重度：** 低（合理扩展，不影响安全性）

### C3 — 端口 5001 + 50MB 上限

**设计要求：** fileserver 端口 127.0.0.1:5001，nginx 反代 `/v1/files/`，上传上限 50MB。

**代码现状：** ❌ 端口不符

- **端口：** `fileserver.py:6132` — `port = int(os.environ.get("PORT", 5050))`
  - systemd: `Environment=PORT=5050`
  - nginx: `proxy_pass http://127.0.0.1:5050`
  - **设计要求 5001，实际为 5050**

- **50MB 上限：** ✅ `fileserver.py:1472` — `MAX_UPLOAD_SIZE = 50 * 1024 * 1024`
- **nginx client_max_body_size：** ✅ `client_max_body_size 50m;`

**差异类型：** b（端口偏差）
**严重度：** **高**（端口是架构约定，A3 也引用了 5001）
**建议：** 要么将代码/systemd/nginx 统一改为 5001，要么更新设计基线为 5050。鉴于系统已稳定运行在 5050，建议更新基线。

### C4 — 前端功能

**设计要求：** Tab 切换 + 目录树 + highlight.js 高亮 + Markdown 预览 + 编辑 + 拖拽上传 + 图片预览 + 下载。

**代码现状：** ✅ 已实现（通过搜索 index.html 确认相关功能均存在）
- Tab 按钮: `index.html:3744` — `<button class="tab-btn" data-tab="files">`
- 目录树、文件编辑、highlight.js、拖拽上传均在前端代码中实现

**差异类型：** 无
**严重度：** —

---

## D. 📊 每日 Dashboard

### D1 — 卡片注册表驱动

**设计要求：** 卡片即插件：注册表驱动，缩略→展开。

**代码现状：** ✅ 已实现
- `fileserver.py:1726` — `CARD_REGISTRY_PATH = os.path.join(USER_DATA_DIR, "card-registry.json")`
- `fileserver.py:1597-1723` — 默认卡片注册表（含 order、cards 数组）

**差异类型：** 无
**严重度：** —

### D2/D3 — 卡片种类

**设计要求：** 首批卡片(资讯/Todo/数据/食谱/心愿) + 扩展 6 张(随手记/收藏夹/照片墙/分享板/提醒/习惯打卡)。

**代码现状：** ✅ 已实现
- `fileserver.py:1814-1830` — 所有卡片数据目录定义：
  ```python
  TODO_DIR, RECIPE_DIR, WISHES_DIR, NOTES_DIR, BOOKMARKS_DIR,
  PHOTOS_DIR, SHARES_DIR, REMINDERS_DIR, HABITS_DIR
  ```
- `fileserver.py:2645` — `NEWS_DIR`（资讯）

**差异类型：** 无
**严重度：** —

### D4 — @前缀分发（已废弃）

**设计要求：** 底部统一输入框 `@前缀` 分发机制已取消。"以现有代码实现为准，不按旧文档判违规"。

**代码现状：** 代码仍存在完整 @前缀解析和分发逻辑
- `fileserver.py:1930-1979` — `_parse_command()` 函数解析 @前缀
- `fileserver.py:2374-2430` — `POST /v1/api/daily/command` 统一指令分发

**差异类型：** c（代码保留了已废弃功能）
**严重度：** 低（设计明确说"不判违规"）
**建议：** 可考虑添加 `@deprecated` 注释标记

### D5 — 卡片数据目录

**设计要求：** 卡片数据目录以 `daily-data/` 为准（原文档写 `user-data/` 已过时）。

**代码现状：** ✅ 正确
- `fileserver.py:161` — `DAILY_DATA_DIR = os.path.join(USER_DATA_DIR, "daily-data")`
- 实际路径：`/home/ubuntu/.openclaw/user-data/daily-data/`
- 所有卡片数据（todo/recipe/wishes/notes 等）均在此目录下

**差异类型：** 无
**严重度：** —

---

## E. 🔐 用户系统

### E1 — 账号密码登录 + JWT

**设计要求：** 账号密码登录 + JWT。

**代码现状：** ✅ 已实现（同 A1 分析）
- bcrypt 密码哈希
- JWT HS256 签发/验证
- 24h/7d 过期可选

**差异类型：** 无
**严重度：** —

### E2 — 注册 + 数据隔离

**设计要求：** 当前不需要注册；数据隔离暂不作为硬性设计要求。

**代码现状：** 代码实现了注册功能（含邀请码机制）
- `fileserver.py:248-309` — `POST /v1/api/auth/register`（需邀请码）
- `fileserver.py:401-430` — 邀请码管理 API

**差异类型：** c（代码多出功能，设计说"不需要"但也不禁止）
**严重度：** 低（不违规，属功能增强）

---

## F. 🔍 全局搜索

**设计要求：** 独立 Tab，跨数据源，手动触发，结果跨 Tab 缓存 + 精准跳转。

**代码现状：** ✅ 已实现
- `fileserver.py:5132-5300` — `GET /v1/api/search` 全局搜索 API
  - 搜索对话 Session（含消息定位 message_index）
  - 搜索卡片数据（todo/notes/wishes 等）
  - 支持 fast / precise 两种模式（jieba 分词 + m3e 语义）
- `index.html:3744` — `🔍 Search` Tab 按钮
- `index.html:3829` — `#tab-search` 内容区
- `index.html:8875+` — 全局搜索前端 JS 逻辑

**差异类型：** 无
**严重度：** —

---

## G. 📱 手机适配

**设计要求：** 一套 CSS 兼容安卓/苹果。

**代码现状：** ✅ 已实现
- `index.html:8` — `<meta name="viewport" content="width=device-width, initial-scale=1.0">`
- `index.html:2594-2654` — 移动端底部导航栏 + 顶栏
- `index.html:2661-2731` — 手机端聊天适配、输入框适配
- `index.html:2722-2731` — `.is-mobile` class 兜底规则
- `index.html:1657-1660` — 多个 `@media` 断点
- `index.html:2989-3010` — 日历移动端适配

**差异类型：** 无
**严重度：** —

---

## H. 🔄 实时同步（WebSocket）

**设计要求：** WebSocket，一人改数据另一人页面秒刷新。

**代码现状：** ⚠️ 已实现，但认证字段有 bug

- `fileserver.py:5494-5592` — WebSocket 实现
  - `@sock.route('/v1/ws')` 路由
  - 心跳 ping/pong
  - `_broadcast()` / `_notify_partner()` 广播机制
  - 支持通过 WS 流式 AI 对话（绕过 CF Tunnel 100s 超时）

- **Bug：** `fileserver.py:5503-5507` — WS 认证解析的是 `payload.get('sub', '')`
  ```python
  payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
  username = payload.get('sub', '')  # ← 错误！JWT 签发用的字段是 'user'
  ```
  而 `make_token()`（line 207）签发的 payload 用的是 `"user"` 字段：
  ```python
  payload = {
      "user": user["username"],  # ← 这里是 'user' 不是 'sub'
      ...
  }
  ```
  这导致 **WebSocket 认证始终失败**（username 为空字符串），连接无法建立。

- `index.html:9079-9234` — 前端 WebSocket 连接、事件处理

**差异类型：** b（行为偏差——WS 认证逻辑 bug 导致功能不可用）
**严重度：** 中（功能存在但因 bug 无法正常工作）
**建议：** 将 `payload.get('sub', '')` 改为 `payload.get('user', '')`

---

## I. 📅 日历

**设计要求：** 独立 Tab，时间中枢，自身不存数据，汇聚 todos/reminders/recipe/notes/photos。

**代码现状：** ✅ 已实现
- `fileserver.py:5306` — `CALENDAR_PATH` 日历事件存储
- `fileserver.py:5323-5365` — `GET /v1/api/calendar/{date}` 日期汇聚：
  - 查 events、todos、reminders、recipe（按星期）、notes、photos
- `fileserver.py:5367+` — `GET /v1/api/calendar/range` 范围查询
- `index.html:3745` — `📅 日历` Tab 按钮
- `index.html:3850-3860` — 日历面板（月视图 + 详情面板）

**注：** 设计说"自身不存数据"，但代码有 `calendar.json` 存储日历事件。这是合理扩展——日历有自己的"事件"概念（如约会），同时也汇聚其他数据源。

**差异类型：** 无（严格说 calendar.json 存事件是 c 类小偏差，但不影响汇聚功能）
**严重度：** —

---

## J. 🎨 UI 美化

**设计要求：** 极简风（替代原暗黑电竞风 #1a1a2e/#e94560）。

**代码现状：** ✅ 已实现
- `index.html:20-37` — CSS 变量：
  ```css
  :root {
    --bg: #fafaf8;
    --bg-card: #ffffff;
    --accent: #2c2c2c;
    ...
  }
  ```
- 无 #1a1a2e / #e94560 残留
- 整体为浅色极简风格

**差异类型：** 无
**严重度：** —

---

## K. 💾 备份

**设计要求：** 每天 23:59 备份用户数据+记忆+配置到 `yukuai26/ai-chat` 的 `backup` 分支。

**代码现状：** ❌ 脚本存在但未注册到 cron

- **备份脚本：** `/tmp/ai-chat-check/scripts/backup.sh` — 完整实现：
  - 初始化 backup 分支
  - rsync 同步 workspace-assistant、workspace-build-cat、user-data、user-sessions、user-files、web-app、server-config
  - git commit + push 到 `yukuai26/ai-chat` 的 `backup` 分支

- **cron 注册：** ❌ 未在系统 crontab 中找到 backup 相关条目
  - `crontab -l` 仅有一条被注释掉的 buildcat trigger
  - 无 systemd timer 关联 backup

- **脚本位置：** 在 /tmp 临时目录（非持久化位置）

**差异类型：** a（功能缺失——脚本写好了但没有部署和注册到定时任务）
**严重度：** **高**（数据备份是关键安全网，未执行等于没有）
**建议：**
1. 将脚本移至持久位置（如 `/home/ubuntu/.openclaw/scripts/backup.sh`）
2. 添加 crontab：`59 23 * * * /home/ubuntu/.openclaw/scripts/backup.sh >> /var/log/backup.log 2>&1`
3. 测试首次运行确保 SSH key 和 git 权限就绪

---

## 统计

| 指标 | 数值 |
|------|------|
| 总发现数 | 7 条 |
| 高严重度 | 3 条（B3-1, C3-1, K-1） |
| 中严重度 | 1 条（H-1） |
| 低严重度 | 3 条（C2-1, E2-1, D4-1） |
| 功能缺失 (a) | 1 条 |
| 行为偏差 (b) | 3 条 |
| 设计外多出 (c) | 3 条 |

---

## 附录：B3 详细格式对比

### fileserver.py 实际输出示例

```json
{
  "role": "system",
  "content": "用户选择了以下文件:\n\n📄 文件: config.yaml (application/x-yaml)\n```\nserver:\n  port: 8080\n  host: 0.0.0.0\n```\n---\n📎 文件: photo.jpg | 类型: image/jpeg | 大小: 2.3MB | 路径: /home/ubuntu/.openclaw/user-files/photo.jpg"
}
```

### OpenClaw Gateway（飞书）实际输出示例

文件内容直接追加到用户消息体（Body）末尾：
```
用户原始消息文本

<file name="config.yaml" mime="application/x-yaml">
server:
  port: 8080
  host: 0.0.0.0
</file>

<file name="photo.jpg" mime="image/jpeg">
[No extractable text]
</file>
```

### 关键差异总结
1. **消息角色不同**：fileserver 用独立 `system` 消息；OpenClaw 追加到 `user` 消息体
2. **格式不同**：fileserver 用 emoji + markdown；OpenClaw 用 XML `<file>` 标签
3. **语义不同**：fileserver 说"用户选择了以下文件"；OpenClaw 直接在消息体中追加文件块
4. **非文本文件处理不同**：fileserver 只标注路径信息；OpenClaw 有 media-understanding 流程（图片描述、音频转录等）
