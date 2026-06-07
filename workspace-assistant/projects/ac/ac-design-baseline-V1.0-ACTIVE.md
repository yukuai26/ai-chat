---
entity: ac
descriptor: design-baseline
version: "1.0"
status: ACTIVE
author: 小助手
created: "2026-06-01"
project_manager: 管理员
purpose: 经管理员 2026-06-01 逐条确认的"真实设计基线"，作为代码审查（设计↔代码比对）的唯一权威依据。覆盖/纠正此前 projects/ac/ 下各分散设计文档中已过时的部分。
---

# ac-design-baseline — Assistant Web Chat 真实设计基线 V1.0

> 本文件由管理员于 2026-06-01 在飞书逐条确认生成。
> **冲突时以本文件为准**，旧的 ac-*-design 文档若与此处矛盾，以此处为最新设计意图。
> 后续代码审查（"代码是否符合设计"）以本文件列出的条目为评判标准。

> ## ⚠️ 铁律：设计与代码双向同步（2026-06-07 管理员确认）
> **改代码的同时必须改设计；改设计的同时必须改代码。** 二者永远一一对应。
> - 任何对 `/var/www/chat/index.html` 或 `fileserver.py` 的功能性改动，都要同步更新本 baseline + audit 报告对应条目。
> - 任何对本 baseline 的设计变更，都要落到实际代码（或在 audit 报告里标 TODO 跟踪）。
> - 代码做了但设计没写 → 补设计；设计写了但代码没做 → 代码里实现或在 audit 标 **TODO**。

## 一、审查范围与原则

- 代码位置：`/var/www/chat/fileserver.py`（后端 ~6000 行）+ `/var/www/chat/index.html`（前端 **9727 行**，2026-06-07）
- DRAFT 文档（营养系统 Phase 17、统一文件 Phase 16、UX 优化）**不纳入"违规"判定**，仅作参考。
- Build喵（buildcat）系统已暂停，**不审查、不纳入**。

## 二、确认后的设计条目（权威）

### A. 整体架构 / 访问与认证
- **A1【已更新】** 访问方式：**用户用账号密码登录后即可使用**。
  - 原 ac-project-plan 中"不做用户登录、使用共享 Token"的范围定义**已作废**。
- A3. 架构：浏览器 → Cloudflare Tunnel → nginx → Gateway(127.0.0.1:18789) + fileserver(127.0.0.1:5050)。

### B. 💬 聊天 + 会话
- B1【沿用】会话存储 `user-sessions/{id}.json`，左侧列表按 今天/昨天/更早 分组。
- B2【沿用】端点：`/v1/sessions/new|list|{id}|{id}/chat`，DELETE 删除。
- **B3【已实现 2026-06-07】** 文件传输：聊天中选/带文件作为附件，注入格式**对齐 OpenClaw/飞书标准**，核心目标=**提升模型识别可靠性**。
  - 格式：`<file name="文件名" mime="类型">\n<文件内容>\n</file>`（XML 标签，结构化边界清晰）。
  - 位置：**追加到 user 消息正文末尾**（不再用独立 system 消息）。
  - 防注入：文件内容里的 `</file>` / `<file` 被转义（`_escape_file_body` / `_escapeFileBody`），防止伪造标签逃逸。
  - 截断：前端文本 50000 字符 / 后端 `MAX_EXTRACT_CONTENT_LENGTH=50000` 字符 / 文本文件大小上限 `MAX_TEXT_EXTRACT_SIZE=500KB`。
  - 二进制/过大/读不了：降级为带 `note` 属性的 `<file>` 块，提示用 read 工具。
  - 对应代码 commit `00a762d`：前端 `_doSendMessage`/`_fallbackHttpSend`（index.html）+ 后端 `_parse_file_attachment`/`_build_gateway_messages`（fileserver.py）。

### C. 📁 文件浏览器【沿用全部】
- C1. 端点：`/v1/files/ls|read|write|upload|mkdir|download|health`。
- C2【已更新 2026-06-07】安全：登录认证 + 路径白名单（**3 个目录：workspace-assistant + workspace-build-cat + user-files**）+ 防 `..` 穿越 + 拒绝绝对路径绕过。
  - 说明：`user-files` 是用户上传/创建文件的存储目录，文件浏览器需读写它，属合理白名单项（原设计仅列 assistant + build-cat，2026-06-07 补入 user-files 与代码对齐，解决 audit C2-1）。
- C3【已更正 2026-06-02】fileserver 端口 127.0.0.1:**5050**（原文档/审查报告写 5001 有误，实际全链路代码/systemd/nginx 均为 5050，以 5050 为准），nginx 反代 `/v1/files/`，上传上限 50MB。
- C4. 前端：Tab 切换 + 目录树（展开折叠/类型图标/高亮）+ highlight.js 高亮 + Markdown 预览 + 编辑(Ctrl+S/未保存警告) + 拖拽上传(进度条) + 图片预览 + 下载。

