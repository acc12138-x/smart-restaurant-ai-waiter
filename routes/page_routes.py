# routes/page_routes.py
import os
from flask import Blueprint, render_template, jsonify
from services.order_service import order_service

page_bp = Blueprint('page', __name__)


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
    return jsonify({
        'status': 'ok' if ok else 'degraded',
        'checks': checks,
    }), 200 if ok else 503


@page_bp.route('/order/<order_id>')
def order_track_page(order_id):
    """订单跟踪页"""
    order = order_service.get(order_id)
    return render_template('order_track.html',
                           order=order, order_id=order_id)
