---
doc_id: "ac-stock-handoff-2026-06-08"
title: "股票/金融功能 — Session 交接文档"
status: "ACTIVE"
created: "2026-06-08T21:54:00+08:00"
purpose: "2026-06-08 晚 session 因反复出现'工具调用写进正文'错误，决定重启新对话。本文档记录全部上下文，供新 session 无缝接续。"
---

# 股票/金融功能 — Session 交接文档（2026-06-08）

## 说明
本文档为 2026-06-08 晚 session 重启的交接材料，记录卡片系统的完整脉络 + 股票功能调研结论，供新 session 接续。

---

## 〇、卡片系统大背景（从最初到现在的脉络）

股票功能不是孤立的，它是 **AC Dashboard 卡片系统** 的又一张新卡片。完整脉络：

### 卡片系统的由来（2026-05-27 设计马拉松）
- Web Chat 网页里有个"每日 Dashboard"，采用**插件式卡片架构**：一张 card-registry 注册表驱动，加新卡片 = 注册表+1 + 数据API + 前端组件，不动现有代码。
- 当时一次性规划了 **11 张卡片**（首批5 + 扩展6）：
  - 首批：📰资讯(news)、📋Todo(todo)、📊数据(data)、🍽️食谱(recipe)、⭐心愿(wishes)
  - 扩展：📝**随手记(notes)**、🔖收藏夹(bookmarks)、📷照片墙(photos)、📤分享板(shares)、⏰提醒(reminders)、✅习惯打卡(habits)

### 卡片的标准结构（card-spec 规范）
每张卡片 = `daily-data/<id>/` 下 4~5 个文件：data.json(数据) / prompt.json(卡片喵指令) / rules.json(规则) / generate-display.py(脚本) → 产出 display.json(前端渲染)。卡片由 **卡片喵 agent(card-assistant, Opus)** 驱动。

### 卡片完成进度（截至 06-07）
- ✅ **真正做完 3 张**：recipe(食谱) / todo / data(健康数据)
- ⬜ **8 张空壳**（只有 prompt.json，无脚本/真数据）：**notes(随手记)** / news(资讯) / wishes / bookmarks / photos / shares / reminders / habits

### "最开始想做 notes 卡" 的来龙去脉
- 卡片队列里 **notes(随手记)** 是扩展卡之一，一直是空壳待做。
- 后来管理员关注点转到 **news 资讯卡** → 调研资讯数据源 → 发现可以爬股票 → 兴趣扩展到**股票/金融**，于是先做股票看板。
- **所以待办卡片池 = notes(随手记) + news(资讯) + wishes/bookmarks/photos/shares/reminders/habits + 新增 stock(股票)**。股票是当前优先，但 notes 等仍在队列里。

> 详细卡片机制见 `ac-card-spec-V1.0-ACTIVE.md`，Phase 队列与进度见 MEMORY.md「设计马拉松」章节。

---

## 一、当前在做什么：股票/金融功能

为卡片系统新增 **股票/金融** 方向。用户（管理员）的兴趣递进：
1. 先做**数据展示看板**（看行情/K线/指标，辅助人工决策）← **当前聚焦 Phase 1**
2. 之后想做**回测**（用历史数据测策略赚不赚钱，不花真钱）
3. 再做**虚拟盘/模拟盘**（实时行情+假钱演习）
4. （远期）真实自动交易 — 暂不做

## 二、已完成的调研（关键结论）

