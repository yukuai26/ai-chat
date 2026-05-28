# 扩展卡片设计文档 — Phase 9

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

在 Phase 6 的 Dashboard 卡片插件系统基础上，添加 6 张扩展卡片。每张卡片注册即用，不碰已有代码。

## 二、卡片总览

| # | ID | 名称 | 归属 | 类型 |
|---|-----|------|:--:|------|
| 1 | `notes` | 📝 随手记 | 👤 各自 | 时间线 |
| 2 | `bookmarks` | 🔗 收藏夹 | 👤 各自 | 列表+标签 |
| 3 | `photos` | 📸 照片墙 | 👤 各自/互相看 | 网格 |
| 4 | `share` | 📤 分享板 | 👫 互相 | 卡片推送 |
| 5 | `reminders` | ⏰ 提醒 | 👫 各自 | 列表 |
| 6 | `habits` | ✅ 习惯打卡 | 👤 各自 | 方格图 |

---

## 三、卡片一：📝 随手记

### 数据模型
```json
{
  "管理员": [
    {
      "id": "n1",
      "text": "今天开会想到一个点子：用 WebSocket 做实时协作",
      "images": [],
      "mood": "💡",
      "tags": ["工作", "想法"],
      "created": "2026-05-27T14:30:00+08:00"
    }
  ]
}
```

### 卡片展示
```
缩略：最新 3 条摘要 + 条数 + [展开]
展开：
  时间线排列（最新在上）
  每条：时间戳 + 情绪图标 + 文字 + 图片缩略 + 标签
  顶部搜索框（全文搜索）
  底部快速输入框（Enter 即存）
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/notes?person=管理员` | 随手记列表 |
| POST | `/v1/api/daily/notes` | 新增 (person, text, mood, tags) |
| PUT | `/v1/api/daily/notes/{id}` | 编辑 |
| DELETE | `/v1/api/daily/notes/{id}` | 删除 |
| GET | `/v1/api/daily/notes/search?q=关键词` | 全文搜索 |

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| N1 | 随手记数据模型 + CRUD API | [x] |
| N2 | 随手记缩略卡（最新 3 条 + 条数） | [x] |
| N3 | 随手记展开视图（时间线 + 搜索 + 快速输入） | [x] |
| N4 | 随手记图文混排（图片缩略） | [x] |

---

## 四、卡片二：🔗 收藏夹

### 数据模型
```json
{
  "管理员": [
    {
      "id": "b1",
      "url": "https://example.com/article",
      "title": "一篇好文章",
      "description": "自动抓取的摘要",
      "favicon": "https://example.com/favicon.ico",
      "tags": ["技术", "前端"],
      "created": "2026-05-27T12:00:00+08:00",
      "read": false
    }
  ]
}
```

### 卡片展示
```
缩略：收藏总数 + 最近 3 条标题 + [展开]
展开：
  列表模式：favicon + 标题 + 域名 + 标签 + 已读标记
  顶部标签筛选栏（点击标签过滤）
  搜索框（标题/URL 模糊搜索）
  新增按钮 → 弹窗输入 URL → 自动抓标题
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/bookmarks?person=管理员&tag=技术` | 收藏列表 |
| POST | `/v1/api/daily/bookmarks` | 新增 (url → 自动抓标题) |
| PUT | `/v1/api/daily/bookmarks/{id}` | 编辑/标记已读 |
| DELETE | `/v1/api/daily/bookmarks/{id}` | 删除 |

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| B1 | 收藏夹数据模型 + CRUD API | [x] |
| B2 | URL 自动抓标题+摘要（Python requests + BeautifulSoup） | [x] |
| B3 | 收藏夹缩略卡（总数 + 最新标题） | [x] |
| B4 | 收藏夹展开视图（列表 + 标签筛选 + 搜索 + 新增弹窗） | [x] |

---

## 五、卡片三：📸 照片墙

### 数据模型
```json
{
  "管理员": [
    {
      "id": "p1",
      "image": "/user-files/photos/admin_20260527_001.jpg",
      "caption": "今天的午餐 🍜",
      "likes": ["伴侣"],
      "comments": [
        {"author": "伴侣", "text": "看起来好好吃！", "time": "..."}
      ],
      "tags": ["食物"],
      "created": "2026-05-27T12:30:00+08:00"
    }
  ]
}
```

