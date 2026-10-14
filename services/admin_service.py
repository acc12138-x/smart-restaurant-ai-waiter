# services/admin_service.py
"""后台管理员业务逻辑"""
import time
from werkzeug.security import generate_password_hash, check_password_hash

from repositories.instances import (
    admin_user_repo, admin_log_repo,
    order_repo, member_repo, message_repo, chat_log_repo,
    kb_history_repo, table_repo,
)
from utils.exceptions import BizError


_login_fails = {}  # ip/username -> [失败时间戳]
_LOGIN_MAX = 5       # 15 分钟内最多失败 5 次
_LOGIN_WINDOW = 900  # 15 分钟


class AdminService:

    def create_admin(self, username, password, role='owner'):
        if not username or not password:
            raise BizError('用户名和密码不能为空')
        if len(password) < 6:
            raise BizError('密码至少 6 位')
        if admin_user_repo.find(username=username):
            raise BizError('用户名已存在')
        return admin_user_repo.create({
            'username': username,
            'password_hash': generate_password_hash(password),
            'role': role,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

    def verify_login(self, username, password):
        rows = admin_user_repo.find(username=username)
        if not rows:
            return None
        user = rows[0]
        if not check_password_hash(user['password_hash'], password):
            return None
        return user

    def log_action(self, admin_id, action, target='', detail='', ip=''):
        try:
            admin_log_repo.create({
                'admin_id': admin_id,
                'action': action,
                'target': target,
                'detail': detail,
                'ip': ip,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            })
        except Exception:
            pass

    def dashboard_stats(self):
        # 「今日」按北京时间算（容器默认 UTC，直接用 datetime.now() 会错 8 小时，
        # 凌晨的单子还会被算成昨天）
        from utils.timeutil import today_str
        today = today_str()
        all_orders = order_repo.get_all()
        today_orders = [o for o in all_orders
                        if (o.get('created_at') or '').startswith(today)]
        rev_total = sum(o.get('total', 0) for o in all_orders
                        if o.get('status') != 'cancelled')
        rev_today = sum(o.get('total', 0) for o in today_orders
                        if o.get('status') != 'cancelled')
        return {
            'order_total': len(all_orders),
            'order_today': len(today_orders),
            'revenue_total': round(rev_total, 2),
            'revenue_today': round(rev_today, 2),
            'user_total': member_repo.count(),
            'message_total': message_repo.count(),
            'chat_total': chat_log_repo.count(),
        }

    # ---------- 周报分析 ----------

    def weekly_report(self):
        """本周经营周报（自然周，周一~周日）

        内容：核心指标 + 环比上周 + 逐日明细 + Top 菜品 + 高峰时段 + 自动洞察。
        日期口径一律走 utils.timeutil（北京时间），不受容器时区影响。
        """
        from datetime import timedelta
        from collections import Counter
        from utils.timeutil import now, parse

        WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

        today = now().date()
        this_mon = today - timedelta(days=today.weekday())
        this_sun = this_mon + timedelta(days=6)
        last_mon = this_mon - timedelta(days=7)
        last_sun = last_mon + timedelta(days=6)

        def in_window(rows, start, end):
            out = []
            for r in rows:
                dt = parse(r.get('created_at'))
                if dt and start <= dt.date() <= end:
                    out.append(r)
            return out

        orders_all = [o for o in order_repo.get_all() if o.get('status') != 'cancelled']

        def metrics(rows):
            revenue = round(sum(float(o.get('total') or 0) for o in rows), 2)
            n = len(rows)
            return {
                'revenue': revenue,
                'orders': n,
                'avg_price': round(revenue / n, 2) if n else 0.0,
                'customers': len({o.get('uid') for o in rows if o.get('uid')}),
            }

        this_orders = in_window(orders_all, this_mon, this_sun)
        last_orders = in_window(orders_all, last_mon, last_sun)
        this_m = metrics(this_orders)
        last_m = metrics(last_orders)

        for m, start, end in ((this_m, this_mon, this_sun), (last_m, last_mon, last_sun)):
            m['new_users'] = len(in_window(member_repo.get_all(), start, end))
            m['messages'] = len(in_window(message_repo.get_all(), start, end))
            m['chats'] = len(in_window(chat_log_repo.get_all(), start, end))

        def pct(cur, prev):
            if not prev:
                return None if not cur else 100.0
            return round((cur - prev) / prev * 100, 1)

        delta = {k: pct(this_m[k], last_m[k])
                 for k in ('revenue', 'orders', 'avg_price', 'customers',
                           'new_users', 'messages', 'chats')}

        # 逐日明细（周一~周日）
        by_day = []
        for i in range(7):
            day = this_mon + timedelta(days=i)
            rows = []
            for o in this_orders:
                dt = parse(o.get('created_at'))
                if dt and dt.date() == day:
                    rows.append(o)
            by_day.append({
                'label': WEEKDAYS[i],
                'date': day.strftime('%Y-%m-%d'),
                'orders': len(rows),
                'revenue': round(sum(float(o.get('total') or 0) for o in rows), 2),
            })

        # Top 菜品（items 里带 name / qty / subtotal）
        dish_qty = Counter()
        dish_rev = Counter()
        for o in this_orders:
            for it in (o.get('items') or []):
                name = it.get('name')
                if not name:
                    continue
                dish_qty[name] += int(it.get('qty') or 0)
                dish_rev[name] += float(it.get('subtotal') or 0)
        top_dishes = [{'name': n, 'qty': q, 'revenue': round(dish_rev[n], 2)}
                      for n, q in dish_qty.most_common(5)]

        # 高峰时段
        hour_cnt = Counter()
        for o in this_orders:
            dt = parse(o.get('created_at'))
            if dt:
                hour_cnt[dt.hour] += 1
        peak = {'hour': None, 'orders': 0, 'weekday': ''}
        if hour_cnt:
            h, c = hour_cnt.most_common(1)[0]
            peak = {'hour': h, 'orders': c, 'weekday': ''}
            day_of_hour = Counter()
            for o in this_orders:
                dt = parse(o.get('created_at'))
                if dt and dt.hour == h:
                    day_of_hour[WEEKDAYS[dt.weekday()]] += 1
            if day_of_hour:
                peak['weekday'] = day_of_hour.most_common(1)[0][0]

        return {
            'range': {
                'start': this_mon.strftime('%Y-%m-%d'),
                'end': this_sun.strftime('%Y-%m-%d'),
                'label': '%s ~ %s' % (this_mon.strftime('%m-%d'), this_sun.strftime('%m-%d')),
                'last_label': '%s ~ %s' % (last_mon.strftime('%m-%d'), last_sun.strftime('%m-%d')),
            },
            'this_week': this_m,
            'last_week': last_m,
            'delta': delta,
            'by_day': by_day,
            'top_dishes': top_dishes,
            'peak': peak,
            'insights': self._weekly_insights(this_m, delta, by_day, top_dishes, peak),
        }

    @staticmethod
    def _weekly_insights(this_m, delta, by_day, top_dishes, peak):
        """把指标翻译成经营结论（纯规则，不调大模型，秒出）"""
        if not this_m['orders']:
            return ['本周还没有订单。等第一单进来，这里会自动生成经营分析。']

        ins = []
        r = delta.get('revenue')
        if r is not None:
            ins.append('本周营业额 ¥%s，环比上周%s %.1f%%。' % (
                format(this_m['revenue'], ',.0f'), '增长' if r >= 0 else '下降', abs(r)))

        busiest = max(by_day, key=lambda d: d['orders'])
        if busiest['orders']:
            ins.append('%s最忙：%d 单、¥%s。' % (
                busiest['label'], busiest['orders'], format(busiest['revenue'], ',.0f')))

        if peak.get('hour') is not None and peak.get('orders'):
            ins.append('高峰时段是%s %02d:00-%02d:00（%d 单），可以据此排班备料。' % (
                peak.get('weekday') or '本周', peak['hour'],
                (peak['hour'] + 1) % 24, peak['orders']))

        if top_dishes:
            d = top_dishes[0]
            ins.append('卖得最好是「%s」：%d 份、¥%s，注意保持备货。' % (
                d['name'], d['qty'], format(d['revenue'], ',.0f')))
            if len(top_dishes) >= 3:
                ins.append('销量前三：%s。' % '、'.join(x['name'] for x in top_dishes[:3]))

        a = delta.get('avg_price')
        if this_m['avg_price'] and a is not None:
            ins.append('客单价 ¥%.1f，环比%s %.1f%%。' % (
                this_m['avg_price'], '提升' if a >= 0 else '下降', abs(a)))

        if this_m['new_users']:
            ins.append('本周新增会员 %d 人，本周共服务 %d 位顾客。' % (
                this_m['new_users'], this_m['customers']))

        if this_m['chats']:
            ins.append('AI 店长本周接待 %d 次对话，收到 %d 条留言。' % (
                this_m['chats'], this_m['messages']))

        return ins

    # ---------- P2 新增：订单管理 ----------

    def get_orders(self, status=None, date=None, page=1, page_size=20):
        all_orders = order_repo.get_all()
        all_orders.sort(key=lambda o: o.get('created_at', ''), reverse=True)

        if status:
            all_orders = [o for o in all_orders if o.get('status') == status]
        if date:
            all_orders = [o for o in all_orders
                          if (o.get('created_at') or '').startswith(date)]

        total = len(all_orders)
        start = (page - 1) * page_size
        items = all_orders[start:start + page_size]

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': items,
        }

    def update_order_status(self, order_id, new_status, admin_id=None):
        from services.order_service import order_service
        order = order_service.update_status(order_id, new_status)
        if admin_id:
            self.log_action(admin_id, 'update_order_status',
                            target=order_id, detail=new_status)
        return order

    # ---------- P2 新增：AI 记录 ----------

    def get_chat_logs(self, page=1, page_size=20):
        all_logs = chat_log_repo.get_all()
        all_logs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        total = len(all_logs)
        start = (page - 1) * page_size
        items = all_logs[start:start + page_size]

        # 补充意图分布
        from collections import Counter
        intents = Counter(x.get('intent') for x in all_logs if x.get('intent'))

        return {
            'total': total,
            'page': page,
            'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': items,
            'intent_distribution': dict(intents.most_common(10)),
        }

    def get_event_stats(self):
        """埋点统计（转发给 track_service）"""
        try:
            from services.track_service import track_service
            return track_service.get_stats()
        except Exception:
            return {
                'total_events': 0, 'total_visitors': 0,
                'today': {'visitors': 0, 'page_view': 0,
                          'chat_message': 0, 'order_created': 0},
                'event_distribution': {}, 'page_distribution': {},
                'intent_distribution': {}, 'hot_questions': [],
                'order_summary': {'count': 0, 'total': 0},
            }

    # ---------- P3 · 用户管理 ----------

    def get_users(self, keyword=None, page=1, page_size=20):
        users = member_repo.get_all()
        users.sort(key=lambda u: u.get('created_at', ''), reverse=True)
        if keyword:
            kw = keyword.lower()
            users = [u for u in users
                     if kw in (u.get('username') or '').lower()
                     or kw in (u.get('nickname') or '').lower()
                     or kw in (u.get('uid') or '').lower()]
        total = len(users)
        start = (page - 1) * page_size
        return {
            'total': total, 'page': page, 'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': users[start:start + page_size],
        }

    def adjust_points(self, uid, delta, reason, admin_id=None):
        from services.points_service import points_service
        result = points_service.add_points(uid, int(delta), reason=reason)
        if result is None:
            from utils.exceptions import BizError
            raise BizError('用户不存在', code=404)
        if admin_id:
            self.log_action(admin_id, 'adjust_points',
                            target=uid, detail=f'{delta} 分 · {reason}')
        return result

    def toggle_user_disabled(self, uid, disabled, admin_id=None):
        member = member_repo.find_by_id(uid)
        if not member:
            from utils.exceptions import BizError
            raise BizError('用户不存在', code=404)
        member_repo.update(uid, {'disabled': 1 if disabled else 0})
        if admin_id:
            self.log_action(admin_id,
                            'disable_user' if disabled else 'enable_user',
                            target=uid)
        return member_repo.find_by_id(uid)

    # ---------- P3 · 留言管理 ----------

    def get_messages(self, page=1, page_size=20, unread_only=False):
        msgs = message_repo.get_all()
        # 排序：先按时间倒序，时间相同（或都为空）时按 id 倒序
        msgs.sort(key=lambda x: (
            x.get('created_at') or '',
            x.get('id', 0)
        ), reverse=True)
        if unread_only:
            msgs = [m for m in msgs if not m.get('read')]
        total = len(msgs)
        start = (page - 1) * page_size
        return {
            'total': total, 'page': page, 'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': msgs[start:start + page_size],
            'unread_count': sum(1 for m in message_repo.get_all()
                                if not m.get('read')),
        }

    def delete_message(self, msg_id, admin_id=None):
        """删除留言"""
        msg = message_repo.find_by_id(msg_id)
        if not msg:
            raise BizError('留言不存在', code=404)
        message_repo.delete(msg_id)
        if admin_id:
            self.log_action(admin_id, 'delete_message',
                            target=str(msg_id),
                            detail=(msg.get('content') or '')[:50])
        return msg

    def mark_message_read(self, msg_id, read=True, admin_id=None):
        result = message_repo.update(msg_id, {'read': 1 if read else 0})
        if result is None:
            from utils.exceptions import BizError
            raise BizError('留言不存在', code=404)
        if admin_id:
            self.log_action(admin_id, 'mark_message_read',
                            target=str(msg_id))
        return result

    # ---------- P3 · 操作日志 ----------

    def get_admin_logs(self, page=1, page_size=30):
        logs = admin_log_repo.get_all()
        logs.sort(key=lambda x: x.get('created_at') or '',
                  reverse=True)
        total = len(logs)
        start = (page - 1) * page_size

        # 补上 admin username
        admins = {u['id']: u['username']
                  for u in admin_user_repo.get_all()}
        items = []
        for lg in logs[start:start + page_size]:
            lg = dict(lg)
            lg['admin_name'] = admins.get(lg.get('admin_id'), '—')
            items.append(lg)

        return {
            'total': total, 'page': page, 'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': items,
        }


    # ---------- P4 · 知识库版本历史 ----------

    def save_kb_version(self, filename, content):
        """保存一份知识库快照"""
        existing = kb_history_repo.find(filename=filename)
        next_ver = max([h.get('version', 0) for h in existing] + [0]) + 1
        return kb_history_repo.create({
            'filename': filename,
            'content': content,
            'version': next_ver,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

    def get_kb_versions(self, filename=None, page=1, page_size=20):
        all_history = kb_history_repo.get_all()
        if filename:
            all_history = [h for h in all_history
                           if h.get('filename') == filename]
        all_history.sort(
            key=lambda h: (h.get('filename', ''), -h.get('version', 0)))
        total = len(all_history)
        start = (page - 1) * page_size
        items = []
        for h in all_history[start:start + page_size]:
            items.append({
                'id': h.get('id'),
                'filename': h.get('filename'),
                'version': h.get('version'),
                'created_at': h.get('created_at'),
                'preview': (h.get('content') or '')[:80],
                'size': len(h.get('content') or ''),
            })
        return {
            'total': total, 'page': page, 'page_size': page_size,
            'pages': max(1, (total + page_size - 1) // page_size),
            'items': items,
        }

    def get_kb_version(self, version_id):
        return kb_history_repo.find_by_id(version_id)

    def rollback_kb_version(self, version_id, admin_id=None):
        import os
        from configs.config import get_config
        v = kb_history_repo.find_by_id(version_id)
        if not v:
            raise BizError('版本不存在', code=404)
        filename = v['filename']
        content = v.get('content') or ''

        cfg = get_config()
        KB_DIR = cfg.DOCS_DIR
        path = os.path.join(KB_DIR, filename)
        if not os.path.abspath(path).startswith(os.path.abspath(KB_DIR)):
            raise BizError('非法路径', code=403)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        try:
            from services import rag_service
            rag_service.rebuild_knowledge_base()
        except Exception as e:
            raise BizError(f'回滚成功但重建失败: {e}', code=500)

        self.save_kb_version(filename, content)

        if admin_id:
            self.log_action(admin_id, 'kb_rollback',
                            target=filename, detail=f'v{v["version"]}')
        return {'filename': filename, 'version': v['version']}


    # ---------- P5 · 桌码管理 ----------

    def get_tables(self):
        tables = table_repo.get_all()
        tables.sort(key=lambda t: t.get('table_no', ''))
        return tables

    def create_table(self, table_no):
        table_no = (table_no or '').strip()
        if not table_no:
            raise BizError('桌号不能为空', code=400)
        if len(table_no) > 10:
            raise BizError('桌号最长 10 个字符', code=400)
        if table_repo.find(table_no=table_no):
            raise BizError('桌号 ' + table_no + ' 已存在', code=400)
        return table_repo.create({
            'table_no': table_no,
            'scan_count': 0,
            'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })

    def delete_table(self, table_id):
        t = table_repo.find_by_id(table_id)
        if not t:
            raise BizError('桌号不存在', code=404)
        table_repo.delete(table_id)
        return t

    def record_scan(self, table_no):
        """扫码计数 +1（不存在则创建）"""
        tables = table_repo.find(table_no=table_no)
        if tables:
            t = tables[0]
            table_repo.update(t['id'],
                              {'scan_count': (t.get('scan_count') or 0) + 1})
        else:
            table_repo.create({
                'table_no': table_no,
                'scan_count': 1,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            })


    # ---------- v3.1 · 菜单管理 ----------

    def get_menu(self):
        from services.menu_service import menu_service
        return menu_service.get_all()

    def save_menu_item(self, category, item, old_name=None, admin_id=None):
        from services.menu_service import menu_service
        if old_name:
            result = menu_service.update_item(category, old_name, item)
            action = 'menu_item_update'
        else:
            result = menu_service.add_item(category, item)
            action = 'menu_item_add'
        if admin_id:
            self.log_action(admin_id, action,
                            target=f'{category}/{item.get("name")}')
        return result

    def delete_menu_item(self, category, name, admin_id=None):
        from services.menu_service import menu_service
        result = menu_service.delete_item(category, name)
        if admin_id:
            self.log_action(admin_id, 'menu_item_delete',
                            target=f'{category}/{name}')
        return result

    def add_menu_category(self, name, admin_id=None):
        from services.menu_service import menu_service
        result = menu_service.add_category(name)
        if admin_id:
            self.log_action(admin_id, 'menu_cat_add', target=name)
        return result

    def delete_menu_category(self, name, admin_id=None):
        from services.menu_service import menu_service
        result = menu_service.delete_category(name)
        if admin_id:
            self.log_action(admin_id, 'menu_cat_delete', target=name)
        return result


    # ---------- v3.8 应用日志 ----------

    def get_app_logs(self, level=None, page=1, page_size=30):
        from repositories.sqlite_repo import get_conn
        conn = get_conn()
        try:
            where = 'WHERE 1=1'
            params = []
            if level:
                where += ' AND level = ?'
                params.append(level)
            cur = conn.execute('SELECT COUNT(*) as c FROM app_logs ' + where, params)
            total = cur.fetchone()['c']
            start = (page - 1) * page_size
            cur = conn.execute(
                'SELECT * FROM app_logs ' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                params + [page_size, start]
            )
            items = [dict(r) for r in cur.fetchall()]
            return {
                'total': total, 'page': page, 'page_size': page_size,
                'pages': max(1, (total + page_size - 1) // page_size),
                'items': items,
            }
        finally:
            conn.close()

    def get_slow_requests(self, limit=10):
        from repositories.sqlite_repo import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                'SELECT id, method, url, elapsed_ms, ip, uid, created_at '
                'FROM app_logs WHERE elapsed_ms IS NOT NULL '
                'ORDER BY elapsed_ms DESC LIMIT ?', (limit,))
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_app_log_stats(self):
        from repositories.sqlite_repo import get_conn
        conn = get_conn()
        try:
            cur = conn.execute(
                'SELECT level, COUNT(*) as c FROM app_logs GROUP BY level')
            by_level = {r['level']: r['c'] for r in cur.fetchall()}
            cur = conn.execute(
                'SELECT COUNT(*) as c FROM app_logs WHERE elapsed_ms IS NOT NULL')
            slow_count = cur.fetchone()['c']
            cur = conn.execute('SELECT COUNT(*) as c FROM app_logs')
            total = cur.fetchone()['c']
            return {'total': total, 'by_level': by_level, 'slow_count': slow_count}
        finally:
            conn.close()

    def check_login_limit(self, key):
        """返回 True 表示允许登录"""
        import time as _t
        now = _t.time()
        fails = [t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW]
        _login_fails[key] = fails
        return len(fails) < _LOGIN_MAX

    def record_login_fail(self, key):
        import time as _t
        _login_fails.setdefault(key, []).append(_t.time())

    def clear_login_fails(self, key):
        _login_fails.pop(key, None)

    def get_login_fail_count(self, key):
        import time as _t
        now = _t.time()
        return len([t for t in _login_fails.get(key, []) if now - t < _LOGIN_WINDOW])


admin_service = AdminService()
