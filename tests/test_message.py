# tests/test_message.py
import pytest
from services.message_service import message_service
from utils.exceptions import BizError


def test_create_message():
    """创建留言"""
    msg = message_service.create(name='测试', content='泡馍好吃')
    assert msg['name'] == '测试'
    assert msg['content'] == '泡馍好吃'
    assert 'id' in msg


def test_create_message_anonymous():
    """匿名留言"""
    msg = message_service.create(name='', content='好吃')
    assert msg['name'] == '匿名老客'


def test_create_message_empty_content():
    """空内容报错"""
    with pytest.raises(BizError):
        message_service.create(name='测试', content='')


def test_create_message_too_long():
    """超长内容报错"""
    with pytest.raises(BizError):
        message_service.create(name='测试', content='x' * 101)