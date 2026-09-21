# API 接口文档

## 通用响应格式

所有接口返回统一格式：

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
| msg | string | 提示信息 |
| data | any | 业务数据 |

**错误码**：

| code | 含义 |
|---|---|
| 0 | 成功 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 404 | 资源不存在 |
| 500 | 服务器错误 |

---

## 认证接口

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
    "token": "eyJhbGciOi..."
  }
}
```

### POST /api/auth/login

登录，参数与响应同注册。

### GET /api/auth/me

查询当前用户（需要 token）。

**请求头**：

```
Authorization: Bearer <token>
```

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

## AI 对话接口

### POST /api/chat

AI 客服对话，支持点菜。

**请求体**：

```json
{ "message": "来两份牛肉泡馍" }
```

**可选请求头**：Authorization: Bearer <token>

**响应（普通对话）**：

```json
{
  "code": 0,
  "data": {
    "reply": "营业时间是每天 10:30 至次日 02:00。",
    "intent": "query_hours",
    "order": null
  }
}
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
      "items": [],
      "total": 48,
      "status": "pending",
      "uid": "uuid"
    }
  }
}
```

### POST /api/chat/clear

清空当前对话历史。

**请求体**：

```json
{}
```

---

## 业务接口

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
        { "name": "牛肉泡馍(小份)", "price": "24", "emoji": "🍜" }
      ]
    }
  ]
}
```

### GET /api/user/orders

查询我的订单（需要 token）。

**请求头**：

```
Authorization: Bearer <token>
```

**响应**：

```json
{
  "code": 0,
  "data": [
    {
      "id": "TSX1789743112659",
      "items": [
        { "name": "羊肉泡馍", "price": 26, "qty": 1, "subtotal": 26 }
      ],
      "total": 26,
      "status": "pending",
      "uid": "uuid",
      "created_at": "2026-09-19 15:30:00"
    }
  ]
}
```

### GET /api/points/me

查询我的积分（需要 token）。

**响应**：

```json
{
  "code": 0,
  "data": {
    "points": 58,
    "level": "新客",
    "next_level": { "name": "常客", "need": 42, "threshold": 100 },
    "exchange_items": [
      { "key": "garlic", "name": "糖蒜(整头)", "cost": 100 },
      { "key": "bingfeng", "name": "冰峰汽水", "cost": 200 },
      { "key": "liangpi", "name": "凉皮", "cost": 300 }
    ]
  }
}
```

### POST /api/points/exchange

积分兑换（需要 token）。

**请求体**：

```json
{ "item": "garlic" }
```

**响应（成功）**：

```json
{
  "code": 0,
  "msg": "兑换成功：糖蒜(整头)",
  "data": {
    "item": "糖蒜(整头)",
    "cost": 100
  }
}
```

**响应（积分不足）**：

```json
{
  "code": 400,
  "msg": "积分不足，需要 100 分，当前 58 分",
  "data": null
}
```

---

## 留言接口

### POST /api/message

提交留言。

**请求体**：

```json
{
  "name": "张三",
  "content": "泡馍很好吃"
}
```

**响应**：

```json
{
  "code": 0,
  "msg": "收到，谢谢",
  "data": null
}
```

---

## 埋点接口

### POST /api/track

上报用户行为。

**请求体**：

```json
{
  "event": "page_view",
  "payload": { "page": "/menu" }
}
```

**支持的事件**：

| 事件名 | 说明 | payload 字段 |
|---|---|---|
| page_view | 页面浏览 | page |
| chat_message | AI 对话 | message, intent, is_order |
| order_created | 下单成功 | order_id, total |
| mode_switch | 主题切换 | mode |
| add_to_cart | 加入购物车 | name, price |

### GET /api/admin/stats

获取看板统计数据。

**响应**：

```json
{
  "code": 0,
  "data": {
    "total_events": 156,
    "total_visitors": 12,
    "today": {
      "visitors": 5,
      "page_view": 23,
      "chat_message": 8,
      "order_created": 3
    },
    "event_distribution": {
      "page_view": 80,
      "chat_message": 45,
      "order_created": 12
    },
    "intent_distribution": {
      "query_menu": 20,
      "place_order": 12,
      "query_hours": 8
    },
    "hot_questions": [
      ["牛肉泡馍多少钱", 5],
      ["营业到几点", 3]
    ],
    "order_summary": {
      "count": 12,
      "total": 468.0
    }
  }
}
```

---

## 系统接口

### GET /health

健康检查。

**响应**：

```json
{
  "status": "ok",
  "checks": {
    "flask": true,
    "vector_store": true,
    "ollama": true
  }
}
```

**状态码**：

- 200：全部正常
- 503：某个依赖不可用（如 Ollama 没启动）

---

## 知识库接口

### POST /api/kb_rebuild

重建知识库（更新文档后调用）。

**响应**：

```json
{
  "code": 0,
  "msg": "知识库已重建",
  "data": null
}
```

---

## 页面路由

| 路径 | 说明 |
|---|---|
| `/` | 首页 |
| `/menu` | 菜单页 |
| `/location` | 门店页 |
| `/chat` | AI 客服 |
| `/profile` | 个人中心 |
| `/admin` | 数据看板 |
| `/health` | 健康检查 |

---

**最后更新**：2026-09-19