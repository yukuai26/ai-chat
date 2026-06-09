---
doc_id: "ac-FINANCE-overview-V1.0-ACTIVE"
title: "📈 金融功能总览 — 新对话接续唯一入口"
version: "V1.0"
status: "ACTIVE"
entity: "ac"
author: "小助手"
created: "2026-06-09"
purpose: "失忆/新对话接续的唯一总入口。一篇看懂：做了哪些、还有哪些没做、整体怎么设计。细节钻进 related 文档。"
related:
  - "ac-stock-MASTER-handoff-V1.0-ACTIVE.md (股票卡片全过程)"
  - "ac-stock-card-maintenance-V1.0-ACTIVE.md (股票卡片维护手册)"
  - "ac-quant-page-design-V1.0-DRAFT.md (量化页面设计+部署记录)"
  - "ac-stock-system-design-V1.0-DRAFT.md (四阶段总规划)"
  - "ac-data-sources-V1.0-ACTIVE.md (数据源清单)"
---

# 📈 金融功能总览（新对话先读这篇）

> **失忆/新对话：读这一篇就懂全部。** 钻细节再进 related 文档。
> 管理员：张三。语言中文。所有操作前确认。

---

## 0. 一句话全局

我们在给 Web Chat 网页做**金融/股票能力**，分两条线，都在推进：
- **线A：股票看板卡片**（Dashboard 上的一张卡）— ✅ Phase1 基本完成，待管理员浏览器实测
- **线B：量化页面**（与卡片/对话同级的新顶级页面，后端用开源 QuantDinger）— 🔨 进行中，已部署后端+搭好接口框架，待前端页面

---

## 1. 大背景（这是什么项目的一部分）

- **AC = Assistant Web Chat 项目**：一个网页版聊天界面 + 每日 Dashboard(插件式卡片系统)。
- 线上真身：`/var/www/chat/`(index.html + fileserver.py)；代码仓库 `~/.openclaw/workspace-build-cat/repo`(远程 github.com/yukuai26/ai-chat, main分支)。
- 卡片系统：每张卡 = `user-data/daily-data/<id>/` 下 5 文件(data/rules/prompt/generate-display→display.json)，卡片喵驱动。
- 金融功能的四阶段路线：**Phase1 数据展示看板** → Phase2 回测 → Phase3 虚拟盘 → Phase4 实盘(不做)。
  - 线A(股票卡) = Phase1。 线B(量化页面/QuantDinger) = 一站式覆盖 Phase2/3(回测+模拟盘)，实盘暂不做。

---

## 2. ✅ 已经做了哪些（DONE）

### 线A — 股票看板卡片（id: stock）
- **后端**(`user-data/daily-data/stock/generate-display.py`, 457行自写)：抓6支(茅台sh600519/腾讯hk00700/苹果us_AAPL/上证sh000001/沪深300ETF sh510300/比特币btc_btcbtcusd)行情+日K+算指标→display.json。
- **数据源全部国内直连零代理**：A股/指数/ETF=新浪 | 港股=新浪+腾讯fqkline | 美股=腾讯usAAPL+新浪US_MinKService(40年) | 加密=新浪btc_+新浪GlobalFutures。
- **技术指标自实现**(纯Python)：MA5/10/20/60 / RSI14 / MACD / 布林带 + 大白话状态。
- **AI点评**：6支各1条(写在 data.json.ai_comment)。
- **前端**(index.html)：renderCardBody 加 stock_detail 渲染，**折线/蜡烛可点击切换 + 周期(1W/1M/3M)切换**；引入 chartjs-chart-financial+luxon；注册到 registry。
- **cron**：系统crontab 盘中15min刷行情 + 每天6:00抓全量K线(refresh-stock.sh)。
- **已 commit+push** main 分支(commit 3117591)。

