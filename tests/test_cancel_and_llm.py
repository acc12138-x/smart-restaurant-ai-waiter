# tests/test_cancel_and_llm.py
"""订单取消逻辑 + LLM 语义层测试"""
import pytest
import os
from services.order_service import order_service
from services.admin_service import admin_service
from utils.exceptions import BizError


# ============================================================
# 订单取消 / 状态流转
# ============================================================
def test_create_order_pending_no_points():
    """下单不立即加积分（v3.0 新规则）"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    assert result['order']['status'] == 'pending'
    # 确认订单没有 uid（未登录）或者加了 uid 时也不立即加分
    # （下一条测试单独验证）


def test_paid_then_cancel_order():
    """已付款订单可以取消"""
    # 创建订单
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']

    # pending → paid
    updated = order_service.update_status(order_id, 'paid')
    assert updated['status'] == 'paid'

    # paid → cancelled（应成功）
    cancelled = order_service.update_status(order_id, 'cancelled')
    assert cancelled['status'] == 'cancelled'


def test_pending_cancel_order():
    """待付款订单可以直接取消"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']
    cancelled = order_service.update_status(order_id, 'cancelled')
    assert cancelled['status'] == 'cancelled'


def test_cooking_cannot_cancel():
    """制作中订单不能取消"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']
    # pending → paid → cooking
    order_service.update_status(order_id, 'paid')
    order_service.update_status(order_id, 'cooking')
    # cooking → cancelled 应失败
    with pytest.raises(BizError):
        order_service.update_status(order_id, 'cancelled')


def test_done_cannot_cancel():
    """已完成订单不能取消"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']
    order_service.update_status(order_id, 'paid')
    order_service.update_status(order_id, 'cooking')
    order_service.update_status(order_id, 'done')
    with pytest.raises(BizError):
        order_service.update_status(order_id, 'cancelled')


def test_cancel_nonexistent_order():
    """取消不存在的订单报错"""
    with pytest.raises(BizError):
        order_service.update_status('TSX_DOES_NOT_EXIST', 'cancelled')


def test_invalid_transition_pending_to_done():
    """pending 不能直接到 done"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']
    with pytest.raises(BizError):
        order_service.update_status(order_id, 'done')


def test_invalid_transition_cancelled_to_paid():
    """已取消不能恢复为已付款"""
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    order_id = result['order']['id']
    order_service.update_status(order_id, 'cancelled')
    with pytest.raises(BizError):
        order_service.update_status(order_id, 'paid')


# ============================================================
# 积分规则（付款后加 / 已付款取消扣回）
# ============================================================
def test_points_added_after_paid():
    """付款后才加积分"""
    from repositories.instances import member_repo
    from services.points_service import points_service

    # 找一个测试用户，没有就跳过
    users = member_repo.get_all()
    if not users:
        pytest.skip('库里没有用户，跳过')
    uid = users[0]['uid']

    # 记录当前积分
    before = member_repo.find_by_id(uid).get('points', 0)

    # 创建订单（带 uid）
    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid)
    order_id = result['order']['id']

    # pending 状态积分不变
    after_pending = member_repo.find_by_id(uid).get('points', 0)
    assert after_pending == before

    # 付款后积分 +6
    order_service.update_status(order_id, 'paid')
    after_paid = member_repo.find_by_id(uid).get('points', 0)
    assert after_paid == before + 6


def test_points_deducted_after_cancel_paid_order():
    """已付款订单取消后扣回积分"""
    from repositories.instances import member_repo
    users = member_repo.get_all()
    if not users:
        pytest.skip('库里没有用户，跳过')
    uid = users[0]['uid']

    before = member_repo.find_by_id(uid).get('points', 0)

    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid)
    order_id = result['order']['id']
    order_service.update_status(order_id, 'paid')

    points_after_paid = member_repo.find_by_id(uid).get('points', 0)
    assert points_after_paid == before + 6

    # 取消已付款订单
    order_service.update_status(order_id, 'cancelled')
    points_after_cancel = member_repo.find_by_id(uid).get('points', 0)
    # 扣回 6 分
    assert points_after_cancel == before


# ============================================================
# LLM Parser
# ============================================================
def test_llm_parser_is_enabled_returns_bool():
    """v3.9：LLM 默认开启，is_enabled() 返回 bool"""
    from services.llm_parser import is_enabled
    assert isinstance(is_enabled(), bool)


def test_llm_parser_returns_none_when_disabled():
    """LLM 关闭时返回 None"""
    from services.llm_parser import parse
    import os
    if os.environ.get('USE_LLM_PARSER') == '1':
        pytest.skip('当前已开启 LLM Parser')
    result = parse('来一份牛肉泡馍')
    assert result is None


def test_intent_service_basic():
    """规则意图识别基本可用"""
    from services.intent_service import classify_intent

    # 查询菜单
    r = classify_intent('牛肉泡馍多少钱')
    assert r['intent'] == 'query_menu'

    # 地址
    r = classify_intent('门店在哪里')
    assert r['intent'] == 'query_location'

    # 营业时间
    r = classify_intent('几点关门')
    assert r['intent'] == 'query_hours'

    # 取消订单
    r = classify_intent('取消订单')
    assert r['intent'] == 'cancel_order'

    # 纯标点
    r = classify_intent('。。。')
    assert r['intent'] == 'other'


def test_intent_place_order():
    """点菜意图识别"""
    from services.intent_service import classify_intent
    r = classify_intent('我要牛肉泡馍')
    assert r['intent'] == 'place_order'


def test_intent_cancel_all():
    """全部取消意图"""
    from services.intent_service import classify_intent
    r = classify_intent('全部退掉')
    assert r['intent'] == 'cancel_all'


def test_intent_modify_order():
    """修改订单意图"""
    from services.intent_service import classify_intent
    r = classify_intent('把牛肉泡馍改成羊肉泡馍')
    assert r['intent'] == 'modify_order'


def test_llm_parser_normalize_items():
    """LLM 结果白名单校验"""
    from services.llm_parser import _normalize_items

    menu_names = ['牛肉泡馍(小份)', '牛肉泡馍(大份)', '冰峰汽水', '糖蒜(整头)']

    # 正常菜名
    r = _normalize_items([{'dish': '冰峰汽水', 'qty': 2}], menu_names)
    assert len(r) == 1
    assert r[0]['name'] == '冰峰汽水'
    assert r[0]['qty'] == 2

    # 大小份拼接
    r = _normalize_items([{'dish': '牛肉泡馍', 'size': '大份', 'qty': 1}], menu_names)
    assert r[0]['name'] == '牛肉泡馍(大份)'

    # 不存在的菜名被丢弃（防幻觉）
    r = _normalize_items([{'dish': '佛跳墙', 'qty': 1}], menu_names)
    assert r == []

    # qty 边界
    r = _normalize_items([{'dish': '冰峰汽水', 'qty': 999}], menu_names)
    assert r[0]['qty'] == 50  # 上限
    r = _normalize_items([{'dish': '冰峰汽水', 'qty': -5}], menu_names)
    assert r[0]['qty'] == 1  # 下限


def test_llm_parser_extract_json():
    """JSON 提取（含 markdown 包裹）"""
    from services.llm_parser import _extract_json

    # 纯 JSON
    r = _extract_json('{"action": "place_order"}')
    assert r['action'] == 'place_order'

    # 带前后文字
    r = _extract_json('好的，这是结果：{"action": "chat"} 请查收')
    assert r['action'] == 'chat'

    # 无效
    r = _extract_json('not json at all')
    assert r is None

    r = _extract_json('')
    assert r is None
