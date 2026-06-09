---
doc_id: "ac-quant-page-design-V1.0-DRAFT"
title: "量化页面设计 — QuantDinger 后端 + 网页顶级页面 + 双向接口"
version: "V1.0"
status: "DRAFT"
entity: "ac"
author: "小助手"
created: "2026-06-09"
purpose: "管理员要求: 用 QuantDinger(7565⭐) 作量化后端,在 Web Chat 加一个与'Dashboard卡片''对话'同等入口级的新顶级页面'量化',展示QuantDinger数据+操作它(读接口+写/操作接口)。本文档基于QuantDinger Agent Gateway API(28端点)出设计,待管理员review。"
related: ["ac-stock-MASTER-handoff-V1.0-ACTIVE.md", "ac-stock-system-design-V1.0-DRAFT.md"]
---

# 量化页面设计 V1.0（DRAFT）

> 需求(管理员 2026-06-09)：
> 1. QuantDinger 作后端跑，产出数据(策略/回测/模拟盘等)
> 2. 网页加一个**与"卡片Dashboard""对话"同等入口级的新顶级页面**(不是塞进卡片)
> 3. 页面要能**展示**这些数据 + **操作**后端(页面操作→传给后端执行)
> 4. 搭好**读接口**(拿数据) + **写/操作接口**(网页操作它)

---

## 一、选型结论：QuantDinger（不选 StockSharp）

| | QuantDinger 7565⭐ | StockSharp 10055⭐ |
|--|---|---|
| 形态 | 自托管 Web 服务(Python/Flask+Vue+Docker) | Windows 桌面 C#/.NET 套件 |
| 与我们栈 | ✅ 同生态(Python/Web/Docker)，易整合 | ❌ 桌面.NET，接不进我们Web栈 |
| AI/Agent | ✅ AI原生 + **Agent Gateway API + MCP** | ❌ 无 |
| 回测/模拟盘/实盘 | ✅ 全有 | ✅ 全有(+HFT,我们用不上) |
| **结论** | **✅ 选它** | 过剩+生态不符,不选 |

> StockSharp 唯一更强是连接器最全+HFT，对个人辅助/模拟需求过剩。

---

## 二、QuantDinger 是什么 / 怎么用

- **自托管量化平台**，闭环：AI研究 → 策略代码 → 回测 → 模拟盘(paper)/实盘 → 监控
- 部署：Docker Compose（后端 Flask + 前端 Vue + PostgreSQL16 + Redis7）
- 对接券商：10+加密所(CCXT) / IBKR / MT5 / Alpaca
- **安全模型**：默认 paper-only(模拟)，实盘要显式开 + 审计日志
- **关键：自带 Agent Gateway API**(`/api/agent/v1/*`, 28端点) + MCP，专为 AI agent 设计(scoped token / paper_only / 审计) → **我们就对接这套 API**

---

## 三、QuantDinger Agent Gateway API（我们要对接的接口，28端点）

### 📖 读接口（拿数据，给页面展示用）
| 端点 | 作用 |
|------|------|
| GET /health | 存活检查 |
| GET /whoami | token的权限/scope/是否paper_only |
| GET /markets, /markets/{m}/symbols | 可查市场/标的搜索 |
| GET /klines, /price | K线/最新价 |
| GET /strategies, /strategies/{id} | 策略列表/详情 |
| GET /indicators, /indicators/{id} | 指标库(含Python源码) |
| GET /indicators/authoring-contract | 指标编写契约+模板 |
| GET /jobs, /jobs/{id}, /jobs/{id}/stream(SSE) | 任务列表/详情/进度流 |
| GET /portfolio/positions | 持仓 |
| GET /portfolio/paper-orders | 模拟盘订单 |
| GET /admin/tokens, /admin/audit | token列表/审计日志(管理员) |

