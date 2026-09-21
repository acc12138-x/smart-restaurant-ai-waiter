# services/openapi_service.py
"""OpenAPI 3.0 规范定义"""


def get_openapi_spec():
    """返回完整 OpenAPI spec"""
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "同盛祥西安泡馍老店 · API",
            "description": "H5 点餐 + AI 客服 + 数据看板",
            "version": "1.0.0",
        },
        "servers": [{"url": "/", "description": "当前服务器"}],
        "tags": [
            {"name": "认证", "description": "用户注册登录"},
            {"name": "AI", "description": "AI 客服与点菜"},
            {"name": "业务", "description": "菜单、订单、积分"},
            {"name": "埋点", "description": "用户行为上报"},
            {"name": "系统", "description": "健康检查"},
        ],
        "paths": {
            "/api/auth/register": {
                "post": {
                    "tags": ["认证"],
                    "summary": "注册新用户",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "username": {"type": "string", "example": "testuser"},
                                        "password": {"type": "string", "example": "123456"},
                                        "nickname": {"type": "string", "example": "测试员"},
                                    },
                                    "required": ["username", "password"],
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "注册成功",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "code": {"type": "integer", "example": 0},
                                            "msg": {"type": "string", "example": "注册成功"},
                                            "data": {
                                                "type": "object",
                                                "properties": {
                                                    "member": {"type": "object"},
                                                    "token": {"type": "string"},
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/auth/login": {
                "post": {
                    "tags": ["认证"],
                    "summary": "登录",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "登录成功"}},
                }
            },
            "/api/auth/me": {
                "get": {
                    "tags": ["认证"],
                    "summary": "查询当前用户",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "用户信息"}},
                }
            },
            "/api/chat": {
                "post": {
                    "tags": ["AI"],
                    "summary": "AI 对话（非流式）",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"message": {"type": "string", "example": "牛肉泡馍多少钱"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "AI 回答"}},
                }
            },
            "/api/chat/stream": {
                "post": {
                    "tags": ["AI"],
                    "summary": "AI 对话（SSE 流式）",
                    "description": "返回 text/event-stream，逐块推送",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"message": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "SSE 事件流"}},
                }
            },
            "/api/chat/clear": {
                "post": {
                    "tags": ["AI"],
                    "summary": "清空对话历史",
                    "responses": {"200": {"description": "成功"}},
                }
            },
            "/api/menu": {
                "get": {
                    "tags": ["业务"],
                    "summary": "获取菜单",
                    "responses": {"200": {"description": "菜单列表"}},
                }
            },
            "/api/message": {
                "post": {
                    "tags": ["业务"],
                    "summary": "提交留言",
                    "responses": {"200": {"description": "成功"}},
                }
            },
            "/api/user/orders": {
                "get": {
                    "tags": ["业务"],
                    "summary": "我的订单",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "订单列表"}},
                }
            },
            "/api/points/me": {
                "get": {
                    "tags": ["业务"],
                    "summary": "我的积分",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "积分信息"}},
                }
            },
            "/api/points/exchange": {
                "post": {
                    "tags": ["业务"],
                    "summary": "积分兑换",
                    "security": [{"BearerAuth": []}],
                    "responses": {"200": {"description": "兑换结果"}},
                }
            },
            "/api/track": {
                "post": {
                    "tags": ["埋点"],
                    "summary": "埋点上报",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "event": {"type": "string"},
                                        "payload": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "成功"}},
                }
            },
            "/api/admin/stats": {
                "get": {
                    "tags": ["埋点"],
                    "summary": "看板统计",
                    "responses": {"200": {"description": "统计数据"}},
                }
            },
            "/health": {
                "get": {
                    "tags": ["系统"],
                    "summary": "健康检查",
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                }
            }
        },
    }