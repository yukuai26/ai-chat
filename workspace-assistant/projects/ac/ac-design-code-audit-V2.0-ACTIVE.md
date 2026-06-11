---
entity: ac
descriptor: design-code-audit
version: "2.0"
status: ACTIVE
author: doc-reader (代码审查子Agent)
created: "2026-06-07"
baseline: ac-design-baseline-V1.0-ACTIVE.md
---

# AC 设计↔代码审查报告 V2.0

> 审查基准：`ac-design-baseline-V1.0-ACTIVE.md`（2026-06-07 版，含 O 模块）
> 后端代码：`/var/www/chat/fileserver.py`（5808 行）
> 前端代码：`/var/www/chat/index.html`（9722 行）
> 审查时间：2026-06-07 15:00 CST
> 对应代码 commit：`00a762d`（B3-1 修复）/ `7b9f5b0`（O 模块）

---

## 问题汇总表

| 编号 | 模块 | 差异描述 | 类型 | 严重度 |
|------|------|----------|------|--------|
| ~~B3-1~~ | 聊天·文件上下文 | ✅ **已解决(2026-06-07, commit 00a762d)**: 改为 `<file>` XML 格式+追加 user 消息+防注入转义 | b | ~~高~~ → 已修 |
| ~~C2-1~~ | 文件浏览器·白名单 | ✅ **已解决(2026-06-07, 补设计)**: baseline C2 已补入 user-files 白名单 | c | ~~低~~ → 已对齐 |

---

## A. 整体架构 / 访问与认证

### A1 — 账号密码登录后即可使用

**设计要求：** 用户用账号密码登录后即可使用。

**代码现状：** ✅ 已实现
- `fileserver.py:248-274` — `POST /v1/api/auth/login` 端点，接收 username/password，bcrypt 校验
- `fileserver.py:206-215` — `make_token()` 签发 JWT（HS256，24h/7d 过期）
- `fileserver.py:218-240` — `auth_required` 装饰器，解析 Bearer JWT
- `fileserver.py:453-493` — `require_token` 双模式认证（JWT 优先 + 旧 API Token 回退）
- `index.html:3877+` — 登录页 UI（用户名/密码输入 + 记住我）

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### A3 — 架构（浏览器→CF Tunnel→nginx→Gateway+fileserver）

**设计要求：** 浏览器 → Cloudflare Tunnel → nginx → Gateway(127.0.0.1:18789) + fileserver(127.0.0.1:5050)。

**代码现状：** ✅ 完全符合
- Gateway URL: `fileserver.py:151` — `GATEWAY_URL = "http://127.0.0.1:18789/v1/chat/completions"` ✅
- fileserver 端口: `fileserver.py:5806` — `port = int(os.environ.get("PORT", 5050))` ✅
- nginx: `proxy_pass http://127.0.0.1:5050` ✅

**差异类型：** 无（C3-1 旧报告的端口问题已通过 2026-06-02 基线修正解决：设计现以 5050 为准）
**严重度：** —
**结论：** 完全符合设计。

---

## B. 💬 聊天 + 会话

### B1 — 会话存储 + 分组

**设计要求：** 会话存储 `user-sessions/{id}.json`，左侧列表按 今天/昨天/更早 分组。

**代码现状：** ✅ 已实现
- `fileserver.py:158` — `SESSION_DIR = "/home/ubuntu/.openclaw/user-sessions"`
- `fileserver.py:641` — 文件为 `{session_id}.json`
- `index.html:5407-5420` — 前端分组逻辑（timeGroupLabel 函数实现今天/昨天/更早分组）

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### B2 — 端点

**设计要求：** 端点：`/v1/sessions/new|list|{id}|{id}/chat`，DELETE 删除。

**代码现状：** ✅ 已实现
- `fileserver.py:622` — `POST /v1/sessions/new`
- `fileserver.py:701` — `GET /v1/sessions/list`
- `fileserver.py:737` — `GET/PATCH /v1/sessions/{id}`
- `fileserver.py:1201` — `POST /v1/sessions/{id}/chat`
- `fileserver.py:796` — `DELETE /v1/sessions/{id}`

