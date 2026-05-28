# 每日 Dashboard 设计文档

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

在网页上新增「📊 每日」Tab，卡片式仪表盘。每个卡片是独立可插拔模块，通过注册表统一管理，支持无限扩展。

### 核心设计原则

1. **卡片即插件**：新功能 = 注册一个新卡片 + API 端点 + 前端组件
2. **指令中枢**：底部统一输入框，通过 `@前缀` 分发到不同功能模块
3. **缩略→展开**：卡片默认折叠显示摘要，点击展开完整内容
4. **多人数据**：Todo / 数据追踪支持多人份（管理员 + 伴侣）

---

## 二、页面布局

### 2.1 卡片模式（默认：折叠缩略）

```
┌──────────────────────────────────────────────────────────┐
│  💬 聊天  │  📁 文件  │  📊 每日                        │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│  │ 📰 资讯   │ │ 📋 Todo  │ │ 📊 数据  │                  │
│  │ 8 条更新  │ │ ☑ 2/5   │ │ 👤 2 人  │                  │
│  │ 08:00 已推│ │ 本周 1/3 │ │ 今日更新 │                  │
│  │ [展开 ▼] │ │ [展开 ▼] │ │ [展开 ▼] │                  │
│  └──────────┘ └──────────┘ └──────────┘                  │
│                                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│  │ 🍽️ 食谱  │ │ 💡 心愿  │ │ + 添加   │                  │
│  │ 午餐:沙拉 │ │ 3 个想法 │ │ 卡片     │                  │
│  │ 热量:1180 │ │ [展开 ▼] │ └──────────┘                  │
│  │ [展开 ▼] │ └──────────┘                                │
│  └──────────┘                                              │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ 📎  │  输入指令...                          [发送]  │ │
│  └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 2.2 卡片展开模式（点击后全屏/大面板）

```
┌──────────────────────────────────────────────────────────┐
│  📰 资讯                                      [✕ 收起]  │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  2026-05-27 周三                                          │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ 🏛️ 政策                                            │  │
│  │ · 央行宣布下调存款准备金率25个基点，释放流动性约5000亿│  │
│  │ · 国务院发布促进AI产业发展新十条                      │  │
│  │ · 上海调整住房限购政策，非户籍购房社保年限缩短        │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ 💻 科技                                            │  │
│  │ · 特斯拉因自动辅助驾驶问题全球召回80万辆Model Y      │  │
│  │ · 苹果Vision Pro在华开启预购，起售价29999元          │  │
│  │ · 字节跳动推出视频生成模型"即梦"，对标Sora           │  │
│  ├─────────────────────────────────────────────────────┤  │
│  │ 🌍 国际                                            │  │
│  │ · 美联储维持利率不变，暗示年内或降息两次              │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  [刷新新闻]  [设置推送时间]  [新闻源管理]                 │
└──────────────────────────────────────────────────────────┘
```

### 2.3 Todo 卡片展开

```
┌──────────────────────────────────────────────────────────┐
│  📋 Todo                                        [✕ 收起] │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  [👤 管理员]  [👤 伴侣]                                   │
│                                                           │
│  📅 今日 (2026-05-27)                                     │
│  ☑ 提交周报                                      [× 删]  │
│  ☐ 回复邮件                                      [× 删]  │
│  ☐ 买牛奶                                        [× 删]  │
│  ┌─ 添加今日 Todo ───────────────────── [+ 添加] ──────┐ │
│                                                           │
│  📅 本周 (W22)                                            │
│  ☐ 周末大扫除                                    [× 删]  │
│  ☐ 写月报                                        [× 删]  │
│  ┌─ 添加本周 Todo ───────────────────── [+ 添加] ──────┐ │
│                                                           │
│  📊 完成率: 2/5 (40%)                                     │
└──────────────────────────────────────────────────────────┘
```

---

## 三、卡片插件系统

### 3.1 卡片注册表

```json
// user-data/card-registry.json
{
  "cards": [
    {
      "id": "news",
      "name": "📰 资讯",
      "width": "medium",
      "enabled": true,
      "api": "/v1/api/daily/news",
      "expandable": true,
      "refreshInterval": 3600
    },
    {
      "id": "todo",
      "name": "📋 Todo",
      "width": "medium",
      "enabled": true,
      "api": "/v1/api/daily/todos",
      "persons": ["管理员", "伴侣"],
      "expandable": true
    },
    {
      "id": "data",
      "name": "📊 数据",
      "width": "medium",
      "enabled": true,
      "api": "/v1/api/daily/data",
      "persons": ["管理员", "伴侣"],
      "expandable": true
    },
    {
      "id": "recipe",
      "name": "🍽️ 食谱",
      "width": "medium",
      "enabled": true,
      "api": "/v1/api/daily/recipe/today",
      "expandable": true
    },
    {
      "id": "wishes",
      "name": "💡 心愿",
      "width": "medium",
      "enabled": true,
      "api": "/v1/api/daily/wishes",
      "expandable": true
    }
  ],
  "layout": {
    "columns": 3,
    "order": ["news", "todo", "data", "recipe", "wishes"],
    "gap": 16
  },
  "commandPrefixes": [
    {"prefix": "@todo", "action": "add_todo", "api": "/v1/api/daily/todos", "method": "POST"},
    {"prefix": "@done", "action": "check_todo", "api": "/v1/api/daily/todos/{id}", "method": "PUT"},
    {"prefix": "@data", "action": "update_data", "api": "/v1/api/daily/data/{person}", "method": "POST"},
    {"prefix": "@news", "action": "query_news", "api": "/v1/api/daily/news", "method": "GET"},
    {"prefix": "@recipe", "action": "recipe", "api": "/v1/api/daily/recipe", "method": "GET"},
    {"prefix": "@schedule", "action": "schedule", "api": "/v1/api/daily/schedule", "method": "POST"},
    {"prefix": "@wish", "action": "add_wish", "api": "/v1/api/daily/wishes", "method": "POST"},
    {"prefix": "@sum", "action": "summary", "api": "/v1/api/daily/summary", "method": "GET"}
  ]
}
```

### 3.2 加新功能流程

```
未来加「📸 拍饭分析」:

