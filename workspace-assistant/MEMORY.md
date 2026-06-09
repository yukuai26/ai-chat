# MEMORY.md — 长期记忆

## ⏳ 待跟进（最近，醒来先看）
> 📈 **金融功能(股票卡+量化页面)新对话先读这篇总入口**：`projects/ac/ac-FINANCE-overview-V1.0-ACTIVE.md`（做了啥/没做啥/整体设计全在里面）

- **2026-06-09 股票卡片实测**：昨夜(06-08深夜)做完了 stock 股票看板卡片 Phase1（六支股票:茅台/腾讯/苹果/上证/沪深300ETF/BTC，含蜡烛/折线K线可切换+指标+AI点评，全国内直连零代理）。**管理员说要去实际网站看效果**。
  - 👉 他一提"网站/股票卡片/看了/效果/蜡烛图"等 = 在说这个。
  - 网址：`https://yoga-findlaw-louisiana-strong.trycloudflare.com`（添加"📈 股票看板"卡 → 点开某股 → 看折线/蜡烛切换、周期切换）
  - 服务器无浏览器我没自测过渲染，**正在等他反馈**。若他说"空白/不显示/报错"→ 让他发 F12 控制台报错，重点查 chartjs-chart-financial/luxon 加载 + _drawStockChart。
  - 全部细节见 `projects/ac/ac-stock-MASTER-handoff-V1.0-ACTIVE.md`（失忆先读这篇）。

