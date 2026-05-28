# 全局搜索设计文档 — Phase 11

> 版本：V2.0 | 状态：ACTIVE | 日期：2026-05-28

---

## 一、概述

跨所有数据源的统一搜索。作为第四个独立 Tab，手动触发搜索，结果跨 Tab 持久缓存，点击精准跳转。

## 二、入口

- **Tab 按钮**：第四位 `[Chat] [Files] [Daily] [🔍 Search]`
- **快捷键**：`Cmd+K`（Mac）/ `Ctrl+K`（Windows），按了直接切到 Search Tab

## 三、搜索界面

```
┌──────────────────────────────────────────────────┐
│  🔍  [_______输入搜索内容_______]  [搜索]        │
├──────────────────────────────────────────────────┤
│                                                  │
│  💬 对话 (3)                                     │
│  └─ 分析财报             8条消息 · 匹配"财报"    │
│  └─ Q1 数据讨论          昨 23:45                │
│                                                  │
│  📁 文件 (2)                                     │
│  └─ 财务报表_2026.pdf     2.3 MB                 │
│  └─ report_q1.docx        前天                    │
│                                                  │
│  📋 Daily (4)                                    │
│  └─ [Todo] 提交财务报表     管理员               │
│  └─ [食谱] 周三晚餐         红烧肉                │
│  └─ [笔记] Q1 财报分析...                         │
│  └─ [收藏夹] 财报分析教程                          │
│                                                  │
└──────────────────────────────────────────────────┘
```

## 四、搜索数据源

### 对话 Session
- **数据**：`user-sessions/*.json`（所有用户 Session 的 title + messages.content）
- **匹配**：语义匹配（Python difflib.SequenceMatcher，兼顾性能和效果）

### 用户文件
- **数据**：`user-files/` 下所有文件名
- **匹配**：模糊匹配文件名

### Daily 卡片（动态枚举）
- **驱动**：读取 `card-registry.json` → 获取所有已启用卡片列表
- **搜索**：遍历每个卡片的数据文件，匹配其内容字段

| 卡片 | 数据文件 | 搜索字段 |
|------|---------|---------|
| NewsCard | news-cache.json | title, summary |
| TodoCard | todos.json (daily + weekly) | text, person |
| DataCard | data/{person}/*.json | journal |
| RecipeCard | recipe.json | lunch, dinner |
| WishesCard | wishes.json | title, description, tags |
| NotesCard | notes.json | title, text, tags |
| BookmarksCard | bookmarks.json | title, description, url, tags |
| PhotosCard | photos.json | caption, tags |
| RemindersCard | reminders.json | text |
| HabitsCard | habits.json | name |
| ShareCard | share_board.json | text |

> 新增卡片只需在 card-registry.json 注册，搜索自动覆盖，无需改搜索代码。

## 五、匹配策略

- **语义模糊匹配**：使用 Python `difflib.SequenceMatcher` 做相似度评分
- **阈值**：ratio >= 0.4 视为匹配
- **优先级**：标题/文件名匹配 > 内容匹配；高优先级数据源 > 低优先级

## 六、后端 API

| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/search?q=搜索词&limit=20` | q: 搜索词, limit: 每源最多条数 | 分组结果 |

**响应格式**
```json
{
  "results": [
    {
      "group": "对话",
      "icon": "💬",
      "items": [
        {
          "id": "sess_20260528_000956",
          "title": "分析财报",
          "subtitle": "4 条消息",
          "match_preview": "...财报数据...",
          "action": "open_session",
          "action_data": {
            "session_id": "sess_20260528_000956",
            "message_index": 2
          }
        }
      ]
    },
    {
      "group": "文件",
      "icon": "📁",
      "items": [
        {
          "id": "report_q1.docx",
          "title": "report_q1.docx",
          "subtitle": "user-files · 2026-05-27",
          "match_preview": null,
          "action": "open_file",
          "action_data": {
            "path": "/user-files/report_q1.docx"
          }
        }
      ]
    },
    {
      "group": "Daily",
      "icon": "📋",
      "items": [
        {
          "id": "todo_3",
          "title": "提交财务报表",
          "subtitle": "Todo · 管理员",
          "match_preview": "提交财务...",
          "action": "open_daily_card",
          "action_data": {
            "card_type": "TodoCard",
            "item_id": "todo_3"
          }
        }
      ]
    }
  ],
  "total": 8,
  "query": "财务"
}
```

## 七、前端交互

### 搜索触发
- 用户输入搜索词 → 点击「搜索」按钮 或 按 Enter → 触发搜索
- **不做自动搜索**，只在用户确认后执行

### 结果缓存
- 搜索结果缓存在前端 `searchResults` 变量中
- 点击结果跳转到其他 Tab → 结果不动
- 再切回 Search Tab → 直接显示缓存结果
- 用户**修改搜索词并再次确认**（按钮/Enter）→ 刷新结果

### 键盘导航
- ↑↓ 键选择结果项
- Enter 打开选中项（跳转）
- 搜索结果页默认焦点在搜索框

### 跳转行为

| action | 跳转目标 |
|--------|---------|
| `open_session` | 切 Chat Tab → `loadConversation(session_id)` → 滚动到 `message_index` → 高亮该消息 2 秒 |
| `open_file` | 切 Files Tab → 展开目录树 → 定位文件并打开（调用 `navigateToFile`） |
| `open_daily_card` | 切 Daily Tab → 展开对应卡片（`expandCard(card_type)`） |

### 关键词高亮
- 搜索结果中匹配文本用 `<mark>` 标签高亮

## 八、实现清单

| # | 内容 | 分类 |
|---|------|:--:|
| GS1 | fileserver.py：新增 `GET /v1/api/search` 端点 | 后端 |
| GS2 | 搜索逻辑：遍历 Session / 文件 / Daily 卡片，语义匹配 | 后端 |
| GS3 | Daily 卡片动态枚举：读 card-registry.json 获取卡片列表 | 后端 |
| GS4 | ✅ | 前端：Search Tab 路由 + Tab 按钮（第四个） | 前端 |
| GS5 | ✅ | 前端：搜索输入框 + 搜索按钮 + Enter 触发 | 前端 |
| GS6 | ✅ | 前端：分组结果列表渲染 + 关键词高亮 | 前端 |
| GS7 | ✅ | 前端：键盘导航（↑↓ Enter） | 前端 |
| GS8 | ✅ | 前端：点击跳转（open_session / open_file / open_daily_card） | 前端 |
| GS9 | ✅ | 前端：搜索结果缓存（切 Tab 不丢，改查询 + 确认才刷新） | 前端 |

## 九、进度追踪

| Phase | 内容 | 状态 |
|:-----:|------|:----:|
| 11 | 🔍 全局搜索 | ✅ 完成 |
