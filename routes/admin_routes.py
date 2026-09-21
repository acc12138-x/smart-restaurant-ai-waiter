# routes/admin_routes.py
"""知识库热更新 + RAG 评估 API"""
import os
from flask import Blueprint, request, jsonify
from services.rag_eval_service import rag_eval_service
from services import rag_service
from utils.response import success, error
from configs.config import get_config

_cfg = get_config()
admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

KB_DIR = _cfg.DOCS_DIR
ADMIN_TOKEN = os.environ.get('ADMIN_TOKEN', 'admin-token-dev')


def _check_admin():
    """简单鉴权：Header X-Admin-Token"""
    token = request.headers.get('X-Admin-Token', '')
    return token == ADMIN_TOKEN


@admin_bp.route('/rag_stats', methods=['GET'])
def rag_stats():
    """RAG 评估数据"""
    if not _check_admin():
        return error(401, '未授权')
    return success(data=rag_eval_service.get_stats())


@admin_bp.route('/kb_files', methods=['GET'])
def kb_files():
    """列出知识库文件"""
    if not _check_admin():
        return error(401, '未授权')
    files = []
    if os.path.exists(KB_DIR):
        for f in os.listdir(KB_DIR):
            if f.endswith(('.md', '.txt')):
                path = os.path.join(KB_DIR, f)
                files.append({
                    'name': f,
                    'size': os.path.getsize(path),
                    'modified': os.path.getmtime(path),
                })
    return success(data=files)


@admin_bp.route('/kb_file', methods=['GET'])
def kb_file_read():
    """读知识库文件"""
    if not _check_admin():
        return error(401, '未授权')
    name = request.args.get('name', '')
    if not name:
        return error(400, '参数错误')
    path = os.path.join(KB_DIR, name)
    if not os.path.abspath(path).startswith(os.path.abspath(KB_DIR)):
        return error(403, '非法路径')
    if not os.path.exists(path):
        return error(404, '文件不存在')
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return success(data={'name': name, 'content': content})


@admin_bp.route('/kb_file', methods=['POST'])
def kb_file_save():
    """保存知识库文件并重建向量库"""
    if not _check_admin():
        return error(401, '未授权')
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    content = data.get('content') or ''

    if not name or not name.endswith(('.md', '.txt')):
        return error(400, '文件名必须以 .md 或 .txt 结尾')

    path = os.path.join(KB_DIR, name)
    if not os.path.abspath(path).startswith(os.path.abspath(KB_DIR)):
        return error(403, '非法路径')

    # 先写历史版本
    try:
        from services.admin_service import admin_service
        admin_service.save_kb_version(name, content)
    except Exception as e:
        print(f'[KB] 保存历史失败: {e}')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

    # 重建向量库
    try:
        rag_service.rebuild_knowledge_base()
    except Exception as e:
        return error(500, f'保存成功但重建失败: {e}')

    return success(msg='已保存并重建知识库')


@admin_bp.route('/kb_file', methods=['DELETE'])
def kb_file_delete():
    """删除知识库文件并重建"""
    if not _check_admin():
        return error(401, '未授权')
    name = request.args.get('name', '')
    if not name:
        return error(400, '参数错误')
    path = os.path.join(KB_DIR, name)
    if not os.path.abspath(path).startswith(os.path.abspath(KB_DIR)):
        return error(403, '非法路径')
    if os.path.exists(path):
        os.remove(path)
        try:
            rag_service.rebuild_knowledge_base()
        except Exception:
            pass
    return success(msg='已删除')