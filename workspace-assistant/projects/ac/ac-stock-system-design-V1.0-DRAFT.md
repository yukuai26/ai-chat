---
doc_id: "ac-stock-system-design-V1.0-DRAFT"
title: "AC 股票/金融功能系统设计"
version: "V1.0"
status: "DRAFT"
entity: "ac"
author: "小助手"
created: "2026-06-08"
updated: "2026-06-08"
purpose: "Web Chat 股票/金融能力的总体规划：数据展示看板 → 回测 → 虚拟盘 → (远期)自动交易。数据源依据见 ac-data-sources-V1.0-ACTIVE。借鉴开源项目做法。当前聚焦 Phase 1（数据展示）。"
related: ["ac-data-sources-V1.0-ACTIVE.md", "ac-card-spec-V1.0-ACTIVE.md"]
---

# AC 股票/金融功能系统设计 V1.0

> 状态：DRAFT — 待管理员逐项确认后转 ACTIVE
> 数据源：见 `ac-data-sources-V1.0-ACTIVE.md`（A股直连零延迟五档 / 美股·全球·ETF·国债·大宗走 Yahoo+代理）
> 网络铁律：国外源走代理 `172.29.4.175:22222` + 失败兜底回退国内源

---

## 0. 总体路线（四阶段，循序渐进）

| 阶段 | 名称 | 做什么 | 难度 | 风险 |
|------|------|--------|:--:|:--:|
| **Phase 1** | 数据展示看板 | 看行情+K线+技术指标，辅助人工判断（不下单） | 🟢 | 无 |
| **Phase 2** | 回测系统 | 写策略，用历史数据模拟跑，出收益报告（不花钱） | 🟡 | 无 |
| **Phase 3** | 虚拟盘(模拟盘) | 实时行情+假钱，跑策略演习（不动真金） | 🟡 | 无 |
| **Phase 4** | 真实自动交易 | 对接券商API实盘下单 | 🔴 | 高(资金/合规)，远期再议 |

> 当前聚焦 **Phase 1**。Phase 2/3 先登记 TODO，Phase 4 暂不规划。

---

## 1. 借鉴的开源项目（参考，非照搬）

| 借鉴点 | 项目 | ⭐ | 用途 |
|--------|------|---:|------|
| 看板布局/交互 | stonks-dashboard / market_dashboard | 172/114 | 自选股列表、多周期切换、详情面板 |
| 后台抓数→JSON→前端 架构 | market_dashboard | 114 | 与我们卡片系统(generate-display.py→display.json)同构，可平移 |
| 技术指标算法 | pandas-ta / talipp | 353/528 | 直接用库算 RSI/MACD/布林带，不手写 |
| AI 解读 | ai-stock-dashboard / AI-Kline | 86/327 | 思路参考；我们用卡片喵(Opus)做点评，更强 |
| React看板+多股对比+预测 | woshijielie/stock_prediction | 361 | Yahoo数据、3年历史、最多5股对比 |
| 收益/风险指标(夏普/回撤) | portfolio-performance | 3897 | Phase2/3 报告指标参考 |
| 回测框架 | Backtrader / backtesting.py | — | Phase2 选型候选 |
| A股数据库 | AKShare | — | Phase2 回测历史数据(比东财接口稳) |

---

## 2. Phase 1 — 数据展示看板（当前重点）

### 2.0 开源看板调研结论（2026-06-08，已读 README）
> 数据源：raw.githubusercontent 走代理拿到。两项目架构高度一致，且与我们卡片系统同构。

- **traderwillhu/market_dashboard (114⭐)**：`build_data.py` 抓 Yahoo → `snapshot.json/events.json/meta.json/charts/*.png` → 静态 `index.html`。**= 我们 generate-display.py→display.json，可直接平移**。监控维度：指数/板块/行业/各国ETF；K线用 TradingView embed；GitHub Actions 周一~五 16:30 ET 自动刷新。
- **pierridotite/stonks-dashboard (172⭐)**：Watchlist(crypto+股票+ETF一屏) + 趋势图(1D/7D/30D/90D) + 详情面板(价/涨跌/高低) + 缓存限流(cache.json)。config.json 配 tickers + updateInterval。

