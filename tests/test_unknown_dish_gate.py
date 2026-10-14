# tests/test_unknown_dish_gate.py
"""未知菜名拦截的回归测试

这道拦截原先对几乎所有意图生效，于是资料型问题常被它吃掉。实测两条真实问句：

- 「我想知道你们家的羊是从哪里来的」→ 判成 other     → 被剥成"你们用是哪里羊肉" → 拦住
- 「你们家的羊从哪来」            → 判成 query_hours → 被剥成"你们家羊从哪"     → 拦住

两次都回一句「菜单里没有「…」哦～」，而知识库里明明写着「选用宁夏滩羊」。

修法两条：
1. 拦截改成白名单，只对点单/询价生效 —— 意图来自大模型，误判难免，
   白名单能保证任何误判都不会把资料型问题拦成"未知菜名"；
2. 候选人里带人称/指示/疑问词的一律不算菜名。
"""
from services.chat_service import UNKNOWN_DISH_INTENTS, chat_service


def test_only_order_and_menu_intents_are_checked():
    assert set(UNKNOWN_DISH_INTENTS) == {'place_order', 'query_menu'}


def test_misclassified_intents_are_not_checked():
    """大模型误判出来的这些意图，都不该触发未知菜名拦截"""
    for intent in ('other', 'query_hours', 'query_location', 'query_total',
                   'chat', 'recommend', 'cancel_order', 'modify_order'):
        assert intent not in UNKNOWN_DISH_INTENTS


def test_real_unknown_dish_is_still_caught():
    """真的问了菜单外的菜，仍然要拦住（防幻觉不能一起放掉）"""
    assert chat_service._detect_unknown_dish('佛跳墙') == '佛跳墙'
    assert chat_service._detect_unknown_dish('汉堡') == '汉堡'


def test_menu_dish_is_not_caught():
    assert chat_service._detect_unknown_dish('羊肉泡馍') is None


def test_price_question_about_menu_dish_is_not_caught():
    assert chat_service._detect_unknown_dish('羊肉泡馍多少钱') is None


def test_question_shaped_text_is_not_treated_as_dish():
    """带人称/疑问词的一律不算菜名 —— 这两句就是实测踩到的"""
    assert chat_service._detect_unknown_dish('你们家的羊从哪来') is None
    assert chat_service._detect_unknown_dish('你们用什么羊肉') is None
