---
entity: ac
descriptor: file-browser-design
version: "1.0"
status: ACTIVE
project: assistant-chat
author: 小助手
created: "2026-05-26"
---

# Web 文件浏览器 — 整体设计

## 一、项目现状

### 当前架构
```
浏览器 ──→ Cloudflare Tunnel ──→ nginx (8081)
                                      ├── / → /var/www/chat/index.html
                                      └── /v1/chat/completions → Gateway HTTP API (18789)
```

### 当前能力
- ✅ 聊天界面（暗色主题、Markdown 渲染）
- ✅ Token 认证
- ✅ Agent 选择
- ✅ 通过 Cloudflare Tunnel 外网访问

### 当前限制
- ❌ 无法查看服务器上的文件
- ❌ 无法编辑文件
- ❌ 无法上传文件到服务器

---

## 二、目标架构

```
浏览器 ──→ Cloudflare Tunnel ──→ nginx (8081)
                                      ├── / → /var/www/chat/index.html
                                      ├── /v1/chat/   → Gateway HTTP API (18789)
                                      └── /v1/files/  → 文件服务 (新)
                                                            ├── GET  /ls?path=xxx
                                                            ├── GET  /read?path=xxx
                                                            ├── POST /write
                                                            └── POST /upload
```

**新增组件：**
- **文件服务**：一个轻量 Python HTTP 服务（Flask），提供文件 CRUD API
- **安全模型**：Token 认证 + 路径白名单 + workspace 沙箱

### 前端页面结构

```
┌──────────────────────────────────────────┐
│  [💬 聊天]  [📁 文件管理器]              │  ← 顶部 Tab
├──────────────────────────────────────────┤
│                                          │
│  Tab=聊天 → 当前聊天界面                  │
│                                          │
│  Tab=文件 → ┌──────────┬──────────────┐  │
│            │ 目录树     │  文件内容     │  │
│            │           │              │  │
│            │ 📂 memory │  # SOUL.md   │  │
│            │ 📂 projects│              │  │
│            │ 📂 sops   │  可编辑+保存  │  │
│            │ 📄 SOUL.md│  可拖拽上传   │  │
│            │ 📄 AGENTS │              │  │
│            └──────────┴──────────────┘  │
└──────────────────────────────────────────┘
```

---

## 三、后端设计

### 3.1 文件服务 API

| 端点 | 方法 | 参数 | 返回 | 说明 |
|------|------|------|------|------|
| `/v1/files/ls` | GET | `path` (目录路径) | `{files: [{name, type, size, modified}]}` | 列出目录 |
| `/v1/files/read` | GET | `path` (文件路径) | `{content, name, size}` | 读取文件 |
| `/v1/files/write` | POST | `path, content` | `{ok: true}` | 写入文件 |
| `/v1/files/upload` | POST | `path, file` (multipart) | `{ok: true, name, size}` | 上传文件 |
| `/v1/files/health` | GET | — | `{ok: true, roots}` | 健康检查 |
| `/v1/files/mkdir` | POST | `path` | `{ok: true}` | 创建目录 |

### 3.2 安全模型

```
✅ Token 认证（和聊天 API 同一个 Token）
✅ 路径沙箱：
   - 只允许访问 /home/ubuntu/.openclaw/workspace-assistant/
   - 只允许访问 /home/ubuntu/.openclaw/workspace-build-cat/
   - 拒绝 .. 路径穿越
   - 拒绝绝对路径绕过
✅ 请求频率限制（简易）
❌ 不记录文件变更日志（Phase 2）
```

### 3.3 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| Web 框架 | Flask | 轻量、Python 生态 |
| 认证 | Bearer Token | 和聊天 API 一致 |
| 运行方式 | systemd 服务 | 开机启动、自动重启 |
| 端口 | 本地 127.0.0.1:5001 | 仅 nginx 反向代理访问 |

### 3.4 nginx 配置变更

```nginx
# 新增文件服务代理
location /v1/files/ {
    proxy_pass http://127.0.0.1:5001/v1/files/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    # 限制上传大小
    client_max_body_size 50m;
}
```

