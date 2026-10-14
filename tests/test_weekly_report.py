# tests/test_weekly_report.py
"""周报聚合的单元测试（用临时库，不依赖真实数据）"""
import json
import sqlite3
from datetime import timedelta

import pytest

import repositories.sqlite_repo as sqlite_repo
from utils.timeutil import now


@pytest.fixture
def rdb(tmp_path, monkeypatch):
    p = tmp_path / 'weekly.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(p))
    # 直接加载真实 schema，避免手写表结构与线上不一致（少一列就会在建索引时炸）
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'repositories', 'schema.sql'), encoding='utf-8') as f:
        schema = f.read()
    conn = sqlite3.connect(str(p))
    conn.executescript(schema)
    conn.commit()
    conn.close()
    return str(p)


def _monday_19h():
    """本周一 19:00 —— 以它为基准造数据，避免依赖"今天"是周几"""
    n = now()
    return (n - timedelta(days=n.weekday())).replace(hour=19, minute=0, second=0, microsecond=0)


def _insert(db, table, vals):
    conn = sqlite3.connect(db)
    conn.execute('INSERT INTO ' + table + ' VALUES (' + ','.join('?' * len(vals)) + ')', vals)
    conn.commit()
    conn.close()


def _order(db, oid, uid, total, ts, items, status='done'):
    _insert(db, 'orders',
            (oid, uid, '05', json.dumps(items, ensure_ascii=False), total, status, ts))


def test_weekly_report_aggregates_and_compares(rdb):
    from services.admin_service import admin_service

    mon = _monday_19h()
    this1 = (mon + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    this2 = (mon + timedelta(days=2, hours=2)).strftime('%Y-%m-%d %H:%M:%S')
    last1 = (mon - timedelta(days=6)).strftime('%Y-%m-%d %H:%M:%S')      # 上周二

    _order(rdb, 'A', 'u1', 30.0, this1, [{'name': '牛肉泡馍(小份)', 'qty': 1, 'subtotal': 30.0}])
    _order(rdb, 'B', 'u2', 20.0, this2, [{'name': '凉皮', 'qty': 2, 'subtotal': 20.0}])
    _order(rdb, 'D', 'u2', 10.0, this2, [{'name': '冰峰汽水', 'qty': 1, 'subtotal': 10.0}])
    _order(rdb, 'C', 'u1', 25.0, last1, [{'name': '羊肉泡馍', 'qty': 1, 'subtotal': 25.0}])

    r = admin_service.weekly_report()
    tw, lw = r['this_week'], r['last_week']

    assert tw['orders'] == 3
    assert tw['revenue'] == 60.0
    assert tw['avg_price'] == 20.0
    assert tw['customers'] == 2                      # u1 + u2
    assert lw['orders'] == 1 and lw['revenue'] == 25.0

    assert r['delta']['revenue'] == 140.0            # 60 相比 25
    assert r['delta']['orders'] == 200.0             # 3 相比 1

    # Top 菜品按销量排序：凉皮 2 份 > 牛肉泡馍 1 份
    assert r['top_dishes'][0]['name'] == '凉皮'
    assert r['top_dishes'][0]['qty'] == 2
    assert r['top_dishes'][0]['revenue'] == 20.0

    # 逐日：周二 1 单、周三 2 单
    by_label = {d['label']: d for d in r['by_day']}
    assert by_label['周二']['orders'] == 1
    assert by_label['周三']['orders'] == 2
    assert by_label['周一']['orders'] == 0

    # 高峰时段取到 21:00（周三那两笔）
    assert r['peak']['hour'] == 21
    assert r['peak']['orders'] == 2
    assert r['insights']


def test_weekly_report_empty_week(rdb):
    from services.admin_service import admin_service
    r = admin_service.weekly_report()
    assert r['this_week']['orders'] == 0
    assert r['delta']['revenue'] is None
    assert '本周还没有订单' in r['insights'][0]


def test_delta_is_none_without_baseline(rdb):
    """上周为 0 时不给环比百分比 —— 否则会显示成误导性的 +100%"""
    from services.admin_service import admin_service

    mon = _monday_19h()
    ts = (mon + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    _order(rdb, 'A', 'u1', 30.0, ts, [{'name': '牛肉泡馍(小份)', 'qty': 1, 'subtotal': 30.0}])

    r = admin_service.weekly_report()
    assert r['this_week']['orders'] == 1
    assert r['last_week']['orders'] == 0
    assert r['delta']['orders'] is None       # 而不是 100.0
    assert r['delta']['revenue'] is None


def test_cancelled_orders_are_excluded(rdb):
    from services.admin_service import admin_service
    mon = _monday_19h()
    ts = (mon + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

    _order(rdb, 'A', 'u1', 30.0, ts, [{'name': '牛肉泡馍(小份)', 'qty': 1, 'subtotal': 30.0}])
    _order(rdb, 'X', 'u1', 99.0, ts, [{'name': '牛肉泡馍(小份)', 'qty': 3, 'subtotal': 99.0}],
           status='cancelled')

    r = admin_service.weekly_report()
    assert r['this_week']['orders'] == 1
    assert r['this_week']['revenue'] == 30.0
