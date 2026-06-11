---
entity: ac
descriptor: card-spec
version: "1.0"
status: ACTIVE
author: 小助手
created: "2026-06-07"
project_manager: 管理员
purpose: Assistant Web Chat「卡片系统」的通用标准契约。任何新卡片都按此规范由卡片喵生成 4 个标准文件即可直接接入，无需改前端/后端代码。
baseline: ac-design-baseline-V1.0-ACTIVE.md (D 模块)
---

# ac-card-spec — 卡片系统通用规范 V1.0

> **用途**：这是所有卡片的"模板蓝图"。有了它，管理员只需告诉卡片喵"我要个什么卡片、收到什么指令做什么、怎么展示"，卡片喵照此规范生成文件，卡片即刻可用。
> **核心原则**：卡片 = 一个目录 + 4 个标准文件。前端/后端是**通用引擎**（不为单张卡片写代码），卡片的全部个性由这 4 个文件描述（数据驱动 / 插件式）。

---

## 一、卡片目录结构（铁律）

每张卡片 = `user-data/daily-data/{card_id}/` 下一个目录，含以下文件：

| 文件 | 谁读写 | 必需 | 作用 |
|------|--------|:--:|------|
| `data.json` | 卡片喵读写 / 前端 REST 读写 | ✅ | **原始数据**（唯一真相） |
| `prompt.json` | 卡片喵读写 | ✅ | 卡片定义：用途 + **data_schema(数据格式约定)** + 偏好 + 经验 |
| `rules.json` | 卡片喵读写 | ✅ | **两类规则**：①交互规则(收到什么指令做什么) ②展示规则(怎么生成 display) |
| `generate-display.py` | 卡片喵读写 | ✅ | rules 的可执行实现：读 data.json → 按 rules 生成 display.json |
| `display.json` | **脚本生成，只读** | ✅ | 前端实际渲染的内容（禁止手改） |
| `media/` | 卡片喵读写 | 可选 | 图片等二进制，按用途分子目录 |

> `card_id` = 目录名 = 英文小写（如 todo / recipe / notes），不是中文名。

---

## 二、四个标准文件的规范

### 2.1 `data.json` — 原始数据
- 格式自由，但**必须与 `prompt.json` 的 `data_schema` 一致**（卡片喵写、REST 写、脚本读，三处都按 schema）。
- **合并不覆盖**：新数据追加到已有数据。
- 多人数据用固定 key：`yukuai26`(管理员) / `gugugu`(伴侣)。

### 2.2 `prompt.json` — 卡片定义
标准字段：
```json
{
  "card_name": "中文显示名",
  "data_schema": {
    "description": "数据格式说明",
    "structure": { /* 数据的真实结构, 改 data 必须遵守 */ }
  },
  "user_preferences": ["用户偏好(卡片喵据此调整行为)"],
  "best_practices": ["操作经验(卡片喵积累)"]
}
```
> **`data_schema` 是数据格式的唯一权威约定**。卡片喵写 data、后端 REST 写 data、脚本读 data，全部以它为准。改了数据结构 = 同步改 data_schema。

### 2.3 `rules.json` — 规则（两类，这是管理员主要"说需求"落点）
```json
{
  "interaction_rules": [
    {
      "trigger": "收到什么(关键词/意图, 如 '勾选完成' / '说记体重X')",
      "action": "做什么(改 data 的哪部分、怎么改)"
    }
  ],
  "display_rules": {
    "summary": "折叠态摘要怎么生成(模板/计算)",
    "sections": [
      {
        "id": "区块标识",
        "title": "区块标题",
        "type": "table|text|kv|grid|list",
        "source": "data.json 里取哪部分",
        "show_when": "always|expand_only|has_data 等条件"
      }
    ]
  }
}
```
> 管理员"我想要什么、碰到什么指令做什么、怎么展示"——就是在填 `interaction_rules`(交互) + `display_rules`(展示)。卡片喵据此生成 generate-display.py。

### 2.4 `generate-display.py` — 可执行实现
- 职责：`读 data.json → 按 rules.json 的 display_rules 计算 → 写 display.json → (可选)发通知`。
- **必须与 rules.json 同步**：改 rules 必改脚本，反之亦然。
- 跑完输出的 display.json 必须含 `sections` 数组（见下）。

### 2.5 `display.json` — 前端渲染契约（前端只认这个结构）
```json
{
  "summary": "折叠态一句话摘要",
  "sections": [
    {"title":"...", "type":"table", "rows":[{"cells":[{"text":"","style":""}]}], "footer":""},
    {"title":"...", "type":"text",  "text":"..."},
    {"title":"...", "type":"kv",    "pairs":[{"key":"","value":""}]},
    {"title":"...", "type":"grid",  "items":[{"img":"","label":""}]},
    {"title":"...", "type":"list",  "items":[{"text":"", "id":0, "done":false, "url":""}]}
  ]
}
```
**5 种 section 类型**：`table`(表格) / `text`(纯文本) / `kv`(键值对) / `grid`(图片网格) / `list`(列表)。
> 前端**不硬编码任何字段名**，只遍历 sections。加卡片新内容 = sections 加一项，前端零改动。
> 交互元素（如 list 项的勾选框）：item 带 `id` + `done` 字段，前端渲染为可勾选，勾选回调走 §三 的统一交互端点。
> **可点链接（2026-06-11 新增）**：list item 带可选 `url` 字段 → 前端渲染为 `<a target="_blank">` 可点跳转（新标签页）。news 卡片即用此机制。与 `done`/`id` 互不冲突。

---

## 三、两种修改方式（都改 data + 都刷新显示）【设计目标】

