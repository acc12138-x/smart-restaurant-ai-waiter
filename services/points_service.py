# services/points_service.py
import time
from repositories.instances import member_repo, order_repo
from utils.exceptions import BizError

# 积分等级阈值
LEVELS = [
    (0,    '新客'),
    (100,  '常客'),
    (500,  '老友'),
    (2000, '铁粉'),
]

# 兑换商品
EXCHANGE_ITEMS = {
    'garlic':  {'name': '糖蒜(整头)', 'cost': 100},
    'bingfeng': {'name': '冰峰汽水',  'cost': 200},
    'liangpi': {'name': '凉皮',      'cost': 300},
}


class PointsService:
    """会员积分业务逻辑"""

    def _calc_level(self, points):
        level = '新客'
        for threshold, name in LEVELS:
            if points >= threshold:
                level = name
        return level

    def add_points(self, uid, amount, reason=''):
        """增加积分"""
        member = member_repo.find_by_id(uid)
        if not member:
            return None

        points = member.get('points', 0) + amount
        level = self._calc_level(points)

        member_repo.update(uid, {
            'points': points,
            'level': level,
            'last_points_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

        # 记一笔积分变动
        self._log(uid, amount, reason)
        return {'points': points, 'level': level, 'change': amount}

    def deduct_points(self, uid, amount, reason='', allow_negative=False):
        """扣除积分
        allow_negative=True 时允许扣成负数（取消订单扣回场景）
        """
        member = member_repo.find_by_id(uid)
        if not member:
            raise BizError('用户不存在', code=404)

        current = member.get('points', 0)
        if not allow_negative and current < amount:
            raise BizError(f'积分不足，需要 {amount} 分，当前 {current} 分')

        points = current - amount
        level = self._calc_level(points)
        member_repo.update(uid, {'points': points, 'level': level})
        self._log(uid, -amount, reason)
        return {'points': points, 'level': level, 'change': -amount}

    def get_info(self, uid):
        """查用户积分信息"""
        member = member_repo.find_by_id(uid)
        if not member:
            raise BizError('用户不存在', code=404)

        points = member.get('points', 0)
        # 下一等级
        next_level = None
        for threshold, name in LEVELS:
            if points < threshold:
                next_level = {'name': name, 'need': threshold - points, 'threshold': threshold}
                break

        return {
            'points': points,
            'level': self._calc_level(points),
            'next_level': next_level,
            'exchange_items': [
                {'key': k, **v} for k, v in EXCHANGE_ITEMS.items()
            ],
        }

    def exchange(self, uid, item_key):
        """积分兑换"""
        item = EXCHANGE_ITEMS.get(item_key)
        if not item:
            raise BizError('兑换商品不存在')

        self.deduct_points(uid, item['cost'], reason=f"兑换 {item['name']}")
        return {
            'item': item['name'],
            'cost': item['cost'],
            'msg': f"兑换成功：{item['name']}",
        }

    def _log(self, uid, change, reason):
        """记录积分流水"""
        from repositories.instances import points_log_repo
        points_log_repo.create({
            'uid': uid,
            'change': change,
            'reason': reason,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

points_service = PointsService()