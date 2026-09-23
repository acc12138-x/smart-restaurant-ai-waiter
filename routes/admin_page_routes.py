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
    get_current_admin,
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

    # 限流：按 IP + 用户名分别计数
    ip_key = 'ip:' + (request.remote_addr or 'unknown')
    user_key = 'user:' + username if username else ''
    if not admin_service.check_login_limit(ip_key) or \
       (user_key and not admin_service.check_login_limit(user_key)):
        n = max(admin_service.get_login_fail_count(ip_key),
                admin_service.get_login_fail_count(user_key))
        return jsonify(code=1,
                       msg=f'登录失败次数过多（已 {n} 次），请 15 分钟后再试'), 429

    user = admin_service.verify_login(username, password)
    if not user:
        admin_service.record_login_fail(ip_key)
        if user_key:
            admin_service.record_login_fail(user_key)
        return jsonify(code=1, msg='用户名或密码错误'), 401

    # 登录成功清除失败计数
    admin_service.clear_login_fails(ip_key)
    if user_key:
        admin_service.clear_login_fails(user_key)

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


@admin_page_bp.route('/api/messages/<int:msg_id>', methods=['DELETE'])
@admin_login_required
def api_message_delete(msg_id):
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        admin_service.delete_message(msg_id, admin_id)
        return jsonify(code=0, msg='已删除')
    except BizError as e:
        return jsonify(code=1, msg=e.msg), e.code


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


# ============================================
# v3.1 · 菜单管理
# ============================================
@admin_page_bp.route('/menu')
@admin_login_required
def menu_admin_page():
    return render_template('admin/menu.html', admin=g.admin)


@admin_page_bp.route('/api/menu')
@admin_login_required
def api_menu_list():
    return jsonify(code=0, data=admin_service.get_menu())


@admin_page_bp.route('/api/menu/item', methods=['POST'])
@admin_login_required
def api_menu_save():
    data = request.get_json(silent=True) or {}
    category = (data.get('category') or '').strip()
    raw = data.get('item') or {}
    old_name = (data.get('old_name') or '').strip() or None

    if not category:
        return jsonify(code=1, msg='分类不能为空'), 400
    name = (raw.get('name') or '').strip()
    if not name:
        return jsonify(code=1, msg='菜名不能为空'), 400

    price_str = str(raw.get('price') or '').strip()
    try:
        price_val = float(price_str)
        if price_val <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(code=1, msg='价格必须是正数'), 400

    item_clean = {
        'name': name,
        'desc': (raw.get('desc') or '').strip(),
        'price': price_str,
        'emoji': (raw.get('emoji') or '🍜').strip()[:4] or '🍜',
    }

    # v3.8 库存：空/null 表示无限
    stock_raw = raw.get('stock', None)
    if stock_raw is None or str(stock_raw).strip() == '':
        pass  # 不加 stock 字段 = 无限
    else:
        try:
            stk = int(stock_raw)
            if stk < 0:
                stk = 0
            item_clean['stock'] = stk
        except (ValueError, TypeError):
            return jsonify(code=1, msg='库存必须是整数'), 400

    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.save_menu_item(category, item_clean, old_name, admin_id)
        return jsonify(code=0, data=result, msg='已保存')
    except Exception as e:
        return jsonify(code=1, msg=str(e)), 400


@admin_page_bp.route('/api/menu/item', methods=['DELETE'])
@admin_login_required
def api_menu_delete():
    data = request.get_json(silent=True) or {}
    category = (data.get('category') or '').strip()
    name = (data.get('name') or '').strip()
    if not category or not name:
        return jsonify(code=1, msg='参数缺失'), 400
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        admin_service.delete_menu_item(category, name, admin_id)
        return jsonify(code=0, msg='已删除')
    except Exception as e:
        return jsonify(code=1, msg=str(e)), 400


@admin_page_bp.route('/api/menu/category', methods=['POST'])
@admin_login_required
def api_menu_add_category():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(code=1, msg='分类名不能为空'), 400
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        result = admin_service.add_menu_category(name, admin_id)
        return jsonify(code=0, data=result, msg='已添加')
    except Exception as e:
        return jsonify(code=1, msg=str(e)), 400


