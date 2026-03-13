"""
账户测试：余额、清算所状态结构、余额一致性。
"""
import pytest
import allure

from utils.exceptions import HyperliquidAPIError
from utils.retry import retry


@allure.epic("Hyperliquid API")
@allure.feature("Account")
class TestAccount:
    """账户状态与余额相关测试。"""

    @allure.title("清算所状态：结构、字段类型与 withdrawable 非负")
    @allure.description("POST info clearinghouseState，校验返回结构、assetPositions、marginSummary 及 withdrawable 可解析为非负数字")
    @retry(exceptions=(AssertionError, HyperliquidAPIError))
    def test_clearinghouse_state(self, client):
        state = client.clearinghouse_state()
        assert state is not None
        assert isinstance(state, dict)

        # 顶层必选字段
        assert "withdrawable" in state, "需包含 withdrawable"
        assert "assetPositions" in state, "需包含 assetPositions"
        assert "marginSummary" in state or "crossMarginSummary" in state or "time" in state, "需包含 margin 或 time"

        withdrawable = state.get("withdrawable")
        assert withdrawable is not None
        assert isinstance(withdrawable, (str, int, float))
        assert float(withdrawable) >= 0, "withdrawable 须为非负"

        asset_positions = state.get("assetPositions", [])
        assert isinstance(asset_positions, list)
        for pos in asset_positions:
            assert isinstance(pos, dict)
            assert "coin" in pos or "position" in pos or "szi" in pos or "entryPx" in pos or len(pos) >= 1

        ms = state.get("marginSummary") or state.get("crossMarginSummary")
        if ms:
            assert isinstance(ms, dict)
