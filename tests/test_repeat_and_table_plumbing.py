# tests/test_repeat_and_table_plumbing.py
"""「老规矩」与桌号传递的回归测试

真实对话踩到的坑：

    顾客：老规矩送到一号桌
    助手：菜单里没有「老规矩送到一号桌」哦～ …        ← 指代被当成菜名
    顾客：羊肉泡馍送到一号桌
    （下单成功，但后台实时订单显示的是"外带"）        ← 桌号没进订单

两个问题分别对应：
1) 「老规矩 / 照旧」这类指代完全没支持，还会被未知菜名闸整串当成菜名拦掉
2) 改单路径把桌号硬编码成"外带"，一改单就丢桌号
"""
import pytest

from services.intent_service import classify_intent


def _intent(text, history=''):
    return classify_intent(text, history=history)['intent']


# ==================== 「老规矩」的意图识别 ====================

@pytest.mark.parametrize('text', [
    '老规矩', '老规矩送到一号桌', '照旧', '老样子', '还那样',
    '和上次一样', '跟上次一样', '按上次的来', '老一套',
])
def test_repeat_last_order_recognized(text):
    assert _intent(text) == 'repeat_last_order'


@pytest.mark.parametrize('text', [
    '老规矩送到一号桌', '照旧送到5号桌', '老样子，送到A2桌',
])
def test_repeat_mentioning_a_table_is_not_hijacked(text):
    """桌号 + 指代的句子绝不能被当成菜名（以前回"菜单里没有「老规矩送到一号桌」"）"""
    from services.chat_service import chat_service
    assert chat_service._detect_unknown_dish(text) is None


def test_other_table_sentences_are_not_dishes():
    from services.chat_service import chat_service
    for text in ['送到1号桌', '我在5号桌', '一号桌加个糖蒜']:
        assert chat_service._detect_unknown_dish(text) is None


def test_real_unknown_dish_still_caught_after_hardening():
    """加守卫不能把防幻觉一起废掉"""
    from services.chat_service import chat_service
    assert chat_service._detect_unknown_dish('佛跳墙') == '佛跳墙'


# ==================== 照上一单重下 ====================

class _FakeOrderService:
    """替身：只记录 create 收到的 table_no 与 items"""

    def __init__(self, history):
        self.history = history
        self.created = []

    def get_by_uid(self, uid):
        return self.history

    def create(self, items, table_no='外带', uid=None):
        self.created.append({'items': items, 'table_no': table_no, 'uid': uid})
        return {
            'order': {'id': 'TSX-TEST', 'items': items, 'total': 60.0,
                      'table_no': table_no, 'status': 'pending'},
            'items': items, 'total': 60.0,
        }

    @staticmethod
    def format_reply(result):
        return '订单已创建 TSX-TEST'


@pytest.fixture
def fake_orders(monkeypatch):
    from services import chat_service as csmod

    last = {
        'id': 'TSX-OLD', 'uid': 'u1', 'status': 'done',
        'created_at': '2026-10-14 12:00:00', 'table_no': '01',
        'items': [{'name': '优质羊肉泡馍', 'qty': 1}, {'name': '冰峰汽水', 'qty': 2}],
        'total': 40.0,
    }
    fake = _FakeOrderService([last])
    monkeypatch.setattr(csmod, 'order_service', fake)
    return fake


def test_repeat_last_order_creates_same_items(fake_orders):
    from services.chat_service import chat_service

    reply, order = chat_service._handle_repeat_last_order('u1', table_no='01')
    assert order is not None
    assert len(fake_orders.created) == 1
    sent = fake_orders.created[0]
    assert sent['table_no'] == '01'                      # 桌号必须传下去
    assert [i['name'] for i in sent['items']] == ['优质羊肉泡馍', '冰峰汽水']
    assert sent['items'][1]['qty'] == 2
    assert '订单已创建' in reply


def test_repeat_without_login_asks_to_login(fake_orders):
    from services.chat_service import chat_service

    reply, order = chat_service._handle_repeat_last_order(None)
    assert order is None
    assert '登录' in reply
    assert not fake_orders.created


def test_repeat_with_no_history(monkeypatch):
    from services import chat_service as csmod
    from services.chat_service import chat_service

    fake = _FakeOrderService([])
    monkeypatch.setattr(csmod, 'order_service', fake)

    reply, order = chat_service._handle_repeat_last_order('u1')
    assert order is None
    assert not fake.created


def test_repeat_skips_dishes_removed_from_menu(monkeypatch):
    """上次点的菜下架了就不能照抄（会把不存在的菜塞进订单）"""
    from services import chat_service as csmod
    from services.chat_service import chat_service

    last = {
        'id': 'TSX-OLD2', 'uid': 'u1', 'status': 'done',
        'created_at': '2026-10-14 12:00:00', 'table_no': '05',
        'items': [{'name': '佛跳墙', 'qty': 1}], 'total': 88.0,
    }
    fake = _FakeOrderService([last])
    monkeypatch.setattr(csmod, 'order_service', fake)

    reply, order = chat_service._handle_repeat_last_order('u1')
    assert order is None
    assert not fake.created                 # 一道都不在菜单里 → 不下单
    assert '佛跳墙' in reply


def test_repeat_skips_cancelled_orders(monkeypatch):
    from services import chat_service as csmod
    from services.chat_service import chat_service

    fake = _FakeOrderService([
        {'id': 'X', 'status': 'cancelled', 'created_at': '2026-10-14 13:00:00',
         'items': [{'name': '优质羊肉泡馍', 'qty': 1}], 'table_no': '01'},
    ])
    monkeypatch.setattr(csmod, 'order_service', fake)

    reply, order = chat_service._handle_repeat_last_order('u1')
    assert order is None
    assert not fake.created


# ==================== 桌号解析本身（补测中文数字 + 覆盖优先级）====================

def test_resolve_uses_chinese_numeral_table(tmp_path, monkeypatch):
    import os
    import sqlite3
    import repositories.sqlite_repo as sqlite_repo
    from repositories.sqlite_repo import SqliteRepository
    from services import table_service as tsmod
    from services.chat_service import chat_service

    p = tmp_path / 't.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(p))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'repositories', 'schema.sql'), encoding='utf-8') as f:
        schema = f.read()
    conn = sqlite3.connect(str(p))
    conn.executescript(schema)
    conn.commit()
    conn.close()
    repo = SqliteRepository('tables', id_field='id', auto_id=True)
    repo.create({'table_no': '01', 'scan_count': 0, 'created_at': '2026-01-01 00:00:00'})

    monkeypatch.setattr(tsmod.table_service, '_repo', repo)
    tsmod.table_service.clear_cache()

    assert chat_service._resolve_table_no('老规矩送到一号桌', '外带', 'repeat_last_order') \
        == ('01', None)
