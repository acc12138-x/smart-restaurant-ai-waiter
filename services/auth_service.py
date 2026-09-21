# services/auth_service.py
import time
import uuid
import jwt
from werkzeug.security import generate_password_hash, check_password_hash

from repositories.instances import member_repo
from utils.exceptions import BizError
from configs.config import get_config

_cfg = get_config()
SECRET = _cfg.SECRET_KEY
TOKEN_EXPIRE_HOURS = 24


class AuthService:
    """用户认证业务逻辑"""

    def register(self, username: str, password: str, nickname: str = ''):
        """注册新用户"""
        username = (username or '').strip()
        password = (password or '').strip()
        nickname = (nickname or '').strip() or username

        if not username:
            raise BizError('用户名不能为空')
        if len(username) < 3 or len(username) > 20:
            raise BizError('用户名长度 3-20 位')
        if not password or len(password) < 6:
            raise BizError('密码至少 6 位')

        existing = member_repo.find(username=username)
        if existing:
            raise BizError('用户名已被占用')

        uid = str(uuid.uuid4())
        member = {
            'uid': uid,
            'username': username,
            'nickname': nickname,
            'password_hash': generate_password_hash(password),
            'points': 10,
            'level': '新客',
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        member_repo.create(member)

        member_safe = {k: v for k, v in member.items() if k != 'password_hash'}
        token = self._generate_token(uid, username)
        return {'member': member_safe, 'token': token}

    def login(self, username: str, password: str):
        """用户登录"""
        username = (username or '').strip()
        password = (password or '').strip()

        if not username or not password:
            raise BizError('用户名和密码不能为空')

        users = member_repo.find(username=username)
        if not users:
            raise BizError('用户名或密码错误')

        member = users[0]
        if not check_password_hash(member['password_hash'], password):
            raise BizError('用户名或密码错误')

        member_safe = {k: v for k, v in member.items() if k != 'password_hash'}
        token = self._generate_token(member['uid'], member['username'])
        return {'member': member_safe, 'token': token}

    def get_by_uid(self, uid: str):
        """按 uid 查用户（不含密码）"""
        member = member_repo.find_by_id(uid)
        if not member:
            return None
        return {k: v for k, v in member.items() if k != 'password_hash'}

    def _generate_token(self, uid: str, username: str) -> str:
        """生成 JWT"""
        payload = {
            'uid': uid,
            'username': username,
            'exp': int(time.time()) + TOKEN_EXPIRE_HOURS * 3600,
            'iat': int(time.time()),
        }
        return jwt.encode(payload, SECRET, algorithm='HS256')

    def verify_token(self, token: str) -> dict:
        """验证 JWT"""
        try:
            return jwt.decode(token, SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise BizError('登录已过期，请重新登录', code=401)
        except jwt.InvalidTokenError:
            raise BizError('无效的登录凭证', code=401)


auth_service = AuthService()