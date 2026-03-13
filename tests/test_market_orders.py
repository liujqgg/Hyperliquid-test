"""
市价单测试：市价开仓（多空随机）-> 查询仓位 -> 减仓 -> 查询仓位 -> 平仓。
Hyperliquid 无单独市价单类型，市价单用 limit + 市价 TIF + 激进价格实现。
FrontendMarket 表示市价单；若交易所返回不支持可改为 Ioc。
"""
import random
import time
import pytest
import allure

from config.loader import get_config
from utils.order_utils import parse_order_response, get_error_from_status, is_filled
from utils.retry import retry
from utils.exceptions import HyperliquidAPIError

# 市价单 TIF：FrontendMarket 使前端/交易所显示为市价单；不支持时改为 "Ioc"
MARKET_TIF = "FrontendMarket"

MIN_NOTIONAL = 11.0  # 略大于交易所 10，避免舍入后不足


def _mid_price(client, symbol: str) -> float:
    mids = client.all_mids()
    return float(mids.get(symbol, 0) or 0)


def _get_position(state: dict, symbol: str) -> dict | None:
    for ap in state.get("assetPositions", []):
        pos = ap.get("position") if isinstance(ap.get("position"), dict) else ap
        coin = (pos or ap).get("coin") or ap.get("coin")
        if coin == symbol:
            return pos or ap
    return None


def _position_size(pos: dict) -> float:
    szi = pos.get("szi") or pos.get("size")
    return abs(float(szi)) if szi is not None else 0.0


def _market_price_hint(mid: float, is_buy: bool) -> float:
    """市价单价格提示（激进价）：买略高于 mid，卖略低于 mid。"""
    if is_buy:
        return round(mid * 1.001, 2) if mid > 1 else round(mid * 1.001, 6)
    return round(mid * 0.999, 2) if mid > 1 else round(mid * 0.999, 6)


def _market_size_rounded(client, symbol: str, mid: float, is_buy: bool) -> tuple[float, float]:
    """市价开仓用：数量与价格，按标的精度舍入，保证名义价值 >= 10。"""
    price_hint = _market_price_hint(mid, is_buy)
    size = max(0.001, 12.0 / max(price_hint, 0.01))
    sz_decimals = client.get_sz_decimals(symbol)
    actual_px = client.round_order_price(symbol, price_hint)
    tick = 10 ** (-sz_decimals)
    size = max(size, MIN_NOTIONAL / max(actual_px, 1e-8))
    size = round(size, sz_decimals)
    if size < tick:
        size = tick
    if size * actual_px < 10:
        size = round(MIN_NOTIONAL / actual_px, sz_decimals)
        if size < tick:
            size = tick
        if size * actual_px < 10:
            size = round(size + tick, sz_decimals)
    return size, price_hint


def _wait_settle() -> None:
    ms = get_config().get("test", {}).get("order_settle_ms", 2000)
    time.sleep(ms / 1000.0)


def _place_market_order(client, symbol: str, is_buy: bool, size: float, price_hint: float, reduce_only: bool = False, cloid: str | None = None) -> dict:
    """下市价单（FrontendMarket），返回交易所原始 response。"""
    kwargs = dict(symbol=symbol, is_buy=is_buy, size=size, price_hint=price_hint, reduce_only=reduce_only, tif=MARKET_TIF)
    if cloid is not None:
        kwargs["cloid"] = cloid
    return client.order(**kwargs)


def _assert_order_ok(resp: dict, require_filled: bool = False) -> None:
    statuses = parse_order_response(resp)
    assert len(statuses) >= 1, resp
    st = statuses[0]
    assert get_error_from_status(st) is None, st
    if require_filled:
        assert is_filled(st), f"预期成交: {st}"


@allure.epic("Hyperliquid API")
@allure.feature("Market Orders")
class TestMarketOrder:
    """市价单：开仓（多空随机）-> 查询仓位 -> 减仓 -> 查询仓位 -> 平仓。"""

    @allure.title("市价单：开仓(多空随机) -> 查询仓位 -> 减仓 -> 查询仓位 -> 平仓")
    @allure.description("市价开仓(Ioc 多空随机) -> 查询持仓 -> 市价减仓(部分) -> 再查持仓 -> 市价平仓(全部)")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_market_order_open_query_reduce_query_close(self, client, default_symbol, unique_cloid):
        mid = _mid_price(client, default_symbol)
        if mid <= 0:
            pytest.skip("无中间价")
        is_buy = random.choice([True, False])
        size, price_hint = _market_size_rounded(client, default_symbol, mid, is_buy)

        # 1. 市价开仓
        resp = _place_market_order(client, default_symbol, is_buy, size, price_hint, reduce_only=False, cloid=unique_cloid)
        _assert_order_ok(resp, require_filled=True)

        # 2. 查询仓位
        _wait_settle()
        state = client.clearinghouse_state()
        pos = _get_position(state, default_symbol)
        assert pos is not None, "开仓后应有持仓"
        open_sz = _position_size(pos)
        assert open_sz >= 0.001, "持仓数量应大于 0"

        # 3. 减仓（约一半）
        reduce_sz = round(open_sz * 0.5, 6)
        if reduce_sz < 0.001:
            reduce_sz = open_sz
        reduce_resp = _place_market_order(client, default_symbol, not is_buy, reduce_sz, _market_price_hint(mid, not is_buy), reduce_only=True)
        _assert_order_ok(reduce_resp)

        # 4. 再查仓位
        _wait_settle()
        state2 = client.clearinghouse_state()
        pos2 = _get_position(state2, default_symbol)
        assert pos2 is not None, "减仓后仍有剩余持仓"
        remaining_sz = _position_size(pos2)
        assert remaining_sz <= open_sz, "减仓后持仓应小于开仓后"

        # 5. 平仓
        if remaining_sz >= 0.001:
            close_resp = _place_market_order(client, default_symbol, not is_buy, remaining_sz, _market_price_hint(mid, not is_buy), reduce_only=True)
            _assert_order_ok(close_resp)