额外端点（设计外，类型 c，不影响核心功能）：
- `POST /v1/sessions/{id}/title` (line 668) — 自动生成标题
- `POST /v1/sessions/{id}/messages` (line 1159) — 追加消息

**差异类型：** 无（核心端点完全一致）
**严重度：** —
**结论：** 完全符合设计。

### B3 — 【核心审查点】文件传输·上下文注入格式

**设计要求：** 当带文件发送消息时，后端拼装给 Gateway 的 prompt 上下文格式，要与"飞书对话中发送文件时"的注入格式保持一致。

**代码现状：** ❌ 格式不一致

#### fileserver.py 后端注入格式

位置：`fileserver.py:946-1103`（`_parse_file_attachment`）+ `fileserver.py:1053-1103`（`_build_gateway_messages`）

**文本文件注入格式（fileserver.py:1020-1023）：**
```python
result["summary"] = (
    f"📄 文件: {file_path.name} ({mime_desc})\n"
    f"```\n{content}\n```"
)
```

**注入 messages 的方式（fileserver.py:1097-1101）：**
```python
if new_files:
    summaries = [_parse_file_attachment(f)["summary"] for f in new_files]
    messages.append({
        "role": "system",
        "content": "用户选择了以下文件:\n\n" + "\n---\n".join(summaries),
    })
```

#### 前端注入格式（WS + HTTP 两路一致）

位置：`index.html:5215-5216`（读取文件内容）+ `index.html:5272`（注入 system 消息）

前端格式与后端一致（emoji+markdown 代码块 + system 角色 + "用户选择了以下文件"前缀）。

#### OpenClaw Gateway/飞书的格式

飞书使用 XML `<file name="..." mime="...">content</file>` 标签，追加到 user 消息 Body 中。

**关键差异：**

| 维度 | fileserver/前端 | OpenClaw 飞书 |
|------|----------------|---------------|
| 格式 | emoji + markdown 代码块 | XML `<file>` 标签 |
| 角色 | 独立 `system` 消息 | 拼接到 `user` 消息体 |
| 文件元信息 | `📄 文件: name (mime)` 文本前缀 | `<file name="..." mime="...">` 属性 |
| 内容包裹 | ` ```\ncontent\n``` ` | 无额外包裹 |
| 多文件分隔 | `\n---\n` | 多个 `<file>` 块 `\n\n` 连接 |
| 大文件截断 | 前端 5000 字符 / 后端 4000 字符 | 配置化 `limits.maxChars` |

**差异类型：** b（行为偏差）
**严重度：** **高**
**TODO：** 将文件注入格式改为与 OpenClaw 飞书一致的 `<file>` XML 格式，并改为追加到 user 消息内容中。

---

## C. 📁 文件浏览器

### C1 — 端点

**设计要求：** 端点：`/v1/files/ls|read|write|upload|mkdir|download|health`

**代码现状：** ✅ 已实现
- `fileserver.py:497` — `GET /v1/files/health`
- `fileserver.py:528` — `GET /v1/files/ls`
- `fileserver.py:559` — `GET /v1/files/read`
- `fileserver.py:586` — `GET /v1/files/download`
- `fileserver.py:1317` — `POST /v1/files/write`
- `fileserver.py:1364` — `POST /v1/files/upload`
- `fileserver.py:1445` — `POST /v1/files/mkdir`

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### C2 — 安全（白名单 + 防穿越）

**设计要求：** 登录认证 + 路径白名单（assistant + build-cat 两个 workspace）+ 防 `..` 穿越 + 拒绝绝对路径绕过。

**代码现状：** ⚠️ 基本符合，白名单多一项
- `fileserver.py:106-109` — 白名单：
  ```python
  WHITELIST = [
      "/home/ubuntu/.openclaw/workspace-assistant",
      "/home/ubuntu/.openclaw/workspace-build-cat",
      "/home/ubuntu/.openclaw/user-files",  # ← 设计未提及
  ]
  ```
