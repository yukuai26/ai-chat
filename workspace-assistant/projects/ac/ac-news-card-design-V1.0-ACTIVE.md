---
entity: ac
descriptor: news-card-design
version: "1.0"
status: ACTIVE
author: 小助手
created: "2026-06-11"
project_manager: 管理员
purpose: 新闻卡片完整设计。遵循 ac-card-spec-V1.0 通用卡片规范，实现"分层信息密度 + 跨源聚合打分 + 来源分块 + 可点链接"。
baseline: ac-card-spec-V1.0-ACTIVE.md
data_sources: ac-data-sources-V1.0-ACTIVE.md
---

# ac-news-card-design — 新闻卡片设计 V1.0

> 需求来源：管理员 2026-06-11 对话。核心诉求 = "打开看最简略我关心的，深入看全部相关信息；都是可点链接跳原文；最下面按来源分块展示全部"。

---

## 一、设计目标（管理员原话提炼）

1. **信息分层**：折叠态=最精简的"我关心的"；展开态=精选+全部。
2. **可点链接**：每条新闻点击跳转原文（新标签页）。
3. **来源分块**：展开态最下方按"来源"分块展示全部条目。
4. **兴趣方向**（加权置顶）：国际政治 / 国内政治 / 杭州本地(含天气) / 经济财经。
5. **刷新**：定时 cron 4 时段（08/12/18/22）+ 手动刷新按钮兜底。

---

## 二、遵循 card-spec 规范（卡片 = 目录 + 标准文件）

新闻卡片**不再用旧的专用 `/v1/api/daily/news` API**，改为标准卡片目录结构，走通用 display 引擎（`GET /v1/api/daily/cards/display/news` 直接读 `daily-data/news/display.json`，前端零改动）。

```
user-data/daily-data/news/
├── data.json           # 全量抓取结果(唯一真相) + 每条 score/topics/source
├── sources.json        # 源清单(15 源, 标注 direct/proxy + 分类)
├── crawl.py            # 🆕 爬虫: 抓 15 源 → 聚合去重 → 打分 → 写 data.json → 跑 generate-display
├── prompt.json         # data_schema + interest_keywords(兴趣词)
├── rules.json          # 交互(@news 查询/调兴趣) + 展示(精选层 + 来源分块层)
├── generate-display.py # 读 data.json → 生成 display.json(精选 + 来源分块)
└── display.json        # 前端渲染契约(脚本生成, 禁手改)
```

旧文件处理：`2026-05-28.json`(旧日期格式)归档；旧 `/v1/api/daily/news`、`news_crawler.py` 占位标记为 DEPRECATED（保留兼容，新卡片不再依赖）。

---

## 三、数据源（15 源全用上，来自 ac-data-sources 实测✅）

| # | 源 | 频道倾向 | 网络 | 类型 |
|---|----|---------|:--:|------|
| 1 | 新浪财经滚动 | 经济财经 | direct | api |
| 2 | 今日头条·财经 | 经济财经 | direct | api |
| 3 | 东方财富要闻 | 经济财经 | direct | api |
| 4 | 新浪滚动新闻 | 国内/国际时事 | direct | api |
| 5 | 百度热搜 | 国内热点 | direct | api |
| 6 | 今日头条热榜 | 国内热点 | direct | api |
| 7 | 知乎热榜 | 国内热议 | direct | api |
| 8 | B站热门视频 | 综合 | direct | api |
| 9 | 浙江在线/杭州网 | 杭州本地 | direct | rss/api |
| 10 | wttr.in 天气 | 杭州天气 | direct | api(特殊渲染) |
| 11 | BBC World | 国际政治 | proxy | rss |
| 12 | NYT World | 国际政治 | proxy | rss |
| 13 | 卫报 World | 国际政治 | proxy | rss |
| 14 | 半岛 Al Jazeera | 国际政治 | proxy | rss |
| 15 | NHK 日本 | 国际 | proxy | rss |
| 16 | 美联社 AP | 国际政治 | proxy | rss |
| 17 | 德国之声 DW 中文 | 国际政治 | proxy | rss |

> 国外源(11-17)走代理 `172.29.4.175:22222`，单源超时 8s，**失败跳过不报错**（不拖累整卡）。

---

## 四、聚合 + 打分（精选层的灵魂）

`crawl.py` 抓取后处理流程：

1. **归一化**：每条 → `{title,url,source,topic_tags,time,summary,raw_category}`
2. **跨源去重聚合**：标题相似度（归一化后 Jaccard/包含）合并同事件，记 `source_count`（几个源报了）。
3. **打分 score**：
   - `source_count` 越大分越高（多源报道 = 越重要）
   - 命中 **兴趣关键词** 加权（国际政治/国内政治/杭州/经济财经 相关词）
   - 频道偏好默认加权：国际政治 + 经济财经 话题基础分更高
   - 时间衰减：越新分越高
4. 输出 `data.json`：全量条目(带 score) + 各来源原始分组 + 兴趣命中标记。

**兴趣关键词（prompt.json.interest_keywords，可对话调整）**：
```
国际政治: 美联储 白宫 拜登 特朗普 欧盟 联合国 制裁 停火 中东 俄乌 北约 关税
国内政治: 国务院 发改委 政策 央行 两会 部署 监管
杭州本地: 杭州 浙江 西湖 钱塘 亚运 天气
经济财经: 经济 GDP A股 股市 降息 加息 通胀 楼市 黄金 原油 比特币 财报
```

