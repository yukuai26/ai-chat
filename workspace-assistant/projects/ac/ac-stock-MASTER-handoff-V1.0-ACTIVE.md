---
doc_id: "ac-stock-MASTER-handoff-V1.0-ACTIVE"
title: "股票卡片 — 完整主交接文档（失忆也能接续）"
version: "V1.0"
status: "ACTIVE"
entity: "ac"
author: "小助手"
created: "2026-06-09"
purpose: "唯一权威总文档。记录股票/金融功能从调研到落地的全过程：做了什么、尝试了什么、踩了哪些坑、完整设计、文件清单、当前状态、怎么继续。明天失忆后只读这一篇即可掌握全部。"
related:
  - "ac-stock-card-design-V1.0-DRAFT.md (详细架构)"
  - "ac-stock-card-maintenance-V1.0-ACTIVE.md (卡片喵维护手册)"
  - "ac-stock-system-design-V1.0-DRAFT.md (四阶段总规划)"
  - "ac-data-sources-V1.0-ACTIVE.md (数据源清单)"
  - "lesson-2026-06-08-shared-proxy-rate-limit.md (代理限流教训)"
---

# 📈 股票卡片 — 完整主交接文档（V1.0）

> **这是唯一权威总文档。** 失忆后读这一篇 = 掌握全部。其它文档是细节展开。

---

## 〇、一句话现状

**stock 股票卡片 Phase 1（数据展示看板）后端+前端已完成并上线，全部国内直连零代理。** 六支样板股票（茅台/腾讯/苹果/上证/沪深300ETF/BTC）的实时行情+蜡烛K线+技术指标+AI点评都跑通了。cron 定时刷新已配。**唯一待办：管理员在浏览器实测渲染效果（服务器无浏览器，我没法自测画面）。**

---

## 一、这是什么 / 大背景

- 这是 **AC Dashboard 卡片系统**的又一张新卡片（id: `stock`）。
- 卡片系统 = Web Chat 网页里的"每日 Dashboard"，插件式：每张卡 = `daily-data/<id>/` 下 5 文件（data/rules/prompt/generate-display→display.json），由卡片喵驱动。
- 已做完的卡：recipe/todo/data。stock 是新增。
- 股票功能的完整路线（4阶段）：**Phase1 数据展示看板(当前,已完成)** → Phase2 回测 → Phase3 虚拟盘 → Phase4 真实交易(远期不做)。

---

## 二、需求（管理员拍板的）

1. **自选股**：现在每市场各 1 支做样板；后续做成"卡片喵可增删的接口"（= 改 data.json 的 watchlist）。
2. **展示**：完整版 = 列表 + K线 + 指标 + AI点评。
3. **K线**：折线图 + 蜡烛图**都要**，顶部**可点击标题切换**两种图。
4. **指标**：越详细越好 + 带 AI 分析。
5. **刷新**：盘中 15 分钟。
6. **数据**：能不走代理就不走代理（→ 最终全部国内直连）。
7. **谁写**：小助手自己写。

---

## 三、调研结论（做过/参考过什么）

### 四类标杆开源项目（各取星最高，已读 README 原文）
| 类别 | 项目 | ⭐ | 是什么 | 我们怎么用 |
|------|------|---:|--------|-----------|
| 量化平台 | StockSharp | 10055 | 自动交易+回测重型平台 | 太重，Phase2借鉴回测思路 |
| 组合追踪 | portfolio-performance/portfolio | 3898 | 桌面App，记持仓算盈亏(收益/回撤/夏普) | Phase2/3指标参考 |
| 看板Dashboard | woshijielie/stock_prediction_and_recommendation | 361 | React+AntD网页看板,Yahoo数据,多股对比,自选,预测 | **Phase1布局抄它** |
| 指标库 | femtotrader/pandas_talib | 780 | 算指标的Python库 | ⚠️它标 work-in-progress 且与pandas3不兼容→**弃用,改自实现** |
| (同类看板) | stonks-dashboard / market_dashboard | 172/114 | 终端/静态看板,周期切换,缓存 | 架构(抓数→JSON→前端)与我们卡片系统同构,可平移 |

### 关键洞察
- `market_dashboard` 的 `build_data.py→snapshot.json→index.html` ＝ 我们的 `generate-display.py→display.json→前端`，**完全同构**。
- 技术指标**自实现**（纯Python，没用 pandas_ta 也没用 pandas-ta，零依赖），因为 pandas_ta 不兼容 pandas3。

---

## 四、数据源（最终方案：全部国内直连，零代理！）