- `fileserver.py:348-374` — `_resolve_path()` 防穿越：解析后围栏检查
- 所有 `/v1/files/*` 端点使用 `@require_token` 认证

**差异类型：** ~~c~~ → ✅ **已对齐 (2026-06-07, 补设计)**
**严重度：** ~~低~~ —
**解决方式：** 按设计↔代码双向同步铁律，代码做了设计没写 → 补设计。baseline C2 已补入 user-files 白名单条目。

### C3 — 端口 5050 + 50MB 上限

**设计要求：** fileserver 端口 127.0.0.1:**5050**，nginx 反代 `/v1/files/`，上传上限 50MB。

**代码现状：** ✅ 完全符合
- 端口：`fileserver.py:5806` — `port = int(os.environ.get("PORT", 5050))` ✅
- 50MB 上限：`fileserver.py:1361` — `MAX_UPLOAD_SIZE = 50 * 1024 * 1024` ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计（基线已于 2026-06-02 更正为 5050）。

### C4 — 前端功能

**设计要求：** Tab 切换 + 目录树（展开折叠/类型图标/高亮）+ highlight.js 高亮 + Markdown 预览 + 编辑(Ctrl+S/未保存警告) + 拖拽上传(进度条) + 图片预览 + 下载。

**代码现状：** ✅ 已实现
- Tab 按钮: `index.html:3723` — `<button class="tab-btn" data-tab="files">`
- 目录树: `index.html:3763-3770` — 目录树 + 拖拽上传区
- highlight.js: `index.html:9646` — CDN 加载 + `index.html:6504` — `hljs.highlightElement(block)`
- Markdown 预览: `index.html:6492` — marked.js 渲染
- Ctrl+S 保存: `index.html:6796` — `if (e.ctrlKey && e.key === 's')`
- 未保存警告: `index.html:6604-6627` — 确认对话框
- 拖拽上传+进度条: `index.html:5904-5912` — dropzone + `index.html:5861` — xhr upload progress
- 图片预览: `index.html:6198+` — 文件查看器
- 下载: `fileserver.py:586` — `GET /v1/files/download`

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## D. 📊 每日 Dashboard

### D1 — 卡片注册表驱动

**设计要求：** 卡片即插件：注册表驱动，缩略→展开。

**代码现状：** ✅ 已实现
- `fileserver.py:1607-1618` — `_load_card_registry()` / `_save_card_registry()`
- `fileserver.py:1485-1606` — `DEFAULT_CARD_REGISTRY`（含 cards 数组、layout、commandPrefixes）
- 每张卡片有 `expandable: True` 属性，前端支持缩略→展开

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### D2/D3 — 卡片种类

**设计要求：** 首批卡片(资讯/Todo/数据/食谱/心愿) + 扩展 6 张(随手记/收藏夹/照片墙/分享板/提醒/习惯打卡)。

**代码现状：** ✅ 已实现
- `fileserver.py:1485-1606` — DEFAULT_CARD_REGISTRY 包含全部 11 张卡片：
  - 首批：news(资讯)、todo(Todo)、data(数据)、recipe(食谱)、wishes(心愿)
  - 扩展：notes(随手记)、bookmarks(收藏夹)、photos(照片墙)、shares(分享板)、reminders(提醒)、habits(习惯打卡)

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### D4 — @前缀分发（已废弃）

**设计要求：** 底部统一输入框 `@前缀` 分发机制已取消。"以现有代码实现为准，不按旧文档判违规"。

**代码现状：** ✅ 已清理
- 旧版有 `_parse_command()` 和 `POST /v1/api/daily/command` 路由，**当前代码已移除**。
- `commandPrefixes` 仅残留在 `DEFAULT_CARD_REGISTRY` 的静态数据结构中（line 1591），无对应路由处理。

**差异类型：** 无（代码已与设计对齐：功能移除，仅注册表定义残留）
**严重度：** —
**结论：** 符合设计。