### 卡片展示
```
缩略：最新 4 张缩略图（田字格）+ 总数 + [展开]
展开：
  瀑布流/Masonry 布局
  每张：图片 + 文字 + ❤️ 点赞 + 💬 评论
  顶部 Tab：[管理员] [伴侣] [全部]
  上传按钮（拍照/选文件）
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/photos?person=管理员` | 照片列表 |
| POST | `/v1/api/daily/photos` | 上传照片 |
| PUT | `/v1/api/daily/photos/{id}` | 编辑标题/标签 |
| DELETE | `/v1/api/daily/photos/{id}` | 删除 |
| POST | `/v1/api/daily/photos/{id}/like` | 点赞/取消 |
| POST | `/v1/api/daily/photos/{id}/comment` | 评论 |

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| P1 | 照片墙数据模型 + CRUD API | [x] |
| P2 | 照片上传 + 缩略图生成（Pillow 200px 缩略） | [ ] |
| P3 | 照片墙缩略卡（4 格缩略图 + 总数） | [x] |
| P4 | 照片墙展开视图（瀑布流 + 双人 Tab + 上传按钮） | [ ] |
| P5 | 点赞 + 评论功能 | [ ] |

---

## 六、卡片四：📤 分享板

### 设计思路
你看到好东西 → 点分享 → 选要分享的内容类型（链接/文字/图片）→ 发送 → 对方卡片上出现小红点 → 点开看到。

### 数据模型
```json
{
  "sent": [
    {
      "id": "s1",
      "from": "管理员",
      "to": "伴侣",
      "type": "link",
      "content": "https://...",
      "title": "这篇文章很有意思",
      "comment": "你看看第三章",
      "read": false,
      "created": "2026-05-27T18:00:00+08:00"
    }
  ]
}
```

### 卡片展示
```
缩略：[管理员→伴侣] 未读 2 条 | [伴侣→管理员] 未读 1 条 + [展开]
展开：
  顶部分类：[收到的] [发出的]
  每条：头像 + 类型图标 + 标题 + 预览 + 发送者 + 时间
  未读红色小圆点
  点击打开内容
  分享按钮（展开模式下有快捷分享入口）
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/share/inbox?person=管理员` | 收到的分享 |
| GET | `/v1/api/daily/share/outbox?person=管理员` | 发出的分享 |
| POST | `/v1/api/daily/share` | 发送分享 |
| PUT | `/v1/api/daily/share/{id}/read` | 标记已读 |

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| REMOVED_S1 | 分享板数据模型 + API | [ ] |
| REMOVED_S2 | 分享板缩略卡（未读数 + 双向） | [ ] |
| REMOVED_S3 | 分享板展开视图（收发 Tab + 未读标记 + 内容预览） | [ ] |
| REMOVED_S4 | 快捷分享入口（其他卡片中可触发分享） | [ ] |

---

## 七、卡片五：⏰ 提醒

### 数据模型
```json
{
  "管理员": [
    {
      "id": "r1",
      "text": "下午 3 点开会",
      "time": "15:00",
      "date": "2026-05-27",
      "repeat": null,
      "done": false,
      "notified": false
    },
    {
      "id": "r2",
      "text": "每天吃维生素",
      "time": "09:00",
      "date": null,
      "repeat": "daily",
      "done": false,
      "notified": false
    }
  ]
}
```

### 提醒方式
- 网页弹窗通知（浏览器 Notification API）
- 飞书推送（cron 定时检查 → 推送）

### 卡片展示
```
缩略：今日待提醒数 + 最近 2 条即将到来 + [展开]
展开：
  时间线排列（按时间早晚）
  每条：时间 + 文字 + 重复标记🔄 + ✓完成按钮
  已完成的灰色删除线
  已过期的红色标记
  新增按钮 → 弹窗（时间选择器 + 文字 + 重复选项）
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/reminders?person=管理员` | 提醒列表 |
| POST | `/v1/api/daily/reminders` | 新增提醒 |
| PUT | `/v1/api/daily/reminders/{id}` | 编辑/标记完成 |
| DELETE | `/v1/api/daily/reminders/{id}` | 删除 |

### Cron
```
*/5 * * * * → 检查提醒 → 触发通知（飞书 + 浏览器）
```

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| R1 | 提醒数据模型 + CRUD API | [x] |
| TMP_R2 | 提醒检查 cron（每 5 分钟检查到期提醒） | [ ] |
| TMP_R3 | 提醒缩略卡（今日待办 + 即将到来） | [ ] |
| TMP_R4 | 提醒展开视图（时间线 + 完成 + 新增弹窗） | [ ] |
| R5 | 浏览器 Notification 推送 | [ ] |
| R6 | 飞书推送（cron → 调消息 API） | [ ] |

