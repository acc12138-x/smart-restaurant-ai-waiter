# tests/test_table_order.py
"""对话里指定桌号 + 后台桌号校验的回归测试

需求：用户说"点一个羊肉泡馍送到 1 号桌"→ 送到 1 号桌，
但**必须先确认后台「桌码管理」里真的有这张桌**，否则菜会送到一张不存在的桌子上。

两个容易踩的点：
- 后台桌号是自由文本（`01`/`A2`/`大厅3`），顾客说"1 号桌"必须能对上"01"（归一化比较）
- 后台"一张桌都没配"时不能拦顾客（全新部署时会把所有单子挡掉）
"""
import os
import sqlite3

import pytest

import repositories.sqlite_repo as sqlite_repo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def tdb(tmp_path, monkeypatch):
    """临时库 + 真实 schema + 3 张后台配过的桌（故意用 01 这种带前导零的写法）"""
    p = tmp_path / 'table.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(p))
    with open(os.path.join(ROOT, 'repositories', 'schema.sql'), encoding='utf-8') as f:
        schema = f.read()
    conn = sqlite3.connect(str(p))
    conn.executescript(schema)
    conn.commit()
    conn.close()

    from repositories.sqlite_repo import SqliteRepository
    repo = SqliteRepository('tables', id_field='id', auto_id=True)
    for t in ('01', '05', 'A2'):
        repo.create({'table_no': t, 'scan_count': 0, 'created_at': '2026-01-01 00:00:00'})
    return repo


def _svc(repo):
    from services.table_service import TableService
    return TableService(repo=repo)


def _patch_singleton(monkeypatch, repo):
    """把模块级单例的 repo 换成临时库（并清掉 10 秒缓存）"""
    from services import table_service as tsmod
    monkeypatch.setattr(tsmod.table_service, '_repo', repo)
    tsmod.table_service.clear_cache()
    return tsmod.table_service


# ==================== 从话里抠桌号 ====================

@pytest.mark.parametrize('text,expect', [
    ('点一个羊肉泡馍送到1号桌', '1'),
    ('送到 3 号桌', '3'),
    ('送到三号桌', '3'),
    ('我在A1桌', 'A1'),
    ('桌号2', '2'),
    ('给我送到１２号桌', '12'),        # 全角数字
    ('来一份羊肉泡馍', None),
    ('来两份', None),
    ('我们3个人', None),               # 没有"桌/台"不能认
])
def test_extract_table_no(tdb, text, expect):
    got, _ = _svc(tdb).extract(text)
    assert got == expect


# ==================== 归一化与校验 ====================

def test_match_keeps_admin_form(tdb):
    """顾客说 1，后台配的是 01 —— 必须匹配上，并且用后台的写法"""
    svc = _svc(tdb)
    assert svc.match('1') == '01'
    assert svc.match('01') == '01'
    assert svc.match('0５') == '05'
    assert svc.match('a2') == 'A2'
    assert svc.match('８') is None      # 店里没有 8 号桌


def test_available_hint(tdb):
    assert _svc(tdb).available_hint() == '01、05、A2'


def test_available_hint_skips_junk(tmp_path, monkeypatch):
    """后台混着自动生成的测试桌号时，不要报给顾客（改为让他看桌上的码）"""
    p = tmp_path / 'junk.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(p))
    with open(os.path.join(ROOT, 'repositories', 'schema.sql'), encoding='utf-8') as f:
        schema = f.read()
    conn = sqlite3.connect(str(p))
    conn.executescript(schema)
    conn.commit()
    conn.close()
    from repositories.sqlite_repo import SqliteRepository
    repo = SqliteRepository('tables', id_field='id', auto_id=True)
    for t in ('Te27a', 'DUP4e5a'):
        repo.create({'table_no': t, 'scan_count': 0, 'created_at': '2026-01-01 00:00:00'})
    assert _svc(repo).available_hint() == ''


# ==================== 端到端：决定这一单送哪张桌 ====================

def test_resolve_uses_mentioned_table(tdb, monkeypatch):
    from services.chat_service import chat_service
    _patch_singleton(monkeypatch, tdb)

    table_no, err = chat_service._resolve_table_no(
        '点一个羊肉泡馍送到1号桌', '外带', 'place_order')
    assert err is None
    assert table_no == '01'             # 用后台的写法，便于后台按桌统计


def test_resolve_rejects_unknown_table(tdb, monkeypatch):
    from services.chat_service import chat_service
    _patch_singleton(monkeypatch, tdb)

    table_no, err = chat_service._resolve_table_no(
        '点一个羊肉泡馍送到8号桌', '外带', 'place_order')
    assert err, '店里没有 8 号桌，必须当场提醒'
    assert '8' in err and '01' in err
    assert table_no == '外带'            # 不改桌号：调用方会直接回复错误、不下单


def test_passing_mention_is_ignored(tdb, monkeypatch):
    """顺口一句『我上次在8号桌吃的』不该被打断"""
    from services.chat_service import chat_service
    _patch_singleton(monkeypatch, tdb)

    table_no, err = chat_service._resolve_table_no('我上次在8号桌吃的', '外带', 'other')
    assert err is None
    assert table_no == '外带'


def test_qr_table_used_when_not_mentioned(tdb, monkeypatch):
    from services.chat_service import chat_service
    _patch_singleton(monkeypatch, tdb)

    assert chat_service._resolve_table_no('来个羊肉泡馍', '05', 'place_order') == ('05', None)


def test_mention_overrides_qr_table(tdb, monkeypatch):
    from services.chat_service import chat_service
    _patch_singleton(monkeypatch, tdb)

    assert chat_service._resolve_table_no('送到1号桌', '05', 'place_order') == ('01', None)


def test_no_config_does_not_block_customer(tdb, monkeypatch):
    """后台一张桌都没配 → 无法校验，不能拦顾客（否则全新部署全废）"""
    from services.chat_service import chat_service
    svc = _patch_singleton(monkeypatch, tdb)
    monkeypatch.setattr(svc, 'list_tables', lambda: [])

    table_no, err = chat_service._resolve_table_no('送到7号桌', '外带', 'place_order')
    assert err is None
    assert table_no == '7'
