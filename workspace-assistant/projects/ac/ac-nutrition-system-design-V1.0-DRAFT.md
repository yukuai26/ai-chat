# 营养追踪与食谱系统设计 — Phase 17

> 版本：V1.0 | 状态：DRAFT | 日期：2026-05-28

---

## 一、需求概述

管理员每周发送食谱图片（周一~周五午餐），系统自动解析并存储。每周一到周五 11:00 根据当天食谱生成食材配比推荐；周六/日 11:00 检测下周食谱是否已提交，未提交则弹卡片提示。管理员可发送早/晚餐照片，系统识别食物、估算热量并记录。Dashboard 展示今日摄入/午餐推荐/本周摄入等。

### 核心场景

| 场景 | 触发方式 | 操作 |
|------|---------|------|
| 提交周食谱 | 管理员发图片 → Agent 视觉分析 | 解析 Mon-Fri 菜单项 → 存入 `recipes/{year}-W{week}.json` |
| 每日午餐推荐 | 系统 cron Mon-Fri 11:00 | 读当天食谱 → 生成食材配比 → 存入 recommendation → 推卡片 |
| 周末催食谱 | 系统 cron Sat/Sun 11:00 | 检测下周食谱是否存在 → 不存在则通知管理员 |
| 记录早/晚餐 | 管理员发照片 → Agent 视觉分析 | 识别食物+估算热量 → 存入 `meals/{date}.json` → 更新卡片 |
| 查看营养卡片 | 打开 Dashboard | 展示今日摄入/午餐推荐/本周汇总 |

---

## 二、数据模型

### 2.1 周食谱

```json
// user-data/nutrition/recipes/2026-W22.json
{
  "year": 2026,
  "week": 22,
  "submitted": "2026-05-24T20:00:00+08:00",
  "updated": "2026-05-24T20:00:00+08:00",
  "days": {
    "monday": {
      "date": "2026-05-25",
      "menu": ["红烧排骨", "清炒时蔬", "番茄蛋汤", "米饭"],
      "source_image": "recipes/images/2026-W22-mon.jpeg",
      "notes": ""
    },
    "tuesday": {
      "date": "2026-05-26",
      "menu": ["宫保鸡丁", "凉拌黄瓜", "紫菜汤", "米饭"],
      "source_image": "recipes/images/2026-W22-tue.jpeg",
      "notes": ""
    },
    "wednesday": {
      "date": "2026-05-27",
      "menu": ["清蒸鲈鱼", "炒西兰花", "冬瓜汤", "米饭"],
      "source_image": "recipes/images/2026-W22-wed.jpeg",
      "notes": ""
    },
    "thursday": {
      "date": "2026-05-28",
      "menu": ["回锅肉", "蒜蓉空心菜", "酸辣汤", "米饭"],
      "source_image": "recipes/images/2026-W22-thu.jpeg",
      "notes": ""
    },
    "friday": {
      "date": "2026-05-29",
      "menu": ["番茄牛腩", "蚝油生菜", "米饭"],
      "source_image": "recipes/images/2026-W22-fri.jpeg",
      "notes": "周五简餐"
    }
  }
}
```

### 2.2 每日餐食记录

