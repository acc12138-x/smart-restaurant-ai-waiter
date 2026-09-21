# services/session_service.py
import time
from collections import defaultdict, deque

# 每个用户保留最近 N 轮对话
MAX_HISTORY = 5
# 会话过期时间（秒）
SESSION_TTL = 30 * 60


class SessionService:
    """管理用户对话历史（内存版，生产可换 Redis）"""

    def __init__(self):
        # uid -> deque([{role, content}, ...])
        self._sessions = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))
        # uid -> last_active_ts
        self._last_active = {}
        # uid -> [订单信息]（用于"一共多少钱"聚合）
        self._orders = defaultdict(list)

    def _key(self, uid):
        """未登录用户用 'anon' 作为 key"""
        return uid or 'anon'

    def get_history(self, uid):
        """获取对话历史（列表）"""
        key = self._key(uid)
        self._cleanup()
        self._last_active[key] = time.time()
        return list(self._sessions[key])

    def add(self, uid, role, content):
        """追加一条对话"""
        key = self._key(uid)
        self._sessions[key].append({
            'role': role,
            'content': content,
            'ts': time.time(),
        })
        self._last_active[key] = time.time()

    def clear(self, uid):
        """清空某用户对话"""
        key = self._key(uid)
        self._sessions[key].clear()
        self._last_active.pop(key, None)
        self._orders.pop(key, None)

    def _cleanup(self):
        """清理过期会话"""
        now = time.time()
        expired = [
            k for k, ts in self._last_active.items()
            if now - ts > SESSION_TTL
        ]
        for k in expired:
            self._sessions.pop(k, None)
            self._last_active.pop(k, None)

    def add_order(self, uid, order):
        """记录本会话成功下单的订单"""
        key = self._key(uid)
        self._orders[key].append({
            'id': order.get('id'),
            'total': float(order.get('total', 0) or 0),
            'items': order.get('items', []),
            'created_at': order.get('created_at', ''),
        })
        # 只保留最近 10 单
        if len(self._orders[key]) > 10:
            self._orders[key] = self._orders[key][-10:]

    def get_orders(self, uid):
        """拿本会话所有下单"""
        key = self._key(uid)
        return list(self._orders.get(key, []))

    def update_order_status(self, uid, order_id, status):
        """更新本会话某订单的状态"""
        key = self._key(uid)
        for o in self._orders.get(key, []):
            if o.get('id') == order_id:
                o['status'] = status
                return True
        return False

    def format_history(self, uid, max_rounds=3):
        """把历史格式化成 prompt 可用的文本"""
        history = self.get_history(uid)
        if not history:
            return ''
        # 只取最近 N 轮
        recent = history[-(max_rounds * 2):]
        lines = []
        for item in recent:
            role = '用户' if item['role'] == 'user' else '助手'
            lines.append(f"{role}：{item['content']}")
        return '\n'.join(lines)


# 单例
session_service = SessionService()