@admin_page_bp.route('/api/menu/category', methods=['DELETE'])
@admin_login_required
def api_menu_delete_category():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(code=1, msg='分类名不能为空'), 400
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        admin_service.delete_menu_category(name, admin_id)
        return jsonify(code=0, msg='已删除')
    except Exception as e:
        return jsonify(code=1, msg=str(e)), 400


# ============================================
# v3.9 · 首页 Hero 配置
# ============================================
@admin_page_bp.route('/hero-setting')
@admin_login_required
def hero_setting_page():
    return render_template('admin/hero-setting.html', admin=g.admin)


@admin_page_bp.route('/api/hero', methods=['GET'])
@admin_login_required
def api_hero_get():
    import json as _json
    from services.settings_service import settings_service

    def _load(key, default):
        raw = settings_service.get(key)
        try:
            return _json.loads(raw) if raw else default
        except Exception:
            return default

    return jsonify(code=0, data={
        'items': _load('hero_items', []),
        'labels': _load('hero_labels', []),
        'autoplay_ms': settings_service.get_int('hero_autoplay_ms', 8000),
    })


@admin_page_bp.route('/api/hero', methods=['POST'])
@admin_login_required
def api_hero_save():
    import json as _json
    from services.settings_service import settings_service

    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    labels = data.get('labels', [])
    autoplay = data.get('autoplay_ms', 8000)

    if not isinstance(items, list) or not isinstance(labels, list):
        return jsonify(code=1, msg='参数格式错误'), 400

    try:
        autoplay = int(autoplay)
        if autoplay < 2000: autoplay = 2000
        if autoplay > 30000: autoplay = 30000
    except (ValueError, TypeError):
        autoplay = 8000

    clean_items = []
    for it in items:
        if not isinstance(it, dict): continue
        dish = (it.get('dish') or '').strip()
        video = (it.get('video') or '').strip()
        label = (it.get('label') or '').strip()
        if not dish or not video: continue
        clean_items.append({'dish': dish, 'video': video, 'label': label})

    clean_labels = []
    for lb in labels[:3]:
        if not isinstance(lb, dict): continue
        name = (lb.get('name') or '').strip()
        cat = (lb.get('category') or '').strip()
        if name and cat:
            clean_labels.append({'name': name, 'category': cat})

    settings_service.set('hero_items', _json.dumps(clean_items, ensure_ascii=False))
    settings_service.set('hero_labels', _json.dumps(clean_labels, ensure_ascii=False))
    settings_service.set('hero_autoplay_ms', str(autoplay))

    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        if admin_id:
            admin_service.log_action(admin_id, 'hero_update',
                                     target=str(len(clean_items)) + ' videos')
    except Exception:
        pass

    return jsonify(code=0, msg='已保存')


@admin_page_bp.route('/api/hero/upload', methods=['POST'])
@admin_login_required
def api_hero_upload():
    import os as _os
    import time as _t
    from configs.config import get_config
    cfg = get_config()

    if 'file' not in request.files:
        return jsonify(code=1, msg='没有上传文件'), 400
    f = request.files['file']
    if not f.filename:
        return jsonify(code=1, msg='文件名为空'), 400

    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('mp4', 'webm', 'mov'):
        return jsonify(code=1, msg='只支持 mp4 / webm / mov'), 400

    hero_dir = _os.path.join(cfg.BASE_DIR, 'static', 'video', 'hero')
    _os.makedirs(hero_dir, exist_ok=True)

    safe_name = 'hero_' + str(int(_t.time() * 1000)) + '.' + ext
    path = _os.path.join(hero_dir, safe_name)
    f.save(path)

    size_mb = _os.path.getsize(path) / 1024 / 1024

    return jsonify(code=0, msg='上传成功', data={
        'video': '/static/video/hero/' + safe_name,
        'filename': safe_name,
        'size_mb': round(size_mb, 2),
    })


@admin_page_bp.route('/api/hero/video/<filename>', methods=['DELETE'])
@admin_login_required
def api_hero_video_delete(filename):
    import os as _os
    from configs.config import get_config
    cfg = get_config()

    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify(code=1, msg='非法文件名'), 400

    hero_dir = _os.path.join(cfg.BASE_DIR, 'static', 'video', 'hero')
    path = _os.path.join(hero_dir, filename)
    if not _os.path.abspath(path).startswith(_os.path.abspath(hero_dir)):
        return jsonify(code=1, msg='非法路径'), 400

    if _os.path.exists(path):
        _os.remove(path)
        return jsonify(code=0, msg='已删除')
    return jsonify(code=1, msg='文件不存在'), 404