```json
// user-data/nutrition/meals/2026-05-27.json
{
  "date": "2026-05-27",
  "person": "管理员",
  "meals": {
    "breakfast": {
      "logged_at": "2026-05-27T08:30:00+08:00",
      "items": [
        {"food": "煮鸡蛋", "amount": "2个", "calories": 140, "protein_g": 12, "carbs_g": 2, "fat_g": 10},
        {"food": "全麦面包", "amount": "2片", "calories": 160, "protein_g": 6, "carbs_g": 30, "fat_g": 2},
        {"food": "牛奶", "amount": "250ml", "calories": 135, "protein_g": 8, "carbs_g": 12, "fat_g": 5}
      ],
      "source_image": "meals/photos/2026-05-27-breakfast.jpeg",
      "total_calories": 435,
      "total_protein_g": 26,
      "total_carbs_g": 44,
      "total_fat_g": 17
    },
    "lunch": {
      "logged_at": null,
      "recipe_ref": "2026-W22",
      "recipe_menu": ["清蒸鲈鱼", "炒西兰花", "冬瓜汤", "米饭"],
      "recommended": {
        "portions": [
          {"dish": "清蒸鲈鱼", "amount_g": 150, "note": "去头去内脏后净重"},
          {"dish": "炒西兰花", "amount_g": 200, "note": ""},
          {"dish": "冬瓜汤", "amount_g": 300, "note": "含汤水"},
          {"dish": "米饭", "amount_g": 180, "note": "熟重"}
        ],
        "nutrition": {
          "calories": 580,
          "protein_g": 38,
          "carbs_g": 55,
          "fat_g": 18,
          "fiber_g": 8
        },
        "rationale": "成年男性日均2400kcal，午餐占35%约840kcal。清蒸鲈鱼150g优质蛋白，米饭180g碳水，西兰花+冬瓜汤补充纤维和维生素，合计约580kcal（预留下午加餐空间）。"
      },
      "actual": null,
      "total_calories": null
    },
    "dinner": {
      "logged_at": null,
      "items": [],
      "source_image": null,
      "total_calories": null
    }
  },
  "daily_totals": {
    "logged_calories": 435,
    "logged_protein_g": 26,
    "logged_carbs_g": 44,
    "logged_fat_g": 17,
    "recommended_calories": 1015,
    "recommended_protein_g": 64,
    "recommended_carbs_g": 99,
    "recommended_fat_g": 35
  }
}
```

### 2.3 用户健康档案（Phase 17-2 实现）

```json
// user-data/nutrition/profile.json
{
  "person": "管理员",
  "height_cm": null,
  "weight_kg": null,
  "age": null,
  "gender": "male",
  "activity_level": "moderate",
  "goal": "maintain",
  "preferences": {
    "allergies": [],
    "dislikes": [],
    "favorites": ["火锅", "海鲜", "川菜"],
    "diet_type": "omnivore"
  },
  "daily_targets": {
    "calories": 2400,
    "protein_g": 80,
    "carbs_g": 300,
    "fat_g": 65,
    "fiber_g": 25
  },
  "updated": null
}
```

### 2.4 每日推荐（cron 生成）

> 🔄 推荐格式以**菜品份量**为准，不是原料克数。例如「回锅肉 150g」而不是「猪五花肉 120g」。

```json
// user-data/nutrition/recommendations/2026-05-28.json
{
  "date": "2026-05-28",
  "generated_at": "2026-05-28T11:00:05+08:00",
  "recipe_ref": "2026-W22",
  "weekday": "thursday",
  "recipe_menu": ["回锅肉", "蒜蓉空心菜", "酸辣汤", "米饭"],
  "portions": [
    {"dish": "回锅肉", "amount_g": 150, "note": "五花肉偏肥，控制份量"},
    {"dish": "蒜蓉空心菜", "amount_g": 200, "note": ""},
    {"dish": "酸辣汤", "amount_g": 300, "note": "含汤水"},
    {"dish": "米饭", "amount_g": 180, "note": "熟重"}
  ],
  "nutrition": {
    "calories": 620,
    "protein_g": 30,
    "carbs_g": 50,
    "fat_g": 28,
    "fiber_g": 6
  },
  "rationale": "午餐占日均35%（约840kcal），回锅肉150g较油约350kcal，蒜蓉空心菜200g约60kcal，酸辣汤300ml约50kcal，米饭180g约210kcal，合计约670kcal（总量可控，下午可轻微加餐）。"
}
```

---

## 三、API 设计

### 3.1 营养相关 API（fileserver.py 新增）

