# tests/test_order.py
import pytest
from services.order_service import order_service
from utils.exceptions import BizError


def test_create_order_success():
    """下单成功"""
    result = order_service.create([
        {'name': '牛肉泡馍(小份)', 'qty': 2}
    ])
    order = result['order']
    assert order['total'] == 48
    assert order['status'] == 'pending'
    assert len(order['items']) == 1


def test_create_order_multiple_items():
    """多个菜品"""
    result = order_service.create([
        {'name': '牛肉泡馍(小份)', 'qty': 2},
        {'name': '冰峰汽水', 'qty': 1},
    ])
    assert result['order']['total'] == 54  # 24*2 + 6


def test_create_order_empty():
    """空订单报错"""
    with pytest.raises(BizError):
        order_service.create([])


def test_create_order_invalid_dish():
    """无效菜品报错"""
    with pytest.raises(BizError) as exc:
        order_service.create([{'name': '佛跳墙', 'qty': 1}])
    assert '佛跳墙' in str(exc.value)


def test_order_status_transition():
    """状态流转"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']

    # pending → paid
    updated = order_service.update_status(order_id, 'paid')
    assert updated['status'] == 'paid'

    # paid → cooking
    updated = order_service.update_status(order_id, 'cooking')
    assert updated['status'] == 'cooking'


def test_order_invalid_transition():
    """非法流转报错"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']

    # pending 不能直接到 done
    with pytest.raises(BizError):
        order_service.update_status(order_id, 'done')