1. card-registry.json 加一行
   {"id":"photo-food","name":"📸 拍饭","width":"medium","enabled":true,...}

2. fileserver.py 加端点
   POST /v1/api/daily/photo-food/analyze

3. index.html 加组件
   class PhotoFoodCard extends BaseCard { ... }

→ 立即可用，不碰现有代码
```

---

## 四、底部指令中枢

### 4.1 输入框特性

- 文本输入（Enter 发送）
- 📎 选择文件（多选，支持拖拽）
- 拖拽文件到输入框区域
- 发送时附带文件路径列表

### 4.2 指令解析

```
输入 "@todo 管理员 买牛奶"
  ↓ POST /v1/api/daily/command
  ↓ 解析: prefix=@todo, person=管理员, text=买牛奶
  ↓ POST /v1/api/daily/todos {person:"管理员", text:"买牛奶", type:"daily"}
  ↓ 返回 {ok:true, msg:"已添加管理员 Todo: 买牛奶"}
  ↓ 前端刷新 Todo 卡片
```

### 4.3 自然语言回退

不匹配任何 `@前缀` 的输入 → 当成自然语言指令 → 发给主 Agent 处理（走聊天通道）

---

## 五、多人数据机制

### 5.1 Todo 数据

```json
{
  "管理员": [
    {"id": 1, "text": "提交周报", "done": true, "type": "daily", "date": "2026-05-27"},
    {"id": 2, "text": "回复邮件", "done": false, "type": "daily", "date": "2026-05-27"}
  ],
  "伴侣": [
    {"id": 1, "text": "买菜", "done": false, "type": "daily", "date": "2026-05-27"}
  ]
}
```

### 5.2 个人数据

```json
{
  "管理员": {
    "weight": {"2026-05-20": 72, "2026-05-27": 71.5},
    "exercise": {"2026-05-27": "跑步 30min"},
    "water": {"2026-05-27": 5}
  },
  "伴侣": {
    "weight": {"2026-05-27": 55},
    "water": {"2026-05-27": 3}
  }
}
```

### 5.3 数据更新规则

- 更新前显示当前值 → 确认后更新
- 指令格式：`@data 管理员 体重 72` → 更新后返回旧值 + 新值
- 网页操作：点击数据值 → 弹输入框 → 确认更新

---

## 六、心愿池机制

### 6.1 心愿状态流转

```
idea → discussing → designing → implementing → done
想法    讨论中      设计中       实现中        完成
```

### 6.2 心愿数据结构

```json
{
  "id": "w1",
  "title": "拍饭分析",
  "description": "拍一张饭的照片，自动分析吃了什么、多少卡路里",
  "status": "idea",
  "created": "2026-05-27",
  "createdBy": "管理员",
  "tags": ["健康", "AI", "图片分析"]
}
```

### 6.3 心愿 → 项目迁移

```
管理员: "把拍饭分析拆成项目做"
  ↓
