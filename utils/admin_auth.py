# utils/admin_auth.py
"""后台管理员 JWT 鉴权（与会员 auth.py 分离）"""
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request, jsonify, redirect, g

SECRET_KEY = os.environ.get('ADMIN_SECRET_KEY', 'tsx-admin-dev-secret-change-me-please-override-in-prod-32bytes')
ALGORITHM = 'HS256'
TOKEN_EXPIRE_HOURS = 24
COOKIE_NAME = 'admin_token'


def create_admin_token(admin_id, username, role='owner'):
    payload = {
        'sub': str(admin_id),
        'username': username,
        'role': role,
        'iat': datetime.now(timezone.utc),
        'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_admin_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_admin():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:].strip()
    if not token:
        return None
    return decode_admin_token(token)


def admin_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin = get_current_admin()
        if not admin:
            if request.path.startswith('/api/'):
                return jsonify(code=401, msg='未登录'), 401
            return redirect('/admin/login')
        g.admin = admin
        return view(*args, **kwargs)
    return wrapped
