# API 接口文档

本项目提供 **50+ 个接口**，分为**用户端**（`/api/*`）和**后台**（`/admin/api/*`）。

## 通用约定

### 响应格式

```json
{
  "code": 0,
  "msg": "ok",
  "data": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| code | int | 0 = 成功，其他 = 失败 |
| msg  | string | 提示信息 |
| data | any | 业务数据 |

### 错误码

| code | 含义 |
|---|---|
| 0   | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

### 认证方式

| 类型 | 传递方式 | 用途 |
|---|---|---|
| 会员 | `Authorization: Bearer <token>` | 用户端接口 |
| 管理员 | `Cookie: admin_token=...` | 后台接口 |

---

## 一、用户认证

### POST /api/auth/register

注册新用户。

**请求体**：
```json
{
  "username": "testuser",
  "password": "123456",
  "nickname": "测试员"
}
```

**响应**：
```json
{
  "code": 0,
  "msg": "注册成功",
  "data": {
    "member": {
      "uid": "uuid",
      "username": "testuser",
      "nickname": "测试员",
      "points": 10,
      "level": "新客"
    },
    "token": "eyJhbGci..."
  }
}
```

### POST /api/auth/login

登录，参数与响应同注册。

### GET /api/auth/me

查询当前用户。

**请求头**：`Authorization: Bearer <token>`

**响应**：
```json
{
  "code": 0,
  "data": {
    "uid": "uuid",
    "username": "testuser",
    "points": 58,
    "level": "新客"
  }
}
```

---

## 二、AI 对话

### POST /api/chat

AI 对话（非流式）。

**请求体**：
```json
{ "message": "来两份牛肉泡馍", "table_no": "外带" }
```

**响应（点菜成功）**：
```json
{
  "code": 0,
  "data": {
    "reply": "好的，已为您下单（订单号 TSX...）",
    "intent": "place_order",
    "order": {
      "id": "TSX1789743112659",
      "items": [{"name": "牛肉泡馍(小份)", "qty": 2, "subtotal": 48}],
      "total": 48,
      "status": "pending",
      "uid": "uuid"
    }
  }
}
```

### POST /api/chat/stream

AI 对话（SSE 流式）。

**请求体**：`{ "message": "..." }`

**响应**：`text/event-stream`，事件类型：

| event | data | 说明 |
|---|---|---|
| meta | `{"intent": "place_order", "order": {...}}` | 元信息 |
| text | `{"text": "好的，"}` | 逐块文本 |
| done | `{}` | 结束 |
| error | `{"msg": "..."}` | 错误 |

### POST /api/chat/clear

清空当前用户对话历史。

### GET /api/chat/welcome

获取个性化欢迎语（需登录）。

**响应**：
```json
{ "code": 0, "data": { "message": "张三您好！上次您点的..." } }
```

---

## 三、菜单 / 订单 / 积分

### GET /api/menu

获取菜单。

**响应**：
```json
{
  "code": 0,
  "data": [
    {
      "category": "招牌泡馍",
      "items": [
        {"name": "牛肉泡馍(小份)", "price": "24", "emoji": "🍜", "stock": null}
      ]
    }
  ]
}
```

### POST /api/order/create

购物车下单（跳过 LLM，毫秒级）。**需登录**。

**请求体**：
```json
{
  "items": [{"name": "牛肉泡馍(小份)", "qty": 1}],
  "table_no": "05"
}
```

**响应**：
```json
{
  "code": 0,
  "msg": "下单成功",
  "data": { "order": {...}, "failed": [] }
}
```

### GET /api/user/orders

查询我的订单。**需登录**。

### POST /api/order/<order_id>/pay

模拟付款（pending → paid，发放积分）。**需登录**。

### POST /api/order/<order_id>/cancel

取消订单（pending/paid → cancelled，paid 状态会扣回积分）。**需登录**。

### GET /api/points/me

查询我的积分。**需登录**。

**响应**：
```json
{
  "code": 0,
  "data": {
    "points": 58,
    "level": "新客",
    "next_level": {"name": "常客", "need": 42, "threshold": 100},
    "exchange_items": [
      {"key": "garlic", "name": "糖蒜(整头)", "cost": 100}
    ]
  }
}
```

### POST /api/points/exchange

积分兑换。**需登录**。

**请求体**：`{ "item": "garlic" }`

---

## 四、留言 / 埋点 / 桌码

### POST /api/message

提交留言。

**请求体**：
```json
{ "name": "张三", "content": "泡馍很好吃" }
```

### POST /api/track

前端埋点上报。支持事件：`page_view`、`chat_message`、`order_created`、`mode_switch`、`add_to_cart`。

**请求体**：
```json
{ "event": "page_view", "payload": {"page": "/menu"} }
```

### POST /api/table/scan

扫码计数（手机打开 `?table=XX` 时前端上报）。

**请求体**：`{ "table_no": "05" }`

---

## 五、首页 Hero

### GET /api/hero

获取首页配置（公开）。

**响应**：
```json
{
  "code": 0,
  "data": {
    "items": [{"dish": "牛肉泡馍", "video": "/static/video/hero/01.mp4", "label": "招牌泡馍"}],
    "labels": [{"name": "招牌泡馍", "category": "招牌泡馍"}],
    "autoplay_ms": 8000
  }
}
```

---

## 六、系统

### GET /health

健康检查。

**响应**：
```json
{
  "status": "ok",
  "checks": {"flask": true, "vector_store": true, "ollama": true}
}
```

### GET /api/docs

Swagger UI 页面。

### GET /api/openapi.json

OpenAPI 3.0 规范。

---

## 七、后台接口

所有后台接口需 **管理员 Cookie**（`admin_token`）。未登录返回 401。

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/admin/login` | 登录页 / 提交登录 |
| POST | `/admin/logout` | 退出登录 |

