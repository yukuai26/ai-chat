---
entity: sys
descriptor: changelog-2026
version: "1.0"
status: ACTIVE
created: "2026-05-26"
---

# 系统变更日志 — 2026

## 2026-05-26
- [系统] Created 完整工作流体系：WORKFLOW.md、HEARTBEAT.md、MISTAKES.md
- [系统] Installed 3 ClawHub skills: project, dev-project-tracker, librarian-mastery
- [系统] 按 librarian-mastery 建立目录架构 (lessons/, sops/, system/, inbox/)
- [系统] 创建 entity prefix registry, source-of-truth registry
- [ac] 建立 assistant-chat 项目规划 (ac-project-plan)
- [ac] 建立风险评估表 (ac-risk-register)
- [ac] 建立 3 个结构化教训 (lesson-2026-05-26-*)
- [ac] 建立 3 个 SOP (session-startup, web-deploy, weekly-maintenance)
- [ac] 建立系统架构文档 (ac-architecture)
- [ac] 部署 Web Chat MVP (tunnel + nginx + gateway + web)
- [ac] 启用推理模式 thinkingDefault: high
- 3 个教训完成 Failure-to-Rule 流水线
- [sys] 创建 Build喵 子 Agent（build-cat，DeepSeek V4 Pro）
- [sys] 注册 build-cat 到 openclaw.json
- [sys] 更新 HEARTBEAT.md 为 10 分钟 Build喵 心跳流程
- [ac] 创建 ac-build-pipeline-sop
- [sys] 创建 pipeline-state.json 共享状态文件

## 2026-05-26 19:43 — Build喵 完整体系部署

### 新增
- `projects/ac/ac-buildcat-system-design-V1.0-ACTIVE.md` — 完整设计文档
- `sops/by-entity/ac/ac-audit-buildcat-sop-V1.0-ACTIVE.md` — 审计 SOP
- `sops/by-entity/ac/ac-build-pipeline-sop-V1.0-ACTIVE.md` — 流水线 SOP
- `pipeline-state.json` v2.0 — 增加 rules.memory + audit 字段
- Build喵 `logs/` 目录 + `_format.md`
- Build喵 `sops/by-workflow/bc-memory-maintenance-sop-V1.0-ACTIVE.md`

### 变更
- HEARTBEAT.md — 加入每日审计（19:00）+ B方案触发
- WORKFLOW.md — 加入审计体系 + Build喵 流水线
- AGENTS.md — 启用到 7 步（含 pipeline-state.json）
- pipeline-state.json — 唯一共享文件，Build喵 不再读 7 个文件
- openclaw.json — 剔除 build-cat 不支持的字段
- source-of-truth registry — 注册 Build喵 12 项 + 审计 SOP

### 架构决策
- 触发方案：B（主 Agent 塞上下文）> C（改 Gateway）> A（信任 LLM）
- 共享文件：pipeline-state.json 唯一
- 留痕：JSONL（实时）+ memory（摘要）+ lessons（复盘）
- 审计：每日 19:00，违规暂停

## 2026-05-26 19:53 — librarian-mastery 铁律内化

### 变更
- SOUL.md — 新增「记忆铁律」段：多记忆、改了文件就注册、命名规范、单一信息源、每周整理
- WORKFLOW.md — 新增「记忆维护」段：新建文件后四步流程、教训格式、每周维护
- openclaw.json — assistant agent 添加 `skills.entries: [librarian-mastery]`（需 Gateway 重启生效）

### 决策
- librarian-mastery 核心规范直接写进 SOUL.md + WORKFLOW.md，不再依赖 skill 触发
- 每次新建项目文件必须执行 4 步流程：命名检查→注册→变更日志→更新索引

## 2026-05-26 20:09 — Build喵 cron 定时触发

### 新增
- cron job `15909563`：每 10 分钟自动触发 Build喵
  - Agent: build-cat, thinking: high, timeout: 600s
  - 自动 announce 到飞书
  - 不需要主 Agent 手动触发

## 2026-05-26 20:23 — 文件浏览器设计文档

### 新增
- `ac-file-browser-design-V1.0-ACTIVE.md` — Web 文件浏览器整体设计
  - 目标：聊天界面加文件管理子页面（浏览→编辑→拖拽上传）
  - 后端：Flask 文件服务 + nginx 代理 + Cloudflare Tunnel
  - 前端：Tab 切换 + 目录树 + 查看器 + 编辑器
  - 共 26 个 TODO（B1-B10, F1-F16, T1-T8）
  - 三阶段实现：Phase 1 浏览 → Phase 2 编辑 → Phase 3 上传

