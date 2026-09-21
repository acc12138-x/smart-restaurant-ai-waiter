import re
# services/intent_service.py
"""意图识别：规则匹配（0ms，不用模型）

Qwen3 加载要 12 秒，且和 bge-m3 抢显存。
菜单/营业/地址/点菜这几类用规则完全够用，不用大模型。
"""

INTENTS = ['query_menu', 'query_location', 'query_hours', 'place_order', 'chat', 'other']




# 中文数字 → 阿拉伯数字
_CN_NUM = {'一':1,'两':2,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'百':100}

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
                                '怎么样', '如何', '推荐', '能不能',
                                '可以', '适合', '难吃', '味道')):
            return {'intent': 'query_menu', 'items': []}

    # ============ 剥离招呼词后继续 ============
    GREET_PREFIX = ['你好', '您好', '嗨', '哈喽', 'hi', 'Hi', 'HI',
                    'hello', 'Hello', '在吗', '老板', '师傅', '嘿']
    for g in sorted(GREET_PREFIX, key=len, reverse=True):
        if t.startswith(g) and len(t) > len(g):
            t = t[len(g):].strip()
            break
    if not t:
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

    # 极短"要X"句式：要 / 要大份 / 要小份 / 要一份 / 要个 等
    # 排除问价格类（要多少、要啥、要什么）
    if len(t) <= 3 and t.startswith('要'):
        if not any(w in t for w in ('多少', '什么', '啥', '价格',
                                     '几块', '几元', '钱', '哪个', '哪个')):
            return {'intent': 'place_order', 'items': []}

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
    order_kw = ['我要', '来一', '来两', '来三', '点一', '点两', '点三',
                '要一', '要两', '要三', '给我', '打包', '下单',
                '再要', '再来', '再点', '再加',
                '添加', '加上']
    if any(k in t for k in order_kw):
        return {'intent': 'place_order', 'items': []}

    # 会话聚合（"一共多少钱"优先于菜单查询）
    total_kw = ['一共多少', '总共多少', '合计多少', '总计多少',
                '一共', '总共', '合计', '总计', '多少了']
    if any(k in t for k in total_kw) and ('钱' in t or '元' in t or '多少' in t):
        return {'intent': 'query_total', 'items': []}

    # 菜单/价格
    menu_kw = ['多少钱', '价格', '几块', '多少元', '什么价', '有吗',
               '有没有', '菜单', '推荐', '好吃', '招牌']
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
    chat_kw = ['你好', '您好', '嗨', '在吗', '谢谢', '再见', '拜拜',
               '好的', '好呀', '好嘞', '行吧', '可以', '嗯', 'OK', 'ok',
               '不用', '没事', '算了', '多谢', '谢了', '麻烦了']
    if any(k in t for k in chat_kw):
        return {'intent': 'chat', 'items': []}

    return {'intent': 'other', 'items': []}