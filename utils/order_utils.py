"""
订单响应解析与辅助函数。
"""
from typing import Any, Optional


def parse_order_response(response: dict) -> list[dict]:
    """从交易所下单响应中解析出 statuses 列表。"""
    if response.get("type") != "order":
        return []
    data = response.get("data") or {}
    return data.get("statuses") or []


def get_oid_from_status(status: dict) -> Optional[int]:
    """从单条订单状态（resting 或 filled）中取出 oid。"""
    if "resting" in status:
        return status["resting"].get("oid")
    if "filled" in status:
        return status["filled"].get("oid")
    return None


def get_error_from_status(status: dict) -> Optional[str]:
    """从单条订单状态中取出错误信息。"""
    return status.get("error")


def is_resting(status: dict) -> bool:
    return "resting" in status


def is_filled(status: dict) -> bool:
    return "filled" in status


def is_error(status: dict) -> bool:
    return "error" in status


def parse_cancel_response(response: dict) -> list[Any]:
    """从撤单响应中解析出 statuses 列表。"""
    if response.get("type") != "cancel":
        return []
    data = response.get("data") or {}
    return data.get("statuses") or []
