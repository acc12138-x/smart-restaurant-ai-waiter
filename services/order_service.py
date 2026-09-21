# services/order_service.py
import time
from repositories.instances import order_repo
from services.menu_service import menu_service
from utils.exceptions import BizError


VALID_TRANSITIONS = {
    'pending':   ['paid', 'cancelled'],
    'paid':      ['cooking', 'cancelled'],
    'cooking':   ['done'],
    'done':      [],
    'cancelled': [],
}


class OrderService:
    """订单业务逻辑"""

    def create(self, items: list, table_no: str = '外带', uid: str = None) -> dict:
        """创建订单"""
        if not items:
            raise BizError('订单不能为空')

        resolved = []
        failed = []
        total = 0.0

        for it in items:
            dish = menu_service.find_dish(it.get('name', ''))
            qty = int(it.get('qty', 1))
            if qty <= 0:
                continue

            if dish:
                subtotal = dish['price'] * qty
                resolved.append({
                    'name': dish['name'],
                    'price': dish['price'],
                    'qty': qty,
                    'subtotal': subtotal,
                })
                total += subtotal
            else:
                failed.append(it.get('name'))

        if not resolved:
            raise BizError(f"菜单里没有找到：{'、'.join(failed)}")

        order = {
            'id': f"TSX{int(time.time() * 1000)}",
            'uid': uid,
            'table_no': table_no,
            'items': resolved,
            'total': round(total, 2),
            'status': 'pending',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        order_repo.create(order)
        # 注意：积分改为"付款后"才发放，见 update_status()

        return {
            'order': order,
            'failed': failed,
        }

    def get(self, order_id: str):
        return order_repo.find_by_id(order_id)

    def get_all(self):
        return order_repo.get_all()

    def get_by_uid(self, uid: str):
        if not uid:
            return []
        orders = order_repo.find(uid=uid)
        orders.sort(key=lambda o: o.get('created_at', ''), reverse=True)
        return orders

    def update_status(self, order_id: str, new_status: str):
        order = order_repo.find_by_id(order_id)
        if not order:
            raise BizError(f'订单不存在: {order_id}', code=404)

        current = order.get('status', 'pending')
        allowed = VALID_TRANSITIONS.get(current, [])
        if new_status not in allowed:
            raise BizError(f'订单状态不能从 {current} 变为 {new_status}')

        order_repo.update(order_id, {'status': new_status})

        uid = order.get('uid')
        total = int(order.get('total', 0) or 0)

        # ============ 积分规则（付款才加、付款后取消才扣）============
        from services.points_service import points_service
        from utils.logger import logger

        # 1) pending → paid：付款，发放积分
        if new_status == 'paid' and current != 'paid' and uid:
            try:
                points_service.add_points(uid, total,
                                           reason=f'下单 {order_id}')
                logger.info(f'[积分] +{total} 订单 {order_id} 已付款')
            except Exception as e:
                logger.warning(f'付款加积分失败: {e}')

        # 2) paid → cancelled：付款后取消，扣回积分
        elif new_status == 'cancelled' and current == 'paid' and uid:
            try:
                points_service.deduct_points(uid, total,
                                              reason=f'取消已付款订单 {order_id}',
                                              allow_negative=True)
                logger.info(f'[积分] -{total} 订单 {order_id} 已付款后取消')
            except Exception as e:
                logger.warning(f'取消扣回积分失败: {e}')

        # 3) pending → cancelled：什么都没加过，不动积分

        return order_repo.find_by_id(order_id)

    def format_reply(self, result: dict) -> str:
        """把订单结果格式化成 AI 回复文案"""
        order = result['order']
        lines = [f"好的，已为您下单（订单号 {order['id']}）："]
        for it in order['items']:
            lines.append(f"  · {it['name']} × {it['qty']} = {it['subtotal']} 元")
        lines.append(f"合计：{order['total']} 元")

        if result.get('failed'):
            lines.append(f"（未找到：{'、'.join(result['failed'])}）")
        return '\n'.join(lines)


order_service = OrderService()