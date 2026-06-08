---
doc_id: "ac-stock-card-design-V1.0-DRAFT"
title: "AC 股票卡片（stock）Phase 1 详细架构设计"
version: "V1.0"
status: "DRAFT"
entity: "ac"
author: "小助手"
created: "2026-06-08"
purpose: "Phase 1 数据展示看板的落地设计。贴合现有卡片系统(5文件: data/rules/prompt/generate-display→display.json)，每市场各选一支样板，完整展示(K线多周期+技术指标+卡片喵AI点评)，自选股后续做成卡片喵可增删的接口。供管理员 review。"
related: ["ac-stock-system-design-V1.0-DRAFT.md", "ac-data-sources-V1.0-ACTIVE.md", "ac-card-spec-V1.0-ACTIVE.md"]
---

# stock 卡片 Phase 1 详细架构设计 V1.0（DRAFT）

> 需求确认（2026-06-08 管理员）：
> - **自选股**：后续做成卡片喵可增删的接口；**现在每个市场各选一支**做样板
> - **展示**：要**完整版**（列表 + K线多周期 + 技术指标 + 卡片喵 AI 点评）
> - 本稿先给整体架构 + 实现方式，管理员 review 后再开工

---

## 一、设计原则：贴着现有卡片系统，不重新发明

已核对现有 `data`（健康）卡的真实落地，stock 卡完全沿用同一套机制：

| 现有机制（已验证） | stock 卡如何复用 |
|---|---|
| 卡片 = `daily-data/<id>/` 下 5 文件：`data.json`/`rules.json`/`prompt.json`/`generate-display.py`→`display.json` | 照搬，新建 `daily-data/stock/` |
| 前端已支持 section type：`chart_tabs`(多tab折线)、`kv`、`table` | 复用 `chart_tabs` 画 K线/指标，`kv` 显示详情，`table` 显示自选列表 |
| `generate-display.py` 算完写 `display.json` → POST `/notify-display-update` 通知前端刷新 | 照搬同一通知机制 |
| 卡片喵按 `rules.json` 的 `interaction_rules` 改 `data.json` | 自选股增删 = 卡片喵改 `data.json` 的 watchlist（天然满足"接口"需求） |

**结论**：不动现有任何卡片代码，只 ①新建 stock 目录 5 文件 ②card-registry 注册 ③前端可能补一个"切标的"交互。

---

## 二、整体架构图

```
┌─ 数据源层（依 ac-data-sources）──────────────────────┐
│  A股  : 新浪/东财 直连（零延迟五档）                    │
│  美股/指数/ETF/币 : Yahoo Finance（走代理 172.29.4.175:22222 + 失败兜底）│
│  历史K线 : Yahoo(40年) / A股 AKShare                    │
└──────────────────────────┬───────────────────────────┘
                           │  抓取（带缓存，避免被限）
                           ▼
┌─ 后端脚本层（平移 market_dashboard 的 build_data 思路）─┐
│  daily-data/stock/                                      │
│   ├─ data.json          ← watchlist(自选清单) + 抓回的行情/K线缓存 │
│   ├─ rules.json         ← 卡片喵交互规则(增删自选股) + 展示规则     │
│   ├─ prompt.json        ← 卡片喵指令 + AI点评 prompt              │
│   ├─ generate-display.py← 抓数+算指标(pandas-ta)+组装 → display.json│
│   └─ display.json       ← 前端直接渲染（产出物）                  │
└──────────────────────────┬───────────────────────────┘
                           │  POST /notify-display-update
                           ▼
┌─ 前端展示层（复用现有卡片渲染器）──────────────────────┐
│  缩略态：自选列表(代码/名/现价/涨跌%) + 几大指数概览       │
│  展开态：选标的 → chart_tabs(K线1D/1W/1M/3M) +           │
│          技术指标(MA/RSI/MACD/布林) + kv详情 + 卡片喵AI点评│
└──────────────────────────────────────────────────────┘
                           ▲
              卡片喵(card-assistant, Opus)
              ├─ 增删自选股(改 data.json.watchlist)
              └─ 生成 AI 点评(写进 display)
```

---

## 三、每个市场的样板标的（P1-1 现阶段）

> 现在每市场各 1 支，后续卡片喵可增删。建议样板：

| 市场 | 样板标的 | 代码 | 数据源 |
|------|---------|------|--------|
| A股 | 贵州茅台 | `sh600519` | 新浪直连（零延迟五档） |
| 港股 | 腾讯控股 | `hk00700` | 新浪/Yahoo |
| 美股 | 苹果 | `AAPL` | Yahoo（代理） |
| 指数 | 上证指数 | `sh000001` | 新浪直连 |
| ETF | 沪深300ETF | `sh510300` | 新浪直连 |
| 加密 | 比特币 | `BTC-USD` | Yahoo / CoinGecko |