### D5 — 卡片数据目录

**设计要求：** 卡片数据目录以 `daily-data/` 为准。

**代码现状：** ✅ 正确
- `fileserver.py:161` — `DAILY_DATA_DIR = os.path.join(USER_DATA_DIR, "daily-data")`
- 实际路径：`/home/ubuntu/.openclaw/user-data/daily-data/`

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## E. 🔐 用户系统

### E1 — 账号密码登录 + JWT

**设计要求：** 账号密码登录 + JWT。

**代码现状：** ✅ 已实现（同 A1 分析）
- bcrypt 密码哈希
- JWT HS256 签发/验证
- 24h/7d（记住我）过期可选

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### E2 — 注册 + 数据隔离

**设计要求：** 当前不需要注册；数据隔离暂不作为硬性设计要求。

**代码现状：** ✅ 符合
- **注册功能已移除**：当前代码中不存在 `auth/register` 或类似注册端点（旧版 V1.0 审查时存在的注册+邀请码代码已被删除）。
- 数据隔离未做（符合"暂不作为硬性要求"的设计）。

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## F. 🔍 全局搜索

**设计要求：** 独立 Tab，跨数据源，手动触发，结果跨 Tab 缓存 + 精准跳转。

**代码现状：** ✅ 已实现
- `fileserver.py:4806-4808` — `GET /v1/api/search` 全局搜索 API
  - 搜索对话 Session + 卡片数据（todo/notes/wishes 等）
  - 支持 fast / precise 两种模式（jieba 分词 + m3e 语义）
- `index.html:3725` — `🔍 Search` Tab 按钮
- 前端搜索界面完整，支持结果展示 + 跳转

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## G. 📱 手机适配

**设计要求：** 一套 CSS 兼容安卓/苹果。

**代码现状：** ✅ 已实现
- `index.html:8` — `<meta name="viewport" content="width=device-width, initial-scale=1.0">`
- `index.html:1657` — `@media (max-width: 1024px)` 断点
- `index.html:1660` — `@media (max-width: 640px)` 断点
- `index.html:2451` — `@media (max-width: 768px)` 面板抽屉适配
- `index.html:2625-2731` — 移动端顶栏 + 底部导航栏 + `.is-mobile` class 完整规则集

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## H. 🔄 实时同步（WebSocket）

**设计要求：** WebSocket，一人改数据另一人页面秒刷新。

**代码现状：** ✅ 已实现（旧报告 H-1 的 JWT 字段 bug 已修复）

- `fileserver.py:5173-5194` — `@sock.route('/v1/ws')` WebSocket 路由
  - **JWT 认证已修正**：`fileserver.py:5180` — `username = payload.get('user', '')` ✅（与 `make_token` 的 `"user"` 字段一致）
  - 心跳 ping/pong
  - AI 对话流式转发（绕过 CF Tunnel 100s 超时）
- `fileserver.py:5277-5281` — `_broadcast()` 广播机制
- `fileserver.py:5284+` — `_notify_partner()` 通知伴侣
- `index.html:8954-9054` — 前端 WebSocket 连接、心跳、断线重连

**差异类型：** 无（H-1 已修复）
**严重度：** —
**结论：** 完全符合设计。

---

## I. 📅 日历

**设计要求：** 独立 Tab，时间中枢，自身不存数据，汇聚 todos/reminders/recipe/notes/photos。

**代码现状：** ✅ 基本符合
- `fileserver.py:4997-5038` — `GET /v1/api/calendar/{date}` 日期汇聚：
  - 查 events、todos、reminders、recipe（按星期）、notes、photos ✅
- `fileserver.py:5040-5055` — `GET /v1/api/calendar/range` 范围查询
- `index.html:3726` — `📅 日历` Tab 按钮
- 日历有自己的 `calendar.json` 存储事件（约会等），这属合理扩展——日历可以有"自己的事件"同时汇聚其他数据。

