# repositories/sqlite_repo.py
"""SQLite 通用数据访问层（接口与 JsonRepository 完全一致）"""
import json
import os
import sqlite3
import threading

from repositories.base import BaseRepository


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'app.db')

_init_lock = threading.Lock()
_initialized = False


def get_conn():
    """每次操作独立连接，WAL 模式支持读写并发"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_db():
    """执行 schema.sql 建表"""
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        schema_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 'schema.sql'
        )
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
        conn = get_conn()
        try:
            conn.executescript(schema)
            conn.commit()
        finally:
            conn.close()
        _initialized = True


class SqliteRepository(BaseRepository):
    """通用 SQLite 数据访问"""

    def __init__(self, table, id_field='id', auto_id=True, json_fields=None):
        self.table = table
        self.id_field = id_field
        self.auto_id = auto_id
        self.json_fields = set(json_fields or [])
        init_db()

    def _row_to_dict(self, row):
        if row is None:
            return None
        d = dict(row)
        for f in self.json_fields:
            if f in d and isinstance(d[f], str):
                try:
                    d[f] = json.loads(d[f])
                except Exception:
                    pass
        return d

    def get_all(self):
        conn = get_conn()
        try:
            cur = conn.execute(f'SELECT * FROM {self.table}')
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def find_by_id(self, id_val):
        conn = get_conn()
        try:
            cur = conn.execute(
                f'SELECT * FROM {self.table} WHERE `{self.id_field}` = ?',
                (id_val,)
            )
            return self._row_to_dict(cur.fetchone())
        finally:
            conn.close()

    def find(self, **conditions):
        if not conditions:
            return self.get_all()
        where = ' AND '.join(f'`{k}` = ?' for k in conditions)
        values = list(conditions.values())
        conn = get_conn()
        try:
            cur = conn.execute(
                f'SELECT * FROM {self.table} WHERE {where}', values
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def create(self, data):
        d = dict(data)
        for f in self.json_fields:
            if f in d and not isinstance(d[f], str):
                d[f] = json.dumps(d[f], ensure_ascii=False)

        fields = list(d.keys())
        placeholders = ', '.join('?' for _ in fields)
        cols = ', '.join(f'`{f}`' for f in fields)
        values = [d[f] for f in fields]

        conn = get_conn()
        try:
            cur = conn.execute(
                f'INSERT INTO {self.table} ({cols}) VALUES ({placeholders})',
                values
            )
            conn.commit()
            if self.auto_id and self.id_field not in data:
                d[self.id_field] = cur.lastrowid
            return d
        finally:
            conn.close()

    def update(self, id_val, data):
        if not data:
            return self.find_by_id(id_val)

        d = dict(data)
        for f in self.json_fields:
            if f in d and not isinstance(d[f], str):
                d[f] = json.dumps(d[f], ensure_ascii=False)

        fields = list(d.keys())
        set_clause = ', '.join(f'`{f}` = ?' for f in fields)
        values = [d[f] for f in fields]
        values.append(id_val)

        conn = get_conn()
        try:
            conn.execute(
                f'UPDATE {self.table} SET {set_clause} WHERE `{self.id_field}` = ?',
                values
            )
            conn.commit()
            return self.find_by_id(id_val)
        finally:
            conn.close()

    def delete(self, id_val):
        conn = get_conn()
        try:
            cur = conn.execute(
                f'DELETE FROM {self.table} WHERE `{self.id_field}` = ?',
                (id_val,)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def count(self):
        conn = get_conn()
        try:
            cur = conn.execute(f'SELECT COUNT(*) as c FROM {self.table}')
            return cur.fetchone()['c']
        finally:
            conn.close()