---

## 五、展示设计（display.json sections）

### 折叠态 summary（第①层 — 一眼精华）
```
🔥 今日要闻 · {N}条  ｜  {top1标题} / {top2标题}  ｜  {HH:MM}更新·共{total}条
```
（杭州天气融入：summary 末尾追加 `🌦️杭州{温度}` 若天气源成功）

### 展开态
**Section 1「🔥 精选」(type=list, 默认展开)** — Top 12 跨源高分
- 每条 item：`{text:标题(带来源小标·若多源报道标"N源"), url:原文链接}`
- **可点**：item 带 url → 前端渲染 `<a target=_blank>`（见 §六 引擎增强）

**Section 2..N「📰 来源分块」(每源一个 type=list section)** — 全部条目
- section.title = 来源名(条数)，如 `BBC World（6）`
- 每条 item 带 url，可点跳原文
- 顺序：经济财经源 → 国内时事源 → 杭州本地 → 国际政治源

**Section 末「🌦️ 杭州天气」(type=kv, 可选)** — 若 wttr.in 成功

---

## 六、前端通用引擎增强（list 支持 url）【需改 index.html】

现状：`renderCardBody` 的 `case 'list'` 只渲染 `item.text` 纯文本，**忽略 url**。

增强（增强通用引擎，非单卡专用代码，符合 card-spec 精神）：
```js
// list item: 若 it.url 存在 → 渲染为可点链接(新标签页)，否则纯文本
// 保留已有 done/id(勾选)逻辑不变
```
同步更新 `ac-card-spec`：list item 字段增加可选 `url`。

---

## 七、刷新机制

- **OpenClaw cron**（agent 待定，建议轻量 agent 或直接 shell cron 跑 crawl.py）：
  - `0 8,12,18,22 * * *` → 执行 `daily-data/news/crawl.py`
  - crawl.py 末尾自动调 notify-display-update → WS 推前端
- **手动刷新**：前端已有 news 刷新按钮（`/v1/api/daily/cards/display/news/refresh`），需把它接到 crawl.py（替代旧 news_crawler 占位）。
- ⚠️ HEARTBEAT.md 记录 cron 已禁用 → 本 cron 为**新启用**，已获管理员同意(2026-06-11)。

---

## 八、实现 TODO

- [x] N1 写 `sources.json`（15 源配置）
- [x] N2 写 `crawl.py`（抓取 + 代理兜底 + 聚合去重 + 打分）
- [x] N3 写 `prompt.json`（data_schema + interest_keywords）
- [x] N4 写 `rules.json`（交互 + 展示规则）
- [x] N5 写 `generate-display.py`（精选 + 来源分块）
- [x] N6 前端 `index.html` list 渲染增强(支持 url 可点)
- [x] N7 跑 crawl.py 出首个 data.json + display.json，验证渲染
- [x] N8 接手动刷新按钮到 crawl.py（refresh 端点）
- [x] N9 注册/确认 card-registry（news enabled）
- [x] N10 建 OpenClaw cron（08/12/18/22）
- [x] N11 文档同步：card-spec(list+url) + baseline + audit + 归档旧 news 数据
- [x] N12 commit + push（代码 repo）

---

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 ACTIVE | 2026-06-11 | 初版：确立分层信息密度(精选+来源分块)+跨源聚合打分+可点链接+兴趣加权+cron刷新。遵循 card-spec 规范。 |

---

## 九、2026-06-11 迭代（管理员反馈）

1. **外文标题翻译**（方案A）：crawl.py 集成 Google 免费翻译端点(走代理+缓存 trans_cache.json)，翻译 BBC/NYT/卫报/半岛/NHK/AP 标题为中文，保留 `title_orig` 原文。德国之声本就中文不译。
2. **多源并排矩阵**（形态①）：展开态"全部来源"区由竖排 list 改为 `source_matrix` section——每来源一列横向并排，列内新闻可点跳原文，横向滚动。精选 Top12 仍保留可点 list。
3. sources.json 外文源加 `translate:true` 标记。
4. 实测：180条/14源/0失败，矩阵13列，翻译质量良好。commit `c7ff06c`(前端) + crawl/generate-display(user-data)。

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 ACTIVE | 2026-06-11 | 迭代：外文翻译(方案A)+多源并排矩阵(source_matrix)+保留链接 |

## 十、2026-06-11 天气提醒化

天气从"显示当前温度"升级为**提醒型**（管理员：希望提醒几小时后下雨、明天高温等需关注信息）：
- `p_wttr` 解析 wttr.in j1 的逐时(每3h)预报 + 未来3天：
  - 今天剩余时段降雨概率≥50%(或含rain≥30%/雷阵雨) → 「约X点XX(降雨N%)，记得带伞」
  - 明天 maxtemp≥35→高温防暑；升/降温≥5度→升降温提醒；mintemp≤5→低温；降雨≥60%→明天有雨
  - 天气描述英→中映射(_WX_ZH)
- 输出 `weather_alerts: []` 存 data.json
- generate-display：提醒块置顶(🌦️杭州天气提醒, list) + 首条提醒放 summary 末尾(最显眼)
- **无需提醒时只显示当前现状**(有需关注才提醒)
- 前端无改动(复用 list 渲染)。实测逻辑正确(模拟下雨80%+明天36°C→正确生成两条提醒)
