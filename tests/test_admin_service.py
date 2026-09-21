# tests/test_admin_service.py
"""后台服务测试：管理员 / 订单管理 / 用户 / 留言 / 日志"""
import pytest
from services.admin_service import admin_service
from services.order_service import order_service
from utils.exceptions import BizError


# ============================================================
# 管理员
# ============================================================
def test_create_admin():
    """创建管理员（用户名已存在就跳过）"""
    try:
        result = admin_service.create_admin('test_admin_x', 'pass1234', 'owner')
        assert result['username'] == 'test_admin_x'
    except BizError as e:
        # 已存在也算通过（多次运行）
        assert '已存在' in str(e)


def test_create_admin_short_password():
    """密码太短报错"""
    with pytest.raises(BizError):
        admin_service.create_admin('test_short_pw', '123')


def test_create_admin_empty():
    """用户名或密码为空报错"""
    with pytest.raises(BizError):
        admin_service.create_admin('', '')
    with pytest.raises(BizError):
        admin_service.create_admin('name', '')


def test_verify_login_wrong_password():
    """错误密码返回 None"""
    result = admin_service.verify_login('admin', 'wrong_pw_here')
    assert result is None


def test_verify_login_not_exist():
    """不存在的用户返回 None"""
    result = admin_service.verify_login('nobody_xxx', 'any_pw')
    assert result is None


# ============================================================
# 订单管理
# ============================================================
def test_get_orders_pagination():
    """订单分页"""
    data = admin_service.get_orders(page=1, page_size=5)
    assert 'total' in data
    assert 'items' in data
    assert 'pages' in data
    assert len(data['items']) <= 5


def test_get_orders_filter_status():
    """按状态筛选"""
    data = admin_service.get_orders(status='pending', page=1, page_size=10)
    for o in data['items']:
        assert o['status'] == 'pending'


def test_get_orders_empty_filter():
    """不存在的状态返回空"""
    data = admin_service.get_orders(status='nonexistent_xxx')
    assert data['total'] == 0
    assert data['items'] == []


# ============================================================
# 用户管理
# ============================================================
def test_get_users():
    """用户列表"""
    data = admin_service.get_users(page=1, page_size=10)
    assert 'total' in data
    assert isinstance(data['items'], list)


def test_get_users_keyword():
    """按关键词搜用户"""
    data = admin_service.get_users(keyword='zzz_no_match_xxx')
    assert data['total'] == 0


# ============================================================
# 留言管理
# ============================================================
def test_get_messages():
    """留言列表"""
    data = admin_service.get_messages(page=1, page_size=10)
    assert 'total' in data
    assert 'unread_count' in data


def test_get_messages_unread_only():
    """只看未读"""
    data = admin_service.get_messages(unread_only=True)
    for m in data['items']:
        assert not m.get('read')


# ============================================================
# 操作日志
# ============================================================
def test_get_admin_logs():
    """操作日志列表"""
    data = admin_service.get_admin_logs(page=1, page_size=10)
    assert 'total' in data
    assert isinstance(data['items'], list)
    # 有日志时应带 admin_name
    for lg in data['items']:
        assert 'admin_name' in lg


# ============================================================
# 看板
# ============================================================
def test_dashboard_stats():
    """看板数据完整性"""
    stats = admin_service.dashboard_stats()
    for key in ['order_total', 'order_today', 'revenue_total',
                'revenue_today', 'user_total', 'message_total',
                'chat_total']:
        assert key in stats
        assert isinstance(stats[key], (int, float))


def test_event_stats():
    """流量数据完整性"""
    stats = admin_service.get_event_stats()
    for key in ['total_events', 'total_visitors', 'today',
                'event_distribution', 'page_distribution',
                'intent_distribution', 'hot_questions']:
        assert key in stats
