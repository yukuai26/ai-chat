---
entity: ac
descriptor: audit-buildcat-sop
version: "1.0"
status: ACTIVE
trigger: "每天一次（心跳 19:00）"
---

# ac-audit-buildcat-sop — Build喵 工作审计

## 审计频率
每天执行一次（低频心跳），检查 Build喵 当天所有工作。

## 审计清单

### 🔍 1. 启动规范
- [ ] 每次都读了 `ASSISTANT/pipeline-state.json`？（看 logs/ 的 read 记录）
- [ ] 阶段流转正确？（idle→creating_issues→developing→reviewing→merging→idle）

### 📝 2. 留痕规范
- [ ] `memory/YYYY-MM-DD.md` 存在且写了本次执行摘要？
- [ ] `logs/YYYY-MM-DD.jsonl` 存在且记录了每次工具调用？
- [ ] 每次 `read` / `write` / `exec` 都有对应行？

### 🛡️ 3. 操作安全
- [ ] 有没有执行 `rm -rf` 等危险命令？
- [ ] Git 操作有没有用代理重试？（看 exec 日志里是否有 `--proxy` 字样）
- [ ] `gh pr merge` 之前有没有 `gh pr diff` 自审？

### 📊 4. 合规检查
- [ ] 每次只推进一步？还是连跳多步？
- [ ] `pipeline-state.json` 的 stage 字段是否被正确更新？
- [ ] Issue / PR 编号是否一致？（创建时写入，merge 时引用）

### 🐛 5. 错误处理
- [ ] 有 exec 返回错误吗？Build喵 是否正确处理了？
- [ ] 如有错误，是否创建了 `lessons/` 文件？

## 审计流程

```
1. 读 Build喵 的 logs/YYYY-MM-DD.jsonl
2. 读 Build喵 的 memory/YYYY-MM-DD.md
3. 读 ASSISTANT/pipeline-state.json（当前 stage）
4. 逐项核对上述清单
5. 输出审计报告：
   - ✅ 全通过 → "Build喵 审计通过，N 次任务，全合规"
   - ⚠️ 有警告 → 列出问题
   - ❌ 有错误 → @管理员 + 暂停流水线
```

## 发现问题的处理

| 等级 | 标准 | 处理 |
|------|------|------|
| ✅ 合规 | 全部通过 | 无事 |
| ⚠️ 警告 | 漏写日志/命名不规范/少读一个文件但不影响结果 | 记录到 lessons，不暂停 |
| ❌ 违规 | 跳步/危险命令/数据不一致 | 暂停流水线、@管理员 |

暂停方法：pipeline-state.json 的 stage 设为 "paused"，写明原因。

## 审计报告格式

```
📋 Build喵 审计报告（{日期}）
  ✅ 合规项：N
  ⚠️ 警告：M（{详情}）
  ❌ 违规：K（{详情}）
  结论：{通过 / 需改进 / 已暂停}
```

## V1.1 更新（2026-05-26）：信任自报 + 系统补漏

### 审计哲学
- Build喵 自报的日志可信（报了=做了）
- 唯一风险：读了没报（漏记）
- 系统审计（inotify）用作补漏，不是对账

### 审计流程
1. 读 Build喵 自报的 `logs/YYYY-MM-DD.jsonl`
2. 按清单逐项核对（启动/留痕/安全/合规/错误）
3. 用 `sys-audit-*.jsonl` 补漏——发现自报没覆盖但有文件事件的，标注"漏记"
4. 大部分检查以自报为准

### 漏记处理
- 漏 1-2 条 → ⚠️ 警告提示
- 漏了关键步骤（如 pipeline.json 没报读）→ ❌ 暂停
