"""
市价单测试：市价开仓（多空随机）-> 查询仓位 -> 可选部分减仓 -> 平仓。
Hyperliquid 无单独市价单类型，市价单用 limit + FrontendMarket + 激进价格。
每笔订单名义须 >= 约 $10；部分减仓时开仓须足够大，否则只做满仓平仓。
"""
import random
import time
import math
import pytest
import allure

from config.loader import get_config
from utils.order_utils import parse_order_response, get_error_from_status, is_filled
from utils.retry import retry
from utils.exceptions import HyperliquidAPIError

MARKET_TIF = "FrontendMarket"
MIN_NOTIONAL_USD = 11.0  # > $10，抵消舍入


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


def _position_szi(pos: dict) -> float:
    raw = pos.get("szi") or pos.get("size")
    return float(raw) if raw is not None else 0.0


def _close_is_buy(pos: dict) -> bool:
    """空头平仓 = 买；多头平仓 = 卖。"""
    return _position_szi(pos) < 0


def _market_price_hint(mid: float, is_buy: bool) -> float:
    if is_buy:
        return round(mid * 1.001, 2) if mid > 1 else round(mid * 1.001, 6)
    return round(mid * 0.999, 2) if mid > 1 else round(mid * 0.999, 6)


def _min_size_meeting_notional(
    client, symbol: str, mid: float, is_buy: bool, usd: float = MIN_NOTIONAL_USD
) -> tuple[float, float]:
    """返回 (size, price_hint)，使 round 后名义 >= usd（与 order() 内舍入一致）。"""
    price_hint = _market_price_hint(mid, is_buy)
    px = client.round_order_price(symbol, price_hint)
    sz_dec = client.get_sz_decimals(symbol)
    tick = 10 ** (-sz_dec)
    need = max(10.0, usd)
    sz = need / max(px, 1e-12)
    sz = math.ceil(sz / tick) * tick
    sz = round(sz, sz_dec)
    if sz < tick:
        sz = tick
    while sz * px < need and sz < 1e9:
        sz = round(sz + tick, sz_dec)
    return sz, price_hint


def _open_size_meeting_notional(
    client, symbol: str, mid: float, is_buy: bool, usd: float
) -> tuple[float, float]:
    """开仓：名义 >= usd（用于后续还能再下一张 >= $10 的 reduce）。"""
    return _min_size_meeting_notional(client, symbol, mid, is_buy, usd=usd)


def _wait_settle() -> None:
    time.sleep(get_config().get("test", {}).get("order_settle_ms", 2000) / 1000.0)


def _place_market_order(
    client, symbol: str, is_buy: bool, size: float, price_hint: float, reduce_only: bool = False, cloid: str | None = None
) -> dict:
    kwargs = dict(
        symbol=symbol, is_buy=is_buy, size=size, price_hint=price_hint, reduce_only=reduce_only, tif=MARKET_TIF
    )
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


def _notional_ok(client, symbol: str, mid: float, is_buy: bool, size: float) -> bool:
    px = client.round_order_price(symbol, _market_price_hint(mid, is_buy))
    sz_dec = client.get_sz_decimals(symbol)
    s = round(size, sz_dec)
    return s * px >= MIN_NOTIONAL_USD - 0.01


@allure.epic("Hyperliquid API")
@allure.feature("Market Orders")
class TestMarketOrder:
    @allure.title("市价单：开仓 -> 查询 -> 可选减仓 -> 平仓")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_market_order_open_query_reduce_query_close(self, client, default_symbol, unique_cloid):
        mid = _mid_price(client, default_symbol)
        if mid <= 0:
            pytest.skip("无中间价")

        is_buy = random.choice([True, False])
        # 至少 ~$22 名义开仓，才有可能「先减一张 >=$10 再平剩余 >=$10」
        open_usd = MIN_NOTIONAL_USD * 2.5
        size, price_hint = _open_size_meeting_notional(client, default_symbol, mid, is_buy, open_usd)

        resp = _place_market_order(client, default_symbol, is_buy, size, price_hint, reduce_only=False, cloid=unique_cloid)
        _assert_order_ok(resp, require_filled=True)

        _wait_settle()
        state = client.clearinghouse_state()
        pos = _get_position(state, default_symbol)
        assert pos is not None, "开仓后应有持仓"
        open_sz = _position_size(pos)
        assert open_sz >= 10 ** (-client.get_sz_decimals(default_symbol)), "应有可平数量"

        close_buy = _close_is_buy(pos)
        sz_dec = client.get_sz_decimals(default_symbol)
        tick = 10 ** (-sz_dec)
        min_sz, _ = _min_size_meeting_notional(client, default_symbol, mid, close_buy, MIN_NOTIONAL_USD)
        px_close = client.round_order_price(default_symbol, _market_price_hint(mid, close_buy))

        # 能否做「部分减仓」：减半后仍 >= min_sz 且剩余也 >= min_sz（两笔都 >= $10）
        half = round(open_sz * 0.5, sz_dec)
        if half < tick:
            half = tick
        rest = open_sz - half
        partial_ok = (
            half >= min_sz - 1e-12
            and rest >= min_sz - 1e-12
            and half * px_close >= MIN_NOTIONAL_USD - 0.5
            and rest * px_close >= MIN_NOTIONAL_USD - 0.5
        )

        if partial_ok:
            reduce_sz = min(half, open_sz - tick)
            reduce_sz = max(reduce_sz, min_sz)
            reduce_sz = min(reduce_sz, open_sz - tick)
            if reduce_sz < min_sz or (open_sz - reduce_sz) * px_close < MIN_NOTIONAL_USD - 0.5:
                partial_ok = False

        if partial_ok:
            reduce_resp = _place_market_order(
                client, default_symbol, close_buy, reduce_sz, _market_price_hint(mid, close_buy), reduce_only=True
            )
            _assert_order_ok(reduce_resp)
            _wait_settle()
            state2 = client.clearinghouse_state()
            pos2 = _get_position(state2, default_symbol)
            assert pos2 is not None, "部分减仓后仍有仓"
            assert _position_size(pos2) < open_sz, "持仓应减少"
            pos = pos2
            close_buy = _close_is_buy(pos)

        # 满仓平掉剩余
        _wait_settle()
        state3 = client.clearinghouse_state()
        pos3 = _get_position(state3, default_symbol)
        if pos3 is None or _position_size(pos3) < tick:
            return
        rem = _position_size(pos3)
        close_buy = _close_is_buy(pos3)
        ph = _market_price_hint(mid, close_buy)
        if not _notional_ok(client, default_symbol, mid, close_buy, rem):
            pytest.skip("剩余名义不足 $10，无法单独平仓（交易所规则）")
        close_resp = _place_market_order(client, default_symbol, close_buy, rem, ph, reduce_only=True)
        _assert_order_ok(close_resp)
