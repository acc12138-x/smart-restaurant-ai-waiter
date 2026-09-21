# routes/points_routes.py
from flask import Blueprint, request, g
from services.points_service import points_service
from utils.response import success, error
from utils.auth import login_required

points_bp = Blueprint('points', __name__, url_prefix='/api/points')


@points_bp.route('/me', methods=['GET'])
@login_required
def my_points():
    """查我的积分"""
    info = points_service.get_info(g.uid)
    return success(data=info)


@points_bp.route('/exchange', methods=['POST'])
@login_required
def exchange():
    """积分兑换"""
    data = request.get_json(silent=True) or {}
    item_key = (data.get('item') or '').strip()
    if not item_key:
        return error(400, '请指定兑换商品')

    result = points_service.exchange(g.uid, item_key)
    return success(data=result, msg=result['msg'])