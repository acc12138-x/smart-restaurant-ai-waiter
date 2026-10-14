# scripts/fix_timezone_offset.py
"""一次性修正历史时间戳：UTC -> 北京时间（+8 小时）

背景：容器长期运行在 UTC（docker-compose 未设 TZ），所以此前写入的所有
'YYYY-MM-DD HH:MM:SS' 时间戳都比实际时间早 8 小时。最典型的症状是
"凌晨 00:00-08:00 的订单被算到前一天"，以及时段分布图整体左移 8 小时。

用法（在服务器上，务必先备份）：

    cd /root/apps/smart-restaurant-ai-waiter
    cp data/app.db data/app.db.bak_$(date +%Y%m%d_%H%M)
    docker exec tsx-app python scripts/fix_timezone_offset.py            # 预览（默认）
    docker exec tsx-app python scripts/fix_timezone_offset.py --apply    # 真正执行

幂等：执行成功后会在 settings 表写入标记 tz_backfill_v1，重复执行直接退出，
避免同一批数据被 +16 小时。想重跑必须先删掉那条标记。
"""
import os
import sys

import repositories.sqlite_repo as sqlite_repo

MARKER_KEY = 'tz_backfill_v1'
OFFSET = '+8 hours'

# 需要整体平移的 (表, 列)
TARGETS = [
    ('users',         'created_at'),
    ('users',         'last_points_at'),
    ('orders',        'created_at'),
    ('messages',      'created_at'),
    ('chat_logs',     'created_at'),
    ('admin_users',   'created_at'),
    ('admin_logs',    'created_at'),
    ('tables',        'created_at'),
    ('kb_history',    'created_at'),
    ('points_log',    'created_at'),
    ('settings',      'updated_at'),
    ('chat_sessions', 'created_at'),
    ('app_logs',      'created_at'),
]

# events 表拆成 date + time 两列，time 平移后要按新时间重算 date
EVENTS = True


def _table_exists(conn, name):
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _marker_done(conn):
    try:
        cur = conn.execute('SELECT value FROM settings WHERE key=?', (MARKER_KEY,))
        row = cur.fetchone()
        return bool(row)
    except Exception:
        return False


def main():
    apply = '--apply' in sys.argv
    db_path = sqlite_repo.DB_PATH

    if not os.path.exists(db_path):
        print(f'[X] 数据库不存在: {db_path}')
        return 1

    conn = sqlite_repo.get_conn()
    try:
        if _marker_done(conn):
            print(f'[SKIP] 已执行过（settings 里有 {MARKER_KEY} 标记），不做任何修改。')
            print('       若要重跑：DELETE FROM settings WHERE key=\'%s\';' % MARKER_KEY)
            return 0

        print(f'数据库: {db_path}')
        print(f'模式:   {"APPLY（真正写入）" if apply else "DRY-RUN（只预览）"}')
        print('-' * 62)

        total = 0
        for table, col in TARGETS:
            if not _table_exists(conn, table):
                continue
            try:
                n = conn.execute(
                    f'SELECT COUNT(*) FROM {table} '
                    f"WHERE {col} IS NOT NULL AND {col} <> ''"
                ).fetchone()[0]
            except Exception as e:
                print(f'  [跳过] {table}.{col}: {e}')
                continue
            if not n:
                continue
            sample = conn.execute(
                f'SELECT {col} FROM {table} '
                f"WHERE {col} IS NOT NULL AND {col} <> '' ORDER BY {col} LIMIT 1"
            ).fetchone()[0]
            shifted = conn.execute('SELECT datetime(?, ?)', (sample, OFFSET)).fetchone()[0]
            print(f'  {table}.{col:<14} {n:>5} 行   {sample} -> {shifted}')
            if apply:
                conn.execute(
                    f'UPDATE {table} SET {col} = datetime({col}, ?) '
                    f"WHERE {col} IS NOT NULL AND {col} <> ''", (OFFSET,))
            total += n

        if EVENTS and _table_exists(conn, 'events'):
            n = conn.execute("SELECT COUNT(*) FROM events WHERE time IS NOT NULL AND time <> ''").fetchone()[0]
            if n:
                sample = conn.execute(
                    "SELECT time FROM events WHERE time IS NOT NULL AND time <> '' "
                    "ORDER BY time LIMIT 1").fetchone()[0]
                shifted = conn.execute('SELECT datetime(?, ?)', (sample, OFFSET)).fetchone()[0]
                print(f'  {"events.time":<21} {n:>5} 行   {sample} -> {shifted}')
                if apply:
                    conn.execute(
                        "UPDATE events SET time = datetime(time, ?) "
                        "WHERE time IS NOT NULL AND time <> ''", (OFFSET,))
                    # date 要按平移后的 time 重算（跨零点的记录会换日期）
                    conn.execute(
                        "UPDATE events SET date = substr(time, 1, 10) "
                        "WHERE time IS NOT NULL AND time <> ''")
                total += n

        print('-' * 62)
        print(f'合计 {total} 个时间戳{"已修正" if apply else "待修正"}')

        if apply:
            conn.execute(
                'INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime("now", ?)) '
                'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (MARKER_KEY, 'done', OFFSET))
            conn.commit()
            print('[OK] 已写入标记 %s，重复执行会被跳过。' % MARKER_KEY)
        else:
            print('这是预览。确认无误后加 --apply 真正执行。')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())