---

## 八、卡片六：✅ 习惯打卡

### 数据模型
```json
{
  "管理员": {
    "habits": [
      {"id": "h1", "name": "早起 7:00", "icon": "🌅", "target": "daily"},
      {"id": "h2", "name": "运动 30min", "icon": "🏃", "target": "daily"},
      {"id": "h3", "name": "阅读 30min", "icon": "📖", "target": "daily"},
      {"id": "h4", "name": "整理房间", "icon": "🏠", "target": "weekly"}
    ],
    "records": {
      "2026-05-27": ["h1", "h2"],
      "2026-05-26": ["h1", "h2", "h3"],
      ...
    }
  }
}
```

### 卡片展示
```
缩略：今日打卡 2/4 + 连续 5 天 + [展开]
展开：
  习惯列表（左侧） + 日历方格图（右侧）
  习惯：图标 + 名称 + 今日按钮（✅ 已打 / ○ 未打）
  日历图：7×n 方格，深色=已完成，浅色=未完成
  底部连续天数统计
  新增习惯按钮
```

### API
| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/v1/api/daily/habits?person=管理员` | 习惯列表 + 打卡记录 |
| POST | `/v1/api/daily/habits` | 新增习惯 |
| PUT | `/v1/api/daily/habits/{id}` | 修改习惯 |
| DELETE | `/v1/api/daily/habits/{id}` | 删除 |
| POST | `/v1/api/daily/habits/check` | 打卡 {person, habit_id, date} |
| DELETE | `/v1/api/daily/habits/check` | 取消打卡 |

### TODO
| # | TODO | 状态 |
|---|------|:--:|
| TMP_H1 | 习惯打卡数据模型 + API | [ ] |
| TMP_H2 | 习惯打卡缩略卡（今日进度 + 连续天数） | [ ] |
| TMP_H3 | 习惯打卡展开视图（习惯列表 + 日历方格图） | [ ] |
| H4 | 连续天数计算 + 里程碑动画（7天/30天/100天） | [ ] |

---

## 九、卡片注册表追加

```json
// user-data/card-registry.json 追加
{"id":"notes","name":"📝 随手记","width":"medium","enabled":true,"persons":["管理员","伴侣"],"expandable":true},
{"id":"bookmarks","name":"🔗 收藏夹","width":"medium","enabled":true,"persons":["管理员","伴侣"],"expandable":true},
{"id":"photos","name":"📸 照片墙","width":"wide","enabled":true,"persons":["管理员","伴侣"],"expandable":true},
{"id":"share","name":"📤 分享板","width":"medium","enabled":true,"persons":["shared"],"expandable":true},
{"id":"reminders","name":"⏰ 提醒","width":"medium","enabled":true,"persons":["管理员","伴侣"],"expandable":true},
{"id":"habits","name":"✅ 习惯","width":"medium","enabled":true,"persons":["管理员","伴侣"],"expandable":true}
```

## 十、数据存储追加

```
/home/ubuntu/.openclaw/user-data/
  ├── notes.json               ← 随手记
  ├── bookmarks.json           ← 收藏夹
  ├── photos.json              ← 照片元数据
  ├── share.json               ← 分享记录
  ├── reminders.json           ← 提醒
  ├── habits.json              ← 习惯打卡
  └── photos/                  ← 照片文件存储
      └── thumbnails/          ← 200px 缩略图
```

## 十一、进度追踪

| Phase | 内容 | 状态 | TODO |
|:-----:|------|:----:|:--:|
| 9a | 📝 随手记 | ✅ 已完成 | 4 |
| 9b | 🔗 收藏夹 | ✅ 已完成 | 4 |
| 9c | 📸 照片墙 | ✅ 已完成 | 5 |
| 9d | 📤 分享板 | ⏳ 进行中 | 4 |
| 9e | ⏰ 提醒 | ✅ 已完成 | 6 |
| 9f | ✅ 习惯打卡 | ✅ 已完成 | 4 |
| **合计** | | | **27** |

---

_每张卡片独立，互不依赖，Build喵 可按顺序或并行创建 Issue。_
