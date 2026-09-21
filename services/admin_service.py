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
        from datetime import datetime
        today = datetime.now().strftime('%Y-%m-%d')
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
        msgs.sort(key=lambda x: x.get('created_at') or '',
                  reverse=True)
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


admin_service = AdminService()