> ⬅️ 这几支只是**默认样板**，请 review 替换/增减。后续全部由卡片喵动态增删。

---

## 四、数据结构（data.json 设计）

```jsonc
{
  "watchlist": [                       // ← 卡片喵可增删的"接口"就是这个数组
    {"market":"A股","name":"贵州茅台","code":"sh600519","source":"sina"},
    {"market":"港股","name":"腾讯控股","code":"hk00700","source":"sina"},
    {"market":"美股","name":"苹果","code":"AAPL","source":"yahoo"},
    {"market":"指数","name":"上证指数","code":"sh000001","source":"sina"},
    {"market":"ETF","name":"沪深300ETF","code":"sh510300","source":"sina"},
    {"market":"加密","name":"比特币","code":"BTC-USD","source":"yahoo"}
  ],
  "quotes": {                          // 脚本抓回的实时行情缓存
    "sh600519": {"price":1680.5,"change_pct":1.23,"open":...,"high":...,"low":...,"updated":"..."}
  },
  "klines": {                          // 各标的多周期K线缓存(脚本抓+算指标)
    "sh600519": {
      "1D": [{"date":"...","o":..,"h":..,"l":..,"c":..,"vol":..,"ma5":..,"ma20":..,"rsi":..,"macd":..}],
      "1W": [...], "1M": [...], "3M": [...]
    }
  },
  "ai_comment": {                      // 卡片喵生成的点评
    "sh600519": {"text":"今天小涨，站上5日线...","ts":"..."}
  }
}
```

---

## 五、展示设计（完整版，display.json → 前端）

### 缩略态（summary + 列表）
- `summary`：`📈 上证 3210(+0.5%) | 茅台 1680(+1.2%)`（挑大盘+涨跌最大几只）
- `table` section：自选列表（市场/名称/现价/涨跌幅，红涨绿跌）

### 展开态（点单只标的）
1. `chart_tabs`（**复用现有渲染器**）— K线/指标多周期切换
   - tab：`1D / 1W / 1M / 3M`
   - 每周期画：收盘价折线 + MA5/MA20 叠加（Phase 1 先折线，蜡烛图作 P1-6 增强）
2. 技术指标区（`kv` 或小图）：最新 RSI / MACD / 布林带位置 + 一句话状态（超买/超卖等）
3. `kv` 详情面板：现价/涨跌/今开/最高/最低/成交量/（A股可加买卖五档）
4. **卡片喵 AI 点评**：大白话解读"今天啥情况、注意啥"

> K线优先用现成 `chart_tabs`（零前端改动）。若要专业蜡烛图，P1-6 引入轻量图表库（如 lightweight-charts），作为增强项单独评估。

---

## 六、技术指标实现

- **用现成库 `pandas-ta`**（不用那个标注 work-in-progress 的 pandas_talib，不手写）
- 算：MA(5/10/20/60) / RSI(14) / MACD(12,26,9) / 布林带(20,2)
- 在 `generate-display.py` 抓到 K线后直接算，结果并进 klines 缓存

---

## 七、卡片喵交互（rules.json）

```jsonc
"interaction_rules": [
  {"trigger":"加自选 XXX / 关注 XXX", "action":"解析市场+代码→append 到 watchlist；触发重新抓数"},
  {"trigger":"删自选 XXX / 取消关注 XXX", "action":"从 watchlist 移除该项"},
  {"trigger":"点评 XXX / XXX怎么样", "action":"读该标的行情+指标→生成大白话点评写 ai_comment"}
]
```
→ 这天然满足"自选股做成卡片喵可增删的接口"：**接口 = 对 data.json.watchlist 的增删，由卡片喵执行**。

---

## 八、刷新机制（cron）

- 盘中（A股 9:30-15:00 / 美股对应时段）：定时抓行情（如每 5-15 分钟，带缓存防限流）
- 收盘后：抓当日完整 K线 + 重算指标 + 卡片喵生成点评
- 复用现有 cron 体系（注意 MEMORY.md：新建 cron 必须更新文档）

---

## 九、Phase 1 实现步骤（落地顺序）

