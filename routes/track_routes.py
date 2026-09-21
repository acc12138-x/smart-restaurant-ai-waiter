# routes/track_routes.py
from flask import Blueprint, request, g
from services.track_service import track_service
from services.auth_service import auth_service
from utils.response import success
from utils.exceptions import BizError

track_bp = Blueprint('track', __name__, url_prefix='/api')


@track_bp.route('/track', methods=['POST'])
def track():
    """前端埋点上报"""
    data = request.get_json(silent=True) or {}
    event = data.get('event')
    payload = data.get('payload') or {}

    # 可选解析 token
    uid = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            payload_token = auth_service.verify_token(auth_header[7:].strip())
            uid = payload_token['uid']
        except BizError:
            pass

    track_service.track(
        event=event,
        payload=payload,
        uid=uid,
        ip=request.remote_addr,
        ua=request.headers.get('User-Agent'),
    )
    return success()


@track_bp.route('/admin/stats', methods=['GET'])
def admin_stats():
    """看板数据（生产环境应加管理员鉴权）"""
    return success(data=track_service.get_stats())