### 数据看板

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/dashboard` | 数据总览页 |
| GET | `/admin/api/stats` | 统计 JSON |
| GET | `/admin/api/stats/trend?days=7` | 趋势数据 |

### 实时订单（SSE）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/live` | 实时看板页 |
| GET | `/admin/api/orders/stream` | SSE 推送新订单 |

### 订单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/orders` | 订单列表（支持 status/date/page 筛选）|
| POST | `/admin/api/orders/<id>/status` | 改订单状态 |
| GET | `/admin/api/orders/export` | 导出 CSV |

### AI 记录

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/chat-logs` | AI 对话记录列表 |

### 用户

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/users` | 用户列表 |
| POST | `/admin/api/users/<uid>/points` | 调整积分 |
| POST | `/admin/api/users/<uid>/disabled` | 禁用 / 启用 |

### 菜单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/menu` | 菜单（含库存）|
| POST | `/admin/api/menu/item` | 新增 / 修改菜品 |
| DELETE | `/admin/api/menu/item` | 删除菜品 |
| POST | `/admin/api/menu/category` | 新增分类 |
| DELETE | `/admin/api/menu/category` | 删除分类 |

### 首页 Hero

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/hero` | 读取 Hero 配置 |
| POST | `/admin/api/hero` | 保存 Hero 配置 |
| POST | `/admin/api/hero/upload` | 上传视频 |
| DELETE | `/admin/api/hero/video/<filename>` | 删除视频 |

### 留言

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/messages` | 留言列表 |
| POST | `/admin/api/messages/<id>/read` | 标记已读 / 未读 |
| DELETE | `/admin/api/messages/<id>` | 删除留言 |

### 桌码

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/tables` | 桌码列表 |
| POST | `/admin/api/tables` | 创建桌码 |
| DELETE | `/admin/api/tables/<id>` | 删除桌码 |
| GET | `/admin/api/tables/<no>/qrcode.png` | 生成二维码 PNG |

### 知识库

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/kb/versions` | 版本历史 |
| GET | `/admin/api/kb/versions/<id>` | 版本详情 |
| POST | `/admin/api/kb/rollback/<id>` | 回滚版本 |
| GET | `/api/admin/kb_files` | 列出文件 |
| GET | `/api/admin/kb_file?name=xxx` | 读文件 |
| POST | `/api/admin/kb_file` | 保存 + 重建向量库 |
| DELETE | `/api/admin/kb_file?name=xxx` | 删除 + 重建 |

### 日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/logs` | 操作日志 |
| GET | `/admin/api/app-logs` | 应用日志（可按 level 筛选）|
| GET | `/admin/api/app-logs/slow?limit=10` | 慢请求 TOP |
| GET | `/admin/api/app-logs/stats` | 日志统计 |

### Excel 导出

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/export/orders.xlsx` | 导出订单 |
| GET | `/admin/api/export/users.xlsx` | 导出用户 |
| GET | `/admin/api/export/points.xlsx` | 导出积分流水 |

### 系统设置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/api/settings` | 读取配置（敏感字段打码）|
| POST | `/admin/api/settings` | 保存配置 |
| POST | `/admin/api/test_ollama` | 测试 Ollama 模型 |
| POST | `/admin/api/test_remote_api` | 测试远程 API |
| POST | `/admin/api/test_notify` | 测试企业微信通知 |

---

**最后更新**：2026-09-23
