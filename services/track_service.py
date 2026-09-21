# services/track_service.py
import time
from collections import Counter
from datetime import datetime, timedelta
from repositories.instances import event_repo


class TrackService:
    """埋点业务逻辑"""

    VALID_EVENTS = [
        'page_view',      # 页面浏览
        'chat_message',   # AI 对话
        'order_created',  # 下单成功
        'mode_switch',    # 主题切换
        'add_to_cart',    # 加入购物车
    ]

    def track(self, event, payload=None, uid=None, ip=None, ua=None):
        """记录一条事件"""
        if event not in self.VALID_EVENTS:
            return None

        record = {
            'event': event,
            'payload': payload or {},
            'uid': uid,
            'ip': ip,
            'ua': (ua or '')[:100],
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        return event_repo.create(record)

    def get_stats(self):
        """统计看板数据"""
        events = event_repo.get_all()
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # 事件计数
        event_counter = Counter(e.get('event') for e in events)
        today_events = [e for e in events if e.get('date') == today]
        yesterday_events = [e for e in events if e.get('date') == yesterday]

        # 独立访客（按 IP）
        today_ips = set(e.get('ip') for e in today_events if e.get('ip'))
        all_ips = set(e.get('ip') for e in events if e.get('ip'))

        # 意图分布（从 chat_message 的 payload 里取）
        intent_counter = Counter()
        for e in events:
            if e.get('event') == 'chat_message':
                intent = (e.get('payload') or {}).get('intent')
                if intent:
                    intent_counter[intent] += 1

        # 热门搜索词（chat_message 的 message）
        hot_questions = Counter()
        for e in events:
            if e.get('event') == 'chat_message':
                msg = (e.get('payload') or {}).get('message', '').strip()
                if msg and len(msg) <= 30:
                    hot_questions[msg] += 1

        # 页面访问分布
        page_counter = Counter()
        for e in events:
            if e.get('event') == 'page_view':
                page = (e.get('payload') or {}).get('page', 'unknown')
                page_counter[page] += 1

        # 订单总额
        order_total = 0
        order_count = 0
        for e in events:
            if e.get('event') == 'order_created':
                order_count += 1
                order_total += (e.get('payload') or {}).get('total', 0)

        return {
            'total_events': len(events),
            'total_visitors': len(all_ips),
            'today': {
                'visitors': len(today_ips),
                'page_view': sum(1 for e in today_events if e.get('event') == 'page_view'),
                'chat_message': sum(1 for e in today_events if e.get('event') == 'chat_message'),
                'order_created': sum(1 for e in today_events if e.get('event') == 'order_created'),
            },
            'yesterday': {
                'visitors': len(set(e.get('ip') for e in yesterday_events if e.get('ip'))),
            },
            'event_distribution': dict(event_counter),
            'intent_distribution': dict(intent_counter),
            'page_distribution': dict(page_counter),
            'hot_questions': hot_questions.most_common(5),
            'order_summary': {
                'count': order_count,
                'total': round(order_total, 2),
            },
        }


track_service = TrackService()