我: 写设计文档 → pipeline-state.json todo
  ↓ wish 状态 → "designing"
Build喵: 拆 Issue → 实现
  ↓ wish 状态 → "implementing"
实现完成 → card-registry 注册
  ↓ wish 状态 → "done"
```

---

## 七、定时任务

| # | Cron | 功能 |
|---|------|------|
| C1 | 每天 08:00 | 爬新闻 + 推送摘要（飞书 + 更新网页缓存） |
| C2 | 每天 20:00 | 今日数据提醒（饮水/Todo 完成率） |
| C3 | 每周日 20:00 | 本周总结（运动天数/Todo 完成率/数据趋势） |

---

## 八、后端 API 设计

### 8.1 指令中枢

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/v1/api/daily/command` | 解析文本指令并分发 |

### 8.2 新闻

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/news` | 读取今日新闻缓存 |
| POST | `/v1/api/daily/news/refresh` | 手动刷新新闻 |
| GET | `/v1/api/daily/news/sources` | 新闻源配置 |
| PUT | `/v1/api/daily/news/sources` | 更新新闻源 |

### 8.3 Todo

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/todos` | 读取 Todo（可选 ?person=管理员 &type=daily） |
| POST | `/v1/api/daily/todos` | 新增 Todo |
| PUT | `/v1/api/daily/todos/{id}` | 更新 Todo（勾选/改文本） |
| DELETE | `/v1/api/daily/todos/{id}` | 删除 Todo |

### 8.4 数据追踪

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/data/{person}` | 读取某人全部数据 |
| GET | `/v1/api/daily/data/{person}/{field}` | 读取某人特定字段（如 weight） |
| POST | `/v1/api/daily/data/{person}` | 更新数据 {field, value, date} |

### 8.5 食谱

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/recipe/today` | 今日食谱建议 |
| POST | `/v1/api/daily/recipe/upload` | 上传/更新食谱 |
| GET | `/v1/api/daily/recipe/week` | 查看整周食谱 |

### 8.6 心愿池

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/wishes` | 列出所有心愿 |
| POST | `/v1/api/daily/wishes` | 新增心愿 |
| PUT | `/v1/api/daily/wishes/{id}` | 更新心愿状态/描述 |
| DELETE | `/v1/api/daily/wishes/{id}` | 删除心愿 |

### 8.7 面板配置

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/config` | 读取面板配置（card-registry + layout） |
| PUT | `/v1/api/daily/config` | 更新面板配置 |
| PUT | `/v1/api/daily/config/cards/{id}` | 启用/禁用/排序单个卡片 |

### 8.8 统计

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/summary/{period}` | period=week/month → 汇总数据 |

---

## 九、数据存储

```
/home/ubuntu/.openclaw/user-data/
  ├── card-registry.json        ← 卡片注册表
  ├── dashboard-config.json     ← 用户布局配置
  ├── todos.json                ← Todo 数据
  ├── profiles/
  │   ├── admin.json            ← 管理员数据
  │   └── partner.json          ← 伴侣数据
  ├── news/
  │   ├── 2026-05-27.json       ← 每日新闻缓存
  │   └── sources.json          ← 新闻源配置
  ├── recipe.json               ← 食谱配置
  ├── wishes.json               ← 心愿池
  └── logs/
      └── commands.jsonl        ← 指令执行日志