### D. 📊 每日 Dashboard / 卡片系统【2026-06-07 完整对齐代码】

> 卡片采用「插件式 + 卡片喵 agent 驱动」架构。这是 D4「@前缀分发」废弃后演变出的**复杂卡片设计**，以下与实际代码一一对应。

#### D1. 插件式架构（注册表驱动）
- 卡片由**注册表** `card-registry.json` 驱动（不存在时用代码 `DEFAULT_CARD_REGISTRY` 默认值，一改即落盘）。
- 注册表 API：
  - `GET/PUT /v1/api/daily/registry` — 读/改整个注册表
  - `PUT /v1/api/daily/registry/cards/<id>` — 改单张卡片配置（enabled/width/顺序/refreshInterval）
- 每张卡片字段：`id / name / width / enabled / api / expandable / persons / refreshInterval`。
- 加新卡片 = 注册表 +1 条 + 数据 API + 前端组件，不改现有代码。

#### D2/D3. 11 张卡片
首批 5：news(资讯) / todo(Todo) / data(数据) / recipe(食谱) / wishes(心愿)。
扩展 6：notes(随手记) / bookmarks(收藏夹) / photos(照片墙) / shares(分享板) / reminders(提醒) / habits(习惯打卡)。

#### D5. 数据目录与每张卡片的 4 个标准文件
- 根目录：`user-data/daily-data/<card_id>/`（**daily-data** 为准）。
- 每张卡片目录下标准文件：
  | 文件 | 作用 |
  |------|------|
  | `data.json` | **原始数据**（真实增删改查落这里） |
  | `display.json` | **展示数据**（前端 Dashboard 直接渲染的，由卡片喵生成） |
  | `prompt.json` | **卡片喵专属指令**（card_name/domain_knowledge/best_practices/user_preferences/examples） |
  | `rules.json` | 卡片规则（如何从 data 生成 display） |
  | （recipe 还有 `generate-display.py` / `media/` / `heartbeat.json` 等扩展） |

#### D6. 卡片更新的两条路径
1. **直接数据 API（结构化 CRUD）**：每张卡片有独立端点，前端按钮/表单直接操作 `data.json`。
   - 例：`/v1/api/daily/todos`(GET/POST) + `/todos/<id>`(PUT/DELETE)；notes/bookmarks/photos/shares/reminders 同理；data 按人 `/data/<person>`；recipe `/recipe/today|week|upload`。
2. **卡片喵 agent（自然语言）**：在 **Daily 会话**（session id 以 `sess_daily_` 开头）里用自然语言说（"今天体重 70kg"），后端 `_is_daily_session` 检测 → 路由到 **`CARD_AGENT_MODEL = openclaw:card-assistant`（卡片喵, DeepSeek V4 Pro）** → 卡片喵理解后写 `data.json` 并生成 `display.json`。

#### D7. display.json 机制（前端渲染入口）
- 前端 `loadDashboard()` 只调一个接口 `GET /v1/api/daily/cards/display` 拿全部卡片展示数据。
- `display.json` **由卡片喵生成**，fileserver 只负责读（`apply_rules` / `cards/display` / `cards/display/<id>`）。
- 卡片喵更新完 display.json 后调 `POST /v1/api/daily/notify-display-update` → WebSocket 推送前端秒刷新（联动 H 模块）。

#### D8. 卡片喵指令体系（prompt）
- `GET/PUT /v1/api/daily/prompt/<card_id>` — 读/改某卡片的 prompt.json（自定义卡片喵在该卡片上的行为）。
- `_detect_card_from_text` + `CARD_KEYWORDS` — 关键词检测消息涉及哪张卡片（如"体重/喝水"→data，"食谱/午饭"→recipe）。

#### D9. 多人数据
- `CARD_PERSONS = ["yukuai26", "gugugu"]`（管理员 + 伴侣），todo/data 卡片按 person 区分。

- ⚠️ **TODO（设计↔代码待确认项）**：card-assistant（卡片喵）agent 的具体配置位置 + display.json 生成的完整规则链（rules.json 如何驱动），本次审查未逐行核对，留待后续精确比对。

### E. 🔐 用户系统
- E1【沿用·结合 A1】账号密码登录 + JWT。
- **E2【已更新】** **当前不需要注册**（登录即用）；**数据隔离仍在考虑中，暂不作为硬性设计要求**（不按"未做数据隔离"判违规）。

### F. 🔍 全局搜索【沿用】独立 Tab，跨数据源，手动触发，结果跨 Tab 缓存 + 精准跳转。

### G. 📱 手机适配【沿用】一套 CSS 兼容安卓/苹果。

### H. 🔄 实时同步【沿用】WebSocket，一人改数据另一人页面秒刷新。

