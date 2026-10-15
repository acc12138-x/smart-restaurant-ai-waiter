# services/table_service.py
"""桌号识别与校验

顾客懒得扫码时会在对话里直接说桌号（"点一份羊肉泡馍送到 1 号桌"）。
这里负责两件事：

1. **从自然语言里把桌号抠出来** —— 支持 `1号桌` / `三号桌` / `A1桌` / `桌号2` / 全角 `１号桌`
2. **拿后台「桌码管理」里配过的桌号校验** —— 顾客说了店里没有的桌，必须当场告诉他，
   而不是把菜送到一张不存在的桌子上

注意：后台的桌号是自由文本（`01`、`A1`、`大厅3` 都合法），所以校验必须做归一化比较，
否则顾客说"1 号桌"会对不上后台配的"01"。
"""
import re

from utils.logger import logger

# 中文数字
_CN = {'一': 1, '两': 2, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
       '七': 7, '八': 8, '九': 9, '十': 10}
_FULLWIDTH = str.maketrans('０１２３４５６７８９', '0123456789')

# 「1号桌」「三号桌」「A1桌」「12号台」
_P_NUM_TABLE = re.compile(
    r'([A-Za-z]?\s*[0-9]{1,3}|[一二两三四五六七八九十]{1,3})\s*号?\s*(?:桌|台)')
# 「桌号1」「桌2」「台号 A1」
_P_TABLE_NUM = re.compile(
    r'(?:桌|台)\s*号?\s*[:：]?\s*([A-Za-z]?\s*[0-9]{1,3}|[一二两三四五六七八九十]{1,3})')

# 明确的送餐/就座措辞：出现这些时，"店里没有这张桌"要当场提醒
_DELIVER = ('送', '端', '上到', '拿到', '放到', '我在', '我是', '坐', '订', '预约', '桌号')

# 缓存后台桌号，避免每轮对话都查库
_CACHE_TTL = 10.0


def _cn_to_int(s):
    """'三' → 3，'十' → 10，'十二' → 12，'二十三' → 23"""
    if not s:
        return None
    if s in _CN:
        return _CN[s]
    if '十' in s:
        parts = s.split('十')
        tens = _CN.get(parts[0], 1) if parts[0] else 1
        ones = _CN.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return None


class TableService:
    """桌号提取 + 校验"""

    def __init__(self, repo=None):
        self._repo = repo
        self._cache = None
        self._cache_at = 0.0

    # ---------- 后台配置的桌号 ----------

    def _get_repo(self):
        if self._repo is None:
            try:
                from repositories.instances import table_repo
                self._repo = table_repo
            except Exception as e:
                logger.warning('[Table] 无法获取 repo: ' + str(e))
                self._repo = False
        return self._repo or None

    def list_tables(self):
        """后台配过的桌号列表（10 秒缓存）"""
        import time
        now = time.time()
        if self._cache is not None and now - self._cache_at < _CACHE_TTL:
            return list(self._cache)
        repo = self._get_repo()
        if not repo:
            return []
        try:
            rows = repo.get_all() or []
            self._cache = [str(r.get('table_no') or '').strip()
                           for r in rows if (r.get('table_no') or '').strip()]
        except Exception as e:
            logger.warning('[Table] 读取桌号失败: ' + str(e))
            return []
        self._cache_at = now
        return list(self._cache)

    def clear_cache(self):
        self._cache = None
        self._cache_at = 0.0

    def normalize(self, raw):
        """归一化：全角转半角、去空格、大写字母、去前导零

        '１号' → '1'；'a1' → 'A1'；'01' → '1'；'三' → '3'
        """
        s = (raw or '').strip().translate(_FULLWIDTH).replace(' ', '')
        if not s:
            return ''
        m = re.fullmatch(r'([A-Za-z]?)(\d{1,3})', s)
        if m:
            return m.group(1).upper() + str(int(m.group(2)))
        n = _cn_to_int(s)
        if n:
            return str(n)
        return s.upper()

    def match(self, raw):
        """返回后台里对应的那条桌号（**保留后台的写法**，便于后台按桌统计）

        '1' 能匹配到后台配的 '01'；没配过返回 None
        """
        if not raw:
            return None
        want = self.normalize(raw)
        for t in self.list_tables():
            if t == raw or self.normalize(t) == want:
                return t
        return None

    def exists(self, table_no):
        """这张桌在后台配过吗（归一化比较，'1' 能对上 '01'）"""
        return self.match(table_no) is not None

    def has_config(self):
        """后台是否配置过桌号 —— 没配过就没法校验，这时不该拦顾客"""
        return bool(self.list_tables())

    def available_hint(self, limit=8):
        """给顾客看的可用桌号提示

        只列"干净"的桌号（1/A1 这种）。后台可能混着 Te27a 这类自动生成的测试值，
        把那些报给顾客只会让人更困惑，这时改为让他看桌上的码。
        """
        clean = []
        for t in self.list_tables():
            n = self.normalize(t)
            if re.fullmatch(r'[A-Za-z]?\d{1,3}', n):
                clean.append(t)
        if not clean:
            return ''
        clean = sorted(set(clean), key=lambda x: (len(x), x))[:limit]
        return '、'.join(clean)

    # ---------- 从话里抠桌号 ----------

    def extract(self, message):
        """返回 (桌号, 是否明确送餐措辞)；没提到桌号时返回 (None, False)"""
        text = (message or '').translate(_FULLWIDTH)
        if not text:
            return None, False
        for pat in (_P_TABLE_NUM, _P_NUM_TABLE):
            m = pat.search(text)
            if m:
                return self.normalize(m.group(1)), self.is_delivery(text)
        return None, False

    @staticmethod
    def is_delivery(text):
        return any(w in (text or '') for w in _DELIVER)


# 单例
table_service = TableService()
