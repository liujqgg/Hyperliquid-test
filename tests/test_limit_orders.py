"""
限价单测试：下单、查询、取消。
限价单创建时限价远离市价 50%（买单 mid*0.5，卖单 mid*1.5），确保挂单不立即成交。
"""
import time
import pytest
import allure

from utils.order_utils import (
    parse_order_response,
    get_oid_from_status,
    get_error_from_status,
    parse_cancel_response,
    is_resting,
    is_filled,
)
from utils.retry import retry
from utils.exceptions import HyperliquidAPIError
from config.loader import get_config


def _mid_price(client, symbol: str) -> float:
    """获取标的中间价。"""
    mids = client.all_mids()
    return float(mids.get(symbol, 0) or 0)


def _limit_px_size_50pct_away(client, symbol: str, is_buy: bool) -> tuple[float, float]:
    """限价远离市价 50%：买单 mid*0.5，卖单 mid*1.5。返回 (limit_px, size)。"""
    mid = _mid_price(client, symbol)
    if mid <= 0:
        pytest.skip("无中间价")
    limit_px = mid * 0.5 if is_buy else mid * 1.5
    limit_px = round(limit_px, 2) if limit_px >= 1 else round(limit_px, 6)
    size = max(0.001, 12.0 / limit_px)
    if size * limit_px < 10:
        size = 11.0 / limit_px
    return limit_px, size


def _place_limit_order(client, symbol: str, is_buy: bool, cloid: str) -> tuple[dict, int | None]:
    """下限价单（限价远离市价 50%），返回 (resp, oid)。"""
    limit_px, size = _limit_px_size_50pct_away(client, symbol, is_buy)
    resp = client.order(
        symbol=symbol,
        is_buy=is_buy,
        size=size,
        limit_px=limit_px,
        reduce_only=False,
        tif="Gtc",
        cloid=cloid,
    )
    statuses = parse_order_response(resp)
    assert len(statuses) >= 1, resp
    oid = get_oid_from_status(statuses[0])
    return resp, oid


def _assert_cancel_ok(cancel_resp: dict) -> None:
    """断言撤单响应为成功。"""
    statuses = parse_cancel_response(cancel_resp)
    assert len(statuses) >= 1
    st = statuses[0]
    assert st == "success" or (isinstance(st, dict) and st.get("error") is None)


def _settle_ms() -> int:
    return get_config().get("test", {}).get("order_settle_ms", 2000)


@allure.epic("Hyperliquid API")
@allure.feature("Limit Orders")
class TestLimitOrderLifecycle:
    """限价单：下单、查询、取消。"""

    @allure.title("下单：限价单远离市价 50%")
    @allure.description("下限价单（买单 mid*0.5，卖单 mid*1.5），校验无错误并取 oid，结束时撤单清理")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_place_limit_order(self, client, default_symbol, unique_cloid):
        resp, oid = _place_limit_order(client, default_symbol, is_buy=True, cloid=unique_cloid)
        st = parse_order_response(resp)[0]
        assert get_error_from_status(st) is None, st
        assert oid is not None or is_resting(st) or is_filled(st), st
        if oid is not None:
            _assert_cancel_ok(client.cancel(default_symbol, oid))

    @allure.title("查询：按 oid 查询订单状态")
    @allure.description("下限价单后调用 orderStatus 查询，校验返回结构后撤单")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_query_order_status(self, client, default_symbol, unique_cloid):
        _, oid = _place_limit_order(client, default_symbol, is_buy=True, cloid=unique_cloid)
        if oid is None:
            pytest.skip("订单立即成交，无 oid")
        time.sleep(_settle_ms() / 1000.0)
        status_resp = client.order_status(oid)
        assert status_resp is not None and isinstance(status_resp, dict)
        assert "status" in status_resp or "order" in status_resp or "status" in str(status_resp).lower()
        _assert_cancel_ok(client.cancel(default_symbol, oid))

    @allure.title("取消：按 oid 撤单")
    @allure.description("下限价单后按 oid 撤单并校验撤单响应")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_cancel_order(self, client, default_symbol, unique_cloid):
        _, oid = _place_limit_order(client, default_symbol, is_buy=True, cloid=unique_cloid)
        if oid is None:
            pytest.skip("订单已成交，无需撤单")
        _assert_cancel_ok(client.cancel(default_symbol, oid))