> 演进：最初设计走 Yahoo+代理 → 踩了代理限流大坑 → 管理员要求"能不走代理就不走" → 实测发现国内源全市场可用 → **彻底废弃 Yahoo+代理**。

| 市场 | 实时行情 | 日K线 | 实测状态 |
|------|---------|-------|:--:|
| A股/指数/ETF | 新浪 `hq.sinajs.cn`(GBK,含五档) | 新浪 `quotes.sina.cn/.../getKLineData` | ✅ |
| 港股 | 新浪 `hq.sinajs.cn/hk00700` | 腾讯 `web.ifzq.gtimg.cn/.../fqkline/get` | ✅ |
| 美股 | 腾讯 `qt.gtimg.cn/q=usAAPL`(GBK) | 新浪 `US_MinKService.getDailyK`(40年史) | ✅ |
| 加密 | 新浪 `hq.sinajs.cn/btc_btcbtcusd` | 新浪 `GlobalFuturesService...DailyKLine?symbol=BTC` | ✅ |

### ❌ 试过但不用的
- **Yahoo Finance + 代理 172.29.4.175:22222**：能拿全品类数据，但**共享代理对Yahoo有自身限流**（429来自网关，返回`Too Many Requests\r\n`），密集请求必被封。调试时把IP打废。已弃用。
- **东方财富 push2.eastmoney.com**：本服务器 DNS/防火墙不通（curl 返回 000，连接建不起来）。弃用。
- **OKX 加密 API**：被墙，无返回。用新浪 btc_ 代替。
- **新浪港股日K(HK_StockService.getDayKLine)**：接口失效(Service not valid)。港股日K改用腾讯。

### 还没有的
- **A股/美股/加密的分时(1D)数据**：国内免费源没有好的分时接口。所以 **1D 周期暂缺**（只有日K一个点，已自动从前端 periods 剔除）。1W/1M/3M 正常。后续可接腾讯分时(`web.ifzq.gtimg.cn/.../minute`)。

---

## 五、文件清单（在哪、是什么）

### 线上权威（卡片运行实体）
```
/home/ubuntu/.openclaw/user-data/daily-data/stock/
├── data.json            watchlist(6支) + quotes/klines/ai_comment 缓存
├── rules.json           交互规则(增删自选股)+刷新规则
├── prompt.json          卡片喵指令 + AI点评prompt
├── generate-display.py  抓数(国内直连,按mkt路由)+自实现指标+生成display
├── display.json         产出物(前端读这个)
└── refresh-stock.sh     cron 刷新包装脚本(quote/full)
```

### 源码副本（workspace，改完两边同步）
`/home/ubuntu/.openclaw/workspace-assistant/projects/ac/stock-card-src/` (同上6文件)

### 线上前端代码（已改，有备份）
- `/var/www/chat/index.html` — 加了 stock_detail/stock_chart 渲染 + 蜡烛插件 + 卡片注册
  - 备份：`index.html.bak-stock-20260609-002452`
- `/var/www/chat/fileserver.py` — DEFAULT_CARD_REGISTRY 加 stock 卡 + layout.order
  - 备份：`fileserver.py.bak-stock-*`

### 设计/文档
- 本文件(主交接) / ac-stock-card-design(详细架构) / ac-stock-card-maintenance(维护手册) / ac-stock-system-design(四阶段) / ac-data-sources(数据源)
- lesson-2026-06-08-shared-proxy-rate-limit(代理限流教训)

---

## 六、技术实现要点

### 后端 generate-display.py
- watchlist 每条有 `mkt` 字段(ashare/hk/us/crypto)决定数据源路由。
- 实时行情：A股/港股/加密走新浪(一把抓)，美股走腾讯。失败→缓存兜底(标 _stale)。
- K线：按 mkt 调 fetch_kline_ashare/hk/us/crypto。**一天抓一次缓存**(klines[code]._date)，当天复用；`--refresh-kline` 强制重抓。
- 指标自实现：MA(5/10/20/60)/RSI(14)/MACD(12,26,9)/布林带(20,2)，算在3M日线上。`indicator_text()` 出大白话状态。
- 写回 data.json(klines缓存+quotes) + 生成 display.json + POST /notify-display-update 通知前端。

### display.json 结构 → 前端
- `table`：自选列表
- 每支一个 `stock_detail`(可折叠)，sub 含：
  - `stock_chart`：折线/蜡烛**可点击切换** + 周期(1W/1M/3M)切换。蜡烛用 Chart.js financial 插件，数据 {x(ISO日期),o,h,l,c}；折线 {date,value}
  - `kv` 详情 + `kv` 指标(footer状态) + `note`(AI点评)