```

---

## 十、TODO

### 后端 — 基础设施

| # | TODO | 状态 |
|---|------|:----:|
| DB1 | 创建用户数据目录 `/home/ubuntu/.openclaw/user-data/` 及子目录 | [x] |
| DB2 | 实现卡片注册表读写（card-registry.json 初始结构） | [x] |
| DB3 | 实现统一指令中枢 POST `/v1/api/daily/command`（前缀解析 + 分发） | [x] |
| DB4 | 实现面板配置 API GET/PUT `/v1/api/daily/config` | [x] |

### 后端 — 新闻模块

| # | TODO | 状态 |
|---|------|:----:|
| DB5 | 实现新闻 API GET `/v1/api/daily/news`（读缓存 + 分类） | [x] |
| DB6 | 实现新闻刷新 POST `/v1/api/daily/news/refresh`（触发爬虫） | [x] |
| DB7 | 实现新闻源管理 API GET/PUT `/v1/api/daily/news/sources` | [x] |
| DB8 | 实现新闻爬虫脚本 `scripts/news_crawler.py` | [x] |

### 后端 — Todo 模块

| # | TODO | 状态 |
|---|------|:----:|
| DB9 | 实现 Todo CRUD（GET/POST/PUT/DELETE `/v1/api/daily/todos`） | [x] |
| DB10 | Todo 支持双人数据（?person= 参数） | [ ] |
| DB11 | Todo 支持每日/每周分类（?type=daily|weekly 参数） | [ ] |

### 后端 — 数据追踪模块

| # | TODO | 状态 |
|---|------|:----:|
| DB12 | 实现个人数据 API GET `/v1/api/daily/data/{person}` | [x] |
| DB13 | 实现个人数据更新 POST `/v1/api/daily/data/{person}` | [x] |
| DB14 | 实现字段级数据查询 GET `/v1/api/daily/data/{person}/{field}` | [x] |

### 后端 — 食谱模块

| # | TODO | 状态 |
|---|------|:----:|
| DB15 | 实现食谱上传 POST `/v1/api/daily/recipe/upload` | [x] |
| DB16 | 实现今日食谱 GET `/v1/api/daily/recipe/today`（根据星期几查） | [x] |
| DB17 | 实现整周食谱 GET `/v1/api/daily/recipe/week` | [x] |

### 后端 — 心愿池模块

| # | TODO | 状态 |
|---|------|:----:|
| DB18 | 实现心愿池 CRUD GET/POST/PUT/DELETE `/v1/api/daily/wishes` | [x] |
| DB19 | 心愿状态流转 + 标签支持 | [x] |

### 后端 — 统计 + 定时

| # | TODO | 状态 |
|---|------|:----:|
| DB20 | 实现统计汇总 GET `/v1/api/daily/summary/week` | [ ] |
| DB21 | 统计汇总支持月度 GET `/v1/api/daily/summary/month` | [ ] |
| DB22 | 设置 cron 新闻推送（每天 08:00） | [x] |
| DB23 | 设置 cron 每日数据提醒（每天 20:00） | [x] |
| DB24 | 设置 cron 每周总结（每周日 20:00） | [x] |

### 后端 — nginx 部署

| # | TODO | 状态 |
|---|------|:----:|
| DB25 | 更新 nginx 配置：添加 `/v1/api/daily/` 代理到 Flask | [x] |

### 前端 — 骨架

| # | TODO | 状态 |
|---|------|:----:|
| DF1 | 新增「📊 每日」Tab 路由（与聊天/文件 Tab 并列） | [x] |
| DF2 | 卡片网格布局引擎（columns 可配，自适应） | [x] |
| DF3 | 卡片缩略模式（默认折叠：标题 + 摘要 + 展开按钮） | [x] |
| DF4 | 卡片展开模式（全宽面板，内容完整渲染，✕ 收起） | [x] |
| DF5 | [+ 添加卡片] 按钮 + 卡片选择弹窗 | [x] |
| DF6 | 卡片排序拖拽（编辑布局） | [x] |

### 前端 — 指令中枢

| # | TODO | 状态 |
|---|------|:----:|
| DF7 | 底部指令输入框组件（常驻 Dashboard 底部） | [x] |
| DF8 | 输入框 📎 文件选择按钮（复用 Phase 5 文件选择器） | [x] |
| DF9 | 拖拽上传区域（输入框接受 drop 事件） | [ ] |
| DF10 | 指令发送 + 返回结果提示（toast） | [x] |
| DF11 | 文件附件标签展示（选中文件在输入框上方显示） | [ ] |

### 前端 — 新闻卡片

| # | TODO | 状态 |
|---|------|:----:|
| DF12 | NewsCard 缩略模式（日期 + 条数 + 最新 3 条摘要 + [展开]） | [ ] |
| DF13 | NewsCard 展开模式（按分类分组列表 + 每条标题+来源可点击） | [ ] |
| DF14 | 新闻详情弹窗（点击标题 → 弹窗显示正文） | [x] (已在 DF13 PR#176 实现) |
| DF15 | 新闻卡片刷新按钮 + 推送时间设置入口 | [ ] |

### 前端 — Todo 卡片

| # | TODO | 状态 |
|---|------|:----:|
| DF16 | TodoCard 缩略模式（完成率 + 待办数 + [展开]） | [ ] |
| DF17 | TodoCard 展开模式（双人 Tab 切换 + 每日/本周 Tab + 勾选+删除） | [ ] |
| DF18 | Todo 添加输入框（展开模式内嵌） | [ ] |
| DF19 | Todo 勾选动画 + 完成率进度条 | [ ] |

### 前端 — 数据卡片

| # | TODO | 状态 |
|---|------|:----:|
| DF20 | DataCard 缩略模式（人数 + 最近更新日期 + [展开]） | [ ] |
| DF21 | DataCard 展开模式（双人 Tab + 字段列表 + 点击编辑） | [ ] |
| DF22 | 数据更新弹窗（显示旧值 → 输入新值 → 确认） | [ ] |

### 前端 — 食谱卡片

| # | TODO | 状态 |
|---|------|:----:|
| DF23 | RecipeCard 缩略模式（日期 + 午/晚餐摘要 + 热量 + [展开]） | [ ] |
| DF24 | RecipeCard 展开模式（整周食谱表格 + 热量合计 + 上传新食谱按钮） | [ ] |

### 前端 — 心愿卡片

| # | TODO | 状态 |
|---|------|:----:|
| DF25 | WishesCard 缩略模式（心愿数量 + 按状态统计 + [展开]） | [ ] |
| DF26 | WishesCard 展开模式（列表 + 状态标签 + 优先级 + 详情） | [ ] |

### 前端 — 统计总结

| # | TODO | 状态 |
|---|------|:----:|
| DF27 | 周/月总结组件（图表化展示运动天数、Todo 完成率、数据趋势） | [x] |

---

## 十一、进度追踪

| Phase | 内容 | 状态 | TODO 数 |
|:-----:|------|:----:|:----:|
| 6a | 骨架：注册表 + 网格布局 + 指令中枢 + 底部输入框 | ✅ 已完成 | 12 |
| 6b | 首批卡片：新闻 + Todo + 食谱 + 数据追踪 + 心愿 | ⏳ 进行中 | 21 |
| 6c | 统计 + 定时任务 + 心愿迁移流程 | ⬚ 待开始 | 10 |
| 6d+ | 后续卡片（拍饭分析/天气/记账/...） | ⬚ 待开始 | 按需 |

---

## 十二、后续扩展预留

| 功能 | 卡片 ID | 说明 |
|------|---------|------|
| 拍饭分析 | `photo-food` | 拍照 → Claude Vision 识别食物 → 计算热量 |
| 天气预报 | `weather` | 调用天气 API → 每日天气卡片 |
| 记账 | `finance` | 支出/收入记录 + 月度汇总 |
| 饮水提醒 | `water-reminder` | 定时提醒 + 饮水打卡 |
| 步数统计 | `steps` | 接入健康数据 |
| 阅读列表 | `reading-list` | 书籍/文章收藏 + 进度 |
| 习惯追踪 | `habits` | 习惯打卡 + 连续天数 |

---

_设计完成，待 Build喵 分析并拆解为 GitHub Issue。_


---

## 十三、首批卡片详细设计（Phase 6b）

> 以下为 Build喵 实现时必须达到的雏形标准。管理员后续微调。

### 13.1 📰 资讯卡片（NewsCard）

**数据模型**
```json
{
  "date": "2026-05-27",
  "generated": "2026-05-27T08:00:00+08:00",
  "articles": [
    {
      "id": "a1",
      "title": "央行宣布下调存款准备金率25个基点",
      "source": "央视新闻",
      "category": "政策",
      "summary": "中国人民银行决定下调金融机构存款准备金率0.25个百分点...",
      "url": "https://...",
      "time": "2026-05-27T07:30:00+08:00"
    }
  ]
}
```

**缩略模式**
- 显示：日期 + 总条数 + 最新 3 条标题（一行一条，截断 30 字）
- 按钮：[展开 ▼]

**展开模式**
- 顶部：日期 + 刷新按钮 + 推送时间设置齿轮
- 正文：按 category 分组，每组标题加粗
- 每条：标题（可点击 → 弹窗显示 summary + 来源链接）+ 来源 + 时间
- 弹窗：标题 + 来源 + 时间 + 摘要全文 + [原文链接]
- 按钮：[刷新新闻] [设置推送时间]

**API**
| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/daily/news` | — | 今日新闻对象 |
| POST | `/v1/api/daily/news/refresh` | — | {ok, count} |
| GET | `/v1/api/daily/news/sources` | — | 新闻源列表 |
| PUT | `/v1/api/daily/news/sources` | {sources:["url1","url2"]} | {ok} |