### 线B — 量化页面（QuantDinger 后端 + 接口框架）
- **选型**：QuantDinger(7565⭐, 开源AI量化平台) 胜 StockSharp(10055⭐, 桌面C#不搭我们Web栈)。理由：Python/Web/Docker同生态 + AI原生 + 自带 Agent Gateway API/MCP。
- **S1 部署**(✅)：装了 Docker(v29.5.3,配代理拉镜像)；QuantDinger 四容器全 healthy：
  - 前端 `8888` / 后端API `127.0.0.1:5000`(/api/agent/v1/*) / pg 5432 / redis 6379
  - 位置 `/home/ubuntu/quantdinger/`；管理员 quantdinger/密码见 `.admin_pw_REMEMBER`；ENABLE_REGISTRATION=false
- **S3 BFF接口框架**(✅)：`/var/www/chat/quant_bff.py` Flask蓝图，转发 `/v1/api/quant/*` → QuantDinger，注入QD token(藏服务器)。
  - 读：overview/strategies/portfolio/indicators/jobs/markets/klines/price
  - 操作：backtests(回测)/create-strategy/quick-trade(强制paper)/kill-switch
  - 安全：实盘拦截(quick-trade强制paper；不开放启动实盘策略)；token未配置优雅503
  - 已验证 /v1/api/quant/health 探测到 QD ok；已 commit+push main(commit ffa63ca)

---

## 3. ⬜ 还有哪些没做（TODO）

### 线A 股票卡
- ⬜ **管理员浏览器实测渲染效果**(服务器无浏览器,我没自测过画面)。tunnel: yoga-findlaw-louisiana-strong.trycloudflare.com
- ⬜ 1D 分时数据(国内免费源缺,目前只有1W/1M/3M)
- ⬜ AI点评自动化(目前手动写,可在 full 刷新后自动触发卡片喵生成)

### 线B 量化页面（关键待办）
- ✅ **S2 agent token 已配**（2026-06-09）：token `yukuai26`，scopes=**B,N,R,W**，**paper_only=true**，无T(实盘)。写入 `/home/ubuntu/quantdinger/agent_token.txt`(chmod 600)。BFF→QD 链路全打通：quant/health token_configured=true，读 overview/strategies/portfolio/markets 全 ok。
- ✅ **8888 tunnel 已挂**：https://floating-reforms-char-cake.trycloudflare.com (临时)。
- ✅ **方案定调**(2026-06-09)：弃 iframe(QD有 X-Frame-Options:SAMEORIGIN 禁嵌 + 同源策略致登录不互通)，改 **方案A(QD完整功能用自带8888网页) + 量化概览卡片(粗略信息+快捷入口) + 对话操作**。
- ✅ **T1 量化概览卡(quant)**：Dashboard 卡，实时拉 BFF 概览(策略/持仓/模拟单/回测数)+「打开完整平台」按钮(走 /quant/url 动态地址)。前端补 note/link section 渲染。已注册。
- ✅ **T3 稳妥地址**：`qd-tunnel.sh` 写地址到 `qd_tunnel_url.txt`；BFF `/quant/url` 动态返回。
- ✅ **T2 对话操作**：卡片喵(card-assistant)通过 BFF 跑回测/查策略/查结果。操作细节写在 quant 卡 prompt.json(BFF_API+BACKTEST_HOWTO+SAFETY_REDLINE)，SOUL 只留指针+安全红线。stock 速查表也从 SOUL 挪回 stock/prompt.json。
- ⚠️ **关键配置**：QD 抓币安行情连 api.binance.com 被墙 → `backend.env` 设 `PROXY_URL=http://172.29.4.175:22222` 走代理(容器内代理连币安 200/0.46s)，重启 backend 生效。否则回测报 "No candle data"。
- ✅ **回测实测通过**：卡片喵跑 BTC双均线金叉(2026 1-6月) → totalReturn -10.78%/maxDD -18.87%/sharpe -0.98/winRate 25%/4笔，并给出专业分析+风险提示。
- ⬜ 可选后续：内置更多策略模板(现只双均线金叉,复杂策略引导去QD网页AI写)；tunnel 做 systemd。
- ⬜ S5 操作类UI(建策略/跑回测/下模拟单)。
- ⬜ 配 LLM key(backend.env)启用 QuantDinger AI 功能(可选)。

---

## 4. 🏗️ 整体设计（架构）

### 线A 股票卡（卡片系统内）
```
国内直连源(新浪/腾讯) → generate-display.py(抓数+自实现指标) → display.json
  → POST /notify-display-update → 前端 stock_detail 渲染(折线/蜡烛切换+周期)
卡片喵: 改 data.json.watchlist 增删自选股; 写 ai_comment 出点评
```

### 线B 量化页面（QuantDinger + BFF）
```
[💬对话] [📊Dashboard] [📈量化(待建)]   ← Web Chat 顶级同级入口
                          │
                  量化页面(待建, index.html 新view; 概览/策略/回测/模拟盘/指标/任务)
                          │ 调 /v1/api/quant/*
                  quant_bff.py (BFF, 已建; 注入QD token; 实盘拦截)
                          │ → http://127.0.0.1:5000/api/agent/v1/*
                  QuantDinger (Docker; 默认paper; 回测+模拟盘+(实盘关闭))
```
**为什么有 BFF**：QD token 不暴露前端 / 复用Web Chat登录 / 数据裁剪 / 审计。
**安全红线**：只做回测+模拟盘，不碰实盘(BFF强制paper+不开放实盘路由；QD agent token给最小scope)。

---

## 5. 🔑 关键坐标/凭据/命令

| 项 | 值 |
|----|----|
| 股票卡运行目录 | `/home/ubuntu/.openclaw/user-data/daily-data/stock/` |
| 股票卡源码副本 | `workspace-assistant/projects/ac/stock-card-src/` |
| 线上网页 | `/var/www/chat/`(index.html/fileserver.py/quant_bff.py) |
| 代码仓库 | `~/.openclaw/workspace-build-cat/repo`(main分支,远程yukuai26/ai-chat) |
| QuantDinger | `/home/ubuntu/quantdinger/` (docker compose) |
| QD管理员 | quantdinger / 见 `/home/ubuntu/quantdinger/.admin_pw_REMEMBER` |
| QD token | `/home/ubuntu/quantdinger/agent_token.txt`(已配,scopes B,N,R,W,paper) |
| QD 8888 tunnel | https://floating-reforms-char-cake.trycloudflare.com (临时,log /tmp/tunnel-quant.log;qd-tunnel.sh重启可换;BFF /quant/url 动态读 qd_tunnel_url.txt) |
| QD 登录 | quantdinger / pgqGEYTQ5GfLdK |
| QD 代理 | backend.env PROXY_URL=http://172.29.4.175:22222 (抓币安行情必需) |
| quant 卡目录 | `/home/ubuntu/.openclaw/user-data/daily-data/quant/`(含 strategy_ema_crossover.py 金叉模板) |
| quant 卡源码副本 | `workspace-assistant/projects/ac/quant-card-src/` |
| Web Chat API token | e0fb40cef753818c92577e3c8fe2af53 |
| fileserver 服务 | `fileserver.service`(监听5050,改后端重启它,**不是**chat-fileserver) |
| tunnel域名 | yoga-findlaw-louisiana-strong.trycloudflare.com(临时,查/tmp/tunnel.log) |

QuantDinger 管理：`cd /home/ubuntu/quantdinger && sudo docker compose ps/logs -f/restart/down/up -d`

---

## 6. ⚠️ 重要坑/教训（别再踩）
1. 共享代理对Yahoo自身限流 → 已全改国内直连(见 lesson-2026-06-08-shared-proxy-rate-limit)。
2. Docker Hub/GHCR 国内直连不通 → dockerd 配了代理(/etc/systemd/system/docker.service.d/http-proxy.conf)。
3. pandas_ta 不兼容 pandas3 → 指标自实现。
4. 5050端口=fileserver.service(不是chat-fileserver,后者僵尸循环待清理)。
5. write工具不能写 /var/www 和 user-data → sudo+python改,workspace留源码副本。
6. 新浪返回GBK → decode('gbk')。
7. backup.sh 曾有分支名bug(push backup应为backup-data),已修；backup-data历史大包代理推不动,管理员说本地备份够用不强求远程。
8. 查git先确认对象(/var/www/chat的.git是老旧副本;真仓库是 workspace-build-cat/repo)。

---

## 7. 新对话第一步该做什么
1. 读本文件 → 懂全局。
2. 看管理员在说线A(股票卡)还是线B(量化)。
3. 若推进线B：先帮管理员能访问 8888(挂tunnel) → 他发token写入 agent_token.txt → 我做 S4 前端页面。
4. 若管理员反馈股票卡渲染问题：查 chartjs-chart-financial/luxon 加载 + _drawStockChart。

---

## 变更记录
| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 | 2026-06-09 | 初版总览。整合线A(股票卡Phase1完成)+线B(QuantDinger部署+BFF接口框架)。做了啥/没做啥/整体设计 全覆盖,供新对话接续 |