### 前端 index.html
- head 引入：`luxon@3` + `chartjs-adapter-luxon@1` + `chartjs-chart-financial@0.2.1`(CDN已验证200)
- renderCardBody switch 加 `case 'stock_detail'`
- 函数：`_renderStockSub`/`_toggleStockDetail`/`_initStockChart`/`_drawStockChart`/`_switchStockMode`/`_switchStockPeriod`
- 注册：allCardIds / IMPLEMENTED_CARDS / getCardSummary 加 'stock'
- 蜡烛涨跌色：up红 down绿(A股习惯)

### 注册(让卡片出现在"添加卡片")
- fileserver.py `DEFAULT_CARD_REGISTRY.cards` 加 stock + `layout.order` 加 stock
- ⚠️ 改 fileserver.py 后必须重启 **`fileserver.service`**(实际监听5050的是它，不是 chat-fileserver.service——后者是抢不到端口的僵尸循环,待清理)

---

## 七、cron 定时刷新（已配，系统 crontab）

脚本：`daily-data/stock/refresh-stock.sh [quote|full]`
- quote = 只刷实时价(用K线缓存) | full = 抓全量K线+算指标(--refresh-kline)

```
30,45 9 * * 1-5     quote   # A股早盘
*/15 10-14 * * 1-5  quote   # A股盘中
0 15 * * 1-5        quote   # A股收盘
30,45 21 * * 1-5    quote   # 美股开盘(北京时间晚)
*/15 22,23 * * 1-5  quote   # 美股盘中
*/15 0-4 * * 2-6    quote   # 美股盘中(凌晨)
0 6 * * *           full    # 每天6:00抓全量K线(美股已收盘)
```
日志：`/home/ubuntu/.openclaw/logs/stock-refresh.log`

> AI点评目前是小助手/卡片喵手动按真实数据生成写入 ai_comment（已写6条）。后续可在 full 刷新后自动触发卡片喵生成。

---

## 八、当前完成度

| 项 | 状态 |
|----|:--:|
| 调研(4类标杆+数据源) | ✅ |
| 设计文档 + 维护手册 | ✅ |
| 后端 generate-display.py(全国内直连) | ✅ 跑通 |
| 6支真实数据(行情+K线+指标) | ✅ |
| AI点评(6条) | ✅ |
| 前端渲染(折线/蜡烛切换+周期) | ✅ 代码完成,⚠️未浏览器实测 |
| 卡片注册(registry/前端) | ✅ |
| cron 定时刷新 | ✅ |
| **浏览器实测渲染效果** | ⬜ **待管理员验证** |
| 1D 分时数据 | ⬜ 缺(国内免费源难,后续接腾讯分时) |
| AI点评自动化(full后自动生成) | ⬜ 后续 |

---

## 九、怎么继续（失忆后的下一步）

1. **先让管理员在浏览器看效果**：`https://yoga-findlaw-louisiana-strong.trycloudflare.com`(临时tunnel域名,可能变,查 /tmp/tunnel.log) → 添加"📈 股票看板"卡 → 点开某股 → 验证折线/蜡烛切换、周期切换。
   - 若蜡烛图空白：浏览器F12看 chartjs-chart-financial/luxon 是否加载、_drawStockChart 是否报错。
2. **增删自选股测试**：按维护手册改 watchlist + 跑脚本，验证卡片喵流程。
3. **补 1D 分时**：接腾讯分时接口。
4. **AI点评自动化**：full 刷新后自动触发卡片喵生成点评。
5. **Phase2 回测**：另起(见 ac-stock-system-design)。

---

## 十、重要坑/教训（别再踩）

1. **共享代理对Yahoo有自身限流**(429来自网关)——调试抓取先用缓存/样本,最后才接真实高频,别把共享IP打废。详见 lesson-2026-06-08。→ 现已全国内直连,无此问题。
2. **东财接口本服务器不通**(DNS/防火墙)。
3. **pandas_ta 不兼容 pandas3**(用了 numpy.NaN 等被移除的API)→ 指标自实现。
4. **5050端口是 fileserver.service**,不是 chat-fileserver.service(后者僵尸循环)。改后端重启前者。
5. **write 工具不能写 /var/www 和 user-data**(workspace外)→ 用 sudo+python 改线上文件,源码在 workspace 留副本。
6. **新浪返回 GBK 编码**,要 decode('gbk')。
7. **workspace-assistant 不是 git 仓库**,文件保存即生效,靠 backup-repo 每日备份。

---

## 变更记录
| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-09 | 初版主交接。整合全过程:调研→设计→后端→甩代理→前端→AI点评→cron。Phase1基本完成,待浏览器实测 |
