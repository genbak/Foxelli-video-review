class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable

    def body(self):
        return {"code": self.code, "message": self.message, "retryable": self.retryable}
