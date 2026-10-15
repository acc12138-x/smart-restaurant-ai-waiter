import re
# services/intent_service.py
"""意图识别：规则匹配（0ms，不用模型）

Qwen3 加载要 12 秒，且和 bge-m3 抢显存。
菜单/营业/地址/点菜这几类用规则完全够用，不用大模型。

设计原则（踩坑之后总结）：
1. 关键词要"窄"——裸的「可以」「来点」「有什么」「给我」会把别的意图吞掉，
   例如"可以用支付宝吗"被判成闲聊、"来点凉皮"被判成要推荐。
2. 含完整菜名时先按菜名细分（问价 / 问口味 / 有无 / 下单），比通用关键词准。
3. 催单和"过去时叙述"要单独识别——前者不该交给模型编等待时间，
   后者（"我刚刚点了一份泡馍"）绝不能当成新下单。
"""

INTENTS = ['query_menu', 'query_location', 'query_hours', 'place_order',
           'query_order_status', 'repeat_last_order', 'chat', 'other']




# 中文数字 → 阿拉伯数字
_CN_NUM = {'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'百':100}

# 确认词：含义取决于上一轮 AI 说了什么（推荐了具体菜 → 接受推荐；否则算闲聊）
CONFIRM_WORDS = ('可以', '可以了', '可以的', '可以啊', '可以呀', '行', '行吧',
                 '好', '好的', '好呀', '好嘞', '嗯', '嗯嗯', 'OK', 'ok', '要')

# 容错比对前先剥掉的数量词/动作词/语气词
_STRIP_FOR_DISH = re.compile(
    r'(我要|我想|给我|来|点|要|买|加|拿|上|份|碗|杯|瓶|盘|个|一|两|二|三|四|五|六|七|八|九|十'
    r'|\d|的|了|吧|呢|吗|啊|呀|哦|嘛)')


def _last_assistant_recommended(history):
    """历史里助手的最后一条是否推荐了具体菜品

    format_history() 的格式是「用户：…\\n助手：…」，取最后一条助手发言来判断。
    """
    if not history:
        return False
    try:
        from services.menu_service import menu_service
        names = []
        for d in menu_service.get_flat():
            names.append(d['name'])
            simple = d['name'].split('(')[0].split('（')[0].strip()
            if len(simple) >= 2:
                names.append(simple)
        lines = [l.strip() for l in str(history).splitlines() if l.strip()]
        for line in reversed(lines):
            if line.startswith(('助手', 'AI', '小同', '店长')):
                return any(n in line for n in names)
        return any(n in str(history) for n in names)
    except Exception:
        return False


def _fuzzy_dish(text, threshold=0.7):
    """错别字容错："羊肉跑馍" → "羊肉泡馍"、"冰锋汽水" → "冰峰汽水"

    大模型本身能做到，但规则层是降级路径，不能因为它退化成"看不懂"。
    长度差超过 2 的直接跳过，避免"你们家羊从哪来"这类问句被误配成菜名。
    """
    try:
        from difflib import SequenceMatcher
        from services.menu_service import menu_service
        t = _STRIP_FOR_DISH.sub('', text or '').strip()
        if len(t) < 2:
            return None
        best, best_score = None, 0.0
        for dish in menu_service.get_flat():
            simple = dish['name'].split('(')[0].split('（')[0].strip()
            for cand in {dish['name'], simple}:
                if len(cand) < 2 or abs(len(cand) - len(t)) > 2:
                    continue
                score = SequenceMatcher(None, t, cand).ratio()
                if score > best_score:
                    best, best_score = dish['name'], score
        return best if best_score >= threshold else None
    except Exception:
        return None


def _parse_cn_number(s):
    """解析 '一/两/十/二十/十五/100' 等"""
    s = (s or '').strip()
    if not s:
        return 1
    if s.isdigit():
        return int(s)
    if s == '十':
        return 10
    if s == '百':
        return 100
    if len(s) == 2 and s[1] == '十':
        return _CN_NUM.get(s[0], 1) * 10
    if len(s) == 2 and s[0] == '十':
        return 10 + _CN_NUM.get(s[1], 0)
    if len(s) == 3 and s[1] == '十':
        return _CN_NUM.get(s[0], 0) * 10 + _CN_NUM.get(s[2], 0)
    return _CN_NUM.get(s, 1)

def classify_intent(text: str, history: str = '') -> dict:
    """规则匹配意图，0ms 返回"""
    t = (text or '').strip()

    # 空 / 纯标点 / 纯 emoji → other
    if not t:
        return {'intent': 'other', 'items': []}
    import re as _re
    # 去掉所有标点和空白后为空
    if _re.sub(r'[\s\W_]+', '', t, flags=_re.UNICODE) == '':
        return {'intent': 'other', 'items': []}
    # 全是 emoji（>=1个，且没有文字）→ other
    if _re.fullmatch(r'[\U0001F300-\U0001FAFF\U00002600-\U000027BF\s]+', t):
        return {'intent': 'other', 'items': []}

    # ============ 否定句优先判断（最高优先级）============
    # 用户明确说"不要/不想/别点/不点" → 不是下单
    neg_kw = ['不要', '不想', '别点', '不点', '不吃', '不喝', '别要',
              '别再', '不买', '取消掉', '不要了']
    # 排除"不要取消"（其实是取消意图）
    if not any(w in t for w in ('取消', '退单', '退掉')):
        if any(k in t for k in neg_kw):
            # 判断是否含菜名（含菜名 → 取消意图；不含 → 闲聊/拒绝）
            has_dish = any(d in t for d in [
                '泡馍', '羊肉', '牛肉', '冰峰', '糖蒜', '凉皮', '臊子',
                '酥糕', '胡辣汤', 'biang', '面', '汽水', '套餐'
            ])
            if has_dish:
                return {'intent': 'cancel_order', 'items': []}
            return {'intent': 'chat', 'items': []}

    # ============ 疑问句（含菜名但是问好不好）============
    # "牛肉泡馍好吃吗" "羊肉泡馍辣不辣"
    if t.endswith(('吗', '呢', '嘛')) or '吗？' in t or '吗?' in t:
        if any(w in t for w in ('好吃', '辣', '咸', '甜', '酸', '淡',
                                '怎么样', '如何', '推荐',
                                '适合', '难吃', '味道')):
            return {'intent': 'query_menu', 'items': []}
        # 门店杂问（"可以开发票吗""能打包吗""支持支付宝吗"）→ other，交给知识库。
        # 既不能当闲聊（chat_kw 里的裸"可以"曾把它们回成"你好！我是金牌店长…"），
        # 也不能被"打包"之类的下单词吞掉。
        if any(w in t for w in ('可以', '能不能', '能', '能否', '支持', '允许')):
            return {'intent': 'other', 'items': []}

    # ============ 剥离招呼词后继续 ============
    GREET_PREFIX = ['你好', '您好', '嗨', '哈喽', 'hi', 'Hi', 'HI',
                    'hello', 'Hello', '在吗', '老板', '师傅', '嘿']
    for g in sorted(GREET_PREFIX, key=len, reverse=True):
        if t.startswith(g) and len(t) > len(g):
            t = t[len(g):].strip()
            break
    if not t:
        return {'intent': 'chat', 'items': []}

    # ============ 确认词（上下文相关，必须早于其它关键词）============
    # "可以""好的""行"到底是闲聊还是接受推荐，取决于上一轮 AI 说了什么：
    # 上一条推荐了具体菜 → 接受推荐（下单）；否则才算闲聊。
    # 实测踩过：AI 推荐"优质羊肉泡馍" → 用户回"可以" → 被当成闲聊，回了
    # "好嘞！那要吃点啥？"，把已经答应的单子丢了。
    if t in CONFIRM_WORDS:
        if _last_assistant_recommended(history):
            return {'intent': 'accept_recommend', 'items': []}
        return {'intent': 'chat', 'items': []}

    # 精确单字/短语：只说"取消"/"退"也算
    if t in ('取消', '退', '撤', '退掉', '不要', '不要了'):
        return {'intent': 'cancel_order', 'items': []}

    # 修改订单（"改成"/"换成"）—— 放在取消之前，因为"改"字优先
    modify_kw = ['改成', '换成', '替换成', '改为', '换为']
    if any(k in t for k in modify_kw):
        return {'intent': 'modify_order', 'items': []}

    # 全部取消（必须放在 cancel_order 之前，因为"全部退掉"里含"退掉"）
    cancel_all_kw = ['全部退', '全都退', '全部都退', '全部取消', '全都取消',
                     '全部都取消', '都取消', '都退掉', '都退了',
                     '全退', '一键取消', '一起取消', '这些全取消',
                     '所有的都取消', '全部退单']
    if any(k in t for k in cancel_all_kw):
        return {'intent': 'cancel_all', 'items': []}

    # 极短"来一个/来两个/再来一个" → 弱下单（从历史找菜）
    if re.match(r'^\s*再?[来要]\s*[一两个三四五]\s*[个份份]?\s*$', t):
        return {'intent': 'place_order', 'items': []}

    # 极短"要X"句式：要 / 要大份 / 要小份 / 要一份 / 要个 等
    # 排除问价格类（要多少、要啥、要什么）
    if len(t) <= 3 and t.startswith('要'):
        if not any(w in t for w in ('多少', '什么', '啥', '价格',
                                     '几块', '几元', '钱', '哪个', '哪个')):
            return {'intent': 'place_order', 'items': []}

    # ============ 老规矩 / 照旧（重复上一单）============
    # "老规矩送到一号桌"这类说法很常见：菜不用重说，照上次的来，桌号另说。
    # 必须在"含菜名细分"和未知菜名闸之前认出来，否则会被当成菜名。
    repeat_kw = ['老规矩', '照旧', '照老样子', '老样子', '老一套', '还那样', '还是那样',
                 '和上次一样', '跟上次一样', '和之前一样', '跟之前一样', '按上次的',
                 '上次那个', '上次的那', '再来一份上次', '一如既往']
    if any(k in t for k in repeat_kw):
        return {'intent': 'repeat_last_order', 'items': []}

    # ============ 催单 / 查订单进度 ============
    # 真实门店最高频的问题之一。以前没有这个意图，"我的菜好了吗""还要等多久"
    # 会落到 other 交给模型自由发挥，于是编出等待时间；现在按订单真实状态回答。
    status_kw = ['好了吗', '好没好', '好了没', '做好了', '做好没', '上菜', '上桌',
                 '到哪了', '到哪儿了', '什么时候好', '还要多久', '等多久', '多久能',
                 '几分钟', '催', '快点', '怎么还没', '还没好', '进度', '订单状态',
                 '我的单', '我的订单', '我的菜', '几点能', '能吃上', '什么时候能好']
    # 过去时叙述（"我刚刚点了一份泡馍"）绝不能当成新下单 —— 那会重复下单
    past_kw = ['刚刚', '刚才', '已经', '之前', '前面', '早就', '上次']
    if not any(w in t for w in ('取消', '退单', '退掉', '不想要')):
        if any(k in t for k in status_kw):
            return {'intent': 'query_order_status', 'items': []}
        if any(w in t for w in past_kw) and any(
                v in t for v in ('点', '要', '下单', '下过', '买', '订', '叫')):
            return {'intent': 'query_order_status', 'items': []}

    # 取消订单（必须放在点菜之前，因为"取消订单XX菜"里会含菜名）
    cancel_kw = ['取消订单', '订单取消', '取消刚刚', '取消刚才',
                 '刚刚订单', '刚才订单', '刚下的单', '刚下的订单',
                 '取消这单', '取消这一单', '退单',
                 '不要了', '不想要了', '别做了', '不买了',
                 '取消掉', '撤销订单', '撤单', '退掉']
    if any(k in t for k in cancel_kw):
        return {'intent': 'cancel_order', 'items': []}

    # "取消X菜" / "取消X的订单" / "退X" 等灵活句式
    if len(t) <= 20:
        if ('取消' in t or '退' in t or '撤' in t):
            # 排除否定/疑问：“不取消”“别取消”“为什么要取消”
            if not any(w in t for w in ('不取消', '别取消', '不要取消',
                                         '为什么', '为啥', '怎么取消',
                                         '能不能取消', '可以取消吗',
                                         '能取消吗', '怎么退')):
                return {'intent': 'cancel_order', 'items': []}

    # ============ 留言 ============
    # 必须放在"点菜关键词"和"含菜名细分"之前：
    # 否则"我要留言"会被 order_kw 的"我要"吞成下单，
    # "我要投诉凉皮里有头发"会被含菜名规则吞成再点一份凉皮。
    msg_kw = ['留言', '留个言', '留句话', '给老店留', '给老板留', '给店长留',
              '反馈', '建议', '投诉', '意见']
    if any(k in t for k in msg_kw):
        return {'intent': 'leave_message', 'items': []}

    # ============ 含完整菜名时先按菜名细分 ============
    # 例："来点凉皮" 过去被 recommend_kw 的"来点"吞掉；"给我推荐个凉皮"被"给我"吞掉。
    # 含菜名时意图其实很明确：问价 → query_menu，问口味/有无 → query_menu，下单 → place_order。
    try:
        from services.menu_service import menu_service
        _PRICE_Q = ('多少', '几块', '几元', '价格', '什么价', '贵不贵', '怎么卖', '多钱')
        _INQUIRY = ('有吗', '有没有', '有卖', '有木有', '看看', '查一下', '了解一下',
                    '介绍', '是什么', '菜单', '在哪', '位置', '有')
        _TASTE_Q = ('好吃', '辣', '咸', '甜', '酸', '淡', '怎么样', '如何',
                    '难吃', '味道', '适合', '能不能吃', '能吃不', '腥', '膻')
        _ORDER_V = ('来', '要', '点', '加', '拿', '上', '买', '给我', '打包', '再来')

        hit_dishes = []
        for dish in menu_service.get_flat():
            nm = dish['name']
            simple = nm.split('(')[0].split('（')[0].strip()
            if nm in t or (len(simple) >= 2 and simple in t):
                hit_dishes.append(nm)

        fuzzy_hit = False
        if not hit_dishes:
            # 错别字容错："来碗羊肉跑馍" → 羊肉泡馍（大模型强项，规则层降级时也不能丢）
            guess = _fuzzy_dish(t)
            if guess:
                hit_dishes = [guess]
                fuzzy_hit = True

        if hit_dishes:
            if any(w in t for w in _PRICE_Q):
                return {'intent': 'query_menu', 'items': []}
            if any(w in t for w in _INQUIRY):
                return {'intent': 'query_menu', 'items': []}
            if any(w in t for w in _TASTE_Q):
                return {'intent': 'query_menu', 'items': []}
            # 模糊命中的说明用户是把菜名写错了，按裸菜名处理 → 直接下单；
            # 否则"羊肉跑馍"会因为没写"来/要"而落到 other
            if fuzzy_hit or any(w in t for w in _ORDER_V):
                return {'intent': 'place_order', 'items': []}
    except Exception:
        pass

    # ============ 消息本身就是完整菜名 → 直接下单 ============
    # 例："优质羊肉泡馍" "冰峰汽水" "糖蒜(整头)"
    try:
        from services.menu_service import menu_service
        msg_clean = t.strip()
        # 去掉末尾语气词
        msg_clean = re.sub(r'[吗呢吧啊呀哦嘛]$', '', msg_clean).strip()
        if len(msg_clean) >= 2:
            for dish in menu_service.get_flat():
                # 完全相等 → place_order
                if msg_clean == dish['name']:
                    return {'intent': 'place_order', 'items': []}
                # 简名完全匹配（去括号后）
                simple = dish['name'].split('(')[0].split('（')[0].strip()
                if simple == msg_clean:
                    return {'intent': 'place_order', 'items': []}
    except Exception:
        pass

    # ============ 点菜优先级最高 ============
    # 1) 通用句式：来/点/要/买 + 数量 + 量词（任意数字）
    #    例："来十份羊肉泡馍" "点2个冰峰" "要两碗泡馍"
    if re.search(r'[来点要买给我吃]\s*[一两二三四五六七八九十百千\d]+\s*[份个碗杯瓶盘]', t):
        return {'intent': 'place_order', 'items': []}
    # 2) 以数量+量词开头的句式
    #    例："十份羊肉泡馍" "2份泡馍" "两份" "10个糖蒜"
    if re.match(r'^\s*[一两二三四五六七八九十百千\d]+\s*[份个碗杯瓶盘]', t):
        return {'intent': 'place_order', 'items': []}
    # 3) "我要吃/我要喝 + 数量 + 量词"
    #    例："我要吃十碗"
    if re.search(r'(吃|喝)\s*[一两二三四五六七八九十百千\d]+\s*[碗份个杯]', t):
        return {'intent': 'place_order', 'items': []}

    # 4) 传统关键词（兜底）
    #    注意：这里刻意不放裸的"给我"——"给我推荐个菜"会被它吞成下单
    order_kw = ['我要', '还要', '还要个', '再来', '再要',
                '来一', '来两', '来三', '来份', '来个', '来份',
                '点一', '点两', '点三', '点份', '点个',
                '要一', '要两', '要三', '要份', '要个',
                '打包', '下单',
                '再点', '再加',
                '添加', '加上']
    if any(k in t for k in order_kw):
        return {'intent': 'place_order', 'items': []}

    # 会话聚合（"一共多少钱"优先于菜单查询）
    total_kw = ['一共多少', '总共多少', '合计多少', '总计多少',
                '一共', '总共', '合计', '总计', '多少了']
    if any(k in t for k in total_kw) and ('钱' in t or '元' in t or '多少' in t):
        return {'intent': 'query_total', 'items': []}

    # （留言判断已提前到"含菜名细分"之前，避免被点菜关键词吞掉）

    # ============ 接受/拒绝推荐（v3.9，放推荐之前）============
    accept_kw = ['就这个', '就要这个', '就要它', '就它', '就那个',
                 '就要那个', '这个吧', '那个吧',
                 '就要你推荐', '就要你推荐的', '就你推荐', '就你推荐的',
                 '你推荐的这个', '推荐的这个',
                 '就按你说的', '按你说的来', '就按你推荐',
                 '来这个', '要这个', '点这个', '这个可以']
    if any(k in t for k in accept_kw):
        return {'intent': 'accept_recommend', 'items': []}

    reject_kw = ['不要这个', '不想要这个', '换一个', '换个', '换别的',
                 '来点别的', '推荐别的', '再推荐', '重新推荐',
                 '不喜欢这个', '这个不好']
    if any(k in t for k in reject_kw):
        return {'intent': 'reject_recommend', 'items': []}

    # 推荐（放菜单之前，因为"推荐"要单独识别）
    # 注意：不放裸的"有什么""来点"——"有什么支付方式""来点凉皮"会被吞掉；
    # 只保留指向"推荐"的完整说法，其余交给 other → 知识库兜底。
    recommend_kw = ['推荐', '随便', '都行', '无所谓', '吃啥', '有啥吃',
                    '有什么推荐', '有什么好吃', '有什么菜', '有什么特色',
                    '有什么招牌', '有什么主食', '有什么小吃',
                    '来点什么', '来点啥', '来点吃的', '来点主食',
                    '看着办', '你选', '你帮我', '你决定', '帮我选', '帮我点',
                    '什么好吃', '招牌', '招牌菜', '招牌是啥', '特色', '特色菜',
                    '特色是啥', '拿手菜', '经典菜', '必点']
    if any(k in t for k in recommend_kw):
        return {'intent': 'recommend', 'items': []}
    # 极简的"有什么 / 有啥 / 有吗"（整句）也算要推荐
    if t in ('有什么', '有啥', '有什么呢', '有啥呢', '有吗', '有什么吃的'):
        return {'intent': 'recommend', 'items': []}

    # 菜单/价格
    # 注意：不放"有吗""有没有""好吃"——"有停车位"会被吞成菜单查询，
    # 进而被未知菜名闸拦成"菜单里没有「有停车位」"。
    menu_kw = ['多少钱', '价格', '几块', '多少元', '什么价', '怎么卖',
               '贵不贵', '菜单', '菜价']
    if any(k in t for k in menu_kw):
        return {'intent': 'query_menu', 'items': []}

    # 地址
    addr_kw = ['在哪', '地址', '怎么走', '位置', '地铁', '怎么去', '导航']
    if any(k in t for k in addr_kw):
        return {'intent': 'query_location', 'items': []}

    # 营业时间/电话
    hours_kw = ['几点', '电话', '营业', '关门', '开门', '打烊', '号码', '联系']
    if any(k in t for k in hours_kw):
        return {'intent': 'query_hours', 'items': []}

    # 闲聊 / 确认
    # 注意：不放裸的"可以"——"可以用支付宝吗""可以开发票吗"会被吞成闲聊
    if t in ('可以', '可以了', '可以的', '可以啊', '行', '好', '嗯嗯'):
        return {'intent': 'chat', 'items': []}
    chat_kw = ['你好', '您好', '嗨', '在吗', '谢谢', '再见', '拜拜',
               '好的', '好呀', '好嘞', '行吧', '嗯', 'OK', 'ok',
               '不用', '没事', '算了', '多谢', '谢了', '麻烦了']
    if any(k in t for k in chat_kw):
        return {'intent': 'chat', 'items': []}

    return {'intent': 'other', 'items': []}