| 方法 | 端点 | 功能 | 认证 |
|------|------|------|:--:|
| GET | `/v1/api/nutrition/today` | 今日营养概况（卡片缩略数据） | ✅ |
| GET | `/v1/api/nutrition/today/detail` | 今日本日详细（卡片展开数据） | ✅ |
| GET | `/v1/api/nutrition/week/{year}-W{week}` | 本周摄入汇总 | ✅ |
| GET | `/v1/api/nutrition/meals/{date}` | 获取某天餐食记录 | ✅ |
| POST | `/v1/api/nutrition/meals/{date}` | 更新某天餐食记录（Agent 调用） | ✅ |
| GET | `/v1/api/nutrition/recipes/week/{year}-W{week}` | 获取某周食谱 | ✅ |
| POST | `/v1/api/nutrition/recipes/week/{year}-W{week}` | 保存某周食谱（Agent 调用） | ✅ |
| GET | `/v1/api/nutrition/recommendation/{date}` | 获取某天推荐 | ✅ |
| POST | `/v1/api/nutrition/recommendation/{date}` | 保存某天推荐（Agent 调用） | ✅ |
| GET | `/v1/api/nutrition/profile` | 获取健康档案 | ✅ |
| POST | `/v1/api/nutrition/profile` | 更新健康档案 | ✅ |
| POST | `/v1/api/nutrition/upload-image` | 上传食谱/餐食图片 | ✅ |

### 3.2 今日营养概况返回格式

```json
// GET /v1/api/nutrition/today
{
  "date": "2026-05-28",
  "weekday": "星期四",
  "has_recipe": true,
  "recipe_menu": ["回锅肉", "蒜蓉空心菜", "酸辣汤", "米饭"],
  "has_recommendation": true,
  "recommendation": {
    "portions": [
      {"dish": "回锅肉", "amount_g": 150},
      {"dish": "蒜蓉空心菜", "amount_g": 200},
      {"dish": "酸辣汤", "amount_g": 300},
      {"dish": "米饭", "amount_g": 180}
    ]
  },
  "meals": {
    "breakfast": {"logged": true, "calories": 435},
    "lunch": {"logged": false, "recommended_calories": 620},
    "dinner": {"logged": false, "calories": null}
  },
  "today_calories": 435,
  "today_protein_g": 26,
  "today_carbs_g": 44,
  "today_fat_g": 17,
  "target_calories": 2400,
  "remaining_calories": 1965,
  "yesterday": {
    "date": "2026-05-27",
    "weekday": "星期三",
    "total_calories": 1920,
    "total_protein_g": 75,
    "total_carbs_g": 220,
    "total_fat_g": 55,
    "meals_logged": 3,
    "note": "全天达标 ✅"
  },
  "week_summary": {
    "week_label": "W22",
    "daily_avg_calories": 1680,
    "total_logged_days": 3,
    "trend": "stable"
  }
}
```

---

## 四、卡片设计

### 4.1 卡片注册

```json
{
  "id": "nutrition",
  "name": "🍽️ 饮食",
  "width": "medium",
  "enabled": true,
  "api": "/v1/api/nutrition/today",
  "detailApi": "/v1/api/nutrition/today/detail",
  "expandable": true,
  "refreshInterval": 300
}
```

### 4.2 缩略卡

```
┌──────────────────────────────────┐
│ 🍽️ 饮食  W22                    │
│                                  │
│ 🔥 今日摄入: 435 / 2400 kcal    │
│ ██░░░░░░░░░░░░░░ 18%            │
│                                  │
│ 📅 昨日摄入: 1,920 / 2400 kcal  │
│ ██████████░░░░░░ 80% ✅         │
│                                  │
│ ☀️ 午餐推荐 (份量):              │
│ 回锅肉 150g | 蒜蓉空心菜 200g   │
│ 酸辣汤 300ml | 米饭 180g        │
│                                  │
│ 📊 本周日均: 1,680 kcal          │
│ ┌──┬──┬──┬──┬──┬──┬──┐         │
│ │一│二│三│四│五│六│日│         │
│ │█ │█ │█ │░ │░ │░ │░ │         │
│ └──┴──┴──┴──┴──┴──┴──┘         │
│                                  │
│ [展开 ▼]                         │
└──────────────────────────────────┘
```

### 4.3 展开卡