---

### 13.2 📋 Todo 卡片（TodoCard）

**数据模型**
```json
{
  "管理员": {
    "daily": [
      {"id": 1, "text": "提交周报", "done": true, "date": "2026-05-27"},
      {"id": 2, "text": "回复邮件", "done": false, "date": "2026-05-27"}
    ],
    "weekly": [
      {"id": 10, "text": "周末大扫除", "done": false, "week": "W22"},
      {"id": 11, "text": "写月报", "done": false, "week": "W22"}
    ]
  },
  "伴侣": { ... }
}
```

**缩略模式**
- 显示：[👤管理员 2/5] [👤伴侣 1/3]
- 本周待办数
- 按钮：[展开 ▼]

**展开模式**
- 顶部：双人 Tab 切换 [👤管理员] [👤伴侣]
- 中部：Tab [📅今日] [📅本周]
- 列表区域：
  - 每条：☑/☐ 勾选框 + 文字 + [× 删除]
  - 已完成：灰色 + 删除线 + 自动排到末尾
  - 点击勾选框 → 切换 done 状态（带动画）
- 底部：输入框 + [+ 添加] 按钮 → 加到当前 Tab
- 底部统计：完成率进度条（如 ████░░░░ 40%）

**API**
| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/daily/todos?person=管理员&type=daily` | — | Todo 列表 |
| POST | `/v1/api/daily/todos` | {person, text, type} | {ok, todo} |
| PUT | `/v1/api/daily/todos/{id}` | {done: true} | {ok} |
| DELETE | `/v1/api/daily/todos/{id}` | — | {ok} |

---

### 13.3 📊 数据追踪卡片（DataCard）

**数据模型**
```json
{
  "管理员": {
    "weight": {"2026-05-20": 72, "2026-05-27": 71.5},
    "exercise": {"2026-05-27": "跑步 30min"},
    "water": {"2026-05-27": 5},
    "sleep": {"2026-05-27": 7.5}
  },
  "伴侣": { ... }
}
```

**字段配置**
```json
{
  "管理员": [
    {"key": "weight", "label": "体重", "unit": "kg", "icon": "⚖️"},
    {"key": "exercise", "label": "运动", "unit": "", "icon": "🏃"},
    {"key": "water", "label": "饮水", "unit": "杯", "icon": "🥤"},
    {"key": "sleep", "label": "睡眠", "unit": "h", "icon": "😴"}
  ]
}
```

**缩略模式**
- 显示：[👤管理员 今天更新2项] [👤伴侣 今天更新1项]
- 按钮：[展开 ▼]

**展开模式**
- 顶部：双人 Tab [👤管理员] [👤伴侣]
- 字段列表：每行 = 图标 + 标签 + 今日值 + 单位
  - 有值时显示数值（点击可编辑）
  - 无值时显示 "— 点击录入"
- 点击数值 → 弹窗（旧值 + 输入新值 + 确认）
- 字段配置可自定义（添加/删除字段）
- 底部：[本周趋势 →]（跳转统计）

**API**
| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/daily/data/{person}` | — | 全部数据 |
| GET | `/v1/api/daily/data/{person}/{field}` | — | 单个字段历史 |
| POST | `/v1/api/daily/data/{person}` | {field, value} | {ok, old, new} |