# ============================================
# v3.8 · 应用日志
# ============================================
@admin_page_bp.route('/api/app-logs')
@admin_login_required
def api_app_logs():
    level = request.args.get('level') or None
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 30))
    data = admin_service.get_app_logs(level=level, page=page, page_size=page_size)
    return jsonify(code=0, data=data)


@admin_page_bp.route('/api/app-logs/slow')
@admin_login_required
def api_app_logs_slow():
    limit = int(request.args.get('limit', 10))
    return jsonify(code=0, data=admin_service.get_slow_requests(limit=limit))


@admin_page_bp.route('/api/app-logs/stats')
@admin_login_required
def api_app_logs_stats():
    return jsonify(code=0, data=admin_service.get_app_log_stats())


# ============================================
# v3.8 · 测试通知
# ============================================
@admin_page_bp.route('/api/test_notify', methods=['POST'])
@admin_login_required
def api_test_notify():
    from services.notify_service import notify_service
    ok, msg = notify_service.test()
    return jsonify(code=0 if ok else 1, msg=msg)


# ============================================
# v3.8 · Excel 导出
# ============================================
@admin_page_bp.route('/api/export/orders.xlsx')
@admin_login_required
def api_export_orders_xlsx():
    from services.export_service import export_service
    buf, fname = export_service.orders()
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={fname}'}
    )


@admin_page_bp.route('/api/export/users.xlsx')
@admin_login_required
def api_export_users_xlsx():
    from services.export_service import export_service
    buf, fname = export_service.users()
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={fname}'}
    )


@admin_page_bp.route('/api/export/points.xlsx')
@admin_login_required
def api_export_points_xlsx():
    from services.export_service import export_service
    buf, fname = export_service.points()
    return Response(
        buf.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename={fname}'}
    )


# ============================================
# v3.8 · 数据趋势
# ============================================
@admin_page_bp.route('/api/stats/trend')
@admin_login_required
def api_stats_trend():
    from repositories.instances import order_repo
    from datetime import datetime, timedelta

    try:
        days = int(request.args.get('days', 7))
    except (ValueError, TypeError):
        days = 7
    if days not in (7, 30):
        days = 7

    orders = order_repo.get_all()
    orders = [o for o in orders if o.get('status') != 'cancelled']

    today = datetime.now().date()
    day_list = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        day_list.append(d.strftime('%Y-%m-%d'))

    rev_by_day = {d: 0.0 for d in day_list}
    cnt_by_day = {d: 0 for d in day_list}
    by_hour = [0] * 24
    heatmap = [[0] * 24 for _ in range(7)]  # 周一=0

    for o in orders:
        ct = o.get('created_at') or ''
        if not ct:
            continue
        try:
            dt = datetime.strptime(ct, '%Y-%m-%d %H:%M:%S')
        except Exception:
            continue
        dstr = dt.strftime('%Y-%m-%d')
        if dstr in rev_by_day:
            rev_by_day[dstr] += float(o.get('total', 0) or 0)
            cnt_by_day[dstr] += 1
        by_hour[dt.hour] += 1
        heatmap[dt.weekday()][dt.hour] += 1

    return jsonify(code=0, data={
        'days': day_list,
        'revenue_by_day': [round(rev_by_day[d], 2) for d in day_list],
        'orders_by_day': [cnt_by_day[d] for d in day_list],
        'orders_by_hour': by_hour,
        'heatmap': heatmap,
    })


# ============================================
# v3.8 · 实时订单看板（SSE）
# ============================================
@admin_page_bp.route('/live')
@admin_login_required
def live_page():
    return render_template('admin/live.html', admin=g.admin)


