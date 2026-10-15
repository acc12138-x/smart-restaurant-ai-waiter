# tests/test_intent_rules.py
"""意图规则与未知菜名闸的回归测试

每条用例都对应一个真实踩过的坑（括号里是修复前的错误行为）：

- "可以用支付宝吗"     → 闲聊，回"你好！我是金牌店长…"（chat_kw 里的裸"可以"）
- "来点凉皮"           → 要推荐，没下单（recommend_kw 里的裸"来点"）
- "有停车位"           → 菜单查询 → 未知菜名闸 → "菜单里没有「有停车位」"
- "我刚刚点了一份泡馍" → 新下单（含"点一"）→ 重复下单
- "我要留言"           → 下单（order_kw 里的"我要"）→ 进不了留言流程
- "我要投诉凉皮里有头发" → 含菜名规则 → 再点一份凉皮
- "我的菜好了吗"       → 没有意图可落 → 交给模型自由发挥，编出等待时间
"""
import pytest

from services.chat_service import chat_service
from services.intent_service import classify_intent


def _intent(text):
    return classify_intent(text)['intent']


# ==================== 新增意图：催单 / 查订单进度 ====================

@pytest.mark.parametrize('text', [
    '我的菜好了吗', '还要等多久', '催一下', '上菜了吗', '什么时候能好',
    '我的订单到哪了', '怎么还没好', '快点好吗',
])
def test_order_status_recognized(text):
    assert _intent(text) == 'query_order_status'


@pytest.mark.parametrize('text', [
    '我刚刚点了一份泡馍', '刚才点了两碗羊肉泡馍', '我已经下过单了', '上次点的凉皮还没上',
])
def test_past_tense_is_status_not_new_order(text):
    """过去时叙述绝不能当成新下单 —— 那会重复下单"""
    assert _intent(text) == 'query_order_status'


# ==================== 收窄过宽关键词 ====================

@pytest.mark.parametrize('text', ['可以用支付宝吗', '可以开发票吗', '可以刷卡吗'])
def test_payment_questions_are_not_smalltalk(text):
    assert _intent(text) != 'chat'


@pytest.mark.parametrize('text', [
    '可以用支付宝吗', '有什么支付方式', '有停车位吗', '有 wifi 吗',
    '能开发票吗', '有停车位',
])
def test_store_questions_fall_through_to_knowledge_base(text):
    """支付/发票/停车/wifi 这类门店杂问应落到 other，由知识库回答
    （other 不参与未知菜名拦截，所以能安全到达检索）"""
    assert _intent(text) == 'other'


def test_dish_with_order_verb_is_an_order():
    """recommend_kw 里的裸"来点"曾把"来点凉皮"判成要推荐"""
    assert _intent('来点凉皮') == 'place_order'
    assert _intent('给我来份凉皮') == 'place_order'
    assert _intent('来个糖蒜') == 'place_order'


def test_dish_with_question_queries_menu():
    assert _intent('凉皮多少钱') == 'query_menu'
    assert _intent('羊肉泡馍几块') == 'query_menu'
    assert _intent('羊肉泡馍辣不辣') == 'query_menu'
    assert _intent('你们有糖蒜吗') == 'query_menu'


def test_complaint_mentioning_a_dish_is_not_a_new_order():
    assert _intent('我要投诉凉皮里有头发') == 'leave_message'


def test_give_me_recommendation_is_not_an_order():
    """order_kw 里的裸"给我"曾把"给我推荐个菜"判成下单"""
    assert _intent('给我推荐个菜') == 'recommend'
    assert _intent('推荐个招牌菜') == 'recommend'


def test_leave_message_not_swallowed_by_order_keywords():
    assert _intent('我要留言') == 'leave_message'
    assert _intent('给老板留句话') == 'leave_message'


def test_bare_have_question_is_not_menu_query():
    """menu_kw 里的"有吗/有没有"曾把"有停车位"引向未知菜名闸"""
    assert _intent('有停车位') != 'query_menu'


# ==================== 未知菜名闸：问句形状不该被当成菜名 ====================

@pytest.mark.parametrize('text', [
    '可以用支付宝', '有停车位', '能开发票', '你们家羊从哪', '你们用什么羊肉',
])
def test_question_shaped_text_is_not_a_dish(text):
    assert chat_service._detect_unknown_dish(text) is None


def test_real_unknown_dish_still_caught():
    """防幻觉不能因此失效：真的点了菜单外的菜仍要被拦"""
    assert chat_service._detect_unknown_dish('佛跳墙') == '佛跳墙'
    assert chat_service._detect_unknown_dish('汉堡') == '汉堡'


# ==================== 原有行为不能被改坏 ====================

@pytest.mark.parametrize('text,expect', [
    ('来两份牛肉泡馍', 'place_order'),
    ('羊肉泡馍', 'place_order'),
    ('取消订单', 'cancel_order'),
    ('全部取消', 'cancel_all'),
    ('把牛肉泡馍改成羊肉泡馍', 'modify_order'),
    ('一共多少钱', 'query_total'),
    ('你们在哪', 'query_location'),
    ('几点关门', 'query_hours'),
    ('就这个', 'accept_recommend'),
    ('换一个', 'reject_recommend'),
    ('招牌菜是啥', 'recommend'),
    ('你好', 'chat'),
    ('。。。', 'other'),
])
def test_existing_behaviour_unchanged(text, expect):
    assert _intent(text) == expect