```
┌──────────────────────────────────────────────┐
│ 🍽️ 饮食管家                         [✕ 收起] │
├──────────────────────────────────────────────┤
│                                              │
│ 📊 2026-05-28 周四                           │
│                                              │
│ 🌅 早餐 (已记录)  🔥 435 kcal                │
│ · 煮鸡蛋 ×2    140 kcal  12g蛋白            │
│ · 全麦面包 ×2  160 kcal   6g蛋白            │
│ · 牛奶 250ml   135 kcal   8g蛋白            │
│ [📷 查看原图]                                 │
│                                              │
│ ☀️ 午餐 — ✅ 11:00 已推荐                    │
│ 食谱: 回锅肉 + 蒜蓉空心菜 + 酸辣汤 + 米饭    │
│                                              │
│ 今日午餐份量推荐:                             │
│ ┌────────────────────────────────────────┐   │
│ │ 🥩 回锅肉       150g  📝 偏油不多吃    │   │
│ │ 🥬 蒜蓉空心菜   200g  📝 多多益善      │   │
│ │ 🍜 酸辣汤       300ml 📝 喝汤占胃      │   │
│ │ 🍚 米饭         180g  📝 熟重          │   │
│ ├────────────────────────────────────────┤   │
│ │ 预估营养: 620 kcal | 蛋白 30g          │   │
│ │           碳水 50g | 脂肪 28g          │   │
│ └────────────────────────────────────────┘   │
│                                              │
│ 🌙 晚餐 (未记录)                              │
│ [📷 拍照记录]                                 │
│                                              │
│ ─────────────────────────────────────────   │
│                                              │
│ 📅 昨日对比 (2026-05-27 周三)                │
│                                              │
│ 昨日摄入: 1,920 / 2,400 kcal (80%) ✅        │
│ ██████████░░░░░░                              │
│ 蛋白 75g | 碳水 220g | 脂肪 55g               │
│ 三餐记录: 早餐 ✅ | 午餐 ✅ | 晚餐 ✅          │
│                                              │
│ ─────────────────────────────────────────   │
│                                              │
│ 📅 本周摄入 (W22)                             │
│                                              │
│ 日均: 1,680 kcal | 趋势: → 稳定              │
│                                              │
│ 周一 ████████████░░ 1,920 kcal               │
│ 周二 ██████████░░░░ 1,550 kcal               │
│ 周三 ███████████░░░ 1,830 kcal               │
│ 周四 ███░░░░░░░░░░░   435 kcal (进行中)      │
│ 周五   — 未记录                              │
│ 周六   — 未记录                              │
│ 周日   — 未记录                              │
│                                              │
│ 🏷️ 今日食谱来源: W22 周食谱                  │
└──────────────────────────────────────────────┘
```

---

## 五、Cron 任务设计

### 5.1 每日午餐推荐（周一~周五 11:00）

```
cron: 0 11 * * 1-5 (Asia/Shanghai)
action: systemEvent → 主 session
message:
  "[系统] 午餐推荐时间 — 请读取当前周食谱文件，
   找到今天对应日期的菜单，生成**菜品份量推荐**（不是原料克数！），
   格式：菜品名 + 克数 + 备注。
   例如：回锅肉 150g（不是猪五花肉 120g）。
   保存到 user-data/nutrition/recommendations/{today}.json（覆盖旧数据），
   并更新 user-data/nutrition/meals/{today}.json 的 lunch.recommended 字段。"
```

### 5.2 周末食谱检查（周六/周日 11:00）

```
cron: 0 11 * * 6,0 (Asia/Shanghai)
action: systemEvent → 主 session
message:
  "[系统] 周末食谱检查 — 检查 /home/ubuntu/.openclaw/workspace-assistant/user-data/nutrition/recipes/ 下
   是否有下周的食谱文件。如果没有，请通过飞书提醒管理员：'📋 新的一周即将开始，请发送下周食谱 📸'"
```

### 5.3 Cron 管理方式

通过 OpenClaw cron add 创建两条 cron job，由 Gateway 直接管理。主 session 自动处理系统事件。

---

## 六、图片分析流程

### 6.1 食谱图片分析（管理员发送周食谱）

```
管理员发图 → Agent 收到图片
  → Agent 用视觉模型分析图片
  → 提取周一~周五每天菜单项
  → 调用 POST /v1/api/nutrition/recipes/week/{year}-W{week} 保存
  → 告知管理员：「已解析本周食谱，共 5 天 18 道菜」
```

**分析要求：**
- 识别每天的菜名（忽略日期标识，关注菜品文字）
- 如果有"周一: xxx，周二: xxx"等格式，按天分组
- 如果只有菜品列表无日期标识，按顺序分配 Mon-Fri
- 允许管理员后续文字修正