**差异类型：** 无（calendar.json 存事件属合理设计补充）
**严重度：** —
**结论：** 符合设计。

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
**结论：** 完全符合设计。

---

## K. 💾 备份

**设计要求：** 每天 23:59 备份用户数据+记忆+配置到 `yukuai26/ai-chat` 的 `backup` 分支。

**代码现状：** ✅ 已实现（旧报告 K-1 cron 缺失问题已修复）

- **备份脚本：** `/home/ubuntu/.openclaw/scripts/backup.sh`（持久位置）
  - 初始化 backup 分支
  - rsync 同步关键数据
  - git commit + push 到 `yukuai26/ai-chat` 的 `backup` 分支

- **cron 注册：** ✅ 已在系统 crontab 中：
  ```
  59 23 * * * /home/ubuntu/.openclaw/scripts/backup.sh >> /home/ubuntu/.openclaw/logs/backup.log 2>&1
  ```

**差异类型：** 无（K-1 已修复）
**严重度：** —
**结论：** 完全符合设计。

---

## O. 💬 聊天上下文与会话记忆【2026-06-07 新增·重点审查】

### O1 — 上下文来源 = session 文件

**设计要求：** 每个对话对应磁盘上的 `user-sessions/{id}.json`，永久保存不过期。发消息时前端从该文件读出历史，拼进 messages 一起发给 Gateway。这是上下文的唯一权威来源。

**代码现状：** ✅ 完全符合
- Session 存储：`fileserver.py:158` — `SESSION_DIR = "/home/ubuntu/.openclaw/user-sessions"`
- 前端读取历史：`index.html:5145-5146`：
  ```javascript
  var r = await authFetch('/v1/sessions/' + encodeURIComponent(sessionId));
  var d = await r.json();
  var all = (d.messages || []).filter(function(m){ return m.role === 'user' || m.role === 'assistant'; });
  ```
- 拼入 messages 发给 Gateway：`index.html:5273-5275`（WS 路径）+ `index.html:5329-5331`（HTTP 路径）
- 永久保存不过期：session 文件无 TTL/清理机制 ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### O2 — 全量带历史 + token 兜底（HISTORY_TOKEN_BUDGET=150000）

**设计要求：** `loadRecentHistory()` 默认全量带该会话所有 user/assistant 消息。仅当累计 token 超 `HISTORY_TOKEN_BUDGET=150000` 时，从最旧开始丢弃。粗估 `_estTokens = 字符数/2`。

**代码现状：** ✅ 完全符合
- `index.html:5139` — `var HISTORY_TOKEN_BUDGET = 150000;` ✅
- `index.html:5140-5141` — `function _estTokens(str) { return Math.ceil((str || '').length / 2); }` ✅
- `index.html:5143-5165` — `loadRecentHistory` 实现：
  - 读取所有 user/assistant 消息 ✅
  - 去重：剔除末尾与当前消息相同的 user 条 ✅
  - 默认全量；从后往前累加，超 budget 时停止（从最旧开始丢弃）✅
  - 注释明确："全量带历史(对齐 DeepSeek 等大厂: 以 session 文件为唯一上下文源, 每次重建)" ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### O3 — Gateway 无状态 / 随机 user（WS + HTTP 两处确认）

**设计要求：** 发消息时 `user` 字段用 `_randomUser()`（每次随机），使 Gateway 每次都当全新会话。WS 路径和 HTTP fallback 两处都用随机 user。

**代码现状：** ✅ 完全符合
- `index.html:5133-5135` — `_randomUser()` 实现：
  ```javascript
  function _randomUser() {
    return 'web-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
  }
  ```
- **WS 路径**：`index.html:5296` — `user: _randomUser()` ✅
- **HTTP fallback 路径**：`index.html:5342` — `user: _randomUser()` ✅
- 注释明确："随机 user: 让 Gateway 每次都当全新会话(会话层自带历史=空), 上下文完全由前端带的历史提供" ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。两条路径都确认使用随机 user。

