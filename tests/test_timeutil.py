# tests/test_timeutil.py
"""时间处理 + 历史时间戳修正脚本的测试

背景：容器长期跑在 UTC，订单时间比实际早 8 小时，凌晨的单子会被算到前一天。
"""
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pytest

import repositories.sqlite_repo as sqlite_repo
from utils.timeutil import CST, now, now_str, today_str, parse, enforce_process_tz


# ==================== timeutil ====================

def test_cst_is_utc_plus_8():
    assert CST.utcoffset(None) == timedelta(hours=8)


def test_now_matches_utc_now():
    """now() 只是"带 +8 时区标注的当前时刻"，不该出现实际偏差"""
    diff = abs((now().astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds())
    assert diff < 5


def test_now_str_and_today_str_format():
    assert re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$', now_str())
    assert re.match(r'^\d{4}-\d{2}-\d{2}$', today_str())


def test_parse_roundtrip():
    dt = parse(now_str())
    assert dt is not None and dt.tzinfo is CST


def test_parse_invalid_returns_none():
    assert parse('') is None
    assert parse(None) is None
    assert parse('乱七八糟') is None


def test_enforce_process_tz_sets_posix_tz():
    enforce_process_tz()
    assert os.environ['TZ'] == 'CST-8'


# ==================== 历史时间戳修正脚本 ====================

@pytest.fixture
def utc_db(tmp_path, monkeypatch):
    """造一个"时间戳按 UTC 记录"的临时库"""
    db = tmp_path / 'utc.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(db))
    conn = sqlite3.connect(str(db))
    conn.executescript('''
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE orders (id TEXT PRIMARY KEY, total REAL, created_at TEXT);
        CREATE TABLE users (uid TEXT PRIMARY KEY, created_at TEXT, last_points_at TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY, date TEXT, time TEXT);
    ''')
    # 一笔实际发生在凌晨 1 点的订单 —— UTC 记录成了前一天 17:00
    conn.execute("INSERT INTO orders VALUES ('TSX1', 30, '2026-10-13 17:00:00')")
    conn.execute("INSERT INTO users VALUES ('u1', '2026-10-13 17:00:00', NULL)")
    conn.execute("INSERT INTO events (date, time) VALUES ('2026-10-13', '2026-10-13 17:00:00')")
    conn.commit()
    conn.close()
    return str(db)


def _run_script(monkeypatch, *argv):
    import scripts.fix_timezone_offset as fix
    monkeypatch.setattr(sys, 'argv', ['fix_timezone_offset.py'] + list(argv))
    return fix.main()


def test_dry_run_does_not_change_data(utc_db, monkeypatch):
    assert _run_script(monkeypatch) == 0
    conn = sqlite3.connect(utc_db)
    try:
        assert conn.execute('SELECT created_at FROM orders').fetchone()[0] == '2026-10-13 17:00:00'
    finally:
        conn.close()


def test_apply_shifts_plus_8_hours(utc_db, monkeypatch):
    assert _run_script(monkeypatch, '--apply') == 0
    conn = sqlite3.connect(utc_db)
    try:
        assert conn.execute('SELECT created_at FROM orders').fetchone()[0] == '2026-10-14 01:00:00'
        assert conn.execute('SELECT created_at FROM users').fetchone()[0] == '2026-10-14 01:00:00'
    finally:
        conn.close()


def test_apply_recomputes_event_date(utc_db, monkeypatch):
    """events 的 date 要跟着跨零点的 time 一起改，否则热力图仍然错位"""
    assert _run_script(monkeypatch, '--apply') == 0
    conn = sqlite3.connect(utc_db)
    try:
        time_v, date_v = conn.execute('SELECT time, date FROM events').fetchone()
    finally:
        conn.close()
    assert time_v == '2026-10-14 01:00:00'
    assert date_v == '2026-10-14'


def test_apply_is_idempotent(utc_db, monkeypatch):
    """第二次执行必须被标记拦住，否则会变成 +16 小时"""
    assert _run_script(monkeypatch, '--apply') == 0
    assert _run_script(monkeypatch, '--apply') == 0
    conn = sqlite3.connect(utc_db)
    try:
        assert conn.execute('SELECT created_at FROM orders').fetchone()[0] == '2026-10-14 01:00:00'
        marker = conn.execute("SELECT value FROM settings WHERE key='tz_backfill_v1'").fetchone()
    finally:
        conn.close()
    assert marker is not None


def test_cli_runs_as_direct_script(utc_db):
    """必须能以 `python scripts/fix_timezone_offset.py` 直接运行。

    直接运行时 sys.path 里是 scripts/ 而不是项目根 —— 线上第一次运行就是栽在这里：
    ModuleNotFoundError: No module named 'repositories'。
    上面的用例都是 import 模块（conftest 已把项目根加进 sys.path），覆盖不到这条路径。
    """
    import subprocess

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(root, 'scripts', 'fix_timezone_offset.py')
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)          # 模拟线上：没有任何路径补偿
    env['PYTHONIOENCODING'] = 'utf-8'    # 否则 Windows 下按 GBK 解码子进程输出会炸

    r = subprocess.run(
        [sys.executable, script, '--db', utc_db],
        capture_output=True, encoding='utf-8', errors='replace', cwd=root, env=env,
    )
    assert r.returncode == 0, 'stdout:\n%s\nstderr:\n%s' % (r.stdout, r.stderr)
    assert 'DRY-RUN' in r.stdout
    assert 'ModuleNotFoundError' not in (r.stderr or '')