### ✍️ 写/操作接口（页面操作→传后端执行）
| 端点 | 作用 | 风险 |
|------|------|:--:|
| POST /strategies | 创建策略 | 低 |
| PATCH /strategies/{id} | 改策略(status=running 需 T scope) | 中(启动实盘) |
| POST /backtests | 提交回测任务 | 低 |
| POST /indicators, /validate, /link-config | 保存/校验指标 | 低 |
| POST /experiments/regime/detect | 市场状态检测 | 低 |
| POST /experiments/pipeline, /structured-tune, /ai-optimize | 网格/调参/AI优化任务 | 低(耗算力) |
| POST /quick-trade/orders | 下单(**默认paper模拟**) | paper低/实盘高 |
| POST /quick-trade/kill-switch | 取消所有未成交paper订单 | 低 |
| POST /admin/tokens, DELETE /admin/tokens/{id} | 发/吊销token(管理员) | 中 |

> 三阶段映射：**回测**=POST /backtests + GET /jobs。**虚拟盘**=quick-trade(paper) + portfolio/positions + paper-orders。**自动交易**=PATCH strategies status=running(需 T scope，实盘高风险，默认关)。

---

## 四、我们的架构设计

```
┌─ Web Chat 顶级导航(同等入口级) ──────────────────────┐
│  [💬 对话]  [📊 Dashboard]  [📈 量化(新)]  [...]        │
└──────────────────────────────┬───────────────────────┘
                               │ (点"量化"进新页面)
                               ▼
┌─ 量化页面(前端,新 view) ──────────────────────────────┐
│  Tab: 概览 | 策略 | 回测 | 模拟盘 | 指标库 | 任务        │
│   展示: 持仓/盈亏/策略列表/回测报告(收益曲线+回撤)/订单   │
│   操作: 新建策略/跑回测/下模拟单/启停策略/kill-switch    │
└──────────────────────────────┬───────────────────────┘
                               │ 调我们的 BFF 接口(下方)
                               ▼
┌─ 我们的 BFF 中间层(fileserver.py 加路由) ──────────────┐
│  /v1/api/quant/*  ← 网页只跟我们的后端说话(带我们的Token)│
│  转发到 QuantDinger Agent Gateway(带QD的scoped token)   │
│  作用: ①隐藏QD token不暴露给前端 ②鉴权 ③数据裁剪/适配    │
└──────────────────────────────┬───────────────────────┘
                               │ HTTP(QD agent token, scope控制)
                               ▼
┌─ QuantDinger 后端(Docker Compose,自托管) ─────────────┐
│  /api/agent/v1/*  Flask+Postgres+Redis  默认paper-only  │
└──────────────────────────────────────────────────────┘
                   ▲
        卡片喵/我 也能经 MCP 或 BFF 直接驱动 QD
```

### 为什么加 BFF 中间层(不让前端直连QD)
1. **安全**：QD 的 agent token 不暴露到浏览器；前端只持有我们网页自己的 token
2. **鉴权**：复用现有 Web Chat 登录态
3. **适配**：把 QD 的响应裁剪成前端好渲染的结构(类似卡片的 display.json 思路)
4. **审计**：所有操作经我们后端，可记日志

---

## 五、我们要搭的接口（BFF，挂在 fileserver.py）

前缀 `/v1/api/quant/*`，一一对应 QD 能力：

**读：**
- GET /v1/api/quant/overview — 聚合(持仓+盈亏+运行中策略数+最近任务) 给概览页
- GET /v1/api/quant/strategies[/{id}] — 策略列表/详情
- GET /v1/api/quant/backtests/{job_id} — 回测结果(转发 jobs)
- GET /v1/api/quant/portfolio — 持仓 + paper订单
- GET /v1/api/quant/indicators[/{id}] — 指标库
- GET /v1/api/quant/jobs[/{id}] (+ SSE 进度)

**写/操作：**
- POST /v1/api/quant/strategies — 建策略
- POST /v1/api/quant/strategies/{id}/start|stop — 启停(start 实盘需二次确认)
- POST /v1/api/quant/backtests — 跑回测
- POST /v1/api/quant/quick-trade — 下模拟单
- POST /v1/api/quant/kill-switch — 全撤
- POST /v1/api/quant/indicators[/validate] — 存/校验指标

> 实现：fileserver.py 加一个 quant 蓝图(blueprint)，内部用 requests 转发到 QD，注入 QD agent token(存配置,不进前端)。

---

## 六、前端(新顶级页面)

