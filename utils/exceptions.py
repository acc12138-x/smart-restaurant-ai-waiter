class BizError(Exception):
    """业务异常"""

    def __init__(self, msg, code=400):
        self.msg = msg
        self.code = code
        super().__init__(msg)


class NotFoundError(BizError):
    """资源不存在"""

    def __init__(self, msg='资源不存在'):
        super().__init__(msg, code=404)


class AuthError(BizError):
    """认证失败"""

    def __init__(self, msg='未授权'):
        super().__init__(msg, code=401)