### O4 — 中途切模型不丢上下文

**设计要求：** `switchModel()` 只改 `agentId`，不碰 `activeConversationId`、不新建 session。切模型后新模型仍从 session 文件历史看到完整对话。

**代码现状：** ✅ 完全符合
- `index.html:3961-3976` — `switchModel(modelId)` 函数：
  ```javascript
  function switchModel(modelId) {
    agentId = modelId;
    // 更新按钮状态
    document.querySelectorAll('.model-btn').forEach(function(b) {
      b.classList.toggle('active', b.dataset.model === modelId);
    });
    // 更新设置面板下拉
    var sel = document.getElementById('agentId');
    if (sel) sel.value = modelId;
    // 保存到 localStorage
    ...
  }
  ```
  - 只修改 `agentId` ✅
  - 不碰 `activeConversationId` ✅
  - 不调用 `create_session`、不新建会话 ✅

- 历史透明混合（不标注来源模型）：session 文件中 messages 不含 model 字段 ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### O5 — 持久记忆铁律（workspace-webchat/SOUL.md）

**设计要求：** `workspace-webchat/MEMORY.md` 是跨对话共享的持久记忆。webchat agent 想写 MEMORY.md 前必须先告知用户、说明"会被所有对话带上"、得到同意后才写。已写入 `workspace-webchat/SOUL.md`。

**代码现状：** ✅ 完全符合
- `/home/ubuntu/.openclaw/workspace-webchat/SOUL.md` 已包含"持久记忆铁律"段落：
  ```
  ## 持久记忆铁律（重要）
  - `MEMORY.md` 是**跨对话共享的持久记忆**——写进去的内容会被**所有对话**（包括其他模型、其他会话）自动带上。
  - **想写持久记忆（MEMORY.md）前，必须先告知用户**：说明你打算记什么、并明确提示"这条记忆会被所有对话带上（跨对话共享）"，**得到用户同意后才写**。
  - 不要自作主张往 MEMORY.md 写东西。
  ```
- `/home/ubuntu/.openclaw/workspace-webchat/MEMORY.md` 文件存在 ✅

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

### O6 — 两条传输路径（WS 主 + HTTP 回退）

**设计要求：** 主路径 = WebSocket（绕过 Cloudflare 100s 超时）；回退 = HTTP 直连 Gateway（WS 5 秒内未连上时）。两路上下文处理一致（都带全量历史 + 随机 user）。

**代码现状：** ✅ 完全符合
- **WS 主路径**：`index.html:5168-5302`（`_doSendMessage` 函数）
  - `index.html:5229-5237` — 等待 WS 连接（最多 5 秒）
  - `index.html:5237-5239` — 超时则回退 HTTP：
    ```javascript
    if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
      return _fallbackHttpSend(text, filesToSend, fileSummaries, fileIDs, now);
    }
    ```
  - WS 发送：`index.html:5288-5299`（`wsConnection.send(JSON.stringify({type:'chat', messages, user:_randomUser(), model:...}))`）

- **HTTP 回退路径**：`index.html:5303-5393`（`_fallbackHttpSend` 函数）
  - 直接 fetch Gateway `/v1/chat/completions`
  - `index.html:5341-5342` — 同样带 `user: _randomUser()`, stream: true

- **上下文一致性确认**：
  - WS：`loadRecentHistory` → push history → push user message → 带 `_randomUser()` ✅
  - HTTP：`loadRecentHistory` → push history → push user message → 带 `_randomUser()` ✅
  - 两路结构完全对称 ✅

- **后端 WS 转发**：`fileserver.py:5206-5261` — 收到 `type:'chat'` 后，透传 messages/user/model 到 Gateway（stream=True），逐 chunk 返回

**差异类型：** 无
**严重度：** —
**结论：** 完全符合设计。

---

## TODO 清单汇总

| 编号 | 模块 | TODO 描述 | 状态 |
|------|------|-----------|--------|
| ~~B3-1~~ | 聊天·文件上下文 | 文件注入改 `<file>` XML 格式+追加 user 消息+防注入 | ✅ 2026-06-07 已完成 (commit 00a762d) |

