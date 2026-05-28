---
entity: sys
descriptor: weekly-maintenance-sop
version: "1.0"
status: ACTIVE
created: "2026-05-26"
trigger: "每周五（或 HEARTBEAT 触发）"
---

# sys-weekly-maintenance-sop — 每周维护标准操作流程

> 参照 librarian-mastery Friday Maintenance 规范

## 检查清单

### 1. 服务健康检查
- [ ] Gateway 运行中：`openclaw gateway status` → RPC probe: ok
- [ ] Tunnel 运行中：`ps aux | grep cloudflared`
- [ ] nginx 运行中：`curl -sI localhost:8080` → 200
- [ ] API 可访问：`curl -X POST /v1/chat/completions` → 200
- [ ] 网页可访问：Tunnel 域名返回 200

### 2. 命名合规检查
- [ ] 所有文件在 canonical 位置（参考 source-of-truth registry）
- [ ] 没有文件使用空格、特殊字符
- [ ] 没有 `FINAL_v2_USE-THIS.md` 之类反模式
- [ ] 没有孤文件（无 name/version/status 的文件）

### 3. 版本一致性
- [ ] 没有两个 ACTIVE 版本的同名文件
- [ ] 版本号连续（V1.0 → V2.0，无跳跃）

### 4. 状态准确性
- [ ] 所有 DRAFT 文件确实在开发中
- [ ] 所有 ACTIVE 文件确实在使用
- [ ] 没有应该归档但未归档的文件

### 5. 交叉引用完整性
- [ ] lesson 文件引用的 SOP 依然存在
- [ ] SOP 引用的配置文件路径正确
- [ ] source-of-truth registry 与实际文件一致

### 6. 记忆蒸馏（如距上次 > 7 天）
- [ ] 回顾本周 `memory/` 日记
- [ ] 重要决策 → 更新 MEMORY.md
- [ ] 新教训 → 创建 lesson 文件
- [ ] 过时信息 → 标记或清理

### 7. 健康评分
```
服务可用性:  /5 (5全正常)
文件合规:    /5 (0反模式)
安全状态:    /5 (Token无异常，配置正确)
总分:        /15
```

### 8. 输出
```
维护报告 → system/audits/audit-report-YYYY-WXX.md
健康分数记录到 system/audits/
异常项通知管理员
```