---

### 13.4 🍽️ 食谱卡片（RecipeCard）

**数据模型**
```json
{
  "week_start": "2026-05-25",
  "days": {
    "mon": {"lunch": "鸡胸沙拉", "dinner": "清蒸鱼", "calories": 1200},
    "tue": {"lunch": "西红柿鸡蛋面", "dinner": "炒青菜", "calories": 1100},
    "wed": {"lunch": "三明治", "dinner": "蔬菜汤", "calories": 1000},
    "thu": {"lunch": "", "dinner": "", "calories": 0},
    "fri": {"lunch": "", "dinner": "", "calories": 0},
    "sat": {"lunch": "", "dinner": "", "calories": 0},
    "sun": {"lunch": "", "dinner": "", "calories": 0}
  }
}
```

**缩略模式**
- 显示：日期 + 星期几 + 午餐/晚餐摘要 + 今日热量
- 如果当天无数据：显示 "今日食谱未设置"
- 按钮：[展开 ▼]

**展开模式**
- 顶部：本周日期范围
- 表格：行=星期，列=午餐 | 晚餐 | 热量
- 空单元格显示 "—"
- 底部：上传新食谱按钮
  - 弹窗：文本输入框（可粘贴整周食谱文字）
  - 格式示例："周一 午餐:沙拉 晚餐:鱼 周二 ..."
  - 后端解析后确认预览 → 保存