### 6.2 餐食照片分析（管理员发送早/晚餐照片）

```
管理员发聊天消息：「早餐」+ 图片 → Agent 收到
  → Agent 用视觉模型分析图片
  → 识别食物项 + 估算重量 + 计算热量
  → 调用 POST /v1/api/nutrition/meals/{date} 保存
  → 回复：「已记录早餐：煮鸡蛋×2 (140kcal) + 全麦面包×2 (160kcal) + 牛奶250ml (135kcal) 
           = 435 kcal | 蛋白 26g 碳水 44g 脂肪 17g」
```

**热量估算参考标准（每100g）：**

| 类别 | 示例 | 热量 kcal | 蛋白 g | 碳水 g | 脂肪 g |
|------|------|:--:|:--:|:--:|:--:|
| 🍚 主食 | 米饭（熟） | 116 | 2.6 | 26 | 0.3 |
| 🍚 主食 | 面条（煮） | 110 | 3.5 | 22 | 0.5 |
| 🍞 主食 | 全麦面包 | 250 | 9 | 46 | 3 |
| 🥩 肉类 | 鸡胸肉 | 133 | 31 | 0 | 1.2 |
| 🥩 肉类 | 猪里脊 | 155 | 20 | 1 | 8 |
| 🥩 肉类 | 牛腱子 | 125 | 23 | 0.1 | 4 |
| 🐟 水产 | 鲈鱼 | 100 | 18.6 | 0 | 3.4 |
| 🐟 水产 | 虾仁 | 93 | 20 | 0 | 1 |
| 🥚 蛋类 | 鸡蛋 | 155 | 13 | 1.5 | 11 |
| 🥛 奶类 | 全脂牛奶 | 65 | 3 | 4.8 | 3.5 |
| 🥬 蔬菜 | 西兰花 | 34 | 2.8 | 6.6 | 0.4 |
| 🥬 蔬菜 | 生菜 | 15 | 1.4 | 2.8 | 0.2 |
| 🥬 蔬菜 | 番茄 | 18 | 0.9 | 3.9 | 0.2 |
| 🫘 豆制品 | 豆腐 | 76 | 8 | 1.9 | 4.8 |
| 🍎 水果 | 苹果 | 52 | 0.2 | 14 | 0.2 |
| 🫒 油脂 | 食用油 | 900 | 0 | 0 | 100 |

---

## 七、系统架构

```
┌─────────────────────────────────────────────────────────┐
│ 前端 (index.html)                                       │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Dashboard「📊 每日」Tab                              ││
│  │  ┌──────────────────────┐                           ││
│  │  │ 🍽️ 饮食卡片           │  其他卡片...             ││
│  │  │ GET /v1/api/nutrition │                           ││
│  │  │ /today                │                           ││
│  │  └──────────────────────┘                           ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  nginx :8080 ── /v1/* → fileserver.py :5001             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ fileserver.py (:5001)                                    │
│                                                          │
│  /v1/api/nutrition/today          → 聚合今日数据         │
│  /v1/api/nutrition/today/detail   → 展开卡数据           │
│  /v1/api/nutrition/meals/{date}   → CRUD 餐食记录       │
│  /v1/api/nutrition/recipes/week/* → CRUD 周食谱         │
│  /v1/api/nutrition/recommendation/{date} → 推荐数据     │
│  /v1/api/nutrition/profile        → 健康档案            │
│                                                          │
│  数据存储: user-data/nutrition/                          │
│    ├── recipes/{year}-W{week}.json                       │
│    ├── meals/{date}.json                                 │
│    ├── recommendations/{date}.json                       │
│    └── profile.json                                      │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ OpenClaw Gateway                                         │
│  ┌─────────────────────────────────────────────────────┐│
│  │ Cron 1: 0 11 * * 1-5 → systemEvent 午餐推荐        ││
│  │ Cron 2: 0 11 * * 6,0 → systemEvent 周末催食谱      ││
│  └─────────────────────────────────────────────────────┘│
│                                                          │
│  主 Agent (assistant)                                    │
│  ├── 收到图片 → 视觉分析 → 写 API                       │
│  ├── 收到 11:00 系统事件 → 读食谱 → 生成推荐 → 写 API  │
│  └── 收到周末系统事件 → 检查 → 通知管理员               │
└─────────────────────────────────────────────────────────┘
```

