# tests/test_menu.py
from services.menu_service import menu_service


def test_get_all_menu():
    """菜单不为空"""
    menu = menu_service.get_all()
    assert isinstance(menu, list)
    assert len(menu) >= 3


def test_menu_has_categories():
    """包含三个分类"""
    cats = menu_service.get_categories()
    assert '招牌泡馍' in cats
    assert '经典小吃' in cats
    assert '清爽搭配' in cats


def test_find_dish_exact():
    """精确匹配"""
    dish = menu_service.find_dish('牛肉泡馍(小份)')
    assert dish is not None
    assert dish['price'] == 24


def test_find_dish_fuzzy():
    """模糊匹配：去掉量词"""
    dish = menu_service.find_dish('一份牛肉泡馍(小份)')
    assert dish is not None
    assert '牛肉泡馍' in dish['name']


def test_find_dish_not_found():
    """查不到返回 None"""
    dish = menu_service.find_dish('佛跳墙')
    assert dish is None


def test_flat_list():
    """扁平列表包含所有菜品"""
    flat = menu_service.get_flat()
    assert len(flat) >= 15
    names = [d['name'] for d in flat]
    assert '牛肉泡馍(小份)' in names
    assert '冰峰汽水' in names