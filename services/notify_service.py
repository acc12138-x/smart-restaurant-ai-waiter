# services/notify_service.py
"""企业微信群机器人通知"""
import threading
import requests
from utils.logger import logger


WEBHOOK_TIMEOUT = 5


class NotifyService:

    def _enabled(self):
        try:
            from services.settings_service import settings_service
            if not settings_service.get_bool('notification_enabled', False):
                return False, ''
            url = (settings_service.get('wecom_webhook') or '').strip()
            if not url.startswith('https://qyapi.weixin.qq.com/'):
                return False, ''
            return True, url
        except Exception:
            return False, ''

    def _post(self, url, text):
        try:
            r = requests.post(
                url,
                json={'msgtype': 'text', 'text': {'content': text}},
                timeout=WEBHOOK_TIMEOUT,
            )
            if r.status_code != 200:
                logger.warning('[Notify] HTTP ' + str(r.status_code))
                return False
            d = r.json()
            if d.get('errcode') != 0:
                logger.warning('[Notify] errcode=' + str(d.get('errcode'))
                               + ' ' + str(d.get('errmsg', '')))
                return False
            logger.info('[Notify] 发送成功')
            return True
        except requests.exceptions.Timeout:
            logger.warning('[Notify] 超时')
            return False
        except Exception as e:
            logger.warning('[Notify] 失败: ' + str(e))
            return False

    def _async(self, text):
        """后台线程发通知，不阻塞"""
        def _run():
            ok, url = self._enabled()
            if not ok:
                return
            self._post(url, text)
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    # ============ 事件 ============

    def notify_new_order(self, order):
        """新订单通知"""
        try:
            items = order.get('items') or []
            items_str = '\n'.join(
                '  · ' + str(it.get('name')) + ' x' + str(it.get('qty'))
                for it in items
            )
            text = (
                '🔔 新订单\n'
                '订单号：' + str(order.get('id', '')) + '\n'
                '桌号：' + str(order.get('table_no') or '外带') + '\n'
                + items_str + '\n'
                '合计：¥' + str(order.get('total', 0))
            )
            self._async(text)
        except Exception as e:
            logger.warning('[Notify] 组装订单消息失败: ' + str(e))

    def notify_new_message(self, msg):
        """新留言通知"""
        try:
            text = (
                '💬 新留言\n'
                '来自：' + str(msg.get('name') or '匿名老客') + '\n'
                '内容：' + str(msg.get('content') or '')
            )
            self._async(text)
        except Exception as e:
            logger.warning('[Notify] 组装留言消息失败: ' + str(e))

    def test(self):
        """后台"测试通知"按钮：同步发一条，返回 (成功, 消息)"""
        ok, url = self._enabled()
        if not ok:
            return False, '通知未启用，或 Webhook 未配置'
        text = '✅ 同盛祥后台测试通知\n这是一条测试消息，收到说明配置正确。'
        if self._post(url, text):
            return True, '已发送，请到企业微信查看'
        return False, '发送失败，检查 Webhook 地址或网络'


notify_service = NotifyService()