### 数据源（已实测，详见 `ac-data-sources-V1.0-ACTIVE.md`）
- **网络铁律**：服务器在国内无翻墙。**国外源必须走代理 `172.29.4.175:22222`**（TOOLS.md 标注不稳定，需失败兜底回退国内源）。
- **资讯**：国内(新浪/百度/头条/知乎/B站/本地/天气)直连✅；国际(BBC/NYT/卫报/半岛/NHK/AP/DW/HackerNews)走代理✅；微博/抖音/小红书/推特原文/石墨爬不了❌。
- **股票金融全品类实测可用**：
  - A股：新浪/东财直连，**零延迟+买卖五档**
  - 美股/全球指数/ETF/国债收益率/黄金有色原油/外汇加密：**Yahoo Finance**（走代理，字段最全，含盘前盘后）
  - 单股能拿：实时盘口五档、K线(分钟/日/周/月可复权)、资金流向、估值(市盈/市净/市值/换手)
  - **历史数据(回测用)**：Yahoo 苹果实测拿到 **1984年至今40年日线**；A股用 AKShare 更稳
  - 拿不到：A股Level-2十档/逐笔(付费)、美股零延迟(付费)、完整三大财报逐项

### 美股"延迟"原因
实时逐笔行情归交易所所有=付费产品，全球免费源(含美国本土Yahoo)通行做法是给15分钟延迟。美国本土免费API：Yahoo Finance(免费无key,首选)、Alpha Vantage(需免费key)、Finnhub(需key)、Stooq(有验证)。

## 三、参考的开源项目（按类别+最高星）

| 类别 | 最高星 | 是什么 | 对我们 |
|------|------|--------|--------|
| 1.量化交易平台 | StockSharp(10055⭐)/QuantDinger(7531⭐) | 自动交易+回测，太重 | 不抄(除回测思路) |
| 2.组合追踪器 | portfolio-performance(3897⭐)/investbrain(853⭐,带LLM) | 记持仓算赚亏/收益指标 | Phase2/3指标参考 |
| 3.看板Dashboard | woshijielie/stock_prediction_and_recommendation(361⭐,React+AntD)/stonks-dashboard(172⭐)/market_dashboard(114⭐)/ai-stock-dashboard(86⭐) | 纯展示行情+K线+指标 | **Phase1布局直接抄** |
| 4.技术指标库 | pandas_talib(780⭐)/talipp(528⭐)/pandas-ta(353⭐)/AI-Kline(327⭐中文) | 算RSI/MACD/布林带的库 | **算法直接用,不手写** |

回测框架候选：Backtrader / backtesting.py。A股历史数据：AKShare。

**关键洞察**：
- `market_dashboard` 架构 = 我们卡片系统(脚本抓数→JSON→前端)，可平移
- 技术指标用现成库(pandas-ta)，不手写
- 我们独有优势：**卡片喵(Opus)** 能做AI点评，比这些项目的弱AI更强

## 四、接下来要做什么

**当前任务（用户最新指令）**：聚焦 **Phase 1 数据展示看板**，参考开源看板项目的做法。

**下一步动作**（新session继续）：
1. ✅ 已读 `market_dashboard`/`stonks-dashboard` README（走代理 raw.githubusercontent），提炼看板要素回填设计 §2.0。两者架构与我们卡片系统同构，可平移。
2. ⬅️ 当前：跟用户确认 Phase1 TODO 里的 P1-1(自选股清单) 和 P1-2(展示粒度)
3. 出 stock 卡片详细设计 → 实现

**设计文档**：`projects/ac/ac-stock-system-design-V1.0-DRAFT.md`（已含 Phase1/2/3 完整 TODO）

## 五、相关文档索引
- `projects/ac/ac-stock-system-design-V1.0-DRAFT.md` — 股票功能总设计(Phase1-4+TODO)
- `projects/ac/ac-data-sources-V1.0-ACTIVE.md` — 数据源完整清单(实测)
- `projects/ac/ac-card-spec-V1.0-ACTIVE.md` — 卡片系统规范(4文件标准)
- `projects/ac/ac-design-baseline-V1.0-ACTIVE.md` — AC设计基线(权威)

## 六、待做卡片池（除股票外）
notes(随手记) / news(资讯) / wishes(心愿) / bookmarks(收藏夹) / photos(照片墙) / shares(分享板) / reminders(提醒) / habits(习惯打卡) — 均为空壳，待逐张做。当前优先 stock(股票)。
