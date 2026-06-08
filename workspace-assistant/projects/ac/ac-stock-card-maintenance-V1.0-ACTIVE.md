---
doc_id: "ac-stock-card-maintenance-V1.0-ACTIVE"
title: "stock 股票卡片 — 卡片喵维护手册"
version: "V1.0"
status: "ACTIVE"
entity: "ac"
author: "小助手"
created: "2026-06-09"
purpose: "给卡片喵(card-assistant)和后续维护者的操作手册：如何增删自选股、生成AI点评、刷新数据、排障。stock 卡片全部国内直连零代理。"
related: ["ac-stock-card-design-V1.0-DRAFT.md", "ac-data-sources-V1.0-ACTIVE.md"]
---

# stock 股票卡片 — 卡片喵维护手册 V1.0

> 给卡片喵 / 维护者：这张卡怎么管。一句话——**改 data.json 的 watchlist + 跑一次脚本**。

---

## 一、文件位置（线上权威）

```
/home/ubuntu/.openclaw/user-data/daily-data/stock/
├── data.json            ← ⭐你主要改这个(watchlist + 缓存)
├── rules.json           ← 交互/刷新规则(一般不动)
├── prompt.json          ← 卡片喵指令 + AI点评prompt
├── generate-display.py  ← 抓数+算指标+生成display(改数据源才动)
└── display.json         ← 产出物(前端读这个,脚本自动生成,别手改)
```
源码副本在 `workspace-assistant/projects/ac/stock-card-src/`（改完记得两边同步）。

---

## 二、最常见操作：增删自选股 🎯

### 加一只股票
1. 编辑 `data.json` 的 `watchlist` 数组，按对应市场格式 append 一条：

| 市场 | 格式示例 | 说明 |
|------|---------|------|
| A股 | `{"market":"A股","name":"宁德时代","code":"sz300750","mkt":"ashare"}` | 沪市 sh，深市 sz |
| 港股 | `{"market":"港股","name":"美团","code":"hk03690","mkt":"hk"}` | hk+5位代码 |
| 美股 | `{"market":"美股","name":"英伟达","code":"us_NVDA","mkt":"us","sym":"NVDA"}` | code 加 us_ 前缀，sym 是纯代码 |
| 指数 | `{"market":"指数","name":"深证成指","code":"sz399001","mkt":"ashare"}` | 当 A股 处理 |
| ETF | `{"market":"ETF","name":"科创50ETF","code":"sh588000","mkt":"ashare"}` | 当 A股 处理 |
| 加密 | `{"market":"加密","name":"以太坊","code":"btc_ethethusd","mkt":"crypto","sym":"ETH"}` | 新浪 btc_ 前缀 |

2. 跑脚本刷新：
```bash
cd /home/ubuntu/.openclaw/user-data/daily-data/stock
python3 generate-display.py --refresh-kline
```
（`--refresh-kline` 强制重抓K线；不加则当天用缓存）

### 删一只股票
1. 从 `data.json` 的 `watchlist` 移除那一条
2. 跑 `python3 generate-display.py`（删除不必重抓，不用 --refresh-kline）

### ⚠️ 关键字段说明
- `mkt`：决定走哪个数据源路由，**必填**（ashare/hk/us/crypto）
- `code`：实时行情用的代码（新浪/腾讯格式）
- `sym`：美股/加密的 K线接口用的纯代码（A股/港股不需要）

---

## 三、生成 AI 点评 🤖

点评存在 `data.json` 的 `ai_comment[code]`，前端会显示在每只股票详情底部。

卡片喵生成点评流程：
1. 读该股的 `quotes[code]`（现价/涨跌）+ `klines[code]` + 算出的指标
2. 按 `prompt.json.ai_comment_prompt` 的口径写 2-4 句大白话（客观中性、提示风险、不荐股不预测）
3. 写入 `data.json`：
```json
"ai_comment": {
  "sh600519": {"text": "茅台今天小跌0.78%，RSI 34 偏弱，跌破20日均线，短期承压，注意量能。", "ts": "2026-06-09T..."}
}
```
4. 跑 `python3 generate-display.py` 让点评进 display