---

## 四、前端设计

### 4.1 功能清单

#### Phase 1 — 文件浏览（只读）
- [x] 顶部 Tab 切换（💬 聊天 / 📁 文件）
- [ ] 左侧目录树组件
  - [ ] 展开/折叠文件夹
  - [ ] 文件类型图标（📄 .md, 🐍 .py, 📋 .json 等）
  - [ ] 当前选中文件高亮
- [ ] 右侧文件查看器
  - [ ] 文本文件内容展示
  - [ ] 代码语法高亮（highlight.js）
  - [ ] 行号显示
  - [ ] Markdown 文件预览渲染
- [ ] 面包屑导航（当前路径）
- [ ] 加载状态 + 错误提示
- [ ] 响应式布局（移动端可用）

#### Phase 2 — 文件编辑
- [ ] 查看器内嵌编辑器（textarea → 双击进入编辑模式）
- [ ] Monaco Editor / CodeMirror 集成（可选，优化体验）
- [ ] Ctrl+S 保存、保存按钮
- [ ] 保存成功/失败提示
- [ ] 未保存修改警告（切换文件前提示）

#### Phase 3 — 拖拽上传
- [ ] 拖拽区域（目录树上方的上传区）
- [ ] 拖入高亮效果
- [ ] 上传进度条
- [ ] 上传成功 → 刷新目录树
- [ ] 同名文件确认覆盖

### 4.2 前端组件树

```
App
├── TabBar (💬 聊天 | 📁 文件)
├── ChatView (现有聊天界面)
└── FileBrowserView (新增)
    ├── Breadcrumb (路径导航)
    ├── FileTree (左侧目录)
    │   ├── TreeItem (文件夹)
    │   │   └── TreeItem[] (递归)
    │   └── TreeItem (文件)
    ├── UploadDropZone (拖拽区，Phase 3)
    └── FileViewer (右侧内容区)
        ├── FileToolbar (编辑/保存/取消按钮)
        ├── CodeViewer (代码模式：带高亮+行号)
        └── MarkdownViewer (Markdown 预览模式)
```

### 4.3 数据流

```
FileBrowserView
  ├── 挂载时 → GET /v1/files/ls?path=/ → 渲染目录树
  ├── 点击文件 → GET /v1/files/read?path=... → 渲染查看器
  ├── 编辑保存 → POST /v1/files/write {path, content} → 刷新
  └── 拖拽上传 → POST /v1/files/upload {path, file} → 刷新目录树
```

### 4.4 API 请求封装

所有文件 API 请求携带相同的 Bearer Token（和聊天 API 一致）：

```javascript
const headers = {
  'Authorization': 'Bearer ' + token,
  'Content-Type': 'application/json',
};

async function apiLs(path) {
  const resp = await fetch(apiUrl + '/v1/files/ls?path=' + encodeURIComponent(path), { headers });
  return resp.json();
}
```

---

## 五、部署计划

### 5.1 文件结构

```
部署到服务器：
  /var/www/chat/index.html          ← 更新（新增文件浏览器 Tab）
  /var/www/chat/fileserver.py       ← 新增（Flask 文件服务）
  /var/www/chat/fileserver.service  ← 新增（systemd 单元）

GitHub 仓库（yukuai26/ai-chat）：
  index.html                        ← 更新
  fileserver.py                     ← 新增
  deploy/                           ← 新增部署配置
    fileserver.service
    nginx-filebrowser.conf
```

### 5.2 部署步骤

1. 更新 `index.html`（前端新功能）
2. 创建 `fileserver.py`（后端文件服务）
3. 配置 systemd 服务（`fileserver.service`）
4. 配置 nginx（添加 `/v1/files/` 代理）
5. 安装依赖（Flask）
6. 启动文件服务 + 重载 nginx
7. 验证：浏览器访问文件 API

---

## 六、TODO 清单

> **说明**：以下 TODO 由 Build喵 逐个拆成 GitHub Issue 并实现。
> 每完成一项，Build喵 更新本文档状态（[ ] → [x]）。

### 后端 TODO

