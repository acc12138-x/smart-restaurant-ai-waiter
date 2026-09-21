# tests/test_api.py
from unittest.mock import patch


def test_api_menu(client):
    """菜单 API 返回正确格式"""
    resp = client.get('/api/menu')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert isinstance(data['data'], list)
    assert len(data['data']) >= 3


def test_api_message_success(client):
    """留言 API"""
    resp = client.post('/api/message', json={
        'name': '测试',
        'content': '泡馍好吃'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0


def test_api_message_empty(client):
    """空留言报错"""
    resp = client.post('/api/message', json={
        'name': '测试',
        'content': ''
    })
    assert resp.status_code == 400
    data = resp.get_json()
    assert data['code'] == 400


def test_api_404(client):
    """404 返回统一格式"""
    resp = client.get('/api/not_exist')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['code'] == 404
    assert data['msg'] == '接口不存在'


@patch('services.chat_service.chat_service.chat')
def test_api_chat_mock(mock_chat, client):
    """AI 接口（mock 掉模型，不真的调 Ollama）"""
    mock_chat.return_value = {
        'reply': '欢迎光临',
        'intent': 'chat',
        'order': None,
    }
    resp = client.post('/api/chat', json={'message': '你好'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['code'] == 0
    assert data['data']['reply'] == '欢迎光临'


def test_api_chat_empty(client):
    """空消息报错"""
    resp = client.post('/api/chat', json={'message': ''})
    assert resp.status_code == 400