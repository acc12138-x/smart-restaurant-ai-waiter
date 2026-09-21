# services/chat_service.py
from services import intent_service
from services.order_service import order_service
from services.session_service import session_service
from utils.logger import logger
import time as _time

class ChatService:
    """AI 对话业务逻辑"""

    CUT_MARKERS = [
        '用户：', '用户:',
        '助手：', '助手:',
        '问题：', '问题:',
        '回答：', '回答:',
        '\n用户', '\n助手',
        '\n问题', '\n回答',
    ]

    FOLLOWUP_WORDS = ['呢', '那个', '这个', '多少', '一份', '一个', '两份', '两个', '三份', '来点', '再要']
    ORDER_WORDS = ['我要', '来一', '来两', '来三', '点一', '点两', '点三', '要一', '要两', '要三', '给我']

    def _clean(self, text: str) -> str:
        if not text:
            return ''
        for m in self.CUT_MARKERS:
            idx = text.find(m)
            if idx > 0:
                text = text[:idx].strip()
                break
        for prefix in ['用户：', '用户:', '助手：', '助手:', '问题：', '问题:', '回答：', '回答:']:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        return text

    def _is_followup(self, message: str) -> bool:
        if len(message) > 12:
            return False
        return any(w in message for w in self.FOLLOWUP_WORDS)

    def _find_last_user_msg(self, uid):
        history = session_service.get_history(uid)
        for item in reversed(history[:-1]):
            if item['role'] == 'user':
                return item['content']
        return None

    def _handle_modify_order(self, uid, message):
        """把'把X改成Y'解析成：取消含X的最近订单 + 用Y下新单"""
        if not uid:
            return '修改订单需要先登录哦～ 点底部「我的」→「立即登录」。'

        import re
        from services.menu_service import menu_service

        # 切分："把A改成B" "A换成B"
        parts = re.split(r'(?:改成|换成|替换成|改为|换为)', message, maxsplit=1)
        if len(parts) != 2:
            return '没看懂您想改成什么，请说"把牛肉泡馍改成羊肉泡馍"这种格式。'

        old_part = re.sub(r'^(把|将)', '', parts[0]).strip()
        new_part = parts[1].strip()

        # 从 new_part 里提取新菜名 + 数量
        new_items = self._extract_items_from_text(new_part)
        if not new_items:
            # 尝试单独匹配菜名
            for dish in menu_service.get_flat():
                if dish['name'] in new_part:
                    new_items = [{'name': dish['name'], 'qty': 1}]
                    break
        if not new_items:
            return f'没找到「{new_part}」这道菜，请换一种说法。'

        qty_err = self._validate_qty(new_items[0]['qty'])
        if qty_err:
            return qty_err

        # 取消含 old_part 的最近一单（复用 cancel 逻辑）
        cancel_msg = self._handle_cancel_order(uid, old_part)
        # 下单新菜
        try:
            result = order_service.create(new_items, table_no='外带', uid=uid)
            reply = order_service.format_reply(result)
            session_service.add_order(uid, result['order'])
            return f'已改单。\n原订单处理：{cancel_msg}\n新订单：{reply}'
        except Exception as e:
            return f'取消原订单成功，但下新单失败：{e}'

    def _handle_cancel_all(self, uid):
        """取消**本会话**所有 pending/paid 订单
        不扫全库，避免误取消历史订单
        """
        if not uid:
            return '取消订单需要先登录哦～ 点底部「我的」→「立即登录」。'

        cancellable = [o for o in session_service.get_orders(uid)
                       if o.get('status') in ('pending', 'paid')]

        if not cancellable:
            return '您本次会话没有可取消的订单哦～（历史订单请到「我的」页面单独处理）'

        # 按时间倒序
        cancellable.sort(key=lambda o: o.get('created_at', '') or '', reverse=True)

        ok = []
        fail = []
        for o in cancellable:
            try:
                # 拿最新状态（可能后台改过）
                latest = order_service.get(o['id'])
                if not latest:
                    fail.append(f"{o['id']}（已不存在）")
                    continue
                st = latest.get('status', 'pending')
                if st not in ('pending', 'paid'):
                    fail.append(f"{o['id']}（状态 {st} 无法取消）")
                    continue
                order_service.update_status(o['id'], 'cancelled')
                session_service.update_order_status(uid, o['id'], 'cancelled')
                items_str = '、'.join(
                    f"{it.get('name')}×{it.get('qty')}"
                    for it in latest.get('items', []))
                ok.append(f"  · {o['id']}  {items_str}  ¥{latest.get('total', 0)}")
            except Exception as e:
                fail.append(f"{o['id']}（{e}）")

        lines = []
        if ok:
            total_cancelled = len(ok)
            lines.append(f'已为您取消 {total_cancelled} 单：')
            lines.extend(ok)
        if fail:
            lines.append(f'以下 {len(fail)} 单未取消：')
            for f in fail:
                lines.append(f'  · {f}')

        if not lines:
            return '取消操作未生效，请稍后再试。'
        return '\n'.join(lines)

    def _handle_cancel_order(self, uid, message):
        """处理取消订单意图
        1. 未登录 → 提示登录
        2. 从 session 找可取消订单（pending/paid）
        3. 用户提到某菜名 → 优先取消含该菜的最近订单
        4. 未提菜名 → 取消最近一单
        5. 调用 order_service 走状态机
        """
        if not uid:
            return '取消订单需要先登录哦～ 点底部「我的」→「立即登录」。'

        from services.menu_service import menu_service

        # ========== 合并 session + DB，按创建时间倒序 ==========
        seen_ids = set()
        cancellable = []

        # 1. session 里的（本会话的）
        for o in session_service.get_orders(uid):
            if o.get('status') in ('pending', 'paid') and o.get('id') not in seen_ids:
                seen_ids.add(o['id'])
                cancellable.append(o)

        # 2. 数据库里的（跨会话的，避免漏掉）
        try:
            from repositories.instances import order_repo
            db_orders = order_repo.find(uid=uid)
            for o in db_orders:
                if o.get('status') in ('pending', 'paid') and o.get('id') not in seen_ids:
                    seen_ids.add(o['id'])
                    cancellable.append({
                        'id': o['id'],
                        'total': float(o.get('total', 0) or 0),
                        'items': o.get('items', []),
                        'created_at': o.get('created_at', ''),
                    })
        except Exception as e:
            from utils.logger import logger
            logger.warning(f'取消订单：查 DB 失败 {e}')

        # 按 created_at 降序，最新的在最前
        cancellable.sort(key=lambda o: o.get('created_at', '') or '', reverse=True)

        if not cancellable:
            return '您没有可取消的订单哦～'

        # 尝试从消息里提取菜名
        target = None
        for dish in menu_service.get_flat():
            if dish['name'] in message:
                # cancellable 已倒序，第一条匹配就是最新的
                for o in cancellable:
                    names = [it.get('name') for it in o.get('items', [])]
                    if dish['name'] in names:
                        target = o
                        break
                if target:
                    break

        # 没指定菜名 → 取最新一单（cancellable[0]）
        if not target:
            target = cancellable[0]

        order_id = target['id']

        # 查最新状态（可能被后台改了）
        latest = order_service.get(order_id)
        if not latest:
            return f'订单 {order_id} 已不存在，可能已被删除。'
        st = latest.get('status', 'pending')
        if st not in ('pending', 'paid'):
            return f'订单 {order_id} 当前状态是「{st}」，无法在线取消，请联系店员。'

        # 取消
        try:
            order_service.update_status(order_id, 'cancelled')
            session_service.update_order_status(uid, order_id, 'cancelled')
            items_str = '、'.join(
                f"{it.get('name')}×{it.get('qty')}"
                for it in latest.get('items', []))
            return (f'好的，订单 {order_id}（{items_str}，'
                    f'¥{latest.get("total", 0)}）已取消。\n'
                    f'如已发放积分会自动扣回。')
        except Exception as e:
            from utils.exceptions import BizError
            if isinstance(e, BizError):
                return f'取消失败：{e.msg}'
            return f'取消失败：{e}'

    def _validate_qty(self, qty):
        """数量校验：0/负 或 >50 返回错误信息；正常返回 None"""
        try:
            q = int(qty)
        except (ValueError, TypeError):
            return '数量必须是整数'
        if q <= 0:
            return '数量至少 1 份哦～'
        if q > 50:
            return f'单次最多 50 份（您要了 {q} 份），建议分次下单或联系店员'
        return None


    def _is_vague_dish(self, message):
        """检测模糊菜名：'要泡馍' → 返回候选菜名列表；不模糊 → None"""
        from services.menu_service import menu_service
        import re

        # 提取纯菜品关键词（去掉数量、动词）
        m = re.sub(r'[一两二三四五六七八九十百\d]+\s*[份个碗杯瓶盘]', '', message)
        m = re.sub(r'(我要|来|点|要|给我|打包|下单|吃|喝|一个|一份|两个|两份)',
                   '', m).strip()
        m = re.sub(r'[，。！？!?；;、\s]+', '', m)
        if not m or len(m) < 2:
            return None

        # 1. 完整菜名匹配 → 不模糊
        for d in menu_service.get_flat():
            if d['name'] == m or d['name'] in message:
                return None

        # 2. 检查是否是某类菜品的泛称
        VAGUE_GROUPS = {
            '泡馍': ['牛肉泡馍(小份)', '牛肉泡馍(大份)', '羊肉泡馍',
                     '优质羊肉泡馍'],
            '面': ['臊子面', '臊夹面', 'biangbiang面', '优质羊肉泡面'],
            '汤': ['肉丸胡辣汤'],
            '蒜': ['糖蒜(整头)', '肉蒜', '糖蒜(剥好)'],
            '汽水': ['冰峰汽水'],
            '饮料': ['冰峰汽水'],
        }
        for k, candidates in VAGUE_GROUPS.items():
            if k in m:
                return candidates
        return None

    def _extract_qty_from_message(self, message):
        """从消息里提取数量，没有则返回 1"""
        import re
        try:
            from services.intent_service import _parse_cn_number
        except Exception:
            return 1
        m = re.search(r'(\d+|[一两二三四五六七八九十百]+)\s*[份个碗杯瓶盘]',
                      message or '')
        if m:
            try:
                return max(1, _parse_cn_number(m.group(1)))
            except Exception:
                return 1
        return 1

    def _find_last_dish_in_history(self, uid, prefer_size=None):
        """从历史里找最近提到的菜品
        只从**用户消息**里找，避免匹配到 AI 回复里的枚举菜单
        prefer_size='大份'/'小份' 时强制优先返回带该份量的名字
        """
        from services.menu_service import menu_service

        def simplify(name):
            x = name
            if '(' in x: x = x.split('(')[0]
            if '（' in x: x = x.split('（')[0]
            return x.strip()

        history = session_service.get_history(uid)
        all_dishes = menu_service.get_flat()

        # 只保留 user 角色的历史（排除 AI 的推荐/列举）
        user_msgs = [item for item in history[:-1]
                     if item.get('role') == 'user']

        # ========== 第一步：如果指定了 prefer_size，优先找带该份量的 ==========
        if prefer_size:
            for item in reversed(user_msgs):
                content = item.get('content', '')
                # 1) 完整名（带括号）且含 prefer_size 直接命中
                for dish in all_dishes:
                    if prefer_size in dish['name'] and dish['name'] in content:
                        return dish['name']
                # 2) 简名匹配 → 用 prefer_size 拼完整名
                for dish in all_dishes:
                    simple = simplify(dish['name'])
                    if len(simple) >= 2 and simple in content:
                        candidates = [d for d in all_dishes
                                      if simplify(d['name']) == simple]
                        for c in candidates:
                            if prefer_size in c['name']:
                                return c['name']
                        return candidates[0]['name'] if candidates else None

        # ========== 第二步：无 prefer_size，从用户消息里找菜名 ==========
        for item in reversed(user_msgs):
            content = item.get('content', '')
            for dish in all_dishes:
                if dish['name'] in content:
                    return dish['name']
            for dish in all_dishes:
                simple = simplify(dish['name'])
                if len(simple) >= 2 and simple in content:
                    return dish['name']
        return None

    def _is_order_intent_weak(self, message: str) -> bool:
        from services.menu_service import menu_service
        m = (message or '').strip()

        # "套餐"是整体推荐请求，不是弱意图
        if '套餐' in message:
            return False

        # 极短句"要/要X"（要、要大份、要小份、要一份、要个）→ 弱下单
        if len(m) <= 4 and m.startswith('要'):
            if not any(w in m for w in ('多少', '什么', '啥', '哪', '几', '吗', '钱')):
                for dish in menu_service.get_flat():
                    if dish['name'] in message:
                        return False
                return True

        # 极短句"X份/X个/X碗"（两份、十份、2份、3个）→ 弱下单
        import re as _re
        if _re.match(r'^\s*[一两二三四五六七八九十百\d]+\s*[份个碗杯瓶盘]\s*$', m):
            return True

        # 极短句"我要吃X碗" → 弱下单
        if len(m) <= 6 and ('吃' in m or '喝' in m) and \
           _re.search(r'[一两二三四五六七八九十百\d]+\s*[碗份个杯]', m):
            return True

        if not any(w in message for w in self.ORDER_WORDS):
            return False
        for dish in menu_service.get_flat():
            if dish['name'] in message:
                return False
        keywords = ['泡馍', '面', '汤', '凉皮', '蒜', '汽水', '饮料']
        for kw in keywords:
            if kw in message:
                return False
        return True

    def _extract_items_from_text(self, text: str) -> list:
        """从用户输入提取菜品和数量"""
        import re
        from collections import defaultdict
        from services.menu_service import menu_service

        def simplify(name):
            s = name
            if '(' in s:
                s = s.split('(')[0]
            if '（' in s:
                s = s.split('（')[0]
            return s.strip()

        # 用 intent_service 里的中文数字解析
        from services.intent_service import _parse_cn_number

        name_map = defaultdict(list)
        for dish in menu_service.get_flat():
            simple = simplify(dish['name'])
            name_map[simple].append(dish['name'])

        items = []
        matched_simple = set()

        # 量词集合
        UNITS = '[份个碗杯瓶盘]'
        # 数量正则：阿拉伯数字 或 中文数字（含"十"、"二十"等）
        QTY_PATTERN = r'(\d+|[一两二三四五六七八九十百]+)'

        for simple in sorted(name_map.keys(), key=len, reverse=True):
            if simple not in text:
                continue
            if any(simple in s for s in matched_simple):
                continue
            matched_simple.add(simple)

            qty = 1
            pos = text.find(simple)

            # 1) 先看菜名后方 "X份/X个/X碗"（如"糖蒜两个"、"羊肉泡馍十份"）
            suffix = text[pos + len(simple):pos + len(simple) + 8]
            m2 = re.search(QTY_PATTERN + r'\s*' + UNITS, suffix)
            if m2:
                qty = _parse_cn_number(m2.group(1))
            else:
                # 2) 再看菜名前方的"X份/X个"（如"两个糖蒜"、"十份羊肉泡馍"）
                prefix = text[max(0, pos - 8):pos]
                m1 = re.search(QTY_PATTERN + r'\s*' + UNITS, prefix)
                if m1:
                    qty = _parse_cn_number(m1.group(1))

            # 3) 兜底：找消息里所有"X份"里最后一个（"我要吃十碗" 这种没有菜名的）
            if qty == 1:
                m3 = re.search(QTY_PATTERN + r'\s*' + UNITS, text)
                if m3:
                    qty = _parse_cn_number(m3.group(1))

            candidates = name_map[simple]
            chosen = candidates[0]
            if len(candidates) > 1:
                if '小份' in text:
                    chosen = next((c for c in candidates if '小份' in c), candidates[0])
                elif '大份' in text:
                    chosen = next((c for c in candidates if '大份' in c), candidates[0])

            items.append({'name': chosen, 'qty': qty})

        return items

    def chat(self, message: str, uid: str = None, table_no: str = '外带') -> dict:
        """非流式聊天（复合意图复用此方法）"""
        history_text = session_service.format_history(uid, max_rounds=3)
        session_service.add(uid, 'user', message)

        result = intent_service.classify_intent(message, history=history_text)
        intent = result['intent']
        items = result.get('items', [])
        logger.info(f"[Chat] uid={uid} 用户: {message} | 意图: {intent} | 商品: {items}")

        # ============ 门店 FAQ ============
        STORE_FAQ = {
            # 位置/交通
            '地址': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '位置': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '在哪': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '怎么走': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '怎么过来': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '怎么去': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '地铁': '地铁 2 号线钟楼站 C 口出，步行 300 米就到了。',
            '导航': '导航搜「同盛祥泡馍老店」，地铁 2 号线钟楼站 C 口出，步行 300 米。',
            # 营业时间
            '营业时间': '每天 10:30 至次日 02:00。深夜 21:00 后进店送热汤。',
            '几点': '每天 10:30 至次日 02:00。深夜 21:00 后进店送热汤。',
            '几点开门': '每天 10:30 开门，至次日 02:00。',
            '几点关门': '每天营业到次日 02:00，深夜 21:00 后进店送热汤。',
            '关门': '每天营业到次日 02:00，深夜 21:00 后进店送热汤。',
            '打烊': '每天营业到次日 02:00。',
            # 电话
            '电话': '电话是 029-8888 6666。',
            '号码': '电话是 029-8888 6666。',
            '联系': '电话是 029-8888 6666。',
            '联系方式': '电话是 029-8888 6666。',
            # 历史/品牌
            '什么时候开': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '哪年': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '创立': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '开业': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '几年了': '同盛祥创立于 1994 年，经营 30 年，是西安老字号。',
            '老汤': '每天凌晨四点开始吊汤，用牛骨、羊肉和二十余味香料熬制，三十年从没断过火。',
            '三十年': '1994 年开店，老汤三十年没断过火。每天凌晨四点开始吊汤，牛骨+羊肉+二十余味香料。',
            '翻新': '2025 年门店翻新，保留老汤锅和木梁，加入暖黄灯光、原木长桌和动漫插画墙。',
            '装修': '2025 年门店翻新，保留老汤锅和木梁，加入暖黄灯光、原木长桌和动漫插画墙。',
            # 深夜食堂
            '深夜食堂': '晚上 21:00 后进店送热汤，营业到次日 02:00。',
            '宵夜': '每天营业到次日 02:00，晚上 21:00 后进店送热汤。',
            '夜宵': '每天营业到次日 02:00，晚上 21:00 后进店送热汤。',
            # 吃法（高频）
            '怎么吃': '馍掰成黄豆大小，越小越入味，配糖蒜和辣子酱，最后来口汤。',
            '正宗': '馍掰成黄豆大小，配糖蒜和辣子酱，用老汤煮，最后来口汤。',
            '吃法': '先掰馍（黄豆大小），下锅煮，配糖蒜、辣子酱，最后喝汤。',
            '配什么': '标配是糖蒜和辣子酱，再来瓶冰峰或酸梅汤，解腻又够味。',
            # 解腻/搭配
            '解腻': '凉皮或糖蒜都很解腻，再喝口酸梅汤，比冰峰更清爽。',
            '搭配': '凉皮或糖蒜都很解腻，再喝口酸梅汤，比冰峰更清爽。',
            '推荐': '第一次来推荐招牌牛肉泡馍(小份) + 凉拌牛腱 + 冰峰汽水，人均 40 上下。',
            # 健康
            '孕妇': '孕期饮食建议以医嘱为准，来店里可以告诉店员您的忌口，我们帮您调整汤的油盐量。',
            '糖尿病': '健康问题请以医嘱为准，来店里可以告诉店员您的忌口，我们帮您调整汤的油盐量。',
        }
        for kw, answer in STORE_FAQ.items():
            if kw in message:
                session_service.add(uid, 'assistant', answer)
                return {'reply': answer, 'intent': intent, 'order': None}

        # ============ 健康关键词 ============
        health_keywords = [
            '糖尿病', '高血压', '高血脂', '血糖', '血压', '胆固醇',
            '孕妇', '怀孕', '哺乳', '过敏', '忌口', '痛风', '肾病',
            '胃病', '胃炎', '胃溃疡', '心脏病', '冠心病', '中风',
            '能不能吃', '可以吃吗', '适合吃', '能吃吗',
        ]
        if any(kw in message for kw in health_keywords):
            reply = (
                '这个建议您以医生或营养师的建议为准。'
                '如果您来店里，可以告诉店员您的忌口，'
                '我们帮您调整汤的油盐量和配菜。'
            )
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': intent, 'order': None}

        # ============ 会话聚合查询（一共/总共/合计多少钱）============
        if intent == 'query_total':
            # 先判断消息里是否提到具体菜品 → 走菜品价格合计
            from services.menu_service import menu_service
            mentioned = []
            for dish in menu_service.get_flat():
                if dish['name'] in message:
                    mentioned.append(dish)
                else:
                    # 简名匹配
                    simple = dish['name'].split('(')[0].split('（')[0].strip()
                    if len(simple) >= 2 and simple in message:
                        mentioned.append(dish)
            # 去重（同名菜只留一个）
            seen = set()
            uniq = []
            for d in mentioned:
                if d['name'] not in seen:
                    seen.add(d['name'])
                    uniq.append(d)

            if uniq:
                lines = []
                sum_price = 0
                for d in uniq:
                    lines.append(f"  · {d['name']}：{d['price']} 元")
                    sum_price += float(d['price'])
                reply = '您问的这几样：\n' + '\n'.join(lines) + \
                        f'\n合计 {sum_price:.2f} 元。'
            else:
                # 没提到具体菜 → 会话订单合计
                orders = session_service.get_orders(uid)
                if orders:
                    total_sum = sum(o['total'] for o in orders)
                    lines = ['您这次一共下了 ' + str(len(orders)) + ' 单，合计 '
                             + f'{total_sum:.2f}' + ' 元：']
                    for i, o in enumerate(orders, 1):
                        items_str = '、'.join(
                            f"{it['name']}×{it['qty']}"
                            for it in o.get('items', []))
                        lines.append(f'  {i}. {items_str} = {o["total"]:.2f} 元')
                    reply = '\n'.join(lines)
                else:
                    reply = '您这次会话还没下单哦～想吃点什么？'
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': 'query_total', 'order': None}


        # ============ 批量取消 ============
        if intent == 'cancel_all':
            reply = self._handle_cancel_all(uid)
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': 'cancel_all', 'order': None}

        # ============ 取消订单 ============
        if intent == 'cancel_order':
            reply = self._handle_cancel_order(uid, message)
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': 'cancel_order', 'order': None}

        # ============ 推荐 ============
        if intent == 'recommend':
            reply = self._handle_recommend(message, uid)
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': 'recommend', 'order': None}

        # ============ 修改订单 ============
        if intent == 'modify_order':
            reply = self._handle_modify_order(uid, message)
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': 'modify_order', 'order': None}

        # ============ 点菜（必须登录）============
        if intent == 'place_order':
            if not uid:
                reply = '下单前请先登录哦～ 点底部「我的」→「立即登录」，登录后每 1 元累积 1 积分。'
                session_service.add(uid, 'assistant', reply)
                return {'reply': reply, 'intent': intent, 'order': None,
                        'need_login': True}

            # 模糊菜名检测（"要泡馍" → 反问）
            vague = self._is_vague_dish(message)
            if vague and len(vague) > 1:
                opts = '、'.join('「' + v + '」' for v in vague[:4])
                reply = f'您想点的是哪一种？我们这儿有 {opts}，请说得具体些～'
                session_service.add(uid, 'assistant', reply)
                return {'reply': reply, 'intent': intent, 'order': None}

            if not items:
                items = self._extract_items_from_text(message)

            # 数量校验
            for it in items:
                err = self._validate_qty(it.get('qty', 1))
                if err:
                    session_service.add(uid, 'assistant', err)
                    return {'reply': err, 'intent': intent, 'order': None}
            if not items and self._is_order_intent_weak(message):
                # 从消息里提取份量偏好
                prefer = None
                if '大份' in message:
                    prefer = '大份'
                elif '小份' in message:
                    prefer = '小份'
                last_dish = self._find_last_dish_in_history(uid, prefer_size=prefer)
                if last_dish:
                    qty = self._extract_qty_from_message(message)
                    items = [{'name': last_dish, 'qty': qty}]

            if items:
                try:
                    order_result = order_service.create(items, table_no=table_no, uid=uid)
                    reply = order_service.format_reply(order_result)
                    session_service.add(uid, 'assistant', reply)
                    session_service.add_order(uid, order_result['order'])
                    return {'reply': reply, 'intent': intent, 'order': order_result['order']}
                except Exception as e:
                    session_service.add(uid, 'assistant', str(e))
                    return {'reply': str(e), 'intent': intent, 'order': None}
            else:
                reply = '请问您想点什么？比如「牛肉泡馍」「羊肉泡馍」「冰峰汽水」。'
                session_service.add(uid, 'assistant', reply)
                return {'reply': reply, 'intent': intent, 'order': None}

        # ============ 闲聊 ============
        if intent == 'chat':
            # 判断是不是"好的/嗯/行"等确认词
            if message.strip() in ('好的', '好呀', '好嘞', '行吧', '可以', '嗯', 'OK', 'ok'):
                reply = '好嘞！需要我帮您下单吗？可以告诉我菜品名字和份数，比如「来一份牛肉泡馍」。'
            else:
                reply = '你好！我是同盛祥的小助手，可以问我菜单、营业时间、门店地址，也可以直接点菜。'
            session_service.add(uid, 'assistant', reply)
            return {'reply': reply, 'intent': intent, 'order': None}

        # ============ 菜单快路径 ============
        from services.rag_service import chat_with_rag_stream
        answer = ''.join(chat_with_rag_stream(message))
        cleaned = self._clean(answer)
        session_service.add(uid, 'assistant', cleaned)
        return {'reply': cleaned, 'intent': intent, 'order': None}

    def chat_stream(self, message: str, uid: str = None, table_no: str = '外带'):
        """流式处理一条消息
        支持复合意图：一句话问多件事，逐段处理
        """
        import re

        # 按标点拆分：逗号、句号、问号、感叹号、分号
        parts = [p.strip() for p in re.split(r'[，。！？!?；;]+', message) if p.strip()]

        # 多意图：逐段处理，拼成一段回答
        if len(parts) > 1:
            logger.info(f"[Chat-Stream-Multi] uid={uid} 用户: {message} | 拆分: {parts}")
            yield ('meta', {'intent': 'multi'})

            session_service.add(uid, 'user', message)

            all_replies = []
            for part in parts:
                # 逐段调用非流式 chat（简单可靠）
                result = self.chat(part, uid, table_no)
                if result.get('reply'):
                    all_replies.append(result['reply'])

            full_reply = '\n\n'.join(all_replies)
            yield ('text', full_reply)
            yield ('done', None)
            return

        # 单意图：走原有逻辑
        yield from self._single_intent_stream(message, uid, table_no)

    def _single_intent_stream(self, message: str, uid: str = None, table_no: str = '外带'):
        """单意图流式处理（原 chat_stream 逻辑）"""
        history_text = session_service.format_history(uid, max_rounds=3)
        session_service.add(uid, 'user', message)

        # 意图识别
        result = intent_service.classify_intent(message, history=history_text)
        intent = result['intent']
        logger.info(f"[Chat-Stream] uid={uid} 用户: {message} | 意图: {intent}")

        yield ('meta', {'intent': intent})

        # ============ 门店 FAQ 快路径 ============
        STORE_FAQ = {
            # 位置/交通
            '地址': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '位置': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '在哪': '同盛祥西安泡馍老店在西安市碑林区老巷子 88 号。地铁 2 号线钟楼站 C 口出，步行 300 米就到。',
            '怎么走': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '怎么过来': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '怎么去': '地铁 2 号线钟楼站 C 口出，步行 300 米就到。也可以导航搜「同盛祥泡馍老店」。',
            '地铁': '地铁 2 号线钟楼站 C 口出，步行 300 米就到了。',
            '导航': '导航搜「同盛祥泡馍老店」，地铁 2 号线钟楼站 C 口出，步行 300 米。',
            # 营业时间
            '营业时间': '每天 10:30 至次日 02:00。深夜 21:00 后进店送热汤。',
            '几点': '每天 10:30 至次日 02:00。深夜 21:00 后进店送热汤。',
            '几点开门': '每天 10:30 开门，至次日 02:00。',
            '几点关门': '每天营业到次日 02:00，深夜 21:00 后进店送热汤。',
            '关门': '每天营业到次日 02:00，深夜 21:00 后进店送热汤。',
            '打烊': '每天营业到次日 02:00。',
            # 电话
            '电话': '电话是 029-8888 6666。',
            '号码': '电话是 029-8888 6666。',
            '联系': '电话是 029-8888 6666。',
            '联系方式': '电话是 029-8888 6666。',
            # 历史/品牌
            '什么时候开': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '哪年': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '创立': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '开业': '同盛祥创立于 1994 年，到今年整整 30 年了。',
            '几年了': '同盛祥创立于 1994 年，经营 30 年，是西安老字号。',
            '老汤': '每天凌晨四点开始吊汤，用牛骨、羊肉和二十余味香料熬制，三十年从没断过火。',
            '三十年': '1994 年开店，老汤三十年没断过火。每天凌晨四点开始吊汤，牛骨+羊肉+二十余味香料。',
            '翻新': '2025 年门店翻新，保留老汤锅和木梁，加入暖黄灯光、原木长桌和动漫插画墙。',
            '装修': '2025 年门店翻新，保留老汤锅和木梁，加入暖黄灯光、原木长桌和动漫插画墙。',
            # 深夜食堂
            '深夜食堂': '晚上 21:00 后进店送热汤，营业到次日 02:00。',
            '宵夜': '每天营业到次日 02:00，晚上 21:00 后进店送热汤。',
            '夜宵': '每天营业到次日 02:00，晚上 21:00 后进店送热汤。',
            # 吃法（高频）
            '怎么吃': '馍掰成黄豆大小，越小越入味，配糖蒜和辣子酱，最后来口汤。',
            '正宗': '馍掰成黄豆大小，配糖蒜和辣子酱，用老汤煮，最后来口汤。',
            '吃法': '先掰馍（黄豆大小），下锅煮，配糖蒜、辣子酱，最后喝汤。',
            '配什么': '标配是糖蒜和辣子酱，再来瓶冰峰或酸梅汤，解腻又够味。',
            # 解腻/搭配
            '解腻': '凉皮或糖蒜都很解腻，再喝口酸梅汤，比冰峰更清爽。',
            '搭配': '凉皮或糖蒜都很解腻，再喝口酸梅汤，比冰峰更清爽。',
            '推荐': '第一次来推荐招牌牛肉泡馍(小份) + 凉拌牛腱 + 冰峰汽水，人均 40 上下。',
            # 健康
            '孕妇': '孕期饮食建议以医嘱为准，来店里可以告诉店员您的忌口，我们帮您调整汤的油盐量。',
            '糖尿病': '健康问题请以医嘱为准，来店里可以告诉店员您的忌口，我们帮您调整汤的油盐量。',
        }
        for kw, answer in STORE_FAQ.items():
            if kw in message:
                session_service.add(uid, 'assistant', answer)
                yield ('text', answer)
                yield ('done', None)
                return

        # ============ 健康关键词拦截 ============
        health_keywords = [
            '糖尿病', '高血压', '高血脂', '血糖', '血压', '胆固醇',
            '孕妇', '怀孕', '哺乳', '过敏', '忌口', '痛风', '肾病',
            '胃病', '胃炎', '胃溃疡', '心脏病', '冠心病', '中风',
            '能不能吃', '可以吃吗', '适合吃', '能吃吗',
        ]
        if any(kw in message for kw in health_keywords):
            reply = (
                '这个建议您以医生或营养师的建议为准。'
                '如果您来店里，可以告诉店员您的忌口，'
                '我们帮您调整汤的油盐量和配菜。'
            )
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 会话聚合查询 ============
        if intent == 'query_total':
            # 先判断消息里是否提到具体菜品 → 走菜品价格合计
            from services.menu_service import menu_service
            mentioned = []
            for dish in menu_service.get_flat():
                if dish['name'] in message:
                    mentioned.append(dish)
                else:
                    simple = dish['name'].split('(')[0].split('（')[0].strip()
                    if len(simple) >= 2 and simple in message:
                        mentioned.append(dish)
            seen = set()
            uniq = []
            for d in mentioned:
                if d['name'] not in seen:
                    seen.add(d['name'])
                    uniq.append(d)

            if uniq:
                lines = []
                sum_price = 0
                for d in uniq:
                    lines.append(f"  · {d['name']}：{d['price']} 元")
                    sum_price += float(d['price'])
                reply = '您问的这几样：\n' + '\n'.join(lines) + \
                        f'\n合计 {sum_price:.2f} 元。'
            else:
                orders = session_service.get_orders(uid)
                if orders:
                    total_sum = sum(o['total'] for o in orders)
                    lines = ['您这次一共下了 ' + str(len(orders)) + ' 单，合计 '
                             + f'{total_sum:.2f}' + ' 元：']
                    for i, o in enumerate(orders, 1):
                        items_str = '、'.join(
                            f"{it['name']}×{it['qty']}"
                            for it in o.get('items', []))
                        lines.append(f'  {i}. {items_str} = {o["total"]:.2f} 元')
                    reply = '\n'.join(lines)
                else:
                    reply = '您这次会话还没下单哦～想吃点什么？'
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 会话聚合查询 ============
        if intent == 'query_total':
            orders = session_service.get_orders(uid)
            if orders:
                total_sum = sum(o['total'] for o in orders)
                lines = ['您这次一共下了 ' + str(len(orders)) + ' 单，合计 '
                         + f'{total_sum:.2f}' + ' 元：']
                for i, o in enumerate(orders, 1):
                    items_str = '、'.join(
                        f"{it['name']}×{it['qty']}"
                        for it in o.get('items', []))
                    lines.append(f'  {i}. {items_str} = {o["total"]:.2f} 元')
                reply = '\n'.join(lines)
            else:
                reply = '您这次会话还没下单哦～想吃点什么？'
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return


        # ============ 批量取消 ============
        if intent == 'cancel_all':
            reply = self._handle_cancel_all(uid)
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 取消订单 ============
        if intent == 'cancel_order':
            reply = self._handle_cancel_order(uid, message)
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 推荐 ============
        if intent == 'recommend':
            reply = self._handle_recommend(message, uid)
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 修改订单 ============
        if intent == 'modify_order':
            reply = self._handle_modify_order(uid, message)
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ 点菜（必须登录）============
        if intent == 'place_order':
            if not uid:
                reply = '下单前请先登录哦～ 点底部「我的」→「立即登录」，登录后每 1 元累积 1 积分。'
                session_service.add(uid, 'assistant', reply)
                yield ('meta', {'intent': intent, 'need_login': True})
                yield ('text', reply)
                yield ('done', None)
                return

            # 模糊菜名检测
            vague = self._is_vague_dish(message)
            if vague and len(vague) > 1:
                opts = '、'.join('「' + v + '」' for v in vague[:4])
                reply = f'您想点的是哪一种？我们这儿有 {opts}，请说得具体些～'
                session_service.add(uid, 'assistant', reply)
                yield ('text', reply)
                yield ('done', None)
                return

            items = self._extract_items_from_text(message)

            # 数量校验
            for it in items:
                err = self._validate_qty(it.get('qty', 1))
                if err:
                    session_service.add(uid, 'assistant', err)
                    yield ('text', err)
                    yield ('done', None)
                    return

            if not items and self._is_order_intent_weak(message):
                # 从消息里提取份量偏好
                prefer = None
                if '大份' in message:
                    prefer = '大份'
                elif '小份' in message:
                    prefer = '小份'
                last_dish = self._find_last_dish_in_history(uid, prefer_size=prefer)
                if last_dish:
                    qty = self._extract_qty_from_message(message)
                    items = [{'name': last_dish, 'qty': qty}]

            if items:
                try:
                    order_result = order_service.create(items, table_no=table_no, uid=uid)
                    reply = order_service.format_reply(order_result)
                    session_service.add(uid, 'assistant', reply)
                    session_service.add_order(uid, order_result['order'])
                    yield ('meta', {'intent': intent, 'order': order_result['order']})
                    yield ('text', reply)
                    yield ('done', None)
                    return
                except Exception as e:
                    logger.warning(f"下单失败: {e}")
                    session_service.add(uid, 'assistant', str(e))
                    yield ('text', f"下单失败：{e}")
                    yield ('done', None)
                    return
            else:
                reply = '请问您想点什么？比如「牛肉泡馍」「羊肉泡馍」「冰峰汽水」。'
                session_service.add(uid, 'assistant', reply)
                yield ('text', reply)
                yield ('done', None)
                return

        # ============ 闲聊 ============
        if intent == 'chat':
            # 判断是不是"好的/嗯/行"等确认词
            if message.strip() in ('好的', '好呀', '好嘞', '行吧', '可以', '嗯', 'OK', 'ok'):
                reply = '好嘞！需要我帮您下单吗？可以告诉我菜品名字和份数，比如「来一份牛肉泡馍」。'
            else:
                reply = '你好！我是同盛祥的小助手，可以问我菜单、营业时间、门店地址，也可以直接点菜。'
            session_service.add(uid, 'assistant', reply)
            yield ('text', reply)
            yield ('done', None)
            return

        # ============ RAG（通用问题） ============
        from services.rag_service import chat_with_rag_stream
        full_reply = ''
        for chunk in chat_with_rag_stream(message):
            full_reply += chunk
            yield ('text', chunk)

        cleaned = self._clean(full_reply)
        session_service.add(uid, 'assistant', cleaned)
        yield ('done', None)

    def _log_chat(self, uid, question, answer, intent='other', elapsed_ms=0):
        """写一条 AI 对话日志（失败不影响主流程）"""
        try:
            from repositories.instances import chat_log_repo
            chat_log_repo.create({
                'uid': uid,
                'question': question[:200],
                'answer': answer[:500],
                'intent': intent,
                'elapsed_ms': round(elapsed_ms, 1),
                'is_hit': 1,
                'created_at': _time.strftime('%Y-%m-%d %H:%M:%S'),
            })
        except Exception:
            pass
chat_service = ChatService()