| # | TODO | Phase | 状态 |
|---|------|:-----:|:----:|
| B1 | 创建 `fileserver.py`：Flask 文件服务，实现 GET /ls、GET /read、POST /write、POST /upload | 1 | [ ] |
| B2 | 实现路径安全校验：白名单 + 防路径穿越 | 1 | [ ] |
| B3 | 实现 Token 认证中间件（从 Gateway 配置文件读取 Token） | 1 | [ ] |
| B4 | 创建 systemd 服务文件（`fileserver.service`） | 1 | [x] |
| B5 | 更新 nginx 配置：添加 `/v1/files/` 反向代理 + 上传大小限制 | 1 | [x] |
| B6 | 安装依赖并启动文件服务 | 1 | [x] |
| B7 | 实现 POST /mkdir（创建目录） | 1 | [x] |
| B8 | 文件服务健康检查端点 + 自动重启 | 1 | [x] |
| B9 | API 错误处理标准化（统一 JSON 错误格式） | 2 | [x] |
| B10 | 大型文件分片上传支持（可选） | 3 | [ ] (⏭️ 跳过，50MB 单文件已满足) |

### 前端 TODO

| # | TODO | Phase | 状态 |
|---|------|:-----:|:----:|
| F1 | 顶部 Tab 导航组件（聊天 / 文件管理器） | 1 | [x] |
| F2 | 左侧目录树组件：递归渲染、展开/折叠、类型图标 | 1 | [x] |
| F3 | 目录树 API 对接（GET /ls 加载子节点） | 1 | [x] |
| F4 | 右侧文件查看器：文本内容 + highlight.js 语法高亮 | 1 | [x] |
| F5 | 查看器 API 对接（GET /read 加载文件内容） | 1 | [x] |
| F6 | 面包屑导航组件 | 1 | [x] |
| F7 | Markdown 文件预览模式（.md 文件渲染后展示） | 1 | [x] |
| F8 | 加载中状态 + 错误 Toast 提示 | 1 | [x] |
| F9 | 响应式布局（移动端目录树缩进/弹出） | 1 | [x] |
| F10 | 文件编辑模式：双击切换编辑、Ctrl+S 保存 | 2 | [x] |
| F11 | 编辑 API 对接（POST /write 保存文件） | 2 | [x] |
| F12 | 未保存修改警告（切换文件前弹窗） | 2 | [x] |
| F13 | 拖拽上传区域组件（目录树上方的 drop zone） | 3 | [x] |
| F14 | 拖拽上传 API 对接（POST /upload + 进度条） | 3 | [x] |
| F15 | 上传后自动刷新目录树 + 成功提示 | 3 | [x] |
| F16 | 新建文件/文件夹按钮（右键菜单或目录树顶部按钮） | 2 | [x] |

### 集成与测试 TODO

| # | TODO | Phase | 状态 |
|---|------|:-----:|:----:|
| T1 | 端到端测试：浏览目录树 → 点击文件 → 查看内容 | 1 | [ ] |
| T2 | 端到端测试：编辑文件 → 保存 → 重新打开验证 | 2 | [ ] |
| T3 | 端到端测试：拖拽上传 → 目录树刷新 → 查看文件 | 3 | [ ] |
| T4 | 安全测试：路径穿越攻击测试（../ 等） | 1 | [ ] |
| T5 | Token 认证测试：无 Token、错误 Token、正确 Token | 1 | [ ] |
| T6 | 大文件上传测试 + 大小限制测试 | 3 | [ ] |
| T7 | 浏览器兼容测试（Chrome, Safari, Firefox） | 1 | [ ] |
| T8 | 移动端响应式测试 | 1 | [ ] |

---

## 七、进度追踪

| Phase | 内容 | 状态 | 开始 | 完成 |
|:-----:|------|:----:|------|------|
| 1 | 文件浏览（只读） | ✅ 完成 | 2026-05-26 | 2026-05-26 |
| 2 | 文件编辑 | ✅ 完成 | 2026-05-26 | 2026-05-26 |
| 3 | 拖拽上传 | ✅ 完成 | 2026-05-27 | 2026-05-27 |
| 4 | 图片预览 + 文件下载 | ✅ 完成 | 2026-05-27 | 2026-05-27 |

