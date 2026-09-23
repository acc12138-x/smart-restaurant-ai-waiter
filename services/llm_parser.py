# services/llm_parser.py
"""LLM 语义理解层：把用户输入解析成结构化意图 + 实体 JSON

设计原则：
- 只做"理解"，不做"执行"
- 优先用 Qwen API（qwen3.7-plus），失败降级到本地 Ollama，再失败降级到规则
- 白名单校验：菜名必须在菜单里，防幻觉
"""
import json
import re
import os
import requests
from configs.config import get_config
from utils.logger import logger

_cfg = get_config()

TIMEOUT = float(os.environ.get('LLM_PARSER_TIMEOUT', '20.0'))
QWEN_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'

_MENU_NAMES = None
_MENU_HASH = None

# 懒加载 OpenAI 客户端（key 变了要重建）
_qwen_client = None
_qwen_client_key = None


def _get_config():
    """运行时读取（支持后台热更新）"""
    try:
        from services.settings_service import settings_service
        return {
            'enabled':       settings_service.get_bool('llm_enabled', True),
            'provider':      settings_service.get('llm_provider') or 'local',
            'base_url':      settings_service.get('api_base_url') or 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'api_key':       settings_service.get('api_key') or '',
            'model':         settings_service.get('api_model') or 'qwen3.7-plus',
            'ollama_model':  settings_service.get('ollama_model') or _cfg.CHAT_MODEL,
        }
    except Exception:
        return {
            'enabled':       os.environ.get('USE_LLM_PARSER', '1') == '1',
            'provider':      'remote' if os.environ.get('USE_QWEN_API') == '1' else 'local',
            'base_url':      os.environ.get('OPENAI_BASE_URL') or 'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'api_key':       os.environ.get('DASHSCOPE_API_KEY', '') or os.environ.get('OPENAI_API_KEY', ''),
            'model':         os.environ.get('QWEN_MODEL', 'qwen3.7-plus'),
            'ollama_model':  _cfg.CHAT_MODEL,
        }


_remote_client = None
_remote_client_key = None


def _get_remote_client(base_url, api_key):
    global _remote_client, _remote_client_key
    cache_key = (base_url, api_key)
    if _remote_client is None or _remote_client_key != cache_key:
        from openai import OpenAI
        _remote_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=TIMEOUT,
        )
        _remote_client_key = cache_key
    return _remote_client
def _get_menu_names():
    global _MENU_NAMES, _MENU_HASH
    try:
        from services.menu_service import menu_service
        names = [d['name'] for d in menu_service.get_flat()]
        h = hash(tuple(sorted(names)))
        if _MENU_NAMES is None or h != _MENU_HASH:
            _MENU_NAMES = names
            _MENU_HASH = h
        return _MENU_NAMES
    except Exception:
        return []


def _get_ollama_host():
    host = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')
    if not host.startswith('http'):
        host = 'http://' + host
    host = host.replace('0.0.0.0', '127.0.0.1')
    return host.rstrip('/')


