# tests/conftest.py
import os
import sys
import json
import pytest
import tempfile

# 把项目根目录加入 path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture
def temp_data_dir(tmp_path):
    """临时数据目录，测试完自动清理"""
    data_dir = tmp_path / 'data'
    data_dir.mkdir()

    # 复制真实菜单数据
    real_menu = os.path.join(ROOT, 'data', 'menu.json')
    if os.path.exists(real_menu):
        with open(real_menu, 'r', encoding='utf-8') as f:
            menu = json.load(f)
        with open(data_dir / 'menu.json', 'w', encoding='utf-8') as f:
            json.dump(menu, f, ensure_ascii=False)

    # 其他文件初始化为空数组
    for name in ['message.json', 'orders.json', 'events.json', 'members.json']:
        with open(data_dir / name, 'w', encoding='utf-8') as f:
            json.dump([], f)

    return str(data_dir)


@pytest.fixture
def client():
    """Flask 测试客户端"""
    os.environ['FLASK_ENV'] = 'development'
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c