**API**
| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/daily/recipe/today` | — | 今日食谱 |
| GET | `/v1/api/daily/recipe/week` | — | 整周食谱 |
| POST | `/v1/api/daily/recipe/upload` | {text: "周一 ..."} | {ok, parsed} |

---

### 13.5 💡 心愿卡片（WishesCard）

**数据模型**
```json
[
  {
    "id": "w1",
    "title": "拍饭分析",
    "description": "拍一张饭的照片，自动分析吃了什么、多少卡路里",
    "status": "idea",
    "priority": "high",
    "tags": ["健康", "AI"],
    "created": "2026-05-27",
    "createdBy": "管理员"
  }
]
```

**状态标签颜色**
```
idea          → 灰色标签 "想法"
discussing    → 蓝色标签 "讨论中"
designing     → 橙色标签 "设计中"
implementing  → 绿色标签 "实现中"
done          → 绿色标签 + 删除线 "已完成"
```

**缩略模式**
- 显示：心愿总数 + 状态分布（想法:3 实现中:1 完成:2）
- 按钮：[展开 ▼]

**展开模式**
- 列表排列（按优先级 + 时间排序）
- 每条：标题 + 状态标签（彩色）+ 描述（2行截断）+ 标签 + 时间
- 点击 → 详情弹窗（完整描述 + 状态流转按钮 + 评论）
- 顶部筛选：[全部] [想法] [设计中] [实现中] [已完成]
- 底部 [+ 新心愿] 按钮 → 弹窗（标题 + 描述 + 优先级 + 标签）

**API**
| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/daily/wishes?status=idea` | — | 心愿列表 |
| POST | `/v1/api/daily/wishes` | {title, desc, priority, tags} | {ok, wish} |
| PUT | `/v1/api/daily/wishes/{id}` | {status: "designing"} | {ok} |
| DELETE | `/v1/api/daily/wishes/{id}` | — | {ok} |

---

## 十四、卡片实现检查清单

Build喵 实现每张卡片时，必须满足：

- [ ] 缩略模式：卡片网格中正常显示（标题 + 摘要数据 + 展开按钮）
- [ ] 展开模式：全宽面板，完整内容渲染
- [ ] API 对接：GET 加载数据，POST/PUT 提交变更
- [ ] 错误处理：API 失败时显示错误提示（不白屏）
- [ ] 加载状态：数据加载中显示骨架屏/loading
- [ ] 空状态：无数据时显示友好提示（不是空白）
- [ ] 多人支持：有 persons 字段的卡片支持 Tab 切换
- [ ] card-registry.json 注册