- **2026-06-09 量化页面工程（进行中）**：决定用 **QuantDinger(7565⭐ 开源AI量化平台)** 作后端，在 Web Chat 加一个**与卡片Dashboard/对话同等入口级的新"量化"页面**，展示+操作它(只读先做)，**只做回测+模拟盘，不碰实盘**。
  - ✅ **S1已完成**：Docker装好(v29.5.3,配了代理拉镜像)，QuantDinger四容器全healthy。前端`8888`、后端API`127.0.0.1:5000`(/api/agent/v1/*)、pg5432、redis6379。管理员账号 quantdinger/密码见 `/home/ubuntu/quantdinger/.admin_pw_REMEMBER`。容器在 `/home/ubuntu/quantdinger/`。
  - ✅ **S3已完成**：`/var/www/chat/quant_bff.py` BFF转发蓝图(/v1/api/quant/* → QuantDinger,注入QD token藏服务器,实盘拦截,token未配置优雅503)。fileserver已注册,验证/quant/health探到QD ok。commit ffa63ca push main。
  - ⬜ **下一步 S2(需管理员参与)**：先给8888挂tunnel让管理员能访问 → 他登录发agent token(最小scope:读+paper) → 写入 `/home/ubuntu/quantdinger/agent_token.txt`，BFF就能拿真数据。
  - ⬜ **S4**：index.html加"量化"顶级页面(与Dashboard/对话同级,只读概览)。
  - 💡 token=调QuantDinger的限权钥匙,只能在8888后台生成,所以需管理员本人发。
  - 👉 他一提"量化/QuantDinger/回测/模拟盘/那个新页面/token" = 在说这个。
  - 完整设计+部署记录见 `projects/ac/ac-quant-page-design-V1.0-DRAFT.md`（失忆先读这篇）。

  - 其它零散待办：股票卡补1D分时 / 股票AI点评自动化。

## 基本信息
- 上线日期：2026-03-01
- 管理员：张三，Feishu ID：ou_fd61aa406c75527901328967376e4a69
- 主要用途：技术开发辅助
- 管理员喜欢的动物：🐼 熊猫
- 管理员最爱吃的食物：🔥 火锅

## 核心教训
1. 不确定就说不知道
2. 犯错先查自己操作记录
3. 断言前先查证
4. 替换前先确认新的能工作
5. 说到做到立即执行
6. 用户反复追问时先承认情绪再解决
7. 中文 Embedding 选 m3e-base（MRR 0.844）
8. 多路召回 > 单路
9. subagent 处理长任务（主 session 不超过3轮 tool call）
10. 新建 pipeline/cron 必须更新文档
11. git commit 包含事实描述
12. 配置文件用追加不用覆写
13. 群聊需要社工检测
14. trash-put 替代 rm
15. 敏感操作先通知管理员
16. **f-string 中写 prompt 示例时，所有花括号 `{xxx}` 必须转义为 `{{xxx}}`**

## Assistant Web Chat 项目

### 架构
```
浏览器 → Cloudflare Tunnel(HTTPS) → nginx:8080
                                       ├── / → 聊天页面 /var/www/chat/index.html
                                       └── /v1/* → Gateway:18789（Token 认证）
```

### 关键配置
- Tunnel 域名：`yoga-findlaw-louisiana-strong.trycloudflare.com`（临时）（临时）
- Gateway 端口：127.0.0.1:18789
- API Token：`e0fb40cef753818c92577e3c8fe2af53`
- nginx 端口：8080，配置 `/etc/nginx/sites-available/chat`
- 网页位置（线上真身/权威源）：`/var/www/chat/index.html` + `/var/www/chat/fileserver.py`
- 代码 git 仓库：`~/.openclaw/workspace-build-cat/repo`（远程 `github.com/yukuai26/ai-chat`，分支 `main`）
- ⚠️ 改完代码后流程：改 `/var/www/chat/` → 同步到 `repo/` → commit + push origin main（走代理重试）
- ⚠️ `~/workspace-assistant/canvas/index.html` 是 310 行废弃旧骨架，已弃用，勿当源文件
- 数据备份仓库（≠代码）：`~/.openclaw/backup-repo`，backup.sh 每天 23:59 推 `backup-data` 分支
- 模型：DeepSeek V4 Pro，推理模式 high
- Agent：assistant

### 当前状态
Phase 1-16 全部完成（文件浏览器、Dashboard、搜索、WebSocket、日历等），流水线空闲

### 🆕 2026-06-07 上下文架构（对齐 DeepSeek 无状态）
- **核心**：模型无状态，上下文每次由前端从 session 文件重建（对齐 DeepSeek/OpenAI）
- 发消息用**随机 user**（`_randomUser()`）→ Gateway 会话层每次空白，消除"塞两遍"
- `loadRecentHistory` **全量带历史 + 150K token 兜底**（非"最近N条"）
- 切模型不丢上下文（历史跟 session 文件走，不跟模型走）
- DeepSeek V4 上下文 = **1M token**（不是 64K！64K 是 V3 旧值）
- 网页对话用两个专用 agent：`webchat-v4`(DeepSeek V4 Pro) / `webchat-opus`(Opus)，共享 workspace `workspace-webchat`
- **持久记忆铁律**：webchat 写 MEMORY.md 前必须先告知用户（跨对话共享），写在 workspace-webchat/SOUL.md
- **文件注入格式**：`<file name mime>内容</file>` XML + 追加 user 消息 + 防注入转义（B3-1）
- Gateway 三层记忆：会话层(按user隔离✅) / workspace记忆层(MEMORY.md共享，曾是串台源) / session-memory hook(只在/new归档)
- commits: `7b9f5b0`(架构) `00a762d`(文件注入)

### 设计文档体系（双向同步铁律）
- `projects/ac/ac-design-baseline-V1.0-ACTIVE.md` — 设计基线（权威，A~K+O 模块）
- `projects/ac/ac-design-code-audit-V2.0-ACTIVE.md` — 设计↔代码审查（2026-06-07，零未完成TODO）
- **铁律**：改代码必须改设计，改设计必须改代码（写在 baseline + SOUL.md + AGENTS.md）

### fileserver 注意
- 由 systemd 管（PID 会变），端口 5050。曾有游离进程占端口的坑，2026-06-07 已清，确保 systemd 接管

### 重要文档
| 文件 | 内容 |
|------|------|
| `projects/ac/ac-project-plan-V1.0-ACTIVE.md` | 完整项目规划（Phase 0.1-0.4） |
| `projects/ac/ac-file-browser-design-V1.0-ACTIVE.md` | 文件浏览器设计（26 TODO） |
| `projects/ac/ac-changes-V1.0-ACTIVE.md` | 变更记录 |

---

## 📈 股票看板卡片（stock，2026-06-09 Phase1 完成）

> ⭐ 权威总文档：`projects/ac/ac-stock-MASTER-handoff-V1.0-ACTIVE.md`（失忆先读这篇）
> 维护手册：`ac-stock-card-maintenance-V1.0-ACTIVE.md`

### 一句话
AC Dashboard 新卡片 `stock`。六支样板(茅台/腾讯/苹果/上证/沪深300ETF/BTC)，完整展示=列表+蜡烛/折线K线(可切换)+全套指标(MA/RSI/MACD/布林)+AI点评。Phase1 后端+前端完成上线，**待浏览器实测渲染**。

### 数据源（全部国内直连，零代理！）
- A股/指数/ETF=新浪hq+新浪日K | 港股=新浪hq+腾讯fqkline | 美股=腾讯usAAPL+新浪US_MinKService(40年) | 加密=新浪btc_+新浪GlobalFutures
- ❌ 弃用 Yahoo+代理(共享代理对Yahoo自身限流,见 lesson-2026-06-08)
- ❌ 东财接口本服务器不通(DNS/防火墙)
- ⬜ 1D分时缺(国内免费源难),只有1W/1M/3M

### 文件
- 运行实体：`user-data/daily-data/stock/`(data/rules/prompt/generate-display/display.json + refresh-stock.sh)
- 源码副本：`workspace-assistant/projects/ac/stock-card-src/`
- 前端：`/var/www/chat/index.html`(stock_detail/stock_chart渲染+蜡烛插件) + `fileserver.py`(registry注册),均有备份
- 指标**自实现**(纯Python,pandas_ta不兼容pandas3弃用)

### 关键
- watchlist 每条 `mkt`(ashare/hk/us/crypto)路由数据源；卡片喵增删=改 data.json.watchlist
- K线一天抓一次缓存,--refresh-kline 强制重抓
- cron已配(系统crontab):盘中15min quote / 每天6:00 full
- 改fileserver.py重启 **fileserver.service**(不是chat-fileserver,后者僵尸)
- 蜡烛涨红跌绿,Chart.js financial插件

---

## 🐱 Build喵 — 已暂停（2026-05-28）

Build喵 自动化流水线已暂停。系统 crontab 和 OpenClaw cron 均已禁用。

---

## 文件浏览器功能设计

> 设计文档：`projects/ac/ac-file-browser-design-V1.0-ACTIVE.md`

### 目标
在 Web 聊天界面加文件管理子页面（浏览 → 编辑 → 拖拽上传）

### 架构变更
```
新增：/v1/files/ → Flask 文件服务 (127.0.0.1:5001)
  ├── GET  /ls?path=xxx     — 列目录
  ├── GET  /read?path=xxx   — 读文件
  ├── POST /write           — 写文件
  ├── POST /upload          — 上传文件
  ├── POST /mkdir           — 创建目录
  └── GET  /health          — 健康检查
```

### 三阶段
- Phase 1：文件浏览（目录树 + 查看器 + 代码高亮）— 18 TODO
- Phase 2：在线编辑（双击编辑 + Ctrl+S 保存）— 6 TODO
- Phase 3：拖拽上传（拖入 + 进度条）— 6 TODO

### 待确认
- 白名单目录：assistant + build-cat 两个 workspaces
- 编辑器：Phase 1 用 textarea，Phase 2 可选 Monaco/CodeMirror
- 上传上限：50MB

---

## 🎨 2026-05-27 设计马拉松 — 完整功能规划

> 详见 `memory/2026-05-27.md`

### Phase 队列（14 个 Phase，~150 TODO）

```
Phase 1-4  ✅ 文件浏览器（已完成）
Phase 5    ✅ 对话历史+文件附件（已完成）
Phase 6    ✅ 每日 Dashboard 骨架+5 张首批卡片（已完成）
Phase 7    ✅ 备份系统（已完成）
Phase 8    ✅ UI 极简美化（已完成）
Phase 9    ✅ 扩展卡片 × 6（已完成）
Phase 10   ✅ 用户系统 JWT 登录（已完成）
Phase 11   ✅ Cmd+K 全局搜索（2026-05-28 完成）
Phase 12   ✅ 手机适配（已完成，手机布局小问题待修）
Phase 13   ✅ WebSocket 实时同步（2026-05-28 完成）
Phase 14   ✅ 日历 Tab 时间中枢（2026-05-28 完成）
Phase 6-16 ✅ 全部完成（pipeline-state.json 确认）
```

### 管理员否掉的

| 内容 | 原因 |
|------|------|
| 💰 分账/记账 | "分账就不用了" |
| 📱 PWA | 等买固定域名后再说 |
| 🏠 家庭库存 / 💸 订阅管家 | 暂不需要 |

### 技术调研结论

- **爬虫**：B站/百度/头条/网易/微博/GitHub 都能爬（免费公开 API），知乎/抖音/小红书极难（需登录+逆向加密）
- **股票**：新浪财经实时盘口（买一/买五）+ AKShare K线，全免费无注册
- **卡片插件体系**：加新卡片 = card-registry.json +1 行 + 新组件 + API，不改现有代码

### 关键架构决策

- 日历是**独立 Tab**（不是卡片），自己不存数据只汇聚
- 用户系统：bcrypt + JWT（24h）+ 邀请制注册
- 手机适配：一套 CSS 断点，不分开做安卓/苹果
- 日历汇聚逻辑：读 todos.json / reminders.json / recipe.json / notes.json / photos.json
- 数据通过 Daily 会话直接操作，不需要中间编排层
- 资讯源设计留在 Phase 6 里，后续随时通过卡片插件加股票/B站/天气等

### 🍽️ Phase 17 — 营养追踪与食谱系统（2026-05-28 设计）

> 设计文档：`projects/ac/ac-nutrition-system-design-V1.0-DRAFT.md`（20 TODO，4 个 Phase）

**需求：** 管理员每周发食谱图片（Mon-Fri）→ 每天 11:00 生成午餐食材配比 → 周末检查催促 → 早/晚餐拍照记录热量 → Dashboard 卡片展示

**数据：** `user-data/nutrition/` 下 recipes/meals/recommendations/profile.json
**Cron：** `0 11 * * 1-5` 午餐推荐 / `0 11 * * 6,0` 周末检查
**卡片：** `nutrition` 注册到 card-registry → 缩略（热量+推荐+周热力图）/ 展开（三餐明细+周汇总）

**待确认：** 单人 vs 双人？推荐推飞书？食谱一张图 vs 五张？是否要晚餐推荐？

---

## 铁律
1. **改完就 commit** — 每次对 git 管理下的文件完成修改后，立即 git add + git commit + git push，用中文写有意义的 commit message。不攒，一次修改一个 commit。

## 关键约束
- 回复语言：中文
- 回复详细程度：详细
- 所有操作前需要确认
- 配置文件用追加不用覆写
- named-files > 裸文件名（librarian-mastery 规范）
- 单一信息源：registry 为权威

## TODO
- [ ] cloudflared 配成 systemd 服务
- [ ] 购买域名绑定
- [ ] Gateway restart 卡住原因排查
