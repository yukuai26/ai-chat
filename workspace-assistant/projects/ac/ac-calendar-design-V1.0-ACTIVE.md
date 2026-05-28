# 日历设计文档 — Phase 14

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、定位

日历不是卡片，是一个**独立的 Tab**（📅），跟 💬聊天 / 📁文件 / 📊每日 并列。

它是整个系统的时间中枢——所有跟日期相关的数据都汇聚到日历上。

## 二、Tab 布局

```
┌──────────────────────────────────────────────────────────┐
│  💬 聊天  │  📁 文件  │  📊 每日  │  📅 日历  │  ⚙     │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────┐                      ┌───────────────────┐ │
│  │   6 月    │                      │ 📅 2026年6月1日   │ │
│  │ 2026     │                      │ 星期一            │ │
│  │           │                      │                   │ │
│  │ 一 二 三 四 五 六 日 │            │ 📋 Todo           │ │
│  │              1  2  3 │            │ ☐ 提交周报       │ │
│  │  4  5  6  7  8  9 10 │            │ ☐ 回复邮件       │ │
│  │ 11 ...              │            │                   │ │
│  │                     │            │ ⏰ 提醒           │ │
│  │                     │            │ 09:00 吃维生素    │ │
│  │                     │            │ 15:00 开会       │ │
│  │                     │            │                   │ │
│  │  日历网格            │            │ 🍽️ 今日食谱       │ │
│  │  · 有 Todo 的日期   │            │ 午餐: 沙拉+鸡胸  │ │
│  │    显示小绿点        │            │ 晚餐: 蒸鱼+蔬菜  │ │
│  │  · 有提醒的日期      │            │                   │ │
│  │    显示小铃铛        │            │ 💝 今天是...      │ │
│  │  · 纪念日          │            │ —                │ │
│  │    显示小红心        │            │                   │ │
│  └──────────┘                      │ 📝 那天的随手记    │ │
│                                     │ "今天开会..."    │ │
│                                     └───────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## 三、核心交互

```
默认：左侧月历 + 右侧今日详情

月历交互：
  ← → 翻月
  点击日期 → 右侧显示那天详情
  今天 → 蓝色圆环标记
  
日期格子内标记（最多 3 个点，超出显示 "+2"）：
  🟢 绿点 = 有 Todo（未完成数）
  🔔 铃铛 = 有提醒
  ❤️ 红心 = 纪念日/生日/特别日子

右侧详情面板（选择的日期）：
  📋 当天 Todo 列表（可勾选）
  ⏰ 当天提醒列表
  🍽️ 当天食谱（如有）
  💝 当天标记（纪念日/生日/事件）
  📝 当天随手记
  📸 当天照片（如有）
  [+ 添加事件] 按钮
```

## 四、数据模型

### 4.1 日历事件

```json
// user-data/calendar.json
{
  "events": [
    {
      "id": "e1",
      "title": "纪念日",
      "date": "2026-06-15",
      "type": "anniversary",
      "icon": "💝",
      "color": "#e8a0a0",
      "description": "在一起第 365 天",
      "repeat": "yearly",
      "created_by": "管理员"
    },
    {
      "id": "e2",
      "title": "看牙医",
      "date": "2026-06-03",
      "time": "14:00",
      "type": "appointment",
      "icon": "🏥",
      "description": "洗牙",
      "created_by": "管理员"
    },
    {
      "id": "e3",
      "title": "女朋友生日",
      "date": "2026-08-20",
      "type": "birthday",
      "icon": "🎂",
      "repeat": "yearly",
      "created_by": "管理员"
    }
  ]
}
```

### 4.2 日期汇聚查询（伪代码）

```python
def get_date_summary(date):
    """查某天的所有关联数据"""
    return {
        "date": date,
        "weekday": get_weekday(date),
        "todos": filter(todos, date=date),
        "reminders": filter(reminders, date=date),
        "recipe": get_recipe(date),
        "events": filter(events, date=date),
        "notes": filter(notes, created=date),
        "photos": filter(photos, created=date),
    }