1. **S1** 建 `daily-data/stock/` + data.json（含样板 watchlist）
2. **S2** 写抓取模块：A股(新浪直连) + Yahoo(代理+兜底) + 缓存
3. **S3** 接 pandas-ta 算指标
4. **S4** 写 generate-display.py → 产出 display.json（summary+table+chart_tabs+kv）
5. **S5** prompt.json（卡片喵指令+点评prompt）+ rules.json（增删交互）
6. **S6** card-registry 注册 stock 卡 + 前端验证渲染
7. **S7** 卡片喵 AI 点评打通
8. **S8** cron 定时刷新 + 文档登记
9. **S9**（增强,可选）专业蜡烛图组件

---

## 十、review 决策结论（2026-06-08 管理员已确认）

1. ✅ **样板标的**：照原列六支（茅台 sh600519 / 腾讯 hk00700 / 苹果 AAPL / 上证 sh000001 / 沪深300ETF sh510300 / BTC-USD）
2. ✅ **K线形态**：**折线图 + 蜡烛图都要**，顶部有个**可点击切换的标题**在两种图之间切换
   - 技术方案（已验证 CDN 200 可用）：现有 **Chart.js 4.4.7** + 加插件 `chartjs-chart-financial@0.2.1`（画蜡烛）+ `chartjs-adapter-luxon@1` + `luxon@3`（日期轴）
   - 前端需扩展 chart_tabs：支持 `chartType` 切换（line/candlestick），蜡烛数据用 {x,o,h,l,c}
3. ✅ **指标**：**越详细越好** + **带 AI 分析**。指标全上 MA(5/10/20/60)/RSI(14)/MACD(12,26,9)/布林带(20,2)，再加成交量、换手率、振幅等；卡片喵生成 AI 点评
4. ✅ **刷新频率**：盘中 **15 分钟** 抓一次
5. ✅ **谁写**：小助手自己写（不 spawn 子 Agent）

> ⚠️ 工作区 workspace-assistant 非 git 仓库；线上代码 `/var/www/chat/` 改动需同步到 `repo/` 并 push（见 MEMORY.md Web Chat 流程），且改代码必须同步改设计（双向同步铁律）。

---

## 十一、实现进度（2026-06-08 夜）

### ✅ 后端已完成并跑通
- 源码在 `projects/ac/stock-card-src/`，已部署到 `user-data/daily-data/stock/`（5文件）
- `generate-display.py` 全链路验证通过：六支自选股 → 列表 + 蜡烛K线(4周期) + 详情 + 全套指标(MA5/10/20/60·RSI·MACD·布林带) + 大白话状态
- 技术指标**自实现**(pandas/numpy 都没用上，纯 Python，零依赖)——因 pandas_ta 标注 work-in-progress 且与 pandas3 不兼容
- A股/指数/ETF K线走**新浪日K直连(零限流)**；港股/美股/加密走 Yahoo

### 🔴 关键发现：代理对 Yahoo 限流极敏感（数据源现实约束）
- `172.29.4.175:22222` 是**共享代理**，对转发请求有**自身速率限制**(429 来自代理网关，返回 `Too Many Requests\r\n`)
- 单发 200，密集请求必被限流；今晚反复调试把该 IP 打进持续限流，需冷却
- **应对(已实现)**：① K线一天抓一次缓存复用(`klines[code]._date`) ② Yahoo quote 失败→缓存兜底(`_stale`) ③ 全局节流 `YH_MIN_INTERVAL`(env 可调) ④ A股完全不依赖 Yahoo(走新浪)
- **当前**：港/美/加密用了**样本缓存数据**(`_sample:true`，基于实测真实现价造的走势)跑通全量；待代理恢复后用 `--refresh-kline` 换真实数据

### ⬜ 前端待做（下一步）
- 引入 Chart.js financial 插件(`chartjs-chart-financial@0.2.1` + `chartjs-adapter-luxon` + `luxon`，CDN 已验证200)
- 在 `index.html` renderCardBody 支持新 section type：`stock_chart`(折线/蜡烛可点击切换 + 周期tab) + `stock_detail`(每标的容器)
- card-registry 注册 stock 卡 + 前端验证渲染
- 注意：display.json 约 216K(蜡烛点多)，后续可优化懒加载

### ⬜ 运维待做
- cron：盘中15min刷行情 / 收盘后抓K线+算指标+AI点评（按各市场交易时段配，注意美股=北京时间晚上）
- 卡片喵 AI 点评打通(ai_comment 生成)

## 变更记录
| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 DRAFT | 2026-06-08 | 初稿。基于现有卡片系统真实结构(已核对 data 卡)设计 stock 卡完整架构，待管理员 review |
| V1.0 (impl) | 2026-06-08夜 | review决策回填；后端实现+跑通(六支全量,指标全套)；发现代理对Yahoo限流敏感→K线缓存+样本兜底；前端/cron待做 |
