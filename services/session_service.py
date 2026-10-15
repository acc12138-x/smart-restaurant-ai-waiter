# services/session_service.py
"""对话记忆（SQLite 持久化 + 内存缓存）

**为什么要落库**：生产用 gunicorn 多 worker，每个 worker 一份内存。
"AI 推荐了羊肉泡馍 → 用户回可以"这两句很可能落在不同 worker 上，
纯内存版会丢掉推荐，用户就只得到一句"那要吃点啥？"。
（chat_sessions 表在 v3.8 就建好了，注释写着"跨会话持久化"，但一直没接上。）

**为什么未登录用户要按设备区分**：以前所有匿名顾客共用 'anon' 这一个 key，
A 顾客的上下文会串到 B 顾客那儿 —— B 说"可以"甚至可能接掉 A 的推荐。
现在由 app.py 在 cookie 里种一个设备号，按设备隔离。
"""
import json
import time
from collections import defaultdict, deque

from utils.logger import logger

# 每个用户保留最近 N 轮对话
MAX_HISTORY = 5
# 会话过期时间（秒）
SESSION_TTL = 30 * 60
# 最近推荐的存活时间（秒）
RECOMMEND_TTL = 300
# 落库时用来区分"推荐"这类非对话内容
ROLE_RECOMMEND = 'recommend'


class SessionService:
    """管理用户对话记忆"""

    def __init__(self, repo=None):
        # uid -> deque([{role, content}, ...])
        self._sessions = defaultdict(lambda: deque(maxlen=MAX_HISTORY * 2))
        # uid -> last_active_ts
        self._last_active = {}
        self._recommend_history = {}
        self._pending_message = {}  # uid -> bool（等待留言内容）
        self._last_recommend = {}
        # uid -> [订单信息]（用于"一共多少钱"聚合）
        self._orders = defaultdict(list)
        self._repo = repo

    def _key(self, uid):
        """会话 key

        已登录 → uid；未登录 → 按设备号隔离（cookie 里由 app.py 种下），
        拿不到设备号时才回退到 'anon'。
        """
        if uid:
            return str(uid)
        try:
            from flask import g, has_request_context
            if has_request_context():
                dev = getattr(g, 'device_id', None)
                if dev:
                    return 'anon:' + str(dev)
        except Exception:
            pass
        return 'anon'

    # ---------- 持久化 ----------

    def _get_repo(self):
        if self._repo is None:
            try:
                from repositories.instances import chat_session_repo
                self._repo = chat_session_repo
            except Exception as e:
                logger.warning('[Session] 无法获取 repo，退回纯内存: ' + str(e))
                self._repo = False
        return self._repo or None

    @staticmethod
    def _cutoff(seconds):
        """N 秒之前的时间串（与 created_at 同格式，可直接字符串比较）"""
        from datetime import timedelta
        from utils.timeutil import now
        return (now() - timedelta(seconds=seconds)).strftime('%Y-%m-%d %H:%M:%S')

    def _db_rows(self, key, ttl=SESSION_TTL):
        """读该会话未过期的行；DB 不可用时返回 None（调用方好退回内存）"""
        repo = self._get_repo()
        if not repo:
            return None
        try:
            rows = repo.find(uid=key) or []
        except Exception as e:
            logger.warning('[Session] 读取失败，退回内存: ' + str(e))
            return None
        cutoff = self._cutoff(ttl)
        fresh, stale = [], []
        for r in rows:
            (fresh if (r.get('created_at') or '') >= cutoff else stale).append(r)
        # 顺手清理过期行，避免表无限增长
        for r in stale[:50]:
            try:
                repo.delete(r['id'])
            except Exception:
                pass
        fresh.sort(key=lambda r: r.get('id') or 0)
        return fresh

    def _db_add(self, key, role, content):
        repo = self._get_repo()
        if not repo:
            return
        try:
            from utils.timeutil import now_str
            repo.create({
                'uid': key, 'role': role, 'content': content,
                'created_at': now_str(), 'ts': time.time(),
            })
        except Exception as e:
            logger.warning('[Session] 写入失败: ' + str(e))

    # ---------- 对话历史 ----------

    def get_history(self, uid):
        """获取对话历史（列表）"""
        key = self._key(uid)
        self._cleanup()
        self._last_active[key] = time.time()

        rows = self._db_rows(key)
        if rows is not None:
            items = [{'role': r['role'], 'content': r['content']}
                     for r in rows if r.get('role') in ('user', 'assistant')]
            return items[-MAX_HISTORY * 2:]
        # DB 不可用 → 退回内存
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
        if role in ('user', 'assistant'):
            self._db_add(key, role, content)

    def clear(self, uid):
        """清空某用户对话"""
        key = self._key(uid)
        self._sessions[key].clear()
        self._last_active.pop(key, None)
        self._orders.pop(key, None)
        self._last_recommend.pop(key, None)
        repo = self._get_repo()
        if repo:
            try:
                for r in repo.find(uid=key) or []:
                    repo.delete(r['id'])
            except Exception:
                pass

    def _cleanup(self):
        """清理过期会话（内存）"""
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
        self._db_add(key, ROLE_RECOMMEND, json.dumps(
            {'text': text, 'items': items or []}, ensure_ascii=False))

    def get_last_recommend(self, uid):
        """读最近推荐，5 分钟过期（先查内存，未命中再查库 —— 跨 worker 也能拿到）"""
        key = self._key(uid)
        v = self._last_recommend.get(key)
        if v and time.time() - v.get('ts', 0) <= RECOMMEND_TTL:
            return v
        if v:
            self._last_recommend.pop(key, None)

        rows = self._db_rows(key, ttl=RECOMMEND_TTL)
        for r in reversed(rows or []):
            if r.get('role') == ROLE_RECOMMEND:
                try:
                    data = json.loads(r.get('content') or '{}')
                except Exception:
                    continue
                if not data.get('items'):
                    continue
                v = {'text': data.get('text', ''),
                     'items': data['items'],
                     'ts': time.time()}
                self._last_recommend[key] = v
                return v
        return None

    def clear_last_recommend(self, uid):
        key = self._key(uid)
        self._last_recommend.pop(key, None)
        repo = self._get_repo()
        if repo:
            try:
                for r in repo.find(uid=key) or []:
                    if r.get('role') == ROLE_RECOMMEND:
                        repo.delete(r['id'])
            except Exception:
                pass

    def add_recommend_history(self, uid, dish_names):
        """记录一次推荐过的菜名，最多保留最近 10 个"""
        key = self._key(uid)
        if key not in self._recommend_history:
            self._recommend_history[key] = []
        for n in (dish_names or []):
            if n and n not in self._recommend_history[key]:
                self._recommend_history[key].append(n)
        # 只留最近 10 个
        self._recommend_history[key] = self._recommend_history[key][-10:]

    def get_recommend_history(self, uid):
        return list(self._recommend_history.get(self._key(uid), []))

    def clear_recommend_history(self, uid):
        self._recommend_history.pop(self._key(uid), None)

    def set_pending_message(self, uid, flag=True):
        self._pending_message[self._key(uid)] = bool(flag)

    def is_pending_message(self, uid):
        return self._pending_message.get(self._key(uid), False)

    def clear_pending_message(self, uid):
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
