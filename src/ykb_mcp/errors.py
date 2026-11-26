class YkbError(Exception):
    pass


class NotLoggedInError(YkbError):
    pass


class TokenExpiredError(YkbError):
    pass


class ApiError(YkbError):
    def __init__(self, code: str, message: str):
        self.code = str(code)
        self.message = message
        super().__init__(f"[{self.code}] {message}")