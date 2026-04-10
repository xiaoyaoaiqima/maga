"""
LLM SDK 异常定义
"""


class LLMError(Exception):
    """LLM SDK 基础异常"""
    pass


class LLMConfigError(LLMError):
    """配置获取异常"""
    pass


class RetryableError(LLMError):
    """可重试错误，触发 failover"""
    
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class NonRetryableError(LLMError):
    """不可重试错误，直接失败"""
    
    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class AllProvidersFailedError(LLMError):
    """所有端点都失败"""
    
    def __init__(self, message: str, last_error: Exception = None, attempts: int = 0):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


class CircuitBreakerOpenError(LLMError):
    """熔断器打开异常"""
    
    def __init__(self, provider_code: str):
        super().__init__(f"Provider '{provider_code}' is circuit-broken")
        self.provider_code = provider_code


def classify_error(status_code: int, error_message: str) -> Exception:
    """
    错误分类
    
    Args:
        status_code: HTTP 状态码
        error_message: 错误信息
    
    Returns:
        RetryableError 或 NonRetryableError
    """
    # 可重试错误：超时、服务端错误、限流
    if status_code in (408, 429, 500, 502, 503, 504):
        return RetryableError(f"HTTP {status_code}: {error_message}", status_code)
    
    # 不可重试错误：认证失败
    if status_code in (401, 403):
        return NonRetryableError(f"认证失败: {error_message}", status_code)
    
    # 不可重试错误：模型不存在
    if status_code == 404:
        return NonRetryableError(f"模型不存在: {error_message}", status_code)
    
    # 不可重试错误：参数错误
    if status_code == 400:
        return NonRetryableError(f"参数错误: {error_message}", status_code)
    
    # 默认为可重试错误
    return RetryableError(f"未知错误 HTTP {status_code}: {error_message}", status_code)

