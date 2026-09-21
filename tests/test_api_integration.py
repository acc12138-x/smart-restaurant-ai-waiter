# tests/test_api_integration.py
"""API 集成测试：订单取消 / 付款 / 后台 / 桌码（走 Flask test client）"""
import pytest
import json
import uuid


# ============================================================
# 辅助：注册/登录会员，返回 token
# ============================================================
def _register_member(client):
    """注册一个随机用户名，返回 (token, uid)"""
    uname = 'test_' + uuid.uuid4().hex[:8]
    resp = client.post('/api/auth/register', json={
        'username': uname,
        'password': 'pass1234',
        'nickname': '测试员',
    })
    data = resp.get_json()
    if data['code'] != 0:
        return None, None
    return data['data']['token'], data['data']['member']['uid']


def _admin_login(client):
    """登录后台，返回 admin_token cookie"""
    resp = client.post('/admin/login', json={
        'username': 'admin',
        'password': 'admin888',
    })
    return resp.get_json().get('code') == 0


# ============================================================
# 订单取消 API
# ============================================================
def test_cancel_order_without_token(client):
    """未登录不能取消订单"""
    # 先创建一个订单（admin 直接建）
    from services.order_service import order_service
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    oid = result['order']['id']

    resp = client.post(f'/api/order/{oid}/cancel')
    assert resp.status_code == 401
    data = resp.get_json()
    assert '登录' in data['msg']


def test_cancel_order_wrong_uid(client):
    """别人的订单不能取消"""
    from services.order_service import order_service

    # 用户 A 下单
    token_a, uid_a = _register_member(client)
    if not token_a:
        pytest.skip('注册失败')
    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid_a)
    oid = result['order']['id']

    # 用户 B 尝试取消
    token_b, uid_b = _register_member(client)
    if not token_b:
        pytest.skip('注册失败')

    resp = client.post(
        f'/api/order/{oid}/cancel',
        headers={'Authorization': f'Bearer {token_b}'})
    assert resp.status_code == 403
    assert '无权' in resp.get_json()['msg']


def test_cancel_order_success(client):
    """用户取消自己的订单成功"""
    from services.order_service import order_service

    token, uid = _register_member(client)
    if not token:
        pytest.skip('注册失败')

    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid)
    oid = result['order']['id']

    resp = client.post(
        f'/api/order/{oid}/cancel',
        headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert data['data']['status'] == 'cancelled'


def test_cancel_nonexistent_order(client):
    """取消不存在的订单 404"""
    token, _ = _register_member(client)
    if not token:
        pytest.skip('注册失败')

    resp = client.post(
        '/api/order/TSX_NOT_EXIST_XXX/cancel',
        headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 404


# ============================================================
# 付款 API
# ============================================================
def test_pay_without_token(client):
    """未登录不能付款"""
    from services.order_service import order_service
    result = order_service.create([{'name': '冰峰汽水', 'qty': 1}])
    oid = result['order']['id']

    resp = client.post(f'/api/order/{oid}/pay')
    assert resp.status_code == 401


def test_pay_success_and_points_added(client):
    """付款成功后积分增加"""
    from services.order_service import order_service
    from repositories.instances import member_repo

    token, uid = _register_member(client)
    if not token:
        pytest.skip('注册失败')

    before = member_repo.find_by_id(uid).get('points', 0)

    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid)
    oid = result['order']['id']

    resp = client.post(
        f'/api/order/{oid}/pay',
        headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0

    after = member_repo.find_by_id(uid).get('points', 0)
    assert after == before + 6


def test_pay_already_paid(client):
    """已付款订单不能重复付款"""
    from services.order_service import order_service

    token, uid = _register_member(client)
    if not token:
        pytest.skip('注册失败')

    result = order_service.create(
        [{'name': '冰峰汽水', 'qty': 1}], uid=uid)
    oid = result['order']['id']

    # 第一次付款
    resp1 = client.post(
        f'/api/order/{oid}/pay',
        headers={'Authorization': f'Bearer {token}'})
    assert resp1.status_code == 200

    # 第二次付款应失败
    resp2 = client.post(
        f'/api/order/{oid}/pay',
        headers={'Authorization': f'Bearer {token}'})
    assert resp2.status_code == 400


# ============================================================
# 后台 API
# ============================================================
def test_admin_orders_requires_login(client):
    """未登录访问后台订单列表 401"""
    resp = client.get('/admin/api/orders')
    assert resp.status_code in (401, 302)


def test_admin_orders_list(client):
    """登录后可以拿订单列表"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/orders?page=1&page_size=5')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert 'total' in data['data']
    assert 'items' in data['data']


def test_admin_users_list(client):
    """后台用户列表"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/users?page=1&page_size=10')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert 'total' in data['data']


def test_admin_chat_logs(client):
    """后台 AI 记录"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/chat-logs')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0


def test_admin_messages(client):
    """后台留言列表"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/messages')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0


def test_admin_logs(client):
    """后台操作日志"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/logs')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0


def test_admin_orders_export_csv(client):
    """导出 CSV"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.get('/admin/api/orders/export')
    assert resp.status_code == 200
    assert 'text/csv' in resp.content_type
    assert resp.data[:3] == '\xef\xbb\xbf'.encode('latin-1')  # BOM


# ============================================================
# 桌码 API
# ============================================================
def test_tables_list_requires_login(client):
    """未登录访问桌码列表 401"""
    resp = client.get('/admin/api/tables')
    assert resp.status_code in (401, 302)


def test_tables_create_and_qrcode(client):
    """创建桌码 + 生成二维码"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    # 创建
    tno = 'T' + uuid.uuid4().hex[:4]
    resp = client.post('/admin/api/tables', json={'table_no': tno})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert data['data']['table_no'] == tno

    # 拿二维码
    resp2 = client.get(f'/admin/api/tables/{tno}/qrcode.png')
    assert resp2.status_code == 200
    assert resp2.content_type == 'image/png'
    # PNG 文件头
    assert resp2.data[:8] == b'\x89PNG\r\n\x1a\n'


def test_tables_create_duplicate(client):
    """重复桌号报错"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    tno = 'DUP' + uuid.uuid4().hex[:4]
    resp1 = client.post('/admin/api/tables', json={'table_no': tno})
    assert resp1.status_code == 200

    resp2 = client.post('/admin/api/tables', json={'table_no': tno})
    assert resp2.status_code == 400
    assert '已存在' in resp2.get_json()['msg']


def test_tables_create_empty(client):
    """空桌号报错"""
    if not _admin_login(client):
        pytest.skip('admin 登录失败')

    resp = client.post('/admin/api/tables', json={'table_no': ''})
    assert resp.status_code == 400


# ============================================================
# 健康检查
# ============================================================
def test_health(client):
    """健康检查接口"""
    resp = client.get('/health')
    # 200 或 503 都算（取决于 Ollama 是否在线）
    assert resp.status_code in (200, 503)
    data = resp.get_json()
    assert 'status' in data
    assert 'checks' in data
