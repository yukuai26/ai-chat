---
entity: ac
descriptor: risk-register
version: "1.0"
status: ACTIVE
created: "2026-05-26"
review_schedule: "每周一检查"
---

# ac-risk-register — 风险评估登记表

> project skill 方法论：只记录 3-5 个**最可能发生、影响最大**的风险。

## 当前风险

| ID | 风险 | 概率 | 影响 | 预警信号 | 缓解措施 | 状态 |
|----|------|------|------|---------|---------|------|
| R1 | **域名丢失** — Tunnel 重启/Cloudflare 轮换导致 trycloudflare 域名变化，用户无法访问 | 高 (60%) | 中 — 需重新告知所有用户 | Tunnel 进程意外退出；curl 返回 5xx/连接拒绝 | ① 配 systemd 自启 ② 买域名绑定 | 🟡监控中 |
| R2 | **Gateway API 不可用** — restart 假死、配置错误导致 API 服务中断 | 中 (30%) | 高 — 所有用户无法使用 | restart 命令无响应；status 显示 RPC probe=fail | ① restart 失败自动回滚 ② 监控脚本告警 | 🟡监控中 |
| R3 | **Token 泄露** — 共享 Token 被未授权人员获取 | 低 (15%) | 高 — 未授权访问 | 未知 IP 大量请求；异常时段访问 | ① 定期轮换 Token ② Cooldown 限制 | 🟢已缓解 |
| R4 | **Cloudflare Tunnel 服务中断** — trycloudflare 服务不稳定或被 block | 低 (10%) | 极高 — 所有访问不可用 | 连续多次 Tunnel 连接失败 | ① 持久化 tunnel 服务 ② 考虑备用隧道方案 | 🟢已缓解 |
| R5 | **Think/推理模式消耗过多 Token** — DeepSeek V4 Pro 推理模式 token 消耗超出预期 | 中 (40%) | 低 — 可随时关闭 | 管理员反馈回复变慢/成本上升 | ① thinkingDefault 可随时改为 off | 🟢已缓解 |

## 已关闭风险

| ID | 风险 | 关闭日期 | 结果 |
|----|------|---------|------|
| R0 | CORS 跨域拦截 — GitHub Pages 跨域请求 Gateway API | 2026-05-26 | 改为 nginx 同源方案彻底解决 |

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| V1.0 | 2026-05-26 | 初始评估，识别 5 个当前风险 |