**提炼出的 Phase1 看板要素（两者交集）**：① Watchlist 自选列表 ② 指数/板块概览 ③ 多周期趋势图 ④ 点单只→详情面板 ⑤ 抓数→JSON→前端架构平移 ⑥ 缓存+限流避免被 Yahoo 限。

### 2.1 形态
做成 Dashboard 上的一张 **股票卡片**（id: `stock`），遵循卡片系统规范（4文件：data/prompt/rules/generate-display + display.json）。

### 2.2 缩略态
- 自选股列表：代码/名称/现价/涨跌幅（红涨绿跌）
- 几大指数概览：上证/深证/纳指/标普/恒生等

### 2.3 展开态
- **自选股 watchlist**（可增删，A股+美股+ETF+指数混合）
- 点某只 → **K线图**（多周期 1D/1W/1M/3M 切换）
- **技术指标**：均线MA / RSI / MACD / 布林带（用 pandas-ta 算）
- **卡片喵 AI 点评**：用大白话解读"今天啥情况、注意啥"
- 可选：板块/大盘概览

### 2.4 数据
- A股：新浪/东财直连（零延迟五档）
- 美股/全球/ETF/国债/大宗：Yahoo Finance（代理+兜底）
- 历史K线：Yahoo(40年) / AKShare(A股)

### 2.5 Phase 1 TODO
- [ ] P1-1 确认自选股清单（管理员关注哪些标的：A股代码/美股/指数/ETF）
- [ ] P1-2 确认展示粒度（只要列表概览？还是要个股K线+指标？）
- [ ] P1-3 后端：stock 数据抓取脚本（A股直连 + Yahoo代理兜底）
- [ ] P1-4 技术指标计算（接入 pandas-ta）
- [ ] P1-5 stock 卡片 4 文件（data/prompt/rules/generate-display）
- [ ] P1-6 前端：K线图组件（chart 类型，参考已有 data 卡 chart_tabs）
- [ ] P1-7 卡片喵 AI 点评 prompt
- [ ] P1-8 注册到 card-registry
- [ ] P1-9 定时刷新 cron（盘中/收盘后）

---

## 3. Phase 2 — 回测系统（TODO，暂不开工）

> 回测=用历史数据测策略赚不赚钱，不花真钱。

### 设计要点（待细化）
- 回测框架选型：Backtrader（主流全功能） vs backtesting.py（轻量入门）
- 数据源：AKShare(A股) / Yahoo(美股)，历史日K/分钟K
- 策略定义：用户用规则描述（如均线金叉买、死叉卖）
- 报告指标：总收益率、年化、最大回撤、夏普比率、胜率、交易次数
- 形态：网页页面 or 卡片展开（待定）

### Phase 2 TODO
- [ ] P2-1 回测框架选型 + 环境搭建
- [ ] P2-2 历史数据接入(AKShare + Yahoo)
- [ ] P2-3 策略定义方式设计(预设策略 / 自定义规则 / 自然语言→策略)
- [ ] P2-4 回测引擎跑通(单策略单标的)
- [ ] P2-5 回测报告(收益曲线+关键指标)
- [ ] P2-6 前端展示(参数输入→跑回测→看报告)

---

## 4. Phase 3 — 虚拟盘/模拟盘（TODO，暂不开工）

> 虚拟盘=实时行情+假钱交易，实盘演习，不动真金。

### 设计要点（待细化）
- 虚拟账户：初始资金、持仓、可用现金
- 实时行情驱动：策略发信号 → 虚拟买卖 → 更新持仓/盈亏
- 跟踪：每日盈亏曲线、当前持仓、交易记录
- 与回测的区别：回测用历史一次性跑完，虚拟盘用实时数据持续跑

### Phase 3 TODO
- [ ] P3-1 虚拟账户数据结构(资金/持仓/流水)
- [ ] P3-2 实时行情驱动机制(定时拉价→触发策略)
- [ ] P3-3 虚拟撮合(按现价成交，计手续费)
- [ ] P3-4 盈亏统计(持仓市值/浮动盈亏/总收益)
- [ ] P3-5 前端展示(虚拟账户面板+盈亏曲线+交易记录)

---

## 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 DRAFT | 2026-06-08 | 初版，规划 Phase1-4 + 登记 Phase1/2/3 TODO，借鉴开源项目清单 |
