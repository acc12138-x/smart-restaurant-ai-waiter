# tests/test_session_memory.py
"""对话记忆的回归测试

真实对话踩到的坑：

    用户：推荐一下菜品
    助手：要不试试咱们的优质羊肉泡馍？肉烂汤浓，微辣鲜香…   ← 推荐了具体菜
    用户：可以
    助手：好嘞！那要吃点啥？                                ← 已经答应的单子丢了

三个根因，分别锁在这里：

1) 规则层把确认词一律当闲聊 —— 见 test_intent_rules / test_context_and_typo
2) `_find_last_dish_in_history` 只从**用户**消息里找菜，可"可以"这句里没有菜名
3) 会话记忆只在内存里 —— 生产是 2 个 gunicorn worker，推荐存在 A、同意落在 B 就丢了
   （chat_sessions 表 v3.8 就建好了，一直没接上）
4) 所有未登录顾客共用 'anon' 一个 key —— B 顾客可能接掉 A 顾客的推荐
"""
import os
import sqlite3

import pytest

import repositories.sqlite_repo as sqlite_repo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def sdb(tmp_path, monkeypatch):
    """临时库 + 真实 schema（少一列就会在建索引时炸，所以不手写表结构）"""
    p = tmp_path / 'session.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(p))
    with open(os.path.join(ROOT, 'repositories', 'schema.sql'), encoding='utf-8') as f:
        schema = f.read()
    conn = sqlite3.connect(str(p))
    conn.executescript(schema)
    conn.commit()
    conn.close()
    return str(p)


def _repo():
    from repositories.sqlite_repo import SqliteRepository
    return SqliteRepository('chat_sessions', id_field='id', auto_id=True)


def _service():
    from services.session_service import SessionService
    return SessionService(repo=_repo())


# ==================== 跨 worker 的记忆 ====================

def test_history_survives_worker_switch(sdb):
    """两个 worker 各有一份内存，但记忆必须一致"""
    w1, w2 = _service(), _service()

    w1.add('u1', 'user', '推荐一下菜品')
    w1.add('u1', 'assistant', '要不试试咱们的优质羊肉泡馍？')

    h = w2.get_history('u1')           # 另一个 worker 也要看得到
    assert [x['content'] for x in h] == ['推荐一下菜品', '要不试试咱们的优质羊肉泡馍？']


def test_last_recommend_survives_worker_switch(sdb):
    w1, w2 = _service(), _service()

    w1.set_last_recommend('u1', '试试优质羊肉泡馍', [{'name': '优质羊肉泡馍', 'qty': 1}])
    got = w2.get_last_recommend('u1')
    assert got and got['items'][0]['name'] == '优质羊肉泡馍'


def test_recommend_record_not_mixed_into_history(sdb):
    """推荐记录不能混进喂给模型的对话历史"""
    w = _service()
    w.add('u1', 'user', '推荐一下')
    w.set_last_recommend('u1', '推荐优质羊肉泡馍', [{'name': '优质羊肉泡馍', 'qty': 1}])
    w.add('u1', 'assistant', '要不要来一份？')

    h = w.get_history('u1')
    assert [x['role'] for x in h] == ['user', 'assistant']


def test_clear_last_recommend_removes_from_db(sdb):
    """接单后要清掉推荐，否则连点两次会重复下单"""
    w1, w2 = _service(), _service()
    w1.set_last_recommend('u1', '推荐优质羊肉泡馍', [{'name': '优质羊肉泡馍', 'qty': 1}])
    w1.clear_last_recommend('u1')
    assert w2.get_last_recommend('u1') is None


# ==================== 未登录顾客按设备隔离 ====================

def test_anonymous_users_are_isolated_by_device(sdb):
    """不能用同一个 anon key 共用记忆（B 会看到 A 的上下文）"""
    from flask import Flask, g

    w = _service()
    app = Flask(__name__)

    with app.test_request_context('/'):
        g.device_id = 'devA'
        w.add(None, 'user', '我要羊肉泡馍')

    with app.test_request_context('/'):
        g.device_id = 'devB'
        assert w.get_history(None) == []        # 换了设备就看不到

    with app.test_request_context('/'):
        g.device_id = 'devA'
        assert len(w.get_history(None)) == 1    # 自己的还在


# ==================== 从助手消息里找回推荐 ====================

def test_find_last_dish_uses_assistant_recommendation(sdb, monkeypatch):
    """'可以' 这句里没有菜名，必须能从助手消息里找到被推荐的那道"""
    from services import session_service as ssmod
    from services.chat_service import chat_service

    monkeypatch.setattr(ssmod.session_service, '_repo', _repo())
    ss = ssmod.session_service

    uid = 'mem-uid-1'
    ss.add(uid, 'user', '推荐一下菜品')
    ss.add(uid, 'assistant', '要不试试咱们的优质羊肉泡馍？肉烂汤浓，微辣鲜香，配上一瓣糖蒜！')
    ss.add(uid, 'user', '可以')

    assert chat_service._find_last_dish_in_history(uid) == '优质羊肉泡馍'


def test_find_last_dish_ignores_menu_enumeration(sdb, monkeypatch):
    """助手在列整份菜单时，不能被当成推荐了某道菜（应返回 None）"""
    from services import session_service as ssmod
    from services.chat_service import chat_service

    monkeypatch.setattr(ssmod.session_service, '_repo', _repo())
    ss = ssmod.session_service

    uid = 'mem-uid-2'
    ss.add(uid, 'user', '你们有什么菜')
    ss.add(uid, 'assistant',
           '我们有：优质羊肉泡馍、牛肉泡馍(小份)、冰峰汽水、糖蒜(整头)、凉皮、肉丸胡辣汤')
    ss.add(uid, 'user', '可以')

    assert chat_service._find_last_dish_in_history(uid) is None


def test_find_last_dish_prefers_user_message(sdb, monkeypatch):
    """用户自己说过的菜优先于助手消息里的"""
    from services import session_service as ssmod
    from services.chat_service import chat_service

    monkeypatch.setattr(ssmod.session_service, '_repo', _repo())
    ss = ssmod.session_service

    uid = 'mem-uid-3'
    ss.add(uid, 'user', '来个凉皮')
    ss.add(uid, 'assistant', '凉皮先记下了，要不要再来一份优质羊肉泡馍？')
    ss.add(uid, 'user', '小份')

    assert chat_service._find_last_dish_in_history(uid) == '凉皮'