@admin_page_bp.route('/api/orders/stream')
def api_orders_stream():
    """SSE 推送：每 2 秒推一次全量 pending 订单"""
    import json as _json
    import time as _time
    from repositories.instances import order_repo

    admin = get_current_admin()
    if not admin:
        return jsonify(code=401, msg='未登录'), 401

    def _fetch_all():
        orders = order_repo.get_all()
        orders.sort(key=lambda o: o.get('created_at') or '', reverse=True)
        out = []
        for o in orders[:100]:
            out.append({
                'id': o.get('id'),
                'table_no': o.get('table_no') or '外带',
                'total': o.get('total', 0),
                'status': o.get('status', 'pending'),
                'created_at': o.get('created_at', ''),
                'uid': o.get('uid'),
                'items': [
                    {'name': it.get('name'), 'qty': it.get('qty')}
                    for it in (o.get('items') or [])
                ],
            })
        return out

    def _generate():
        # 心跳：让浏览器确知连接建立
        yield 'event: hello\ndata: {}\n\n'
        while True:
            try:
                payload = _json.dumps(
                    {'orders': _fetch_all()}, ensure_ascii=False)
                yield 'event: orders\ndata: ' + payload + '\n\n'
            except GeneratorExit:
                break
            except Exception as e:
                yield 'event: error\ndata: ' + _json.dumps(
                    {'msg': str(e)}, ensure_ascii=False) + '\n\n'
            _time.sleep(2)

    return Response(
        _generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )


# ============================================
# v3.7 · 系统设置
# ============================================
@admin_page_bp.route('/settings')
@admin_login_required
def settings_page():
    return render_template('admin/settings.html', admin=g.admin)


@admin_page_bp.route('/api/settings')
@admin_login_required
def api_settings_get():
    from services.settings_service import settings_service
    return jsonify(code=0, data=settings_service.get_all(mask_sensitive=True))


@admin_page_bp.route('/api/settings', methods=['POST'])
@admin_login_required
def api_settings_save():
    from services.settings_service import settings_service, DEFAULTS, SENSITIVE_KEYS
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(code=1, msg='参数格式错误'), 400
    allowed = set(DEFAULTS.keys())
    update = {}
    for k, v in data.items():
        if k not in allowed:
            continue
        v = '' if v is None else str(v)
        if k in SENSITIVE_KEYS and (v == '' or '*' in v):
            continue
        update[k] = v
    if not update:
        return jsonify(code=0, msg='没有需要更新的字段')
    settings_service.set_many(update)
    try:
        admin_id = int(g.admin.get('sub')) if g.admin.get('sub') else None
        if admin_id:
            admin_service.log_action(admin_id, 'settings_update', target=','.join(update.keys())[:200])
    except Exception:
        pass
    return jsonify(code=0, msg='已保存 ' + str(len(update)) + ' 项')



@admin_page_bp.route('/api/test_ollama', methods=['POST'])
@admin_login_required
def api_test_ollama():
    """测试 Ollama 模型是否存在"""
    import requests as _req
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify(code=1, msg='模型名不能为空'), 400
    try:
        import os as _os
        host = _os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
        if not host.startswith('http'):
            host = 'http://' + host
        host = host.replace('0.0.0.0', '127.0.0.1').rstrip('/')
        r = _req.post(host + '/api/show', json={'name': name}, timeout=5)
        if r.status_code == 200:
            info = r.json()
            details = info.get('details', {}) or {}
            return jsonify(code=0, msg='模型存在', data={
                'name': name,
                'family': details.get('family', ''),
                'params': details.get('parameter_size', ''),
            })
        else:
            return jsonify(code=1, msg='模型不存在，请用 ollama list 查看')
    except Exception as e:
        return jsonify(code=1, msg='无法连接 Ollama: ' + str(e))



@admin_page_bp.route('/api/test_remote_api', methods=['POST'])
@admin_login_required
def api_test_remote_api():
    """测试远程 OpenAI 兼容 API 是否可用"""
    data = request.get_json(silent=True) or {}
    base_url = (data.get('base_url') or '').strip()
    api_key  = (data.get('key') or '').strip()
    model    = (data.get('model') or '').strip()
    if not base_url or not api_key or not model:
        return jsonify(code=1, msg='base_url / key / model 都要填'), 400
    if not base_url.startswith(('http://', 'https://')):
        return jsonify(code=1, msg='base_url 要以 http:// 或 https:// 开头'), 400
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=10)
        response = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': 'ping'}],
            max_tokens=5,
        )
        return jsonify(code=0, msg='连接成功，模型响应正常')
    except Exception as e:
        return jsonify(code=1, msg='连接失败: ' + str(e)[:200])