---

## 八、确认事项（✅ 已确认 2026-05-28）

| # | 问题 | 决定 | 确认人 |
|---|------|------|:--:|
| 1 | 营养数据是否需要"伴侣"维度？ | **单人** | ✅ |
| 2 | 午餐推荐是否推送到飞书？ | **仅卡片** | ✅ |
| 3 | 推荐格式？ | **按菜品给克数**（如「回锅肉 150g，蒜蓉空心菜 200g」不是原料克数） | ✅ |
| 4 | 晚餐推荐也需要吗？ | **否，仅午餐** | ✅ |
| 5 | 历史记录保留多久？ | 无限（默认） | — |

### 额外要求（2026-05-28）
- **清除旧数据：** 每次保存新的食谱/推荐前，先清除（覆盖）之前的同日数据
- **昨日对比：** 卡片 display 同时展示今日摄入和昨日摄入

---

## 九、Phase 拆分

### Phase 17-1：数据层 + 卡片骨架（MVP）
- [ ] N1: 创建 `user-data/nutrition/` 目录结构
- [ ] N2: 实现 `/v1/api/nutrition/today` 聚合 API（含 yesterday 昨日数据）
- [ ] N3: 实现 `/v1/api/nutrition/meals/{date}` GET/POST（POST 时覆盖旧数据）
- [ ] N4: 实现 `/v1/api/nutrition/recipes/week/*` GET/POST（POST 时覆盖旧数据）
- [ ] N5: 实现 `/v1/api/nutrition/recommendation/{date}` GET/POST（POST 时覆盖旧数据）
- [ ] N6: 实现 `/v1/api/nutrition/profile` GET/POST
- [ ] N7: 卡片注册（card-registry.json 加 nutrition）
- [ ] N8: 前端缩略卡组件（今日+昨日热量对比 + 菜品份量推荐 + 周热力图）
- [ ] N9: 前端展开卡组件（三餐明细 + 菜品份量推荐详情 + 昨日对比 + 周汇总）

### Phase 17-2：Cron + 智能推荐
- [ ] N10: 创建 Mon-Fri 11:00 cron job
- [ ] N11: 创建 Sat/Sun 11:00 cron job
- [ ] N12: Agent 处理午餐推荐系统事件（读食谱 → 生成推荐 → 存 JSON）
- [ ] N13: Agent 处理周末检查系统事件（检查 → 通知）

### Phase 17-3：图片分析 + 健康档案
- [ ] N14: Agent 处理食谱图片（视觉分析 → 提取菜单 → 存 API）
- [ ] N15: Agent 处理餐食图片（视觉分析 → 识别食物 → 估算热量 → 存 API）
- [ ] N16: 实现 `/v1/api/nutrition/upload-image`（文件上传端点）
- [ ] N17: 实现 `/v1/api/nutrition/today/detail`（展开卡数据）
- [ ] N18: 前端完善卡片交互（上传按钮、日切换、热力图交互）
- [ ] N19: 健康档案表单（身高/体重/偏好设置 UI）
- [ ] N20: 热量数据库 + 精准计算（替换 Agent 估算为标准数据库）

### Phase 17-4：高级特性（可选）
- [ ] N21: 本周 vs 上周对比
- [ ] N22: 营养素达标率可视化（蛋白/碳水/脂肪/纤维 环形图）
- [ ] N23: 食谱图片浏览器（查看历史周食谱原图）
- [ ] N24: 日历集成（日历 Tab 显示当天食谱和营养数据）
- [ ] N25: 食物知识库（AI 营养点评 + 改进建议）

---

## 十、与现有系统的集成点

| 现有模块 | 集成方式 |
|----------|---------|
| Dashboard 卡片系统 | 新卡 `nutrition` 注册到 card-registry.json |
| 日历 Tab | 日历日期点击时显示当天食谱+营养（N24） |
| 文件浏览器 | 统一管理 cooking/assets 目录下的图片 |
| 指令中枢 | 新增 `@diet` 指令：查询饮食/记录餐食 |

---

_状态：DRAFT — 待管理员审阅确认后转为 ACTIVE_
