# tests/test_unknown_dish_gate.py
"""未知菜名拦截的回归测试

背景：intent == 'other' 会走知识库兜底，但原先它也要过"未知菜名"检测 ——
"你们家的羊从哪来"这种剥离疑问词后只剩 2-8 个汉字的问句会被当成菜名，
回一句"菜单里没有「…」哦～"，永远到不了知识库（实测：知识库写了宁夏滩羊，
却答成"陕北现宰"）。
"""
from services.chat_service import SKIP_UNKNOWN_DISH_INTENTS, chat_service


def test_other_intent_skips_unknown_dish_check():
    """other 必须在豁免名单里，否则知识库兜底形同虚设"""
    assert 'other' in SKIP_UNKNOWN_DISH_INTENTS


def test_dish_intents_still_checked():
    """点单/询价仍要过拦截 —— 防幻觉不能一起放掉"""
    for intent in ('place_order', 'query_menu'):
        assert intent not in SKIP_UNKNOWN_DISH_INTENTS


def test_real_unknown_dish_is_still_caught():
    """真的问了菜单外的菜，检测器仍然要拦住"""
    assert chat_service._detect_unknown_dish('佛跳墙') == '佛跳墙'


def test_menu_dish_is_not_caught():
    assert chat_service._detect_unknown_dish('羊肉泡馍') is None


def test_price_question_about_menu_dish_is_not_caught():
    assert chat_service._detect_unknown_dish('羊肉泡馍多少钱') is None
