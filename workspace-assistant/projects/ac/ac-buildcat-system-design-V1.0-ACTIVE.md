---
entity: ac
descriptor: buildcat-system-design
version: "1.0"
status: ACTIVE
date: "2026-05-26"
---

# ac-buildcat-system-design — Build喵 完整流水线体系设计

## 1. 架构概览

```
管理员 ──对话──→ 主 Agent (assistant: DeepSeek V4 Pro)
                   │
           HEARTBEAT 每10分钟（带上下文）
                   │
                   ↓
              Build喵 (build-cat: DeepSeek V4 Pro)
                   │
           唯一共享：pipeline-state.json
                   │
              yukuai26/ai-chat (GitHub)
```

## 2. 工作空间

| Agent | Workspace | 关键文件 |
|-------|-----------|---------|
| 主 Agent | `/home/ubuntu/.openclaw/workspace-assistant` | pipeline-state.json, HEARTBEAT.md, WORKFLOW.md, MEMORY.md |
| Build喵 | `/home/ubuntu/.openclaw/workspace-build-cat` | SOUL.md, AGENTS.md, logs/, memory/, lessons/, sops/ |

## 3. 唯一共享：pipeline-state.json

### 路径
`/home/ubuntu/.openclaw/workspace-assistant/pipeline-state.json`

### 结构
```json
{
  "project": { "name", "repo", "description" },
  "stage": "idle|creating_issues|developing|reviewing|merging|paused",
  "current": { "issue", "pr" },
  "todos": [],
  "completed": [],
  "rules": {
    "git": "...",
    "code": [...],      // f-string转义、原代码修改、自审清单
    "safety": [...],    // trash>rm、配置追加
    "execution": [...],  // 一步退出、更新pipeline、写日志
    "memory": [...]     // JSONL日志、摘要、SOP引用、命名规范
  },
  "lessons_recent": [...],
  "audit": {
    "enabled": true,
    "frequency": "daily 19:00",
    "sop": "sops/by-entity/ac/ac-audit-buildcat-sop-V1.0-ACTIVE.md",
    "on_violation": "stage='paused', @管理员"
  }
}
```

### 谁写谁读
- **主 Agent 写**：添加 todos、更新 rules/lessons_recent
- **Build喵 读**：启动时读取，做完后更新 stage/current/todos/completed
- **审计读**：主 Agent 每日 19:00 读取 Build喵 的 logs/ 对账

## 4. Build喵 启动流程

```
1. 读 pipeline-state.json
2. 按 stage 执行 1 步
3. 每次工具调用 → 写 logs/YYYY-MM-DD.jsonl
4. 退出前 → 写 memory/YYYY-MM-DD.md
5. 更新 pipeline-state.json
6. 回复结果
```

## 5. 阶段流转

```
idle ──(有 todos)──→ creating_issues ──→ developing ──→ reviewing
  ↑                                                         │
  └────── merging ←──(✅ 自审全过)──────│
              │
              └──(❌ 打回)──→ developing
```

### 各阶段操作
| 阶段 | 操作 |
|------|------|
| idle | todos 空=空闲；有→下一阶段 |
| creating_issues | `gh issue create` |
| developing | git clone→branch→编码→自审→commit→push→`gh pr create` |
| reviewing | `gh pr diff` 自审（改动范围/代码质量/安全/兼容） |
| merging | `gh pr merge --squash` → `gh issue close` → stage=idle |

## 6. 留痕体系（三层）

| 层 | 文件 | 内容 | 频率 |
|------|------|------|------|
| 📏 实时 | `logs/YYYY-MM-DD.jsonl` | 每次工具调用（read/write/exec）一行 JSONL | 每次 |
| 📝 摘要 | `memory/YYYY-MM-DD.md` | 人类可读执行总结 | 退出前 |
| 📚 教训 | `lessons/by-date/YYYY/YYYY-QX/lesson-YYYY-MM-DD-{描述}.md` | Failure-to-Rule 详细复盘 | 犯错时 |

### JSONL 格式
```jsonl
{"time":"ISO","action":"read|write|exec","target":"文件/命令","result":"摘要","stage":"当前","duration_ms":0}
```

## 7. 记忆维护

### SOP
`sops/by-workflow/bc-memory-maintenance-sop-V1.0-ACTIVE.md`（Build喵 workspace）

### 规范
- librarian-mastery 全套
- 命名：`bc-{描述}-V{x.y}-{STATUS}.md`
- 状态：DRAFT→ACTIVE→ARCHIVED
- 新增文件必须更新对应 `_index.md`

## 8. 审计体系

### SOP
`sops/by-entity/ac/ac-audit-buildcat-sop-V1.0-ACTIVE.md`（主 Agent workspace）

### 流程
1. 主 Agent 每日 19:00 读 Build喵 `logs/` + `memory/`
2. 核对：启动规范 / 留痕规范 / 操作安全 / 合规 / 错误处理
3. 出审计报告
4. 违规 → `stage: "paused"` + `@管理员`

### 违规等级
| 等级 | 标准 | 处理 |
|------|------|------|
| ✅ 合规 | 全通过 | 无事 |
| ⚠️ 警告 | 漏写日志/命名不规范 | 记录 lessons，不暂停 |
| ❌ 违规 | 跳步/危险命令/数据不一致 | 暂停 + @管理员 |

## 9. 触发方式

### 常规触发（cron job 全自动）
```bash
# cron job ID: 15909563
# 已配置自动触发，不需要手动运行

# 如需手动触发：
openclaw agent --agent build-cat --deliver \
  --reply-to "user:ou_fd61aa406c75527901328967376e4a69" \
  --timeout 600 \
  --message "执行流水线。先读 pipeline-state.json，按 stage 推进一步。"
```

### 手动触发（管理员要求）
同上述命令，可追加 `--message` 给具体指令。

## 10. 模型配置
- Build喵：deepseek/deepseek-v4-pro（在 openclaw.json 注册）
- 超时：600 秒（10 分钟）

## 11. 关键设计决策

| 决策 | 理由 |
|------|------|
| 单 Agent 串行推进 | 避免并行冲突，一次一步可控 |
| pipeline-state.json 唯一共享 | 避免 Build喵 读 7 个文件不靠谱 |
| B 方案：触发时塞上下文 | 80% 可靠 > 信任 LLM 自主 60% |
| 审计 + 暂停机制 | 自动发现问题比事后补救有效 |
| librarian-mastery 全盘贯彻 | 统一命名和归档标准 |
| 主 Agent 写 todos / Build喵 执行 | 设计决策归主 Agent，执行归 Build喵 |

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-05-26 | 初始设计文档 |
