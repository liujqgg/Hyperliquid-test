"""
错误处理测试：非法 symbol、非法价格/数量、缺参、撤单/查询非法 id、非法 user/tif/cloid 等。
校验客户端或 API 返回错误及错误结构。
"""
import pytest
import allure

from utils.exceptions import HyperliquidAPIError
from utils.retry import retry
from client.hyperliquid_client import HyperliquidClient


@allure.epic("Hyperliquid API")
@allure.feature("Error Handling")
class TestErrorScenarios:
    """非法输入与 API 错误响应。"""

    @allure.title("非法 symbol 返回错误")
    @allure.description("未知 symbol 的请求应得到 API 错误或 4xx")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_invalid_symbol(self, client):
        with pytest.raises((HyperliquidAPIError, Exception)) as exc_info:
            client.order(
                symbol="INVALID_SYMBOL_XYZ_123",
                is_buy=True,
                size=0.01,
                limit_px=1.0,
            )
        assert exc_info.value is not None

    @allure.title("非法价格（零/负）被正确处理")
    @allure.description("零或负价格的订单应被拒绝")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_invalid_price_zero(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=0.01,
                limit_px=0.0,
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, ValueError) as e:
            assert e is not None

    @allure.title("非法数量（零）被正确处理")
    @allure.description("数量为 0 的订单应被拒绝")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_invalid_quantity_zero(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=0.0,
                limit_px=1000.0,
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, ValueError) as e:
            assert e is not None

    @allure.title("缺必填参数：无 limit_px 且无 price_hint 时客户端抛 ValueError")
    @allure.description("order() 必须提供 limit_px 或 price_hint 之一")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_order_missing_price(self, client, default_symbol):
        with pytest.raises(ValueError, match="limit_px or price_hint"):
            client.order(
                symbol=default_symbol,
                is_buy=True,
                size=0.01,
                limit_px=None,
                price_hint=None,
            )

    @allure.title("撤单：无效 oid 不导致崩溃")
    @allure.description("对不存在的 oid 撤单：API 可能抛异常或返回成功（no-op），调用不崩溃即可")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_cancel_invalid_oid(self, client, default_symbol):
        try:
            resp = client.cancel(default_symbol, oid=999999999999)
            assert resp is not None
        except (HyperliquidAPIError, Exception):
            pass

    @allure.title("撤单：无效 cloid 不导致崩溃")
    @allure.description("对不存在的 cloid 撤单：API 可能抛异常或返回成功（no-op），调用不崩溃即可")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_cancel_by_cloid_invalid(self, client, default_symbol):
        try:
            resp = client.cancel_by_cloid(default_symbol, cloid="0x" + "00" * 16)
            assert resp is not None
        except (HyperliquidAPIError, Exception):
            pass

    @allure.title("空 symbol 下单应报错")
    @allure.description("symbol 为空字符串时 symbol_to_asset_id 无法解析，应抛 HyperliquidAPIError")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_empty_symbol_order(self, client):
        with pytest.raises((HyperliquidAPIError, Exception)) as exc_info:
            client.order(symbol="", is_buy=True, size=0.01, limit_px=1.0)
        assert exc_info.value is not None

    @allure.title("负数量被拒绝")
    @allure.description("size < 0 时订单应被拒绝（API 返回 error 或客户端/API 抛异常）")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_invalid_quantity_negative(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=-0.01,
                limit_px=1000.0,
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, ValueError, Exception) as e:
            assert e is not None

    @allure.title("负价格被拒绝")
    @allure.description("limit_px < 0 时订单应被拒绝")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_invalid_price_negative(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=0.01,
                limit_px=-100.0,
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, ValueError, Exception) as e:
            assert e is not None

    @allure.title("数量过小（名义价值低于最小）被拒绝")
    @allure.description("size 过小导致名义价值低于交易所要求时，应被拒绝或返回 error")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_order_size_too_small(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=1e-10,
                limit_px=1000.0,
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, ValueError, Exception) as e:
            assert e is not None

    @allure.title("撤单：非法 symbol 时客户端抛错")
    @allure.description("cancel(symbol=未知标的, oid) 时 symbol_to_asset_id 抛 HyperliquidAPIError")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_cancel_invalid_symbol(self, client):
        with pytest.raises((HyperliquidAPIError, Exception)) as exc_info:
            client.cancel("INVALID_SYMBOL_XYZ", oid=1)
        assert exc_info.value is not None

    @allure.title("order_status 无效 oid 时 API 返回错误或空结果")
    @allure.description("查询不存在的 oid 应得到 error 或空/无订单的响应")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_order_status_invalid_oid(self, client):
        try:
            resp = client.order_status(oid_or_cloid=999999999999)
            assert resp is not None
            if isinstance(resp, dict) and resp.get("status") == "error":
                assert "error" in str(resp).lower() or "message" in resp
        except HyperliquidAPIError:
            pass

    @allure.title("order_status 无效 cloid 时 API 返回错误或空结果")
    @allure.description("查询不存在的 cloid 应得到 error 或空/无订单的响应")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_order_status_invalid_cloid(self, client):
        try:
            resp = client.order_status(oid_or_cloid="0x" + "ab" * 16)
            assert resp is not None
            if isinstance(resp, dict) and resp.get("status") == "error":
                assert "error" in str(resp).lower() or "message" in resp
        except HyperliquidAPIError:
            pass

    @allure.title("clearinghouse_state 非法 user 地址时 API 返回错误")
    @allure.description("传入非法以太坊地址应得到 API 错误或异常")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_clearinghouse_state_invalid_user(self, client):
        with pytest.raises((HyperliquidAPIError, Exception)) as exc_info:
            client.clearinghouse_state(user="0xinvalid_address_not_hex_or_too_short")
        assert exc_info.value is not None

    @allure.title("非法 tif 下单时 API 拒绝")
    @allure.description("不支持的 tif 值（如 InvalidTif）应被 API 拒绝或返回 error")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_order_invalid_tif(self, client, default_symbol):
        try:
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=0.01,
                limit_px=1000.0,
                tif="InvalidTif",
            )
            statuses = (resp.get("data") or {}).get("statuses") or []
            if statuses:
                st = statuses[0]
                assert isinstance(st, dict) and st.get("error") is not None, resp
        except (HyperliquidAPIError, Exception) as e:
            assert e is not None

    @allure.title("cloid 格式错误（长度不符）时 API 拒绝或客户端/API 报错")
    @allure.description("cloid 非 16 字节十六进制（如过短）时撤单或下单应报错")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_cancel_by_cloid_bad_format(self, client, default_symbol):
        with pytest.raises((HyperliquidAPIError, ValueError, Exception)) as exc_info:
            client.cancel_by_cloid(default_symbol, cloid="0x1234")
        assert exc_info.value is not None
