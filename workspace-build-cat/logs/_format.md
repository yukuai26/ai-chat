# Build喵 工作日志格式 (JSONL)

每行一条 JSON，记录每次工具调用。

## 字段
- time: ISO 时间
- action: read|write|exec|exit
- target: 文件路径（read/write）或命令（exec）
- result: 结果摘要（<100 字）
- stage: 当前阶段
- duration_ms: 耗时

## 示例
```jsonl
{"time":"2026-05-26T19:30:00+08:00","action":"read","target":"ASSISTANT/pipeline-state.json","result":"stage=idle todos=[]","stage":"idle","duration_ms":200}
{"time":"2026-05-26T19:30:30+08:00","action":"write","target":"memory/2026-05-26.md","result":"写入执行摘要","stage":"idle","duration_ms":100}
{"time":"2026-05-26T19:30:35+08:00","action":"exit","target":"","result":"空闲中，等待新任务","stage":"idle","duration_ms":0}
```

## 规则
- 每次 read/write/exec 各一行
- 退出前追加到 logs/YYYY-MM-DD.jsonl
- 不覆盖，纯追加