状态图例：⬚ 待开始 → ⏳ 进行中 → ✅ 完成

---

## 八、待确认事项

| # | 问题 | 默认答案 |
|---|------|----------|
| Q1 | workspace 白名单包含哪些目录？ | assistant + build-cat 两个 workspaces |
| Q2 | 是否需要编辑器（Monaco/CodeMirror）？ | Phase 1 用 textarea，Phase 2 可选升级 |
| Q3 | 上传文件大小上限？ | 50MB |
| Q4 | 文件服务端口？ | 5001（本地 only） |
| Q5 | 是否需要只读模式（给普通用户）？ | 当前所有人 Token 相同，暂不区分 |

> 管理员确认后，将本文档路径注册到 pipeline-state.json，Build喵 开始拆 Issue。


---

## 九、Phase 4 — 图片预览 + 文件下载

### 9.1 现状
- `/v1/files/read` 已通过 `send_file` 返回正确的 MIME，前端只处理了文本类
- 没有下载按钮

### 9.2 目标
- 图片文件直接在浏览器预览（`<img>` 标签）
- 所有文件支持一键下载

### 9.3 TODO

#### 后端

| # | TODO | 状态 |
|---|------|:----:|
| B11 | GET /download 端点：返回文件 + Content-Disposition 头（触发浏览器下载） | [x] |
| B12 | /read 端点支持 Range 请求（大文件流式读取） | [x] |

#### 前端

| # | TODO | 状态 |
|---|------|:----:|
| F17 | 图片预览组件：根据 MIME/扩展名判断，显示 `<img>` | [x] |
| F18 | 下载按钮：文件列表/查看器顶部添加下载图标 | [x] |
| F19 | 下载 API 对接：点击触发文件下载 | [x] |

### 9.4 进度追踪

| 项目 | Phase | 状态 |
|------|:-----:|:----:|
| 图片预览 + 下载 | 4 | ✅ 完成 |


---

## 十、Phase 5 — 对话历史 + 文件附件

### 10.1 目标

1. 每次对话存为一个 Session，左侧显示列表
2. 新打开网页可新建对话或继续旧对话
3. 发消息时可多选文件作为附件，子 Agent 基于文件和指令执行任务

### 10.2 架构

```
Flask 新增端点：
  POST   /v1/sessions/new          创建 Session
  GET    /v1/sessions/list         列出所有 Session
  GET    /v1/sessions/{id}         获取 Session 消息历史
  POST   /v1/sessions/{id}/chat    发送消息（调 Gateway）
  DELETE /v1/sessions/{id}         删除 Session

存储：/home/ubuntu/.openclaw/user-sessions/{id}.json
      /home/ubuntu/.openclaw/user-files/  (用户上传/生成的文件)

前端布局：
  ┌────────────┬──────────────────────────┐
  │ 📋 对话列表 │  💬 当前对话              │
  │ [+新建]    │  消息区域                  │
  │ 昨天       │  文件选择器                │
  │ ├→ 分析财报 │  输入框 + 发送按钮          │
  │ └→ 写周报  │                           │
  └────────────┴──────────────────────────┘
```

### 10.3 Session 数据格式

```json
{
  "id": "sess_20260527_003000",
  "title": "分析财报",
  "created": "2026-05-27T00:30:00+08:00",
  "updated": "2026-05-27T00:35:00+08:00",
  "messages": [
    {
      "role": "user",
      "content": "帮我分析这个文档",
      "files": ["/home/ubuntu/.openclaw/user-files/report.docx"],
      "time": "2026-05-27T00:30:00+08:00"
    },
    {
      "role": "assistant",
      "content": "好的，分析如下...",
      "time": "2026-05-27T00:30:15+08:00"
    }
  ]
}
```

### 10.4 数据流 — 文件附件 + 子 Agent