```

## 五、数据汇聚逻辑

日历自身不存 Todo/提醒/食谱，而是从各自的数据源读取：

```
日历打开时的数据流：
  ① 读 calendar.json → 纯日历事件（纪念日/生日/约会）
  ② 读 todos.json → 按日期过滤 → 标记到日期格子上
  ③ 读 reminders.json → 按日期过滤 → 标记到日期格子
  ④ 读 recipe.json → 按星期几匹配 → 显示当天食谱
  
点击某个日期：
  ⑤ 汇总 ①~④ → 渲染右侧详情面板
  ⑥ 加上那天的随手记 + 照片
```

## 六、API

| 方法 | 端点 | 入参 | 返回 |
|------|------|------|------|
| GET | `/v1/api/calendar/{date}` | — | 该日全部汇聚数据 |
| GET | `/v1/api/calendar/range?from=...&to=...` | — | 日期范围内的标记统计（用于月历渲染格子） |
| POST | `/v1/api/calendar/events` | {title, date, type, ...} | {ok, event} |
| PUT | `/v1/api/calendar/events/{id}` | {...} | {ok} |
| DELETE | `/v1/api/calendar/events/{id}` | — | {ok} |
| GET | `/v1/api/calendar/upcoming` | — | 未来 7 天的重要日期 |

**range 端点响应**
```json
{
  "2026-06-01": {"todos": 3, "reminders": 1, "events": [], "is_anniversary": false},
  "2026-06-02": {"todos": 2, "reminders": 0, "events": [], "is_anniversary": false},
  "2026-06-03": {"todos": 1, "reminders": 1, "events": ["看牙医"], "is_anniversary": false},
  ...
}
```

## 七、Todo 通过日历联动

在日历上点某天 → 看到 Todo → 直接勾选。这意味着：
- 日历和 Dashboard Todo 卡片读写同一份 `todos.json`
- 日历改了 Todo → Todo 卡片秒刷新 → WebSocket 推给伴侣

## 八、跟卡片系统的关系

| 卡片 | 日历关系 |
|------|------|
| 📋 Todo | 日历读 todos.json → 标记日期 + 可勾选 |
| ⏰ 提醒 | 日历读 reminders.json → 标记日期 |
| 🍽️ 食谱 | 日历读 recipe.json → 按星期几显示 |
| 📝 随手记 | 日历读 notes.json → 按日期显示 |
| 📸 照片墙 | 日历读 photos.json → 按日期显示 |
| 💝 纪念日 | 日历自己管理 → 独立数据，但可在其他卡片中引用 |

## 九、手机适配

```
手机日历：
  顶部：月份选择器（← 6月 →）
  月历网格（紧凑版，格子更小）
  点击日期 → 下方滑出详情面板（半屏 Sheet）
```

## 十、TODO

### 后端

| # | TODO | 状态 |
|---|------|:--:|
| CL1 | 日历事件数据模型 + CRUD API（calendar.json） | [x] |
| CL2 | 日期汇聚 GET `/v1/api/calendar/{date}`（跨数据源汇总） | [x] |
| CL3 | 范围标记 GET `/v1/api/calendar/range`（月历格子渲染数据） | [x] |
| CL4 | 未来事件 GET `/v1/api/calendar/upcoming` | [x] |
| CL5 | 日历事件 API 集成 WebSocket broadcast | [x] |

### 前端

| # | TODO | 状态 |
|---|------|:--:|
| CL6 | 📅 日历 Tab（第四 Tab，路由注册） | [x] |
| CL7 | 月历网格组件（7×6 格子 + 翻月 + 今天标记） | [x] |
| CL8 | 日期格内标记（绿点/Todo + 铃铛/提醒 + 红心/纪念日） | [x] |
| CL9 | 右侧日期详情面板（Todo + 提醒 + 食谱 + 事件 + 随手记） | [x] |
| CL10 | 日期详情内嵌 Todo 勾选（同步 todos.json） | [x] |
| CL11 | 添加事件弹窗（标题/日期/类型/重复/描述） | [x] |
| CL12 | 事件编辑 + 删除 | [x] |
| CL13 | 日历手机适配（紧凑网格 + 半屏详情 Sheet） | [x] |

## 十一、进度追踪

| Phase | 内容 | 状态 | TODO |
|:-----:|------|:----:|:--:|
| 14 | 📅 日历 Tab | ✅ 已完成 | 13 |
