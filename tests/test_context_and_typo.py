# tests/test_context_and_typo.py
"""上下文记忆 + 错别字容错的回归测试

真实对话踩到的两个问题：

1) AI 推荐"优质羊肉泡馍" → 用户回"可以" → 被当成闲聊，回了"好嘞！那要吃点啥？"，
   已经答应的单子丢了。根因：规则层把确认词一律判成 chat，而 _get_intent_result()
   优先信任规则层对 accept/reject 的判断，所以 LLM 根本没机会纠正它。

2) 用户打错字"羊肉跑馍" → 全链路匹配不到菜名，下单失败。
   大模型能认出来，但规则层（降级路径）不能因此退化成"看不懂"。
"""
import pytest

from services import llm_parser
from services.intent_service import classify_intent
from services.menu_service import menu_service

HISTORY_WITH_RECOMMEND = (
    '用户：推荐一下菜品\n'
    '助手：要不试试咱们的优质羊肉泡馍？肉烂汤浓，微辣鲜香，配上一瓣糖蒜，那叫一个过瘾！\n'
)
HISTORY_NO_DISH = (
    '用户：你好\n'
    '助手：你好！我是同盛祥的金牌店长小同 👨‍🍳 想吃啥？\n'
)


def _intent(text, history=''):
    return classify_intent(text, history=history)['intent']


# ==================== 上下文：确认词要接住上一轮的推荐 ====================

@pytest.mark.parametrize('text', ['可以', '好的', '好', '行', '嗯', '要', 'OK'])
def test_confirmation_accepts_previous_recommendation(text):
    assert _intent(text, HISTORY_WITH_RECOMMEND) == 'accept_recommend'


@pytest.mark.parametrize('text', ['可以', '好的', '嗯', 'OK'])
def test_confirmation_without_recommendation_is_smalltalk(text):
    assert _intent(text, HISTORY_NO_DISH) == 'chat'
    assert _intent(text) == 'chat'          # 没有历史时也算闲聊


def test_confirmation_logic_does_not_swallow_other_questions():
    """确认词走上下文判断，不能把"可以用支付宝吗"这类问题也吞成接受推荐"""
    assert _intent('可以用支付宝吗', HISTORY_WITH_RECOMMEND) != 'accept_recommend'
    assert _intent('可以开发票吗', HISTORY_WITH_RECOMMEND) != 'accept_recommend'


# ==================== 错别字容错 ====================

@pytest.mark.parametrize('text,expect', [
    ('羊肉跑馍', '羊肉泡馍'),
    ('冰锋汽水', '冰峰汽水'),
    ('牛肉泡馍（小份）', '牛肉泡馍(小份)'),
])
def test_find_dish_tolerates_typos(text, expect):
    dish = menu_service.find_dish(text)
    assert dish is not None, '%s 没匹配到菜' % text
    assert dish['name'] == expect


def test_find_dish_does_not_invent_dishes():
    """容错不能变成乱认：菜单外的菜仍要返回 None"""
    assert menu_service.find_dish('佛跳墙') is None
    assert menu_service.find_dish('汉堡') is None


@pytest.mark.parametrize('text', ['羊肉跑馍', '来碗羊肉跑馍', '我要一份羊肉跑馍'])
def test_typo_still_classified_as_order(text):
    assert _intent(text) == 'place_order'


def test_typo_with_price_question_is_still_menu_query():
    assert _intent('羊肉跑馍多少钱') == 'query_menu'


def test_question_with_dish_like_words_is_not_an_order():
    """容错不能把问句误配成菜名并下单"""
    assert _intent('我想知道你们家的羊是从哪里来的') != 'place_order'
    assert _intent('你们家的羊从哪来') != 'place_order'


def test_llm_items_tolerate_typos():
    names = [d['name'] for d in menu_service.get_flat()]
    assert llm_parser._normalize_items([{'dish': '羊肉跑馍', 'qty': 2}], names) == \
        [{'name': '羊肉泡馍', 'qty': 2}]


def test_llm_items_still_drop_unknown_dishes():
    names = [d['name'] for d in menu_service.get_flat()]
    assert llm_parser._normalize_items([{'dish': '佛跳墙', 'qty': 1}], names) == []