def _build_prompt(message, history, menu_names):
    menu_str = '、'.join(menu_names)
    history_str = history or '(无)'
    return (
        '你是泡馍店订单理解助手。只输出 JSON，不要任何解释。\n\n'
        '【菜单】' + menu_str + '\n\n'
        '【输出 JSON 格式】\n'
        '{"action": "...", "items": [...], "target": "...", "new_dish": "...", "reply_hint": "..."}\n\n'
        '【action 取值】\n'
        '- place_order: 下单/点菜（"来一份羊肉泡馍"、"10份"、"要大份"、"再要两份"）\n'
        '- cancel_order: 取消**最近一单**。触发词："取消订单"、"取消"、"退单"、"退了"、'
        '"取消牛肉泡馍"（有具体菜名时也走 cancel_order）。'
        '只要没说"全部/所有/都/一起"，一律 cancel_order。\n'
        '- cancel_all: 仅当明确说"全部取消"、"所有都取消"、"都退掉"、"一起取消"时用。\n'
        '- modify_order: 改单（"把A改成B"）\n'
        '- query_menu: 问菜单价格（"牛肉泡馍多少钱"、"有哪些菜"）\n'
        '- query_total: 问合计（"一共多少钱"）\n'
        '- query_location: 问地址位置（"在哪"、"怎么走"）\n'
        '- query_hours: 问营业时间/电话（"几点关门"）\n'
        '- recommend: 要推荐（"有推荐吗"、"推荐个套餐"）\n'
        '- accept_recommend: 接受上一轮的推荐（"就这个"、"就要你推荐的"、'
        '"来这个"、"就按你说的"、"这个吧"）。必须先检查【对话历史】里助手是否刚推荐过\n'
        '- reject_recommend: 拒绝上一轮推荐，要求换（"不要这个"、"换一个"、'
        '"推荐别的"、"再推荐"）\n'
        '- leave_message: 想给老店留言（"我要留言"、"给老店留句话"、"反馈一下"、'
        '"投诉"、"建议"）。留言内容填 reply_hint。\n'
        '- chat: 打招呼闲聊（"你好"、"谢谢"）\n'
        '- other: 其他（纯标点、纯 emoji、看不懂）\n\n'
        '【items 格式】\n'
        '[{"dish": "菜单上的完整菜名", "size": "大份|小份|", "qty": 数字}]\n\n'
        '【规则】\n'
        '1. dish 必须是菜单里存在的完整菜名，不要编造\n'
        '2. qty 省略时默认 1，最大 50\n'
        '3. size 只对"牛肉泡馍"填大份/小份，其他菜留空\n'
        '4. cancel_order 时把要取消的菜名填 target\n'
        '5. modify_order 时原菜名填 target，新菜名填 new_dish\n'
        '6. 纯标点/emoji/看不懂 → action="other"\n'
        '7. 只输出 JSON，不要 markdown 代码块\n\n'
        '【上下文理解】\n'
        '- "X的"/"就要X"/"来X吧"/"要X" 这类省略句：参考【对话历史】里 AI 最近一次反问的选项\n'
        '- "还要个"/"再来个"/"再要一份"：从历史里找最近一次下单/提到的菜名\n'
        '- "好的"/"嗯"/"行"/"可以"/"OK"：判断上文——AI 上一条是推荐具体菜品 → 按推荐下单；是反问 → 结合更早的上下文；只是闲聊 → action=chat\n'
        '- "就这个"/"就要"/"来这个"/"就按你说的"/"这个吧"：如果助手上一条推荐了具体菜品 → action=accept_recommend\n'
        '- "换一个"/"不要这个"/"推荐别的"：如果助手上一条推荐过 → action=reject_recommend\n'
        '- "X小份"/"X大份"但菜单里没有对应规格（例如"羊肉泡馍小份"但菜单只有"羊肉泡馍"）：直接返回主菜名\n'
        '- 短句"X份"/"X个"没有明确菜名：先判断历史可推断；无法推断时 action=place_order 且 items=[]\n\n'
        '【菜单匹配】\n'
        '- 严格用菜单里的完整菜名，不要编造\n'
        '- 用户问的菜不在菜单里（如"木头馍"）：action=query_menu，items=[]，reply_hint="菜单里没有这道菜"\n\n'
        '【对话历史】\n' + history_str + '\n\n'
        '【用户输入】\n' + message + '\n\n'
        '【JSON】'
    )


def _extract_json(text):
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def _normalize_items(items, menu_names):
    if not isinstance(items, list):
        return []
    result = []
    menu_set = set(menu_names)
    for it in items:
        if not isinstance(it, dict):
            continue
        dish = (it.get('dish') or '').strip()
        if not dish:
            continue
        size = (it.get('size') or '').strip()
        if size in ('大份', '小份'):
            cand = dish + '(' + size + ')'
            if cand in menu_set:
                dish = cand
        if dish not in menu_set:
            matched = None
            for m in menu_names:
                if dish == m or dish in m or m in dish:
                    if matched is None or len(m) > len(matched):
                        matched = m
            if matched:
                dish = matched
            else:
                logger.warning('[LLM] 菜名不在菜单: ' + dish)
                continue
        try:
            qty = int(it.get('qty', 1))
        except (ValueError, TypeError):
            qty = 1
        qty = max(1, min(50, qty))
        result.append({'name': dish, 'qty': qty})
    return result


