# services/settings_service.py
"""系统设置（key-value，存 SQLite）
v3.7 通用版：
- llm_provider: 'local' | 'remote'
- api_base_url / api_key / api_model：任意 OpenAI 兼容 API
- ollama_model：本地对话模型
- ollama_embed_model：本地嵌入模型（RAG 用）
"""
import time
import threading
from repositories.sqlite_repo import get_conn
from utils.logger import logger


DEFAULTS = {
    # LLM
    'llm_provider':       'local',
    'llm_enabled':        'true',
    'api_base_url':       'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'api_key':            '',
    'api_model':          'qwen3.7-plus',
    'ollama_model':       'modelscope.cn/Qwen/Qwen3-4B-GGUF:latest',
    'ollama_embed_model': 'bge-m3',

    # 门店
    'shop_name':    '同盛祥西安泡馍老店',
    'shop_address': '西安市碑林区老巷子 88 号',
    'shop_phone':   '029-8888 6666',
    'shop_hours':   '10:30 至次日 02:00',
    'shop_notice':  '深夜 21:00 后进店送热汤',

    # 积分
    'points_rate':         '1',
    'points_signup_bonus': '10',

    # 开关
    'emoji_enabled':     'true',
    'recommend_enabled': 'true',

    # 通知
    'notification_enabled': 'false',
    'wecom_webhook':        '',

    # v3.9 首页 Hero
    'hero_items':       '[]',
    'hero_labels':      '[]',
    'hero_autoplay_ms': '8000',
}

SENSITIVE_KEYS = {'api_key', 'wecom_webhook'}


def _mask(value):
    if not value:
        return ''
    if len(value) <= 8:
        return '*' * len(value)
    return value[:4] + '*' * (len(value) - 8) + value[-4:]


class SettingsService:
    def __init__(self):
        self._cache = {}
        self._cache_loaded = False
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self):
        try:
            conn = get_conn()
            try:
                conn.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
                conn.commit()
                logger.info('[Settings] 表检查完成')
            finally:
                conn.close()
        except Exception as e:
            logger.warning('[Settings] 建表失败: ' + str(e))

    def _load_all(self):
        try:
            conn = get_conn()
            try:
                cur = conn.execute('SELECT key, value FROM settings')
                self._cache = {r['key']: (r['value'] or '') for r in cur.fetchall()}
                self._cache_loaded = True
            finally:
                conn.close()
        except Exception as e:
            logger.warning('[Settings] 加载失败: ' + str(e))
            self._cache = {}

    def get(self, key, default=None):
        if not self._cache_loaded:
            with self._lock:
                if not self._cache_loaded:
                    self._load_all()
        if key in self._cache and self._cache[key] != '':
            return self._cache[key]
        if default is not None:
            return default
        return DEFAULTS.get(key, '')

    def get_int(self, key, default=0):
        try:
            return int(self.get(key))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key, default=False):
        v = self.get(key)
        if isinstance(v, bool):
            return v
        return str(v).lower() in ('true', '1', 'yes', 'on')

    def get_all(self, mask_sensitive=True):
        result = dict(DEFAULTS)
        for k, v in self._cache.items():
            result[k] = v
        if mask_sensitive:
            for k in SENSITIVE_KEYS:
                if result.get(k):
                    result[k + '_masked'] = _mask(result[k])
                    result[k] = ''
        return result

    def set(self, key, value):
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        conn = get_conn()
        try:
            conn.execute('INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at', (key, str(value), now))
            conn.commit()
        finally:
            conn.close()
        self._cache[key] = str(value)
        return True

    def set_many(self, data):
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        conn = get_conn()
        try:
            for k, v in data.items():
                conn.execute('INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at', (k, str(v), now))
                self._cache[k] = str(v)
            conn.commit()
        finally:
            conn.close()
        return len(data)

    def invalidate_cache(self):
        with self._lock:
            self._cache_loaded = False
            self._cache = {}


settings_service = SettingsService()