卡片支持两条对称的修改路径，**殊途同归到同一套数据流**：

```
方式1【对话框 → 卡片喵】(自然语言)
  你说话 → 卡片喵读 data → 按 interaction_rules 改 data → 跑 generate-display.py → 发通知

方式2【展开态交互 → 前端 REST】(勾选/按钮)
  你点勾选 → REST 端点改 data → [统一钩子]跑 generate-display.py → 发通知

两者都: 改 data.json(真相) → 脚本生成 display.json → notify-display-update → WS 推送 → 前端自动刷新
```

### 3.1 实时刷新机制（已有，前端零改动）
- 后端改完 display 调 `POST /v1/api/daily/notify-display-update {"card":"id"}`（或 `{"cards":[...]}`）
- → WebSocket 推送 `card_changed` 事件 → 前端 `handleWSEvent` 自动清缓存 + 重渲染该卡片
- **效果**：勾选/对话改完，折叠态/其他端实时更新，无需手动刷新。

### 3.2 卡片喵不需要"实时感知"前端的改动
- 卡片喵是**被动操作员**，非常驻进程。前端 REST 改了 data，卡片喵不会"知道"，**也不需要知道**。
- 卡片喵每次被调用时**第一步就重新读 data.json**（SOUL 铁律：先读后写），自然看到最新状态（含前端的改动）。
- 一致性靠"**data.json 是唯一真相 + 大家都按 data_schema**"保证，不靠实时通知。

---

## 四、新建卡片的标准流程（管理员视角）

管理员只需对卡片喵说清三件事，卡片喵生成文件即可用：

1. **要个什么卡片**（用途）→ 卡片喵写 `prompt.json`(card_name + data_schema)
2. **收到什么指令做什么**（交互）→ 卡片喵写 `rules.json` 的 `interaction_rules`
3. **怎么展示**（展示）→ 卡片喵写 `rules.json` 的 `display_rules` + `generate-display.py`

卡片喵再：建目录 → 写 4 文件 → data.json 给初始值 → 跑脚本生成首个 display.json → 把卡片注册进 `card-registry`(enabled) → 通知前端。

> 删除卡片：卡片喵通知管理员确认，不自行删目录。

---

## 五、当前现状 vs 本规范（待收齐项）

> 本规范是**目标标准**。现状部分卡片尚未完全符合，需逐步向标准看齐（不阻塞规范成立）。

| 卡片 | data_schema 一致 | 有 generate-display.py | rules 含交互+展示 | 状态 |
|------|:--:|:--:|:--:|------|
| recipe | ✅ | ✅ | ✅(展示全, 无勾选交互) | ✅ 完整(2026-06-07恢复11点心跳cron) |
| todo | ✅ | ✅ | ✅(交互+三段展示+分栏) | ✅ **已收齐(2026-06-07, 标准范例)** |
| **data 健康** | ✅ | ✅ | ✅(识图交互+7日折线+评级) | ✅ **已完成(2026-06-07)** |
| 其他 8 张 | 待盘点 | 待盘点 | 待盘点 | 待做 |

### 待办 TODO
- **T1**：按本规范做一次全卡片盘点，列清每张卡片的符合度。
- ~~**T2**~~：✅ **todo 已收齐(2026-06-07)**——扁平 data+done_date / generate-display.py(三段+左右两栏) / rules(交互+展示) / 后端v2端点 / 前端两栏渲染。作为标准范例。
- **T3**：✅ **`_regenerate_display(card_id)` 已实现并挂到 todo 写端点**(POST/PUT/DELETE)；方案C `_maybe_refresh_timesensitive` 已挂到 display 读端点。**其他卡片待逐张接入**(它们写端点尚未挂钩子)。
- **T4**：交互型 section（list 带 id/done）的前端勾选 → 统一交互端点 的标准化。

---

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-06-07 | 初版：确立卡片 4 文件标准、display sections 渲染契约、两种修改方式数据流、新建卡片流程；列现状待收齐项 T1-T4 |
| V1.0 | 2026-06-07 | **todo 卡片按规范完整落地**(标准范例)：T2 完成、T3 钩子(_regenerate_display)+方案C(_maybe_refresh_timesensitive)实现。对应代码 commit `4d39498` |
| V1.0 | 2026-06-07 | **data 健康卡片完成**：身体/摄入/运动三类+7日折线图(新增 chart_tabs section 类型,可切换体重/体脂/摄入/消耗)+稀疏数据处理+评级展示+卡片喵识图规则。新增前端 chart.js 渲染。commit `fdc5b1b` |
| V1.0 | 2026-06-11 | **新增 `source_matrix` section 类型**：多源并排矩阵(每来源一列横向并排，列内 items 带 url 可点)。news 卡片"全部来源"区使用。前端 renderCardBody 加 case。 |
| V1.0 | 2026-06-11 | **list item 增加可选 `url` 字段**：前端通用 list 渲染支持"带 url 渲染为可点链接(新标签页)"。配合 news 卡片落地(ac-news-card-design-V1.0)。前端 index.html renderCardBody 的 list case 增强。新增通用刷新端点 `/v1/api/daily/cards/display/<id>/refresh`(跑卡片目录 crawl.py)。 |
| V1.0 | 2026-06-07 | **recipe 心跳恢复**：查清卡片 heartbeat.json 无调度器在跑(Build喵暂停后全停)。新建 2 个 OpenClaw cron(card-assistant)：工作日`0 11 * * 1-5`生成午餐推荐 + 周末`0 11 * * 6,0`检查催促。手动验证卡片喵能正确执行。卡片喵=Opus(非DeepSeek) |
