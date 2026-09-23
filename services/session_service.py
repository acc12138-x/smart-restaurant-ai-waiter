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
        self._recommend_history = {}
        self._pending_message = {}  # uid -> bool（等待留言内容）
        self._last_recommend = {}
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
        self._last_recommend.pop(key, None)

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

    # ---------- 最近推荐（v3.9） ----------
    def set_last_recommend(self, uid, text, items):
        """记录最近一次推荐，供"就这个"接单"""
        key = self._key(uid)
        self._last_recommend[key] = {
            'text': text,
            'items': items or [],
            'ts': time.time(),
        }

    def get_last_recommend(self, uid):
        """读最近推荐，5 分钟过期"""
        key = self._key(uid)
        v = self._last_recommend.get(key)
        if not v:
            return None
        if time.time() - v.get('ts', 0) > 300:
            self._last_recommend.pop(key, None)
            return None
        return v

    def clear_last_recommend(self, uid):
        if not hasattr(self, '_last_recommend'):
            return
        self._last_recommend.pop(self._key(uid), None)

    def add_recommend_history(self, uid, dish_names):
        """记录一次推荐过的菜名，最多保留最近 10 个"""
        if not hasattr(self, '_recommend_history'):
            self._recommend_history = {}
        key = self._key(uid)
        if key not in self._recommend_history:
            self._recommend_history[key] = []
        for n in (dish_names or []):
            if n and n not in self._recommend_history[key]:
                self._recommend_history[key].append(n)
        # 只留最近 10 个
        self._recommend_history[key] = self._recommend_history[key][-10:]

    def get_recommend_history(self, uid):
        if not hasattr(self, '_recommend_history'):
            return []
        return list(self._recommend_history.get(self._key(uid), []))

    def clear_recommend_history(self, uid):
        if hasattr(self, '_recommend_history'):
            self._recommend_history.pop(self._key(uid), None)

    def set_pending_message(self, uid, flag=True):
        if not hasattr(self, '_pending_message'):
            self._pending_message = {}
        self._pending_message[self._key(uid)] = bool(flag)

    def is_pending_message(self, uid):
        if not hasattr(self, '_pending_message'):
            return False
        return self._pending_message.get(self._key(uid), False)

    def clear_pending_message(self, uid):
        if hasattr(self, '_pending_message'):
            self._pending_message.pop(self._key(uid), None)

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