> 也可由用户触发："点评一下茅台" / "茅台怎么样"。

---

## 四、数据源（全部国内直连，零代理！）

| 市场 | 实时行情 | 日K线 |
|------|---------|-------|
| A股/指数/ETF | 新浪 `hq.sinajs.cn` | 新浪 `getKLineData` |
| 港股 | 新浪 `hq.sinajs.cn` | 腾讯 `web.ifzq.gtimg.cn/fqkline` |
| 美股 | 腾讯 `qt.gtimg.cn/q=usXXX` | 新浪 `US_MinKService`(40年史) |
| 加密 | 新浪 `hq.sinajs.cn/btc_*` | 新浪 `GlobalFuturesService` |

> 🚫 **不再用 Yahoo + 代理**（共享代理对 Yahoo 限流极敏感，见 lesson-2026-06-08-shared-proxy-rate-limit）。新增标的优先用上面的国内源。

---

## 五、定时刷新（cron，待配）

| 任务 | 建议频率 | 命令 |
|------|---------|------|
| 盘中刷行情 | 每15分钟(交易时段) | `python3 generate-display.py`(用K线缓存,只更新实时价) |
| 收盘抓K线+算指标 | 每天1次 | `python3 generate-display.py --refresh-kline` |
| AI点评 | 每天1-2次 | 卡片喵生成 ai_comment 后跑脚本 |

> 美股交易时段是北京时间晚上(夏令时 21:30-04:00)。cron 待落地（注意 MEMORY 铁律：新建 cron 必须更新文档）。

---

## 六、技术指标说明

脚本自实现(纯Python，零依赖)，算在最长周期(3M)上：
- MA5/10/20/60、RSI(14)、MACD(12,26,9)、布林带(20,2)
- `indicator_text()` 把指标翻译成大白话状态(超买超卖/均线多空/布林位置)

---

## 七、前端展示结构（display.json → 网页）

- `table` section：自选列表
- 每只股票一个 `stock_detail` section（可折叠），内含 `sub`：
  - `stock_chart`：折线/蜡烛**可点击切换** + 周期(1W/1M/3M)切换。蜡烛用 Chart.js financial 插件
  - `kv` 详情：现价/开高低/量/振幅/52周高低
  - `kv` 指标：MA/RSI/MACD/布林 + footer 状态
  - `note`：AI 点评(有 ai_comment 才显示)

> 注：1D 周期因无免费分时数据，单点不画，已自动从 periods 剔除。后续接分时源可恢复。

### 前端注册位置（改卡片名/图标时）
- `fileserver.py` `DEFAULT_CARD_REGISTRY`：stock 卡定义 + layout.order
- `index.html`：`allCardIds` / `IMPLEMENTED_CARDS` / `getCardSummary`
- 新 section 渲染逻辑：`index.html` 的 `renderCardBody` switch(`stock_detail` case) + `_renderStockSub`/`_drawStockChart` 等函数
- 蜡烛插件：`index.html` head 的 chartjs-chart-financial + luxon CDN

---

## 八、排障

| 症状 | 排查 |
|------|------|
| 某股价格显示 — | 该股实时接口挂了；看脚本日志 `⚠️` 行；检查 code/mkt 格式 |
| K线空白 | 该周期数据<2点；看 `klines[code]` 缓存；--refresh-kline 重抓 |
| 蜡烛图不显示 | 浏览器控制台看 chartjs-chart-financial 是否加载；luxon 是否加载 |
| 卡片不出现 | registry 没注册；重启 `fileserver.service` |
| 数据是旧的 | K线当天缓存了；要新数据加 --refresh-kline |

### 改完代码后
- 同步 `stock-card-src/` ↔ `daily-data/stock/`
- 改了 fileserver.py/index.html → 重启 `fileserver.service`（注意：5050 实际是 fileserver.service，不是 chat-fileserver.service）
- 改设计必须改文档（双向同步铁律）

---

## 变更记录
| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-09 | 初版。全国内直连零代理；增删自选股/AI点评/刷新/排障完整指南 |
