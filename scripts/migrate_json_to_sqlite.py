# scripts/migrate_json_to_sqlite.py
"""把现有 JSON 数据迁移到 SQLite"""
import os
import sys
import json
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from repositories.sqlite_repo import init_db
from repositories.instances import (
    member_repo, order_repo, message_repo, event_repo,
)

DATA_DIR = os.path.join(ROOT, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backup')


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def backup_json():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for f in ['members.json', 'orders.json', 'message.json', 'events.json']:
        src = os.path.join(DATA_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(BACKUP_DIR, f))
            print(f'  备份 {f}')


def migrate_members():
    rows = load_json('members.json')
    n = 0
    for m in rows:
        if not m.get('uid'):
            continue
        if member_repo.find_by_id(m['uid']):
            continue
        member_repo.create({
            'uid': m['uid'],
            'username': m.get('username', ''),
            'password_hash': m.get('password_hash', ''),
            'nickname': m.get('nickname', ''),
            'points': m.get('points', 0),
            'level': m.get('level', '新客'),
            'disabled': 0,
            'created_at': m.get('created_at', ''),
            'last_points_at': m.get('last_points_at', ''),
        })
        n += 1
    print(f'  迁移用户 {n} 条')


def migrate_orders():
    rows = load_json('orders.json')
    n = 0
    for o in rows:
        if not o.get('id'):
            continue
        if order_repo.find_by_id(o['id']):
            continue
        order_repo.create({
            'id': o['id'],
            'uid': o.get('uid'),
            'table_no': o.get('table_no'),
            'items': o.get('items', []),
            'total': o.get('total', 0),
            'status': o.get('status', 'pending'),
            'created_at': o.get('created_at', ''),
        })
        n += 1
    print(f'  迁移订单 {n} 条')


def migrate_messages():
    rows = load_json('message.json')
    n = 0
    for m in rows:
        message_repo.create({
            'name': m.get('name', '匿名老客'),
            'content': m.get('content', ''),
            'read': 0,
            'created_at': m.get('created_at', ''),
        })
        n += 1
    print(f'  迁移留言 {n} 条')


def migrate_events():
    rows = load_json('events.json')
    n = 0
    for e in rows:
        event_repo.create({
            'event': e.get('event', ''),
            'payload': e.get('payload', {}),
            'uid': e.get('uid'),
            'ip': e.get('ip'),
            'ua': e.get('ua'),
            'date': e.get('date', ''),
            'time': e.get('time', ''),
        })
        n += 1
    print(f'  迁移埋点 {n} 条')


def main():
    print('=== 初始化数据库 ===')
    init_db()
    print()

    print('=== 备份原 JSON ===')
    backup_json()
    print()

    print('=== 迁移数据 ===')
    migrate_members()
    migrate_orders()
    migrate_messages()
    migrate_events()
    print()

    print('=== 完成 ===')


if __name__ == '__main__':
    main()