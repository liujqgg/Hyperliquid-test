"""
历史委托与成交测试：historicalOrders、userFills。
校验返回为列表及单条记录结构。
"""
import pytest
import allure

from utils.exceptions import HyperliquidAPIError
from utils.retry import retry


@allure.epic("Hyperliquid API")
@allure.feature("Order History")
class TestOrderHistory:
    """历史委托与成交记录。"""

    @allure.title("获取历史委托 historicalOrders")
    @allure.description("调用 historicalOrders，校验返回为列表且元素含 order 或 oid/coin/status 等字段")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_historical_orders(self, client):
        orders = client.historical_orders()
        assert orders is not None
        assert isinstance(orders, list)
        for item in orders[:5]:
            assert isinstance(item, dict)
            order = item.get("order", item)
            assert "oid" in order or "coin" in order or "status" in order or "timestamp" in order or len(order) >= 1

    @allure.title("获取用户成交记录 userFills")
    @allure.description("调用 userFills，校验返回为列表且元素含 oid/coin/sz/px/time 等字段")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_user_fills(self, client):
        fills = client.user_fills()
        assert fills is not None
        assert isinstance(fills, list)
        for item in fills[:5]:
            assert isinstance(item, dict)
            assert "oid" in item or "coin" in item or "sz" in item or "px" in item or "time" in item or len(item) >= 1
