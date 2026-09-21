# scripts/init_admin.py
"""初始化默认管理员账号（只跑一次）"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from services.admin_service import admin_service
from utils.exceptions import BizError

try:
    admin_service.create_admin('admin', 'admin888', 'owner')
    print('管理员创建成功：admin / admin888')
    print('  上线前请立即改密码')
except BizError as e:
    print(f'提示：{e}（可能已存在，无需重复创建）')
