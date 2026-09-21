# repositories/instances.py
"""全局 Repository 单例（SQLite 版）"""
from repositories.sqlite_repo import SqliteRepository

# 用户表（用 uid 作主键）
member_repo = SqliteRepository(
    'users',
    id_field='uid',
    auto_id=False,
)

# 订单表（用 TSX 订单号作主键，items 是 JSON）
order_repo = SqliteRepository(
    'orders',
    id_field='id',
    auto_id=False,
    json_fields=['items'],
)

# 留言表
message_repo = SqliteRepository(
    'messages',
    id_field='id',
    auto_id=True,
)

# 埋点表（payload 是 JSON）
event_repo = SqliteRepository(
    'events',
    id_field='id',
    auto_id=True,
    json_fields=['payload'],
)

# ---------- v3.0 新增 ----------

# 后台管理员
admin_user_repo = SqliteRepository(
    'admin_users',
    id_field='id',
    auto_id=True,
)

# 后台操作日志
admin_log_repo = SqliteRepository(
    'admin_logs',
    id_field='id',
    auto_id=True,
)

# 桌码
table_repo = SqliteRepository(
    'tables',
    id_field='id',
    auto_id=True,
)

# 知识库版本历史
kb_history_repo = SqliteRepository(
    'kb_history',
    id_field='id',
    auto_id=True,
)

# 积分流水
points_log_repo = SqliteRepository(
    'points_log',
    id_field='id',
    auto_id=True,
)

# AI 对话记录
chat_log_repo = SqliteRepository(
    'chat_logs',
    id_field='id',
    auto_id=True,
)