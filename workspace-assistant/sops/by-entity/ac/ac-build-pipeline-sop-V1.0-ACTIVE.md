---
entity: ac
descriptor: build-pipeline-sop
version: "1.0"
status: ACTIVE
created: "2026-05-26"
trigger: "HEARTBEAT 每 10 分钟"
---

# ac-build-pipeline-sop — Build喵 流水线标准操作流程

## 架构

```
管理员（飞书）←→ 主 Agent（assistant）
                      │
                      │ HEARTBEAT 每 10 分钟
                      ▼
                 Build喵（build-cat）
                      │
                      │ 读/写
                      ▼
              pipeline-state.json
                      │
                      ▼
              yukuai26/ai-chat（GitHub）
```

## 阶段流转

| 当前阶段 | 操作 | 下一阶段 |
|---------|------|---------|
| idle | 检查 TODO，有则推进 | creating_issues |
| creating_issues | 创建 GitHub Issue | developing |
| developing | 写代码 → push → 开 PR | reviewing |
| reviewing | 自审 PR | merging（通过）/ developing（打回） |
| merging | gh pr merge + close issue | idle |

## 快慢车道

| 情况 | 处理 |
|------|------|
| stage = developing/reviewing/creating_issues 且上次触发 < 30 分钟 | 跳过（等 Build喵 完成） |
| stage = idle 且有新 TODO | 立即触发 |
| stage = idle 且 TODO 为空 | 跳过 |

## 管理员交互

- **添加任务**：管理员告诉主 Agent → 主 Agent 写入 pipeline-state.json 的 todos
- **新建设计文档**：主 Agent 写完后 → 立即写入 pipeline-state.json 的 todos + 更新 designDoc ⚠️
- **修正方向**：管理员告诉主 Agent → 主 Agent 更新 pipeline-state.json
- **查看进度**：管理员问主 Agent → 主 Agent 读取状态汇报

> **教训（2026-05-27）：** 设计文档写了 ≠ Build喵 知道了。Build喵 只看 pipeline-state.json，不看 MEMORY.md。设计文档写完必须立刻写入 todos。

## 版本历史
| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-05-26 | 初始创建 |
