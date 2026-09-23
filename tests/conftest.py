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


@pytest.fixture(autouse=True)
def clean_stock_before_test():
    """每个测试前把 menu.json 里的 stock 字段清掉（防测试互相扣库存）"""
    import json
    menu_path = os.path.join(ROOT, 'data', 'menu.json')
    backup_path = menu_path + '.testbak'

    if not os.path.exists(menu_path):
        yield
        return

    # 备份
    with open(menu_path, 'rb') as f:
        original_bytes = f.read()

    try:
        # 清 stock
        with open(menu_path, encoding='utf-8') as f:
            menu = json.load(f)
        for cat in menu:
            for it in cat.get('items', []):
                it.pop('stock', None)
        with open(menu_path, 'w', encoding='utf-8') as f:
            json.dump(menu, f, ensure_ascii=False, indent=2)

        # 让 menu_service 重新加载
        try:
            from services.menu_service import menu_service
            menu_service._cache = None
            menu_service._cache_mtime = 0
        except Exception:
            pass

        yield
    finally:
        # 恢复原始文件
        with open(menu_path, 'wb') as f:
            f.write(original_bytes)
        try:
            from services.menu_service import menu_service
            menu_service._cache = None
            menu_service._cache_mtime = 0
        except Exception:
            pass


@pytest.fixture
def client():
    """Flask 测试客户端"""
    os.environ['FLASK_ENV'] = 'development'
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c