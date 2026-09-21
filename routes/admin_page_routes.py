# routes/admin_page_routes.py
"""后台管理页面路由（与知识库 API 的 admin_bp 并存）"""
from flask import (
    Blueprint, request, jsonify, render_template, make_response, g, Response
)
from io import StringIO
import csv

from services.admin_service import admin_service
from utils.admin_auth import (
    create_admin_token, admin_login_required, COOKIE_NAME,
)
from utils.exceptions import BizError

admin_page_bp = Blueprint('admin_page', __name__, url_prefix='/admin')


@admin_page_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('admin/login.html')

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    user = admin_service.verify_login(username, password)
    if not user:
        return jsonify(code=1, msg='用户名或密码错误'), 401

    token = create_admin_token(user['id'], user['username'], user.get('role', 'owner'))
    admin_service.log_action(user['id'], 'login', ip=request.remote_addr)

    resp = make_response(jsonify(code=0, msg='登录成功', data={
        'username': user['username'],
        'role': user.get('role', 'owner'),
    }))
    resp.set_cookie(COOKIE_NAME, token, httponly=True,
                    max_age=24 * 3600, samesite='Lax')
    return resp


@admin_page_bp.route('/logout', methods=['POST'])
def logout():
    resp = make_response(jsonify(code=0, msg='已退出'))
    resp.delete_cookie(COOKIE_NAME)
    return resp


@admin_page_bp.route('/')
@admin_page_bp.route('/dashboard')
@admin_login_required
def dashboard():
    stats = admin_service.dashboard_stats()
    events = admin_service.get_event_stats()
    return render_template('admin/dashboard.html', stats=stats, events=events, admin=g.admin)


@admin_page_bp.route('/api/stats')
@admin_login_required
def api_stats():
    return jsonify(code=0, data=admin_service.dashboard_stats())
# ============================================
# P2 · 订单管理
# ============================================
@admin_page_bp.route('/orders')
@admin_login_required
def orders_page():
    return render_template('admin/orders.html', admin=g.admin)


@admin_page_bp.route('/api/orders')
@admin_login_required
def api_orders():
    status = request.args.get('status') or None
    date = request.args.get('date') or None
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    data = admin_service.get_orders(
        status=status, date=date, page=page, page_size=page_size)
    return jsonify(code=0, data=data)


@admin_page_bp.route('/api/orders/<order_id>/status', methods=['POST'])
@admin_login_required
def api_order_status(order_id):
    data = request.get_json(silent=True) or {}
    new_status = (data.get('status') or '').strip()
    if not new_status:
        return jsonify(code=1, msg='缺少 status'), 400
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        order = admin_service.update_order_status(order_id, new_status, admin_id)
        return jsonify(code=0, data=order, msg='已更新')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


@admin_page_bp.route('/api/orders/export')
@admin_login_required
def api_orders_export():
    data = admin_service.get_orders(page=1, page_size=99999)
    rows = data['items']

    buf = StringIO()
    buf.write('\ufeff')  # Excel 中文 BOM
    writer = csv.writer(buf)
    writer.writerow(['订单号', '用户', '桌号', '菜品', '总额', '状态', '下单时间'])
    for o in rows:
        items_str = '; '.join(
            f"{it.get('name')}×{it.get('qty')}" for it in o.get('items', []))
        writer.writerow([
            o.get('id', ''),
            o.get('uid') or '匿名',
            o.get('table_no') or '外带',
            items_str,
            o.get('total', 0),
            o.get('status', ''),
            o.get('created_at', ''),
        ])

    return Response(
        buf.getvalue(),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition':
                 'attachment; filename=orders.csv'}
    )


# ============================================
# P2 · AI 记录
# ============================================
@admin_page_bp.route('/chat-logs')
@admin_login_required
def chat_logs_page():
    return render_template('admin/chat-logs.html', admin=g.admin)


@admin_page_bp.route('/api/chat-logs')
@admin_login_required
def api_chat_logs():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    data = admin_service.get_chat_logs(page=page, page_size=page_size)
    return jsonify(code=0, data=data)

# ============================================
# P2 · 知识库管理页（原 /admin/kb 迁移过来）
# ============================================
@admin_page_bp.route('/kb')
@admin_login_required
def kb_page():
    return render_template('admin/kb.html', admin=g.admin)


# ============================================
# P3 · 用户管理
# ============================================
@admin_page_bp.route('/users')
@admin_login_required
def users_page():
    return render_template('admin/users.html', admin=g.admin)


@admin_page_bp.route('/api/users')
@admin_login_required
def api_users():
    keyword = request.args.get('keyword') or None
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    data = admin_service.get_users(keyword=keyword, page=page,
                                    page_size=page_size)
    return jsonify(code=0, data=data)


