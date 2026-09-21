# services/llm_parser.py
"""LLM 语义理解层：把用户输入解析成结构化意图 + 实体 JSON

设计原则：
- 只做"理解"，不做"执行"
- 失败/超时返回 None，调用方降级到规则
- 白名单校验：菜名必须在菜单里，防幻觉
"""
import json
import re
import os
import requests
from configs.config import get_config
from utils.logger import logger

_cfg = get_config()

ENABLED = os.environ.get('USE_LLM_PARSER', '0') == '1'
TIMEOUT = float(os.environ.get('LLM_PARSER_TIMEOUT', '20.0'))

_MENU_NAMES = None
_MENU_HASH = None


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
        '- cancel_order: 取消指定订单（"取消牛肉泡馍"、"退掉糖蒜"）\n'
        '- cancel_all: 全部取消（"全部退掉"、"都取消"）\n'
        '- modify_order: 改单（"把A改成B"）\n'
        '- query_menu: 问菜单价格（"牛肉泡馍多少钱"、"有哪些菜"）\n'
        '- query_total: 问合计（"一共多少钱"）\n'
        '- query_location: 问地址位置（"在哪"、"怎么走"）\n'
        '- query_hours: 问营业时间/电话（"几点关门"）\n'
        '- recommend: 要推荐（"有推荐吗"、"推荐个套餐"）\n'
        '- chat: 打招呼闲聊（"你好"、"谢谢"）\n'
        '- other: 其他（纯标点、纯 emoji、看不懂）\n\n'
        '【items 格式】\n'
        '[{"dish": "菜单上的完整菜名", "size": "大份|小份|", "qty": 数字}]\n\n'
        '【规则】\n'
        '1. dish 必须是菜单里存在的菜名\n'
        '2. qty 省略默认 1，最大 50\n'
        '3. size 只对"牛肉泡馍"填大份/小份\n'
        '4. cancel_order 时把要取消的菜名填 target\n'
        '5. modify_order 时原菜名填 target，新菜名填 new_dish\n'
        '6. 纯标点/emoji/看不懂 → action="other"\n'
        '7. 只输出 JSON，不要 markdown 代码块\n\n'
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


VALID_ACTIONS = {'place_order', 'cancel_order', 'cancel_all', 'modify_order',
                 'query_menu', 'query_total', 'query_location', 'query_hours',
                 'recommend', 'chat', 'other'}


def parse(message, history=''):
    if not ENABLED:
        return None
    if not message or not message.strip():
        return None

    menu_names = _get_menu_names()
    if not menu_names:
        return None

    prompt = _build_prompt(message.strip(), history, menu_names)
    host = _get_ollama_host()
    url = host + '/api/chat'

    payload = {
        'model': _cfg.CHAT_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'stream': False,
        'format': 'json',
        'think': False,  # ← 新增这行
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

        action = parsed.get('action', 'other')
        if action not in VALID_ACTIONS:
            action = 'other'

        result = {
            'intent': action,
            'items': _normalize_items(parsed.get('items', []), menu_names),
            'target': (parsed.get('target') or '').strip(),
            'new_dish': (parsed.get('new_dish') or '').strip(),
            'reply_hint': (parsed.get('reply_hint') or '').strip(),
            'source': 'llm',
        }
        logger.info('[LLM] ' + message[:30] + ' → ' + action + ' ' + str(result['items']))
        return result
    except requests.exceptions.Timeout:
        logger.warning('[LLM] 超时 ' + str(TIMEOUT) + 's，降级到规则')
        return None
    except Exception as e:
        logger.warning('[LLM] 调用失败: ' + str(e) + '，降级到规则')
        return None


def is_enabled():
    return ENABLED