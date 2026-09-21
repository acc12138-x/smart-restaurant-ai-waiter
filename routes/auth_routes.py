# routes/auth_routes.py
from flask import Blueprint, request, g
from services.auth_service import auth_service
from utils.response import success, error
from utils.auth import login_required

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json(silent=True) or {}
    result = auth_service.register(
        username=data.get('username'),
        password=data.get('password'),
        nickname=data.get('nickname'),
    )
    return success(data=result, msg='注册成功')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    result = auth_service.login(
        username=data.get('username'),
        password=data.get('password'),
    )
    return success(data=result, msg='登录成功')


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    member = auth_service.get_by_uid(g.uid)
    if not member:
        return error(404, '用户不存在')
    return success(data=member)