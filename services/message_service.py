# services/message_service.py
from repositories.instances import message_repo
from utils.exceptions import BizError


class MessageService:
    """留言业务逻辑"""

    MAX_LEN = 100
    MAX_NAME_LEN = 20

    def create(self, name: str, content: str) -> dict:
        content = (content or '').strip()
        name = (name or '').strip() or '匿名老客'

        if not content:
            raise BizError('内容不能为空')
        if len(content) > self.MAX_LEN:
            raise BizError(f'内容超过 {self.MAX_LEN} 字')
        if len(name) > self.MAX_NAME_LEN:
            raise BizError(f'称呼超过 {self.MAX_NAME_LEN} 字')

        return message_repo.create({
            'name': name,
            'content': content,
        })

    def get_all(self):
        return message_repo.get_all()

    def count(self):
        return message_repo.count()


# 单例
message_service = MessageService()