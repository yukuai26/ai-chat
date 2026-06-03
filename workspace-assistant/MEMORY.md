# MEMORY.md — 长期记忆

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

### 重要文档
| 文件 | 内容 |
|------|------|
| `projects/ac/ac-project-plan-V1.0-ACTIVE.md` | 完整项目规划（Phase 0.1-0.4） |
| `projects/ac/ac-file-browser-design-V1.0-ACTIVE.md` | 文件浏览器设计（26 TODO） |
| `projects/ac/ac-changes-V1.0-ACTIVE.md` | 变更记录 |

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