## 2026-05-26 20:28 — 新增 analyzing_design 阶段 + 记忆固化

### 变更
- Build喵 阶段流转新增 `analyzing_design` 阶段
  - 读设计文档 → 拆 TODO → 创建 Issue → 标记 Phase
  - 实现 Issue 时回写设计文档 TODO 状态（[ ] → [x]）
- Build喵 SOUL.md + AGENTS.md 同步更新
- MEMORY.md 完整重写：归档今日全部设计决策
  - Build喵 体系（阶段/回合/审计）
  - 文件浏览器设计（架构/三阶段/26 TODO）
  - pipeline-state.json 结构
  - 第三方协作约定

| 2026-05-27T01:18:59.838761+08:00 | 新建 | ac-daily-dashboard-design-V1.0-ACTIVE.md | Phase 6 每日 Dashboard 设计文档 |
| 2026-05-27T01:25:01.070531+08:00 | 新建 | ac-backup-design-V1.0-ACTIVE.md | Phase 7 备份系统设计文档 |
| 2026-05-27T01:27:03.463288+08:00 | 新建 | ac-ui-polish-design-V1.0-ACTIVE.md | Phase 8 UI 美化设计文档 |
| 2026-05-27T01:40:23.715009+08:00 | 新建 | ac-extended-cards-design-V1.0-ACTIVE.md | Phase 9 扩展卡片设计文档 |
| 2026-05-27T01:48:07.969090+08:00 | 新建 | ac-user-system-design-V1.0-ACTIVE.md | Phase 10 用户系统设计文档 |
| 2026-05-27T01:48:47.910988+08:00 | 新建 | ac-global-search-design-V1.0-ACTIVE.md | Phase 11 全局搜索设计文档 |
| 2026-05-27T01:58:16.085090+08:00 | 新建 | ac-mobile-adapt-design-V1.0-ACTIVE.md | Phase 12 手机适配设计文档 |
| 2026-05-27T01:58:16.085090+08:00 | 新建 | ac-realtime-sync-design-V1.0-ACTIVE.md | Phase 13 实时同步设计文档 |
| 2026-05-27T02:01:40.537268+08:00 | 新建 | ac-calendar-design-V1.0-ACTIVE.md | Phase 14 日历设计文档 |
| 2026-05-28 | 新建 | ac-nutrition-system-design-V1.0-DRAFT.md | Phase 17 营养追踪与食谱系统设计文档（周食谱/午餐推荐/热量记录/Dashboard卡片） |

## 2026-06-03
- **新增** `lessons/.../lesson-2026-06-03-assert-no-git-repo.md` — 教训:没查全就断言无git仓库(medium/process)
- **新增** `lessons/.../lesson-2026-06-03-stale-tunnel-domain.md` — 教训:日志旧域名当当前域名(low/process)
- **更新** `lessons/_index.md` — 登记上述2条,审查日期→2026-06-03
- **更新** `MEMORY.md` — 修正网页源文件路径:权威源=/var/www/chat/,代码仓库=workspace-build-cat/repo,废弃canvas/index.html
- **修复** Web Chat 登录页JS崩溃:删除index.html主script 2处多余`}`(线上+repo+force push对齐)
- **代码仓库** workspace-build-cat/repo main 以线上为准,commit 15691ec,force push origin main(剔除issue-439营养)

## 2026-06-07
- Web Chat 上下文架构对齐 DeepSeek：随机 user(Gateway无状态) + 全量历史(150K兜底) + 切模型不丢 (commit 7b9f5b0)
- 持久记忆铁律写入 workspace-webchat/SOUL.md
- 设计文档：baseline 新增 O 模块 + 设计↔代码双向同步铁律(三处)；audit V2.0 全量重审(零未完成TODO)
- B3-1 文件注入改 <file> XML 格式 + 防注入 + 截断调大 (commit 00a762d)
- C2-1 白名单补设计对齐(user-files)
- 新增 2 条 lesson：misjudge-token-invalid(误判e0fb40) / misled-by-surface-symptom(诊断被表面401带偏)
- 日记 memory/2026-06-07.md + MEMORY.md 更新
