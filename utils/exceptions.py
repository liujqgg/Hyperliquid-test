"""
统一的 API 与测试异常。
"""


class HyperliquidTestError(Exception):
    """框架/测试相关错误的基类。"""
    pass


class HyperliquidAPIError(HyperliquidTestError):
    """API 返回错误或非预期响应时使用。"""
    def __init__(self, message: str, response: dict | None = None):
        self.response = response or {}
        super().__init__(message)
