# routes/page_routes.py
import os
import time
from flask import Blueprint, render_template, jsonify
from services.order_service import order_service

page_bp = Blueprint('page', __name__)

# 进程启动时间：与"代码最后修改时间"一比，就知道进程里跑的是不是新代码
_BOOT_TS = time.time()

_SOURCE_GLOBS = (
    'app.py', 'server.py', 'wsgi.py',
    'routes/*.py', 'services/*.py', 'repositories/*.py',
    'utils/*.py', 'configs/*.py',
    'templates/**/*.html', 'static/css/*.css', 'static/js/*.js',
)


def _newest_source_mtime():
    """运行时代码里最新的一个修改时间

    这是判断"拉了代码但没重启"最直接的信号：
    容器挂载的是宿主机源码，`git pull` 后文件 mtime 会变新，
    而已经在跑的 gunicorn 进程仍然加载着旧代码。
    """
    import glob
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    newest = 0.0
    for pat in _SOURCE_GLOBS:
        for f in glob.glob(os.path.join(base, pat), recursive=True):
            try:
                newest = max(newest, os.path.getmtime(f))
            except OSError:
                pass
    return newest


def _git_commit():
    """当前代码的 git 短哈希（直接读 .git，容器里没装 git 也能用）

    compose 默认不挂 .git，读不到就返回 unknown（不影响使用）。
    """
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        git_dir = os.path.join(base, '.git')
        with open(os.path.join(git_dir, 'HEAD'), encoding='utf-8') as f:
            head = f.read().strip()
        if not head.startswith('ref:'):
            return head[:7]
        ref = head.split(' ', 1)[1].strip()
        ref_file = os.path.join(git_dir, *ref.split('/'))
        if os.path.exists(ref_file):
            with open(ref_file, encoding='utf-8') as f:
                return f.read().strip()[:7]
        packed = os.path.join(git_dir, 'packed-refs')
        if os.path.exists(packed):
            with open(packed, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and line.endswith(' ' + ref):
                        return line.split()[0][:7]
        return 'unknown'
    except Exception:
        return 'unknown'


def _fmt_ts(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)) if ts else ''


@page_bp.route('/')
def index():
    return render_template('index.html')


@page_bp.route('/menu')
def menu_page():
    return render_template('menu.html')


@page_bp.route('/chat')
def chat_page():
    return render_template('chat.html')

@page_bp.route('/profile')
def profile_page():
    return render_template('profile.html')

@page_bp.route('/health')
def health():
    checks = {
        'flask': True,
        'vector_store': os.path.exists(os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'vector_store'
        )),
        'ollama': False,
    }
    try:
        import urllib.request
        host = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
        with urllib.request.urlopen(f'{host}/api/tags', timeout=2) as r:
            checks['ollama'] = r.status == 200
    except Exception:
        pass

    ok = all(checks.values())
    newest = _newest_source_mtime()
    # 进程启动早于最后一次代码改动 → 说明拉了代码但没重启，跑的还是旧代码
    stale = bool(newest and newest > _BOOT_TS + 1)
    return jsonify({
        'status': 'ok' if ok else 'degraded',
        'checks': checks,
        'code': {
            'commit': _git_commit(),
            'process_started_at': _fmt_ts(_BOOT_TS),
            'newest_source_mtime': _fmt_ts(newest),
            'stale': stale,
            'hint': ('代码比进程新 —— 拉了代码但没重启，跑的还是旧代码；'
                     '执行 docker compose restart 后重新访问本接口确认'
                     if stale else '进程已加载最新代码'),
        },
    }), 200 if ok else 503


@page_bp.route('/order/<order_id>')
def order_track_page(order_id):
    """订单跟踪页"""
    order = order_service.get(order_id)
    return render_template('order_track.html',
                           order=order, order_id=order_id)
