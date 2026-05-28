# 实时同步设计文档 — Phase 13

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

用 WebSocket 实现实时数据同步。一人改了数据，另一人页面秒刷新。

## 二、技术选型

`flask-sock`（简单 WebSocket for Flask），不需要改 nginx。

```bash
pip install flask-sock
```

## 三、工作原理

```
浏览器 A（管理员）          服务器             浏览器 B（伴侣）
      │                       │                    │
      │── POST /todos ──────→ │                    │
      │   (加了购物清单)       │                    │
      │                       │── WS push ────────→│
      │                       │  {event:"todo_changed"}│
      │                       │                    │
      │                       │                    │── GET /todos ──→
      │                       │                    │← 刷新数据 ────
      │                       │                    │  页面更新
```

## 四、WebSocket 事件

```json
// 服务器推给客户端
{"event": "todo_changed", "by": "管理员", "time": "..."}
{"event": "data_changed", "by": "管理员", "field": "weight"}
{"event": "share_received", "from": "管理员", "type": "link"}
{"event": "photo_liked", "by": "管理员", "photo_id": "p1"}
{"event": "news_refreshed", "by": "system"}
{"event": "reminder_fired", "text": "下午3点开会", "person": "管理员"}
```

## 五、后端实现

```python
from flask_sock import Sock

sock = Sock(app)
connections = {}  # {user: [ws1, ws2, ...]}

@sock.route('/v1/ws')
def ws_handler(ws):
    """WebSocket 连接"""
    # 1. 从 URL 参数取 JWT token 验证
    # 2. 解析用户身份
    # 3. 注册连接: connections[user].append(ws)
    # 4. 保持连接，接收客户端心跳
    # 5. 断开时清理

def broadcast(event, exclude_user=None):
    """向所有在线用户广播事件"""
    for user, sockets in connections.items():
        if user != exclude_user:
            for ws in sockets:
                ws.send(json.dumps(event))

def notify_partner(user, event):
    """仅通知伴侣"""
    partner = get_partner(user)
    if partner in connections:
        for ws in connections[partner]:
            ws.send(json.dumps(event))
```

## 六、集成到现有 API

```python
@app.route('/v1/api/daily/todos', methods=['POST'])
@auth_required
def add_todo():
    # ... 原有逻辑 ...
    
    # 新增：通知伴侣
    broadcast({"event": "todo_changed", "by": request.user})
    
    # 新增：通知自己的其他设备
    notify_self_other_devices({"event": "todo_changed"})
```

在以下端点加 broadcast：
- POST/PUT/DELETE `/v1/api/daily/todos`
- POST `/v1/api/daily/data/*`
- POST `/v1/api/daily/share`
- POST `/v1/api/daily/bookmarks`
- POST `/v1/api/daily/notes`
- POST `/v1/api/daily/photos`
- POST `/v1/api/daily/photos/{id}/like`

## 七、前端实现

```javascript
// index.html
let ws;

function connectWS() {
  const token = localStorage.getItem('jwt');
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/v1/ws?token=${token}`);
  
  ws.onopen = () => console.log('WebSocket 已连接');
  
  ws.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
  };
  
  ws.onclose = () => setTimeout(connectWS, 3000); // 断线重连
}

function handleEvent(event) {
  switch(event.event) {
    case 'todo_changed':
      refreshTodoCard();
      showToast(`📋 ${event.by} 更新了 Todo`);
      break;
    case 'data_changed':
      refreshDataCard();
      break;
    case 'share_received':
      refreshShareCard();
      showToast(`📤 ${event.from} 给你分享了东西`, true); // true = 小红点
      break;
    case 'photo_liked':
      refreshPhotoCard();
      break;
  }
}
```

## 八、性能

- WebSocket 连接数：最多 4 个（两人各 2 台设备）
- 每 30 秒心跳 ping/pong
- 断线自动重连（3 秒间隔）
- 消息极短（几十字节 JSON）

## 九、TODO

| # | TODO | 状态 |
|---|------|:--:|
| WS1 | pip install flask-sock | [x] |
| WS2 | 实现 WebSocket 路由 `/v1/ws`（JWT 验证 + 连接管理） | [x] |
| WS3 | 实现 broadcast / notify_partner 函数 | [x] |
| WS4 | 在 Todo API 中集成 broadcast | [x] |
| WS5 | 在数据追踪 API 中集成 broadcast | [x] |
| WS6 | 在分享板 API 中集成 broadcast | [x] |
| WS7 | 在照片点赞 API 中集成 broadcast | [x] |
| WS8 | 前端 WebSocket 连接管理（connect + 断线重连 + 心跳） | [x] |
| WS9 | 前端事件处理（刷新卡片 + Toast 提示 + 小红点） | [x] |

## 十、进度追踪

| Phase | 内容 | 状态 | TODO |
|:-----:|------|:----:|:--:|
| 13 | 🔄 实时同步 | ✅ 完成（后端+前端） | 9 |