**当前无任何未完成 TODO。** C2-1 已于 2026-06-07 通过补设计对齐（baseline C2 加入 user-files）。设计与代码已完全一一对应。

---

## 统计

| 指标 | 数值 |
|------|------|
| 总发现数 | 2 条（B3-1 已修复 + C2-1 已对齐，全部闭环）|
| 高严重度 | 0 条（B3-1 已修复）|
| 中严重度 | 0 条 |
| 低严重度 | 0 条（C2-1 已对齐）|
| 功能缺失 (a) | 0 条 |
| 行为偏差 (b) | 1 条 |
| 设计外多出 (c) | 0 条（已对齐）|
| TODO 待实现 | 0 条 |

---

## 与旧版 V1.0 报告的差异说明

| 旧编号 | 旧状态 | V2.0 状态 | 说明 |
|--------|--------|-----------|------|
| C3-1 | 端口 5001 vs 5050 | ✅ 已解决 | 基线 2026-06-02 已更正为 5050 |
| K-1 | cron 未注册 | ✅ 已解决 | 脚本已移至持久位置 + crontab 已注册 |
| H-1 | WS JWT 字段 bug | ✅ 已解决 | `payload.get('sub')` 改为 `payload.get('user')` |
| E2-1 | 代码有注册功能 | ✅ 已解决 | 注册端点已移除 |
| D4-1 | @前缀代码残留 | ✅ 已解决 | 路由+解析函数已移除，仅注册表数据结构残留 |
| B3-1 | 文件格式不一致 | ✅ 已解决 | 2026-06-07 改 `<file>` XML 格式+防注入, commit 00a762d |
| C2-1 | 白名单多 user-files | ✅ 已对齐 | 2026-06-07 补入 baseline C2 设计 |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 DRAFT | 2026-06-01 | 初始审查，发现 7 条差异 |
| V2.0 ACTIVE | 2026-06-07 | 全面重审：5 条旧问题已修复，新增 O 模块审查（6 条全部符合设计），总差异降至 2 条 |
| V2.0 ACTIVE | 2026-06-07 | **B3-1 已修复**（commit 00a762d）：`<file>` XML 格式+防注入 |
| V2.0 ACTIVE | 2026-06-07 | **C2-1 已对齐**：补 baseline C2 白名单设计（user-files）。全部差异闭环 |
| V2.0 ACTIVE | 2026-06-07 | **D模块/卡片系统深化**：新增 ac-card-spec 规范；todo 卡片按规范重构(两栏三段+done_date+方案C+钩子) commit `4d39498`；其他卡片待逐张接入钩子(见 card-spec T3) |

---

## 🐛 2026-06-11 认证 Bug 修复（登录后立即被踢回登录页）

| 编号 | 模块 | 类型 | 状态 | 说明 |
|------|------|------|------|------|
| AU-FIX-1 | 用户系统(AU14 拦截器) | 行为偏差 | ✅ 已修复 | 全局 fetch 拦截器对任意 401 即 `clearAuth`+`showLoginOnly`；而 Dashboard 卡片请求从 `#token` 框取 Gateway Token（网页登录用户该框为空）→ 发出空 `Bearer ` → 拦截器误判"已带 auth"不注入 JWT → 服务端 401 → 立即被踢回登录页 |

**修复内容（index.html，commit `41bd17e`）：**
1. **拦截器治本**：将"空 Bearer"识别为无有效凭证，自动用 JWT 覆盖注入（约 4021 行 `window.fetch` 包装）。
2. **源头修正**：卡片相关请求取 token 由 `document.getElementById('token').value` 改为 `authJwt || ...`（含 `loadCardData` 共 29 处），凭证从源头带对，拦截器仅兜底。

**未改动**：`connect()`（4538 行）连接 Gateway 时仍读 `#token` 输入框（该处确需 Gateway Token，非 JWT）。