```
用户选择文件 + 写指令 → 点击发送
  ↓
Flask /v1/sessions/{id}/chat
  ├── 读取选中的文件内容（文字提取）
  ├── 拼装消息：指令 + 文件内容摘要 + 文件路径
  ├── 调用 Gateway /v1/chat/completions
  │     messages: [
  │       {role: "system", content: "用户选择了以下文件: report.docx (内容摘要...)"},
  │       {role: "user", content: "帮我分析这个文档"}
  │     ]
  ├── 等待 Gateway 返回（流式）
  └── 保存完整对话到 session 文件
  ↓
前端收到回复 → 渲染
```

### 10.5 子 Agent 触发规则

当消息中包含文件且用户要求分析/处理时：
- 主 Agent（我）收到系统消息 "用户选择了文件 X, Y"
- 主 Agent 判断是否需要 spawn doc-reader 子 Agent
- 子 Agent 处理完 → 结果返回 → 我整合 → 回复用户

### 10.6 TODO

#### 后端 — Session 管理

| # | TODO | 状态 |
|---|------|:----:|
| B13 | 实现 POST /v1/sessions/new（创建 Session，自动生成标题） | [x] |
| B14 | 实现 GET /v1/sessions/list（返回所有 Session 列表，按更新时间排序） | [x] |
| B15 | 实现 GET /v1/sessions/{id}（返回完整消息历史） | [x] |
| B16 | 实现 POST /v1/sessions/{id}/chat（接收消息 → 拼装上下文 → 调 Gateway → 保存回复） | [x] |
| B17 | 实现 DELETE /v1/sessions/{id}（删除 Session） | [x] |

#### 后端 — 文件附件处理

| # | TODO | 状态 |
|---|------|:----:|
| B18 | 消息中文件附件的解析：自动提取文本内容（txt/md/code）或标注文件类型+路径 | [x] |
| B19 | 文件附件的 MIME 识别 + 大小检查（>10MB 提示走文件浏览器） | [x] |

#### 后端 — 部署

| # | TODO | 状态 |
|---|------|:----:|
| B20 | 更新 nginx 配置：添加 /v1/sessions/ 代理 | [x] |
| B21 | 创建用户文件目录 /home/ubuntu/.openclaw/user-files/ + 用户 session 目录 | [x] |

#### 前端 — 对话列表

| # | TODO | 状态 |
|---|------|:----:|
| F20 | 左侧对话列表 Sidebar 组件（时间分组：今天/昨天/更早） | [x] |
| F21 | 对话列表 API 对接（GET /v1/sessions/list） | [x] |
| F22 | 新建对话按钮（POST /v1/sessions/new → 刷新列表 → 跳转） | [x] |
| F23 | 点击对话项 → 加载历史消息（GET /v1/sessions/{id}） | [x] |
| F24 | 删除对话功能（长按/右键 → DELETE /v1/sessions/{id}） | [x] |

#### 前端 — 消息区域

| # | TODO | 状态 |
|---|------|:----:|
| F25 | 消息渲染组件重构（区分 user/assistant 角色、时间戳、附件标签） | [x] |
| F26 | 流式消息展示（SSE 或分块加载，打字机效果） | [x] |
| F27 | 消息输入框 + 发送按钮 + Enter 发送 | [x] |

#### 前端 — 文件选择器

| # | TODO | 状态 |
|---|------|:----:|
| F28 | 📎 文件选择按钮（悬浮在输入框左侧） | [x] |
| F29 | 文件选择弹窗组件（从 user-files 目录读取，支持多选） | [x] |
| F30 | 选中文件标签展示（在输入框上方显示，支持删除单个） | [x] |
| F31 | 文件选择器搜索/过滤（按文件名筛选） | [x] |

#### 前端 — 布局适配

| # | TODO | 状态 |
|---|------|:----:|
| F32 | 三栏布局：对话列表 + 消息区 + 设置面板（响应式） | [x] |
| F33 | 侧边栏折叠/展开（移动端适配） | [x] |

### 10.7 进度追踪

| 项目 | Phase | 状态 |
|------|:-----:|:----:|
| 对话历史 + 文件附件 | 5 | ✅ 已完成 |