def _pack_result(parsed, menu_names, message, source):
    """把解析出的 dict 打包成标准返回结构"""
    action = parsed.get('action', 'other')
    if action not in VALID_ACTIONS:
        action = 'other'
    return {
        'intent': action,
        'items': _normalize_items(parsed.get('items', []), menu_names),
        'target': (parsed.get('target') or '').strip(),
        'new_dish': (parsed.get('new_dish') or '').strip(),
        'reply_hint': (parsed.get('reply_hint') or '').strip(),
        'source': source,
    }


VALID_ACTIONS = {'place_order', 'cancel_order', 'cancel_all', 'modify_order',
                 'query_menu', 'query_total', 'query_location', 'query_hours',
                 'recommend', 'accept_recommend', 'reject_recommend',
                 'leave_message',
                 'chat', 'other'}


def _try_remote_api(prompt, message, menu_names, cfg):
    """尝试远程 OpenAI 兼容 API；成功返回 result，失败返回 None"""
    if cfg.get('provider') != 'remote':
        return None
    api_key = cfg.get('api_key') or ''
    if not api_key:
        logger.warning('[Qwen API] 未配置 API Key，跳过')
        return None

    try:
        client = _get_remote_client(cfg.get('base_url'), api_key)
        response = client.chat.completions.create(
            model=cfg.get('model') or 'qwen3.7-plus',
            messages=[{'role': 'user', 'content': prompt}],
            stream=False,
            temperature=0.1,
            max_tokens=400,
            response_format={'type': 'json_object'},
        )
        content = response.choices[0].message.content
        parsed = _extract_json(content)
        if not parsed:
            logger.warning('[Qwen API] JSON 解析失败: ' + (content[:120]))
            return None
        result = _pack_result(parsed, menu_names, message, 'qwen_api')
        logger.info('[Qwen API] ' + message[:30] + ' → ' + result['intent'] +
                    ' ' + str(result['items']))
        return result
    except Exception as e:
        logger.warning('[Qwen API] 调用失败: ' + str(e) + '，降级到本地 Ollama')
        return None


def _try_ollama(prompt, message, menu_names, cfg):
    """尝试本地 Ollama；成功返回 result，失败返回 None"""
    host = _get_ollama_host()
    url = host + '/api/chat'

    payload = {
        'model': cfg.get('ollama_model') or _cfg.CHAT_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': False,
        'format': 'json',
        'think': False,
        'options': {'temperature': 0.1, 'num_predict': 400},
    }

    try:
        r = requests.post(url, json=payload, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        content = (data.get('message', {}) or {}).get('content', '')
        parsed = _extract_json(content)
        if not parsed:
            logger.warning('[LLM] JSON 解析失败: ' + (content[:120]))
            return None
        result = _pack_result(parsed, menu_names, message, 'llm')
        logger.info('[LLM] ' + message[:30] + ' → ' + result['intent'] +
                    ' ' + str(result['items']))
        return result
    except requests.exceptions.Timeout:
        logger.warning('[LLM] 超时 ' + str(TIMEOUT) + 's，降级到规则')
        return None
    except Exception as e:
        logger.warning('[LLM] 调用失败: ' + str(e) + '，降级到规则')
        return None


def parse(message, history=''):
    cfg = _get_config()
    if not cfg.get('enabled'):
        return None
    if not message or not message.strip():
        return None

    menu_names = _get_menu_names()
    if not menu_names:
        return None

    prompt = _build_prompt(message.strip(), history, menu_names)

    # 1) 如果用户选了 Qwen API
    if cfg.get('provider') == 'remote':
        result = _try_remote_api(prompt, message, menu_names, cfg)
        if result:
            return result
        # Qwen 失败 → 降级本地 Ollama
        logger.info('[LLM] Qwen 失败，降级到本地 Ollama')

    # 2) 本地 Ollama（默认路径 / Qwen 失败后）
    result = _try_ollama(prompt, message, menu_names, cfg)
    if result:
        return result

    # 3) 都失败
    return None


def is_enabled():
    return _get_config().get('enabled', False)


def get_source_info():
    """给后台/调试用：当前优先级"""
    cfg = _get_config()
    return {
        'enabled': cfg.get('enabled'),
        'provider': cfg.get('provider'),
        'remote_api': cfg.get('provider') == 'remote' and bool(cfg.get('api_key')),
        'remote_model': cfg.get('model'),
        'api_base_url': cfg.get('base_url'),
        'ollama_model': _cfg.CHAT_MODEL,
        'timeout': TIMEOUT,
    }
