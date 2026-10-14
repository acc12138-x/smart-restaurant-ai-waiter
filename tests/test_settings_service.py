# tests/test_settings_service.py
"""settings_service 的缓存行为回归测试

修复过的 bug：get_all() 漏了懒加载，新起的 worker 里第一次调用它会返回
一整份默认值 —— 后台设置页因此把"使用方式"显示成"本地 Ollama"，
并把 API Base URL / API Key / 模型名三行全部隐藏（前端只在这些字段上挂
.remote-only，provider=local 时不显示）。
"""
import sqlite3
import time

import pytest

import repositories.sqlite_repo as sqlite_repo


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """把 settings 表隔离到临时库，避免污染 data/app.db"""
    db = tmp_path / 'test.db'
    monkeypatch.setattr(sqlite_repo, 'DB_PATH', str(db))
    conn = sqlite3.connect(str(db))
    conn.execute('CREATE TABLE IF NOT EXISTS settings '
                 '(key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)')
    conn.commit()
    conn.close()
    return str(db)


def _fresh_worker():
    """模拟一个新启动的 worker 进程里的 SettingsService 实例（缓存为空）"""
    from services.settings_service import SettingsService
    return SettingsService()


def test_get_all_sees_db_values_on_first_call(temp_db):
    """新 worker 第一次就调 get_all()（= 管理员打开设置页）必须看到库里的真值"""
    writer = _fresh_worker()
    writer.set('llm_provider', 'remote')
    writer.set('api_model', 'qwen-plus')

    reader = _fresh_worker()
    cfg = reader.get_all(mask_sensitive=False)

    assert cfg['llm_provider'] == 'remote'      # 修复前是默认值 'local'
    assert cfg['api_model'] == 'qwen-plus'      # 修复前是默认值 'qwen3.7-plus'


def test_get_all_keeps_defaults_for_missing_keys(temp_db):
    cfg = _fresh_worker().get_all(mask_sensitive=False)
    assert cfg['shop_name'] == '同盛祥西安泡馍老店'


def test_get_all_masks_sensitive_keys(temp_db):
    s = _fresh_worker()
    s.set('api_key', 'sk-1234567890abcdef')

    cfg = s.get_all(mask_sensitive=True)
    assert cfg['api_key'] == ''                 # 原始值不下发
    assert cfg['api_key_masked'].startswith('sk-1')
    assert cfg['api_key_masked'].endswith('cdef')
    assert '*' in cfg['api_key_masked']


def test_get_all_fresh_bypasses_cache(temp_db):
    """fresh=True 必须绕过缓存（后台设置页就靠这个参数）"""
    a = _fresh_worker()
    b = _fresh_worker()
    b.get('llm_provider')                       # b 先把缓存加载好
    a.set('llm_provider', 'remote')

    assert b.get('llm_provider') == 'local'     # 缓存还是旧的
    assert b.get_all(mask_sensitive=False, fresh=True)['llm_provider'] == 'remote'


def test_ttl_propagates_changes_to_other_worker(temp_db):
    """一个 worker 保存后，另一个 worker 在 TTL 到期后应看到新值"""
    from services.settings_service import CACHE_TTL

    a = _fresh_worker()
    b = _fresh_worker()
    assert b.get('llm_provider') == 'local'     # b 先加载（库里还没值）

    b._loaded_at = time.time()                  # 固定时间戳，排除慢机器影响
    a.set('llm_provider', 'remote')
    assert b.get('llm_provider') == 'local'     # TTL 内仍读缓存

    b._loaded_at -= (CACHE_TTL + 1)             # 模拟 TTL 到期
    assert b.get('llm_provider') == 'remote'    # 重读后拿到 a 的改动


def test_invalidate_cache_forces_reload(temp_db):
    a = _fresh_worker()
    b = _fresh_worker()
    b.get('llm_provider')
    a.set('llm_provider', 'remote')

    b.invalidate_cache()
    assert b.get('llm_provider') == 'remote'
