# utils/remote_llm.py
"""通用 LLM 调用：优先远程 API，失败降级本地 Ollama
读 settings.llm_provider 决定走哪条路
"""
from utils.logger import logger


def chat(prompt, temperature=0.4, max_tokens=400, timeout=30):
    """一次性调用（非流式），返回文本或 None"""
    try:
        from services.settings_service import settings_service
        provider = settings_service.get('llm_provider') or 'local'
    except Exception:
        provider = 'local'

    if provider == 'remote':
        result = _call_remote(prompt, temperature, max_tokens, timeout)
        if result:
            return result
        logger.info('[LLM] 远程失败，降级本地 Ollama')
    return _call_ollama(prompt, temperature, max_tokens, timeout)


def chat_stream(prompt, temperature=0.4, max_tokens=400, timeout=120):
    """流式调用，yield 文本块"""
    try:
        from services.settings_service import settings_service
        provider = settings_service.get('llm_provider') or 'local'
    except Exception:
        provider = 'local'

    if provider == 'remote':
        got_any = False
        for chunk in _stream_remote(prompt, temperature, max_tokens, timeout):
            if chunk:
                got_any = True
                yield chunk
        if got_any:
            return
        logger.info('[LLM] 远程流式失败，降级本地 Ollama')

    for chunk in _stream_ollama(prompt, temperature, max_tokens, timeout):
        yield chunk


# ============ 远程 OpenAI 兼容 API ============
def _call_remote(prompt, temperature, max_tokens, timeout):
    try:
        from services.settings_service import settings_service
        api_key = settings_service.get('api_key') or ''
        base_url = settings_service.get('api_base_url') or ''
        model = settings_service.get('api_model') or ''
        if not (api_key and base_url and model):
            return None
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        r = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (r.choices[0].message.content or '').strip()
    except Exception as e:
        logger.warning('[LLM] 远程调用失败: ' + str(e)[:120])
        return None


def _stream_remote(prompt, temperature, max_tokens, timeout):
    try:
        from services.settings_service import settings_service
        api_key = settings_service.get('api_key') or ''
        base_url = settings_service.get('api_base_url') or ''
        model = settings_service.get('api_model') or ''
        if not (api_key and base_url and model):
            return
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        stream = client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
            except Exception:
                continue
    except Exception as e:
        logger.warning('[LLM] 远程流式失败: ' + str(e)[:120])


# ============ 本地 Ollama ============
def _call_ollama(prompt, temperature, max_tokens, timeout):
    try:
        import requests
        from services.llm_parser import _get_ollama_host, _get_config
        from configs.config import get_config as _cfg
        cfg_llm = _get_config()
        host = _get_ollama_host()
        model = cfg_llm.get('ollama_model') or _cfg().CHAT_MODEL
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
            'think': False,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        r = requests.post(host + '/api/chat', json=payload, timeout=timeout)
        r.raise_for_status()
        return ((r.json().get('message', {}) or {}).get('content') or '').strip()
    except Exception as e:
        logger.warning('[LLM] 本地 Ollama 失败: ' + str(e)[:120])
        return None


def _stream_ollama(prompt, temperature, max_tokens, timeout):
    try:
        import requests, json
        from services.llm_parser import _get_ollama_host, _get_config
        from configs.config import get_config as _cfg
        cfg_llm = _get_config()
        host = _get_ollama_host()
        model = cfg_llm.get('ollama_model') or _cfg().CHAT_MODEL
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': True,
            'think': False,
            'options': {'temperature': temperature, 'num_predict': max_tokens},
        }
        with requests.post(host + '/api/chat', json=payload, stream=True, timeout=timeout) as r:
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    c = (d.get('message', {}) or {}).get('content', '')
                    if c:
                        yield c
                except Exception:
                    continue
    except Exception as e:
        logger.warning('[LLM] 本地流式失败: ' + str(e)[:120])
