# utils/auth.py
from functools import wraps
from flask import request, g
from services.auth_service import auth_service
from utils.exceptions import AuthError


def login_required(f):
    """需要登录的接口装饰器"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            raise AuthError('缺少登录凭证')

        token = auth_header[7:].strip()
        if not token:
            raise AuthError('缺少登录凭证')

        payload = auth_service.verify_token(token)
        g.uid = payload['uid']
        g.username = payload['username']
        return f(*args, **kwargs)
    return wrapper