# routes/api_routes.py
from flask import Blueprint, request, g
from services.menu_service import menu_service
from services.message_service import message_service
from services.chat_service import chat_service
from services.order_service import order_service
from services.auth_service import auth_service
from services.rag_service import chat_plain, rebuild_knowledge_base
from utils.response import success, error
from utils.exceptions import BizError
from utils.auth import login_required
from services.session_service import session_service

api_bp = Blueprint('api', __name__, url_prefix='/api')




# ============================================
# AI 对话记录落库（异步 fire-and-forget，不阻塞响应）
# ============================================
def _log_chat_async(uid, question, answer, intent='other', elapsed_ms=0, is_hit=1):
    """写一条 chat_logs 记录。失败不影响主流程。"""
    try:
        from repositories.instances import chat_log_repo
        from datetime import datetime
        chat_log_repo.create({
            'uid': uid,
            'question': (question or '')[:200],
            'answer': (answer or '')[:500],
            'intent': intent or 'other',
            'elapsed_ms': round(float(elapsed_ms or 0), 1),
            'is_hit': 1 if is_hit else 0,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
    except Exception as e:
        from utils.logger import logger
        logger.warning(f'chat_log 写入失败: {e}')

@api_bp.route('/menu')
def api_menu():
    return success(data=menu_service.get_all())


@api_bp.route('/message', methods=['POST'])
def api_message():
    data = request.get_json(silent=True) or request.form.to_dict()
    message_service.create(
        name=data.get('name'),
        content=data.get('content'),
    )
    return success(msg='收到，谢谢')


@api_bp.route('/chat', methods=['POST'])
def api_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or '').strip()
    if not msg:
        return error(400, '消息不能为空')

    # 可选：解析 token（不带也能聊）
    uid = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            payload = auth_service.verify_token(auth_header[7:].strip())
            uid = payload['uid']
        except BizError:
            pass  # token 过期/无效，当匿名处理

    table_no = (data.get('table_no') or '外带').strip()[:10]
    import time as _t
    _t0 = _t.time()
    result = chat_service.chat(msg, uid=uid, table_no=table_no)
    _elapsed = (_t.time() - _t0) * 1000

    # 异步落库（同步写，但异常被吞掉）
    _log_chat_async(
        uid=uid,
        question=msg,
        answer=result.get('reply', ''),
        intent=result.get('intent', 'other'),
        elapsed_ms=_elapsed,
    )
    return success(data=result)


@api_bp.route('/chat_plain', methods=['POST'])
def api_chat_plain():
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or '').strip()
    if not msg:
        return error(400, '消息不能为空')
    answer = chat_plain(msg)
    return success(data={'reply': answer})


@api_bp.route('/kb_rebuild', methods=['POST'])
def api_kb_rebuild():
    rebuild_knowledge_base()
    return success(msg='知识库已重建')


# ============================================
# 用户订单
# ============================================
@api_bp.route('/user/orders', methods=['GET'])
@login_required
def my_orders():
    orders = order_service.get_by_uid(g.uid)
    return success(data=orders)



@api_bp.route('/chat/clear', methods=['POST'])
def chat_clear():
    """清空当前用户的对话历史"""
    data = request.get_json(silent=True) or {}
    uid = data.get('uid')  # 可选，不传则清匿名
    session_service.clear(uid)
    return success(msg='对话已清空')

from flask import Response
import json as _json


@api_bp.route('/chat/stream', methods=['POST'])
def api_chat_stream():
    """AI 对话（SSE 流式）"""
    data = request.get_json(silent=True) or {}
    msg = (data.get('message') or '').strip()
    if not msg:
        return error(400, '消息不能为空')

    # 可选解析 token
    uid = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            payload = auth_service.verify_token(auth_header[7:].strip())
            uid = payload['uid']
        except BizError:
            pass

    def generate():
        import time as _t
        _t0 = _t.time()
        _full_text = ''
        _intent = 'other'
        try:
            table_no = (data.get('table_no') or '外带').strip()[:10]
            for typ, content in chat_service.chat_stream(msg, uid=uid, table_no=table_no):
                if typ == 'meta':
                    if isinstance(content, dict) and content.get('intent'):
                        _intent = content.get('intent')
                    yield f"event: meta\ndata: {_json.dumps(content, ensure_ascii=False)}\n\n"
                elif typ == 'text':
                    _full_text += (content or '')
                    yield f"event: text\ndata: {_json.dumps({'text': content}, ensure_ascii=False)}\n\n"
                elif typ == 'done':
                    yield "event: done\ndata: {}\n\n"
                    break

            # 流结束，落库
            _log_chat_async(
                uid=uid,
                question=msg,
                answer=_full_text,
                intent=_intent,
                elapsed_ms=(_t.time() - _t0) * 1000,
            )
        except Exception as e:
            yield f"event: error\ndata: {_json.dumps({'msg': str(e)}, ensure_ascii=False)}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        }
    )

# ============================================
# 用户取消订单（凭订单号）
# ============================================
@api_bp.route('/order/<order_id>/cancel', methods=['POST'])
def cancel_order(order_id):
    order = order_service.get(order_id)
    if not order:
        return error(404, '订单不存在')

    # ---- 无条件要求登录 ----
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return error(401, '请先登录后再取消订单')
    try:
        payload = auth_service.verify_token(auth_header[7:].strip())
    except BizError:
        return error(401, '登录已过期，请重新登录')

    order_uid = order.get('uid')
    if not order_uid:
        # 历史匿名订单：本系统现在要求登录才能操作
        return error(403, '此订单为历史匿名订单，无法在线取消，请联系店员')
    if payload.get('uid') != order_uid:
        return error(403, '无权取消他人的订单')

    status = order.get('status', 'pending')
    if status not in ('pending', 'paid'):
        return error(400, '当前状态（' + status + '）无法取消，请找店员处理')

    try:
        updated = order_service.update_status(order_id, 'cancelled')
        return success(data=updated, msg='订单已取消')
    except BizError as e:
        return error(e.code, e.msg)


# ============================================
# 模拟付款（真实场景应接支付网关）
# ============================================
@api_bp.route('/order/<order_id>/pay', methods=['POST'])
def pay_order(order_id):
    order = order_service.get(order_id)
    if not order:
        return error(404, '订单不存在')

    # 必须登录
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return error(401, '请先登录后再付款')
    try:
        payload = auth_service.verify_token(auth_header[7:].strip())
    except BizError:
        return error(401, '登录已过期，请重新登录')

    order_uid = order.get('uid')
    if not order_uid:
        return error(403, '此订单为历史匿名订单，无法付款')
    if payload.get('uid') != order_uid:
        return error(403, '无权支付他人的订单')

    if order.get('status') != 'pending':
        return error(400, '当前状态（' + order['status'] + '）无法付款')

    try:
        updated = order_service.update_status(order_id, 'paid')
        return success(data=updated, msg='付款成功，积分已到账')
    except BizError as e:
        return error(e.code, e.msg)