@admin_page_bp.route('/api/users/<uid>/points', methods=['POST'])
@admin_login_required
def api_user_points(uid):
    data = request.get_json(silent=True) or {}
    try:
        delta = int(data.get('delta', 0))
    except (ValueError, TypeError):
        return jsonify(code=1, msg='积分必须是整数'), 400
    if delta == 0:
        return jsonify(code=1, msg='积分变动不能为 0'), 400
    reason = (data.get('reason') or '后台调整').strip()[:50]
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.adjust_points(uid, delta, reason, admin_id)
        return jsonify(code=0, data=result, msg='已调整')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


@admin_page_bp.route('/api/users/<uid>/disabled', methods=['POST'])
@admin_login_required
def api_user_disabled(uid):
    data = request.get_json(silent=True) or {}
    disabled = bool(data.get('disabled'))
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.toggle_user_disabled(uid, disabled, admin_id)
        return jsonify(code=0, data=result,
                       msg='已禁用' if disabled else '已启用')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


# ============================================
# P3 · 留言管理
# ============================================
@admin_page_bp.route('/messages')
@admin_login_required
def messages_page():
    return render_template('admin/messages.html', admin=g.admin)


@admin_page_bp.route('/api/messages')
@admin_login_required
def api_messages():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    unread_only = request.args.get('unread') == '1'
    data = admin_service.get_messages(page=page, page_size=page_size,
                                       unread_only=unread_only)
    return jsonify(code=0, data=data)


@admin_page_bp.route('/api/messages/<int:msg_id>/read', methods=['POST'])
@admin_login_required
def api_message_read(msg_id):
    data = request.get_json(silent=True) or {}
    read = bool(data.get('read', True))
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.mark_message_read(msg_id, read, admin_id)
        return jsonify(code=0, data=result,
                       msg='已标记已读' if read else '已标记未读')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


# ============================================
# P3 · 操作日志
# ============================================
@admin_page_bp.route('/logs')
@admin_login_required
def logs_page():
    return render_template('admin/logs.html', admin=g.admin)


@admin_page_bp.route('/api/logs')
@admin_login_required
def api_logs():
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 30))
    data = admin_service.get_admin_logs(page=page, page_size=page_size)
    return jsonify(code=0, data=data)


# ============================================
# P4 · 知识库版本历史
# ============================================
@admin_page_bp.route('/api/kb/versions')
@admin_login_required
def api_kb_versions():
    filename = request.args.get('filename') or None
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    data = admin_service.get_kb_versions(
        filename=filename, page=page, page_size=page_size)
    return jsonify(code=0, data=data)


@admin_page_bp.route('/api/kb/versions/<int:version_id>')
@admin_login_required
def api_kb_version_detail(version_id):
    v = admin_service.get_kb_version(version_id)
    if not v:
        return jsonify(code=1, msg='版本不存在'), 404
    return jsonify(code=0, data=v)


@admin_page_bp.route('/api/kb/rollback/<int:version_id>', methods=['POST'])
@admin_login_required
def api_kb_rollback(version_id):
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.rollback_kb_version(version_id, admin_id)
        return jsonify(code=0, data=result,
                       msg=f'已回滚到 v{result["version"]}')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


# ============================================
# P5 · 桌码管理
# ============================================
@admin_page_bp.route('/tables')
@admin_login_required
def tables_page():
    return render_template('admin/tables.html', admin=g.admin)


@admin_page_bp.route('/api/tables')
@admin_login_required
def api_tables():
    return jsonify(code=0, data=admin_service.get_tables())


@admin_page_bp.route('/api/tables', methods=['POST'])
@admin_login_required
def api_table_create():
    data = request.get_json(silent=True) or {}
    table_no = (data.get('table_no') or '').strip()
    try:
        result = admin_service.create_table(table_no)
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        if admin_id:
            admin_service.log_action(admin_id, 'create_table',
                                     target=table_no)
        return jsonify(code=0, data=result, msg='已创建')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


@admin_page_bp.route('/api/tables/<int:tid>', methods=['DELETE'])
@admin_login_required
def api_table_delete(tid):
    try:
        result = admin_service.delete_table(tid)
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        if admin_id:
            admin_service.log_action(admin_id, 'delete_table',
                                     target=str(result.get('table_no', tid)))
        return jsonify(code=0, msg='已删除')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


@admin_page_bp.route('/api/tables/<table_no>/qrcode.png')
@admin_login_required
def api_table_qrcode(table_no):
    """生成桌码 PNG（含 URL 拼接：/?table=<table_no>）"""
    import qrcode
    from io import BytesIO

    base = request.args.get('base') or request.url_root.rstrip('/')
    if not base.startswith(('http://', 'https://')):
        base = 'http://' + base
    url = base.rstrip('/') + '/?table=' + table_no

    img = qrcode.make(url)
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)

    return Response(
        buf.getvalue(),
        mimetype='image/png',
        headers={
            'Content-Disposition':
                'inline; filename="table_' + table_no + '.png"',
            'Cache-Control': 'no-cache',
        }
    )
