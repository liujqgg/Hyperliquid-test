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

MIN_NOTIONAL = 11.0  # 略大于交易所 $10，避免舍入后不足
# 部分减仓时单笔仍须 ≥ $10；开仓至少 2 倍，保证「减半」仍满足最小名义金额
MIN_OPEN_NOTIONAL_FOR_PARTIAL = MIN_NOTIONAL * 2.2


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
    """有符号持仓：多正空负。"""
    raw = pos.get("szi") or pos.get("size")
    return float(raw) if raw is not None else 0.0


def _reduce_close_is_buy(pos: dict) -> bool:
    """减仓/平仓方向：空头须买入平仓；多头须卖出平仓。"""
    return _position_szi(pos) < 0


def _market_price_hint(mid: float, is_buy: bool) -> float:
    """市价单价格提示（激进价）：买略高于 mid，卖略低于 mid。"""
    if is_buy:
        return round(mid * 1.001, 2) if mid > 1 else round(mid * 1.001, 6)
    return round(mid * 0.999, 2) if mid > 1 else round(mid * 0.999, 6)


def _market_size_rounded(
    client, symbol: str, mid: float, is_buy: bool, min_notional_usd: float = MIN_NOTIONAL
) -> tuple[float, float]:
    """市价单数量与价格，按标的精度舍入，保证名义价值 >= min_notional_usd（交易所单笔最低约 $10）。"""
    price_hint = _market_price_hint(mid, is_buy)
    need = max(10.0, min_notional_usd)
    size = max(0.001, (need + 1) / max(price_hint, 0.01))
    sz_decimals = client.get_sz_decimals(symbol)
    actual_px = client.round_order_price(symbol, price_hint)
    tick = 10 ** (-sz_decimals)
    size = max(size, need / max(actual_px, 1e-8))
    size = round(size, sz_decimals)
    if size < tick:
        size = tick
    if size * actual_px < need:
        size = round(need / actual_px, sz_decimals)
        if size < tick:
            size = tick
        if size * actual_px < need:
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
        # 开仓名义要够大，否则「减半减仓」会低于 $10 被交易所拒绝
        size, price_hint = _market_size_rounded(
            client, default_symbol, mid, is_buy, min_notional_usd=MIN_OPEN_NOTIONAL_FOR_PARTIAL
        )

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
        # 必须用真实持仓方向，不能只用开仓时的 is_buy（与 not is_buy 在边界/重试下易错位）
        close_side_buy = _reduce_close_is_buy(pos)
        px_close = client.round_order_price(default_symbol, _market_price_hint(mid, close_side_buy))
        sz_dec = client.get_sz_decimals(default_symbol)
        tick = 10 ** (-sz_dec)
        min_sz_for_10 = MIN_NOTIONAL / max(px_close, 1e-8)
        min_sz_for_10 = round(min_sz_for_10, sz_dec)
        if min_sz_for_10 < tick:
            min_sz_for_10 = tick

        # 3. 减仓：仅当「减半」与「剩余」两笔都能满足 $10 名义；否则一次满仓平掉
        half_sz = round(open_sz * 0.5, sz_dec)
        if half_sz < tick:
            half_sz = tick
        remainder_after_half = open_sz - half_sz
        rem_notional = remainder_after_half * px_close
        can_partial = (
            half_sz >= min_sz_for_10
            and remainder_after_half >= tick
            and rem_notional >= MIN_NOTIONAL
            and half_sz < open_sz - tick * 0.5
        )
        if can_partial:
            reduce_sz = max(min_sz_for_10, min(half_sz, open_sz - tick))
            reduce_sz = min(reduce_sz, open_sz - tick)
            if reduce_sz <= 0 or open_sz - reduce_sz < tick or (open_sz - reduce_sz) * px_close < MIN_NOTIONAL:
                can_partial = False
        if can_partial:
            reduce_resp = _place_market_order(
                client,
                default_symbol,
                close_side_buy,
                reduce_sz,
                _market_price_hint(mid, close_side_buy),
                reduce_only=True,
            )
            _assert_order_ok(reduce_resp)
            _wait_settle()
            state2 = client.clearinghouse_state()
            pos2 = _get_position(state2, default_symbol)
            assert pos2 is not None, "减仓后应有持仓"
            remaining_sz = _position_size(pos2)
            assert remaining_sz < open_sz, "部分减仓后持仓应缩小"
            close_side_buy = _reduce_close_is_buy(pos2)
        else:
            remaining_sz = open_sz

        # 4. 平仓（方向再次按当前持仓）
        _wait_settle()
        state3 = client.clearinghouse_state()
        pos3 = _get_position(state3, default_symbol)
        if pos3 is None or _position_size(pos3) < tick:
            return
        remaining_sz = _position_size(pos3)
        close_side_buy = _reduce_close_is_buy(pos3)
        px_out = client.round_order_price(default_symbol, _market_price_hint(mid, close_side_buy))
        # 剩余名义不足 $10 时只能一次性平掉（整仓 reduce_only）
        close_sz = round(remaining_sz, sz_dec)
        if close_sz * px_out < MIN_NOTIONAL:
            close_sz = remaining_sz
        close_resp = _place_market_order(
            client,
            default_symbol,
            close_side_buy,
            close_sz,
            _market_price_hint(mid, close_side_buy),
            reduce_only=True,
        )
        _assert_order_ok(close_resp)
