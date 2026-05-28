# 用户系统设计文档 — Phase 10

> 版本：V1.0 | 状态：ACTIVE | 日期：2026-05-27

---

## 一、概述

从 URL Token 拼接认证 → 账号密码登录 + JWT。两人各自有独立账号，数据自动隔离。

## 二、认证流程

```
打开网页 → 登录页 → 输入用户名+密码 → Flask /login → 返回 JWT
  ↓
JWT 存 localStorage → 所有后续请求带 Authorization: Bearer <jwt>
  ↓
JWT 过期 → 自动跳回登录页
```

## 三、JWT 设计

- 有效期：24 小时
- 「记住我」勾选 → 7 天
- Payload：{user, display_name, partner, exp}
- 密钥：`/home/ubuntu/.openclaw/jwt-secret`（openssl rand 生成）

## 四、用户数据

```json
// user-data/users.json
{
  "admin": {
    "password_hash": "$2b$12$...",
    "display_name": "管理员",
    "partner": "partner",
    "created": "2026-05-27"
  },
  "partner": {
    "password_hash": "$2b$12$...",
    "display_name": "伴侣",
    "partner": "admin",
    "created": "2026-05-27"
  }
}
```

密码 bcrypt 加密，不存明文。管理员邀请制注册（管理员在设置页生成邀请码）。

## 五、后端 API

| 方法 | 端点 | 入参 | 返回 | 认证 |
|------|------|------|------|:--:|
| POST | `/v1/api/auth/login` | {username, password, remember} | {token, user} | — |
| POST | `/v1/api/auth/register` | {username, password, invite_code} | {token, user} | — |
| POST | `/v1/api/auth/logout` | — | {ok} | JWT |
| GET | `/v1/api/auth/me` | — | {user, partner} | JWT |

## 六、认证中间件

所有 `/v1/api/*` 和 `/v1/files/*` 端点统一加认证中间件：

```python
def auth_required(f):
    """从 Authorization header 解析 JWT，注入 request.user"""
    # 1. 检查 Bearer token
    # 2. 验证 JWT 签名 + 过期时间
    # 3. 从 users.json 查用户信息
    # 4. request.user = {username, display_name, partner}
```

Token 认证的旧端点保留过渡期（`/v1/files/*` 兼容旧 Token）。

## 七、数据隔离

认证后，API 自动使用当前用户，无需手动传 `person` 参数：

```
旧: GET /v1/api/daily/todos?person=管理员
新: GET /v1/api/daily/todos   ← 从 JWT 解析 user
```

共享数据（分享板/日历/记账）→ 双方可读写，通过 `partner` 字段判断关系。

## 八、登录页

```
┌──────────────────────────────────┐
│            📊 小助手              │
│    ┌────────────────────────┐    │
│    │ 用户名                  │    │
│    └────────────────────────┘    │
│    ┌────────────────────────┐    │
│    │ 密码                   │    │
│    └────────────────────────┘    │
│    ☐ 记住我（7 天免登录）        │
│    [      登 录       ]          │
│    没有账号？联系管理员           │
└──────────────────────────────────┘
```

- 极简白底，同 Phase 8 配色
- 登录失败 → 抖动 + 提示
- 登录成功 → 跳转主页

## 九、右上角用户信息

登录后在页面右上角显示：
- 头像（默认首字母）+ display_name
- 点击 → 下拉 [个人信息] [邀请伴侣] [退出登录]

## 十、邀请机制

管理员登录后在设置页 → 生成邀请码（一次性） → 发给伴侣 → 注册页输入邀请码 + 设密码。

## 十一、兼容过渡

| 端点 | 过渡期 | 最终 |
|------|:--:|:--:|
| `/v1/files/*` | JWT 或旧 Token 都接受 | 仅 JWT |
| `/v1/chat/*` | Gateway 不变 | 后续加用户映射 |
| 设置页 Token 输入 | 保留 | 移除 |

## 十二、TODO

### 后端

| # | TODO | 状态 |
|---|------|:--:|
| AU1 | pip install bcrypt pyjwt | [x] |
| AU2 | 生成 JWT 密钥（openssl rand -hex 32） | [x] |
| AU3 | 实现注册 API POST `/v1/api/auth/register`（邀请码校验） | [ ] |
| AU4 | 实现登录 API POST `/v1/api/auth/login`（bcrypt 验证 + JWT 签发） | [ ] |
| AU5 | 实现用户信息 API GET `/v1/api/auth/me`（返回用户+伴侣信息） | [ ] |
| AU6 | 实现退出 API POST `/v1/api/auth/logout` | [ ] |
| AU7 | 实现认证中间件 `@auth_required`（JWT 验证 + 注入 request.user） | [ ] |
| AU8 | 更新所有现有 API 端点使用 `@auth_required` + 自动数据隔离 | [x] |
| AU9 | 兼容过渡：/v1/files/* 同时接受 JWT 和旧 Token | [x] |
| AU10 | 邀请码机制（生成/使用/失效） | [x] |

### 前端

| # | TODO | 状态 |
|---|------|:--:|
| AU11 | 登录页（用户名+密码+记住我） | [x] |
| AU12 | 登录逻辑（POST /login → 存 JWT → 跳主页） | [x] |
| AU13 | 所有 fetch 请求自动带 Authorization header | [x] |
| AU14 | JWT 过期检测（401 → 跳登录页） | [x] |
| AU15 | 右上角用户信息 + 退出按钮 | [x] |
| AU16 | 注册页（邀请码 + 用户名 + 密码） | [x] |
| AU17 | 移除旧的 Token 输入框（过渡期后） | [x] |

### nginx

| # | TODO | 状态 |
|---|------|:--:|
| AU18 | nginx 配置更新（静态文件从 /v1/auth 排除 auth） | [x] |

## 十三、进度追踪

| Phase | 内容 | 状态 | TODO |
|:-----:|------|:----:|:--:|
| 10 | 👥 用户系统 | ✅ 已完成 | 18 |
