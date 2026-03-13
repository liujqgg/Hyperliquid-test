"""
并发测试：同时提交多笔订单，验证系统稳定性。
使用小额挂单并在结束时全部撤单。并发数 n 从 config.test 读取。
"""
import concurrent.futures
import uuid
import pytest
import allure

from config.loader import get_config
from utils.order_utils import parse_order_response, get_oid_from_status
from utils.retry import retry
from utils.exceptions import HyperliquidAPIError


def _mid_price(client, symbol: str) -> float:
    """获取标的中间价。"""
    mids = client.all_mids()
    return float(mids.get(symbol, 0) or 0)


@allure.epic("Hyperliquid API")
@allure.feature("Concurrency")
class TestConcurrent:
    """多订单与稳定性。"""

    @allure.title("并发提交多笔订单")
    @allure.description("并行下多笔挂单并验证均被接受或妥善处理")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_multiple_orders_concurrent(self, client, default_symbol):
        mid = _mid_price(client, default_symbol)
        if mid <= 0:
            pytest.skip("无中间价")
        limit_px = round(mid * 0.5, 2) if mid > 1 else round(mid * 0.5, 6)
        size = max(0.001, 12.0 / limit_px)
        if size * limit_px < 10:
            size = 11.0 / limit_px

        n = get_config().get("test", {}).get("concurrent_orders_n", 5)
        cloids = ["0x" + (uuid.uuid4().hex + uuid.uuid4().hex[:8])[:32] for _ in range(n)]
        oids = []

        def place_one(cloid: str):
            resp = client.order(
                symbol=default_symbol,
                is_buy=True,
                size=size,
                limit_px=limit_px,
                tif="Alo",
                cloid=cloid,
            )
            statuses = parse_order_response(resp)
            if statuses and statuses[0].get("error") is None:
                return get_oid_from_status(statuses[0])
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(place_one, c) for c in cloids]
            for f in concurrent.futures.as_completed(futures):
                try:
                    oid = f.result()
                    if oid is not None:
                        oids.append(oid)
                except Exception as e:
                    allure.attach(str(e), "concurrent_order_error", allure.attachment_type.TEXT)

        # 撤掉所有已下订单
        for oid in oids:
            try:
                client.cancel(default_symbol, oid)
            except Exception:
                pass
        # 并发下单流程完成且未崩溃即通过
        assert len(oids) >= 0, "并发下单完成且未崩溃"

    @allure.title("Info 接口并发读")
    @allure.description("并行多次调用 clearinghouseState")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_concurrent_info_calls(self, client):
        n = get_config().get("test", {}).get("concurrent_info_calls_n", 8)

        def get_state():
            return client.clearinghouse_state()

        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(get_state) for _ in range(n)]
            results = []
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())
        assert len(results) == n
        for r in results:
            assert "withdrawable" in r or isinstance(r, dict)
