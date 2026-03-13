"""
等待/轮询辅助，用于订单状态与稳定性判断。
"""
import time
import logging
from typing import Callable, TypeVar, Optional

from config.loader import get_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


def wait_until(
    condition: Callable[[], T],
    timeout_seconds: Optional[float] = None,
    poll_interval_ms: Optional[float] = None,
    message: str = "condition",
) -> T:
    """
    轮询 condition() 直到返回真值或超时。
    返回 condition() 的返回值；若始终未为真则抛出 TimeoutError。
    """
    cfg = get_config()
    test_cfg = cfg.get("test", {})
    timeout = timeout_seconds if timeout_seconds is not None else test_cfg.get("poll_timeout_seconds", 30)
    interval = (poll_interval_ms or test_cfg.get("poll_interval_ms", 500)) / 1000.0
    deadline = time.monotonic() + timeout
    last_val: Optional[T] = None
    while time.monotonic() < deadline:
        last_val = condition()
        if last_val:
            return last_val
        time.sleep(interval)
    raise TimeoutError(f"wait_until 超时（{message}），{timeout}s 后仍未满足。最后返回值: {last_val}")
