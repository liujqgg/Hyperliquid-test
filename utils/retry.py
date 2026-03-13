"""
重试装饰器与辅助。
"""
import time
import logging
from functools import wraps
from typing import Callable, TypeVar, Tuple, Type

from config.loader import get_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(
    times: int | None = None,
    delay: float | None = None,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
):
    """在指定异常发生时重试被装饰函数。times/delay 为 None 时从 config.test.retry_times、retry_delay_seconds 读取。"""
    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @wraps(f)
        def wrapper(*args, **kwargs) -> T:
            cfg = get_config()
            test_cfg = cfg.get("test", {})
            n = times if times is not None else test_cfg.get("retry_times", 3)
            d = delay if delay is not None else test_cfg.get("retry_delay_seconds", 2)
            exc_tuple = exceptions
            last: Exception | None = None
            for attempt in range(1, n + 1):
                try:
                    return f(*args, **kwargs)
                except exc_tuple as e:
                    last = e
                    if on_retry:
                        on_retry(e, attempt)
                    if attempt < n:
                        logger.warning("Retry %s/%s after %s: %s", attempt, n, d, e)
                        time.sleep(d)
            if last:
                raise last
            raise RuntimeError("retry exhausted")
        return wrapper
    return decorator