### I. 📅 日历【沿用】独立 Tab，时间中枢，自身不存数据，汇聚 todos/reminders/recipe/notes/photos。

### J. 🎨 UI 美化【沿用】极简风（替代原暗黑电竞风 #1a1a2e/#e94560）。

### K. 💾 备份【沿用】每天 23:59 备份用户数据+记忆+配置 到 `yukuai26/ai-chat` 的 `backup` 分支。

### O. 💬 聊天上下文与会话记忆【2026-06-07 新增·核心设计】

> 背景：对话式 AI 的上下文记忆机制。对齐 DeepSeek/OpenAI 大厂标准——**模型无状态，上下文每次由前端从持久化历史重建**。
> 网页对话使用两个专用 agent：`webchat-v4`（DeepSeek V4 Pro）/ `webchat-opus`（Claude Opus），共享 workspace `workspace-webchat`。

- **O1【上下文来源 = session 文件】** 每个对话对应磁盘上的 `user-sessions/{id}.json`，**永久保存不过期**。发消息时前端从该文件读出历史，拼进 `messages` 一起发给 Gateway。这是上下文的**唯一权威来源**。
- **O2【全量带历史 + token 兜底】** `loadRecentHistory()` 默认**全量带**该会话所有 user/assistant 消息（不再是"最近 N 条"）。仅当累计 token 超 `HISTORY_TOKEN_BUDGET=150000`（按最小模型 Opus 200K 窗口保守取值）时，从最旧的开始丢弃。粗估 `_estTokens = 字符数/2`。
- **O3【Gateway 无状态 / 随机 user】** 发消息时 `user` 字段用 `_randomUser()`（每次随机），使 Gateway **每次都当全新会话、会话层自带历史=空**。彻底消除"Gateway 自带历史 + 前端塞历史"的**重复（塞两遍）**问题。WS 路径和 HTTP fallback 两处都用随机 user。
- **O4【中途切模型不丢上下文】** `switchModel()` 只改 `agentId`，不碰 `activeConversationId`、不新建 session。因历史跟 **session 文件**走（不跟模型走），切 ⚡V4 / 🧠Opus 后新模型仍能从带入的历史看到完整对话。历史**透明混合**，不标注来源模型。
- **O5【持久记忆铁律】** `workspace-webchat/MEMORY.md` 是**跨对话共享**的持久记忆（写进去会被所有对话/所有模型带上）。webchat agent **想写 MEMORY.md 前必须先告知用户**、说明"会被所有对话带上"、得到同意后才写（已写入 `workspace-webchat/SOUL.md`）。保留写记忆能力，但禁止自作主张写。
- **O6【两条传输路径】** 主路径 = WebSocket（`type:chat`，长连接，绕过 Cloudflare 100s 超时，扛长回复）；回退 = HTTP 直连 Gateway `/v1/chat/completions`（WS 5 秒内未连上时）。两路上下文处理一致（都带全量历史 + 随机 user）。

## 三、明确排除（不审查）
- **L. 营养系统**（Phase 17）：属卡片具体设计，不在 Web 端设计范围，跳过。
- **M. 统一文件上传**（Phase 16 DRAFT）：管理员认为现有代码设计可接受，保持现状，不判违规。
- **N. Build喵 系统**：已暂停，目前不用，跳过。

## 四、已知"文档 vs 现实"疑点（供审查参考）
1. ac-project-plan 范围定义整体过时（A1/E1 已推翻"不做登录/上传"）。
2. Dashboard 数据目录 user-data/ → daily-data/（D5）。
3. @前缀分发已废弃（D4）。

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-06-01 | 初始基线，经管理员逐条确认 |
| V1.0 | 2026-06-02 | C3 端口更正 5001→5050（采纳审查报告 C3-1，选择以现状 5050 为准）；配合本轮修复 K-1/H-1/E2/D4 |
| V1.0 | 2026-06-07 | 新增 **O. 聊天上下文与会话记忆**（O1-O6：session文件为准/全量历史+150K兜底/随机user无状态/切模型不丢/持久记忆铁律/双路径）；新增**设计↔代码双向同步铁律**；行数更新 index.html→9727；对应代码 commit `7b9f5b0` |
| V1.0 | 2026-06-07 | **B3 已实现**：文件注入改为 `<file>` XML 格式 + 追加 user 消息 + 防注入转义 + 截断调大(50K/500KB)；解决 audit B3-1 高优先 TODO；index.html→9722；对应代码 commit `00a762d` |
| V1.0 | 2026-06-07 | **D 模块（卡片系统）完整重写对齐代码**：D1 注册表 / D5 四标准文件(data/display/prompt/rules) / D6 两条更新路径(直接API + 卡片喵agent) / D7 display.json由卡片喵生成+WS推送 / D8 prompt指令体系 / D9 多人。留 1 个待确认 TODO(卡片喵配置+rules链) |
