# app.py
import os
import gzip
from flask import Flask, request
from configs.config import get_config
from utils.logger import logger
from utils.response import error
from utils.exceptions import BizError
from routes import (page_bp, api_bp, auth_bp, points_bp, track_bp, docs_bp, admin_bp, admin_page_bp)

# ============================================
# 创建 app
# ============================================
app = Flask(__name__)
app.config.from_object(get_config())
app.json.ensure_ascii = False


# ============================================
# Gzip 压缩
# ============================================
@app.after_request
def gzip_response(response):
    if response.mimetype == 'text/event-stream':
        return response
    try:
        ctype = response.content_type or ''
    except Exception:
        return response

    compressible = (
        ctype.startswith('text/') or
        ctype.startswith('application/json') or
        ctype.startswith('application/javascript') or
        ctype.startswith('application/xml') or
        ctype.startswith('image/svg')
    )
    if not compressible:
        return response
    if response.status_code != 200:
        return response
    if 'gzip' not in request.headers.get('Accept-Encoding', ''):
        return response
    if response.headers.get('Content-Encoding'):
        return response

    try:
        data = response.get_data()
    except Exception:
        return response

    if len(data) < 500:
        return response

    gzipped = gzip.compress(data)
    response.set_data(gzipped)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(gzipped)
    response.headers['Vary'] = 'Accept-Encoding'
    return response


# ============================================
# 慢请求监控（v3.8）
# ============================================
SLOW_THRESHOLD_MS = 3000


@app.before_request
def _mark_start():
    from time import time
    request._tsx_start = time()


@app.after_request
def _log_slow(response):
    from time import time
    t0 = getattr(request, '_tsx_start', None)
    if t0 is None:
        return response
    if (response.content_type or '').startswith('text/event-stream'):
        return response
    elapsed = (time() - t0) * 1000
    if elapsed >= SLOW_THRESHOLD_MS:
        uid = None
        try:
            from flask import g
            uid = getattr(g, 'uid', None)
        except Exception:
            pass
        logger.warning(
            '慢请求 %.0fms %s %s' % (elapsed, request.method, request.path),
            extra={
                'elapsed_ms': round(elapsed, 1),
                'url': request.path,
                'method': request.method,
                'ip': request.remote_addr,
                'uid': uid,
            }
        )
    return response


# ============================================
# 全局异常处理
# ============================================
@app.errorhandler(BizError)
def handle_biz_error(e):
    logger.warning(f"业务异常: {e.msg}")
    return error(e.code, e.msg)


@app.errorhandler(Exception)
def handle_error(e):
    logger.error(
        '未捕获异常: %s %s %s' % (request.method, request.path, str(e)),
        exc_info=True,
        extra={
            'url': request.path,
            'method': request.method,
            'ip': request.remote_addr,
        }
    )
    return error(500, '服务器内部错误')


@app.errorhandler(404)
def handle_404(e):
    return error(404, '接口不存在')


# ============================================
# 注册 Blueprint（必须在 app 创建之后）
# ============================================
app.register_blueprint(page_bp)
app.register_blueprint(api_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(track_bp)
app.register_blueprint(points_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(admin_page_bp)
# ============================================
# 预热函数
# ============================================
def warmup():
    """预热 AI 服务：对话模型 + 嵌入模型 + 向量库"""
    import os
    logger.info("=== 正在预热 AI 服务 ===")
    try:
        from services.rag_service import get_llm, get_embeddings, load_or_build_vectorstore

        # 1. 对话模型（Qwen3-4B）
        logger.info("--- 加载对话模型 ---")
        get_llm()

        # 2. 嵌入模型（bge-m3）+ 向量库
        # 显存紧张时设 WARMUP_EMBED=0 跳过
        if os.environ.get('WARMUP_EMBED', '1') == '1':
            logger.info("--- 加载嵌入模型 ---")
            get_embeddings()
            logger.info("--- 加载向量库 ---")
            load_or_build_vectorstore()

        logger.info("=== 预热完成 ===")
    except Exception as e:
        logger.warning(f"=== AI 预热失败（不影响其他功能）: {e} ===")

# 模块加载时自动预热（Gunicorn 也会触发）
# CI 环境设 SKIP_WARMUP=1 跳过（无 Ollama 时不拖时间）
if os.environ.get('SKIP_WARMUP', '0') != '1':
    try:
        warmup()
    except Exception as e:
        print(f"预热失败: {e}")
else:
    print("[SKIP] SKIP_WARMUP=1，跳过 AI 预热")


# ============================================
# 启动
# ============================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