- 在导航/入口加 **📈 量化** 项(与 对话/Dashboard 同级)。需找到 index.html 现有的"页面/视图切换"机制(Dashboard/对话/日历Tab 等),照其模式加一个 view。
- 页面内部用 Tab：概览 / 策略 / 回测 / 模拟盘 / 指标库 / 任务
- 复用现有组件：图表用 Chart.js(回测收益曲线/K线复用股票卡的蜡烛逻辑)、表格、kv
- 操作类按钮 → 调 /v1/api/quant/* → 转 QD。实盘相关操作**强制二次确认 + 默认禁用**。

---

## 七、安全红线（重要）

1. **默认 paper-only**(QD 本身也默认)，实盘下单/启动实盘策略 = 显式开关 + 二次确认 + 告警
2. QD agent token 用**最小 scope**(先只给读 + paper 操作，不给实盘 T scope)
3. token 存服务器配置，绝不下发前端
4. 所有操作经 BFF 记审计

---

## 八、落地步骤(待管理员确认后开工)

1. **S1 部署 QuantDinger**(Docker Compose;评估服务器资源:Postgres+Redis+Flask,需几GB)
2. **S2 发一个 agent token**(最小 scope: 读+paper)，跑通 /health /whoami
3. **S3 fileserver.py 加 quant 蓝图**(BFF 转发，先实现读接口)
4. **S4 前端加"量化"顶级页面 + 概览Tab**(先只读展示)
5. **S5 逐步加操作**(建策略→跑回测→看报告→模拟下单)
6. **S6 实盘**(远期,严格安全开关)

---

## 九、待 review / 待确认
1. QuantDinger 用 **Docker Compose 自托管**(要装 Postgres/Redis,占资源) —— 服务器资源够吗？还是先小规模试？
2. 新页面入口位置：和现有哪些顶级入口并列？(需看 index.html 导航结构)
3. 先做到哪一步？建议 **S1-S4(部署+读接口+只读页面)** 先跑通，操作类后续逐步加
4. 实盘交易：是否明确**暂不做**(只回测+模拟盘)？

---

## 变更记录
| 版本 | 日期 | 说明 |
|------|------|------|
| V1.0 DRAFT | 2026-06-09 | 初稿。基于 QuantDinger Agent Gateway API(28端点实测获取)设计: 新顶级页面+BFF双向接口+安全红线+落地步骤。待管理员review |

---

## 十、部署记录（2026-06-09 凌晨，已完成 S1）

### Docker 环境
- 装了 Docker v29.5.3 + compose v5.1.4(官方apt源), systemctl enable, ubuntu 入 docker 组
- **dockerd 配了代理**拉镜像：`/etc/systemd/system/docker.service.d/http-proxy.conf` → HTTP(S)_PROXY=172.29.4.175:22222（Docker Hub/GHCR 国内直连不通，必须走代理）

### QuantDinger 部署
- 位置：`/home/ubuntu/quantdinger/`（git clone，--depth 1）
- 用 **GHCR 预构建镜像版**(`docker-compose.ghcr.yml` → 复制为 docker-compose.yml)
- 四容器全 healthy：
  - `quantdinger-frontend` → **8888**(0.0.0.0，Web界面)
  - `quantdinger-backend` → **127.0.0.1:5000**(Flask API，含 /api/agent/v1/*)
  - `quantdinger-db` postgres16 → 127.0.0.1:5432
  - `quantdinger-redis` redis7 → 127.0.0.1:6379
- 配置：`backend.env`(SECRET_KEY随机/ADMIN_PASSWORD随机/ENABLE_REGISTRATION=false)
- **管理员账号**：`quantdinger` / 密码见 `/home/ubuntu/quantdinger/.admin_pw_REMEMBER`
- 验证：agent health `{"status":"ok"}`，frontend 200，backend 200

### 容器管理命令
```bash
cd /home/ubuntu/quantdinger
sudo docker compose ps          # 状态
sudo docker compose logs -f backend   # 看日志
sudo docker compose restart     # 重启
sudo docker compose down/up -d  # 停/起
sudo docker compose pull && sudo docker compose up -d  # 更新
```

### 下一步(S2起)
- S2: 登录 8888 前端，发一个 agent token(最小scope:读+paper)，跑通 /whoami
- S3: fileserver.py 加 /v1/api/quant/* BFF 转发(注入QD token)
- S4: Web Chat 加"量化"顶级页面(只读概览)
