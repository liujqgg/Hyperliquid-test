"""
Hyperliquid API 客户端（无 SDK）。Info 只读接口与 Exchange 需签名接口。
"""
import json
import math
from typing import Any, Optional

import requests
from eth_account import Account

from client.signing import (
    build_cancel_action,
    build_cancel_by_cloid_action,
    build_order_action,
    get_timestamp_ms,
    price_size_to_wire,
    sign_l1_action,
)
from config.loader import get_config
from utils.exceptions import HyperliquidAPIError
from utils.log import get_logger, get_api_logger

logger = get_logger(__name__)
api_log = get_api_logger()


def _safe_json(obj: Any) -> str:
    """将对象序列化为 JSON 字符串用于日志。"""
    if obj is None:
        return "null"
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return repr(obj)


class HyperliquidClient:
    """Hyperliquid 测试网/主网 API 客户端（Info + Exchange）。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        wallet_address: Optional[str] = None,
        private_key: Optional[str] = None,
        timeout: int = 30,
        is_mainnet: Optional[bool] = None,
    ):
        cfg = get_config()
        api = cfg.get("api", {})
        wallet = cfg.get("wallet", {})
        self.base_url = (base_url or api.get("base_url", "")).rstrip("/")
        self.info_path = api.get("info_path", "/info")
        self.exchange_path = api.get("exchange_path", "/exchange")
        self.timeout = timeout or api.get("timeout_seconds", 30)
        self._is_mainnet = is_mainnet if is_mainnet is not None else "testnet" not in self.base_url.lower()
        addr = wallet_address or wallet.get("address")
        pk = private_key or wallet.get("private_key")
        if not addr or not pk:
            raise ValueError("wallet address and private_key are required (config or args)")
        self.wallet_address = addr.lower()
        if not self.wallet_address.startswith("0x"):
            self.wallet_address = "0x" + self.wallet_address
        self._account = Account.from_key(pk)
        self._meta: Optional[dict] = None

    @property
    def is_mainnet(self) -> bool:
        return self._is_mainnet

    def _info_url(self) -> str:
        return self.base_url + self.info_path

    def _exchange_url(self) -> str:
        return self.base_url + self.exchange_path

    def _user(self, user: Optional[str] = None) -> str:
        """返回归一化后的用户地址（小写、0x 前缀）。"""
        u = (user or self.wallet_address).lower()
        return u if u.startswith("0x") else "0x" + u

    def _ensure_meta(self) -> None:
        """确保已加载并缓存 meta。"""
        if self._meta is None:
            self._meta = self.meta_and_asset_ctxs()

    def _get_universe(self) -> list:
        """从缓存的 meta 解析出 universe 列表（API 可能返回 dict 或 list 形态）。"""
        self._ensure_meta()
        raw = self._meta
        if isinstance(raw, list):
            if not raw:
                return []
            first = raw[0]
            if isinstance(first, list):
                return first
            if isinstance(first, dict):
                return first.get("universe", [])
            return []
        if isinstance(raw, dict):
            return raw.get("universe", [])
        return []

    # ---------- Info 只读接口 ----------

    def _post_info(self, payload: dict) -> Any:
        """向 info 接口 POST，无需签名。"""
        url = self._info_url()
        logger.debug("POST %s %s", url, payload)
        api_log.info("REQUEST  POST %s  body=%s", url, _safe_json(payload))
        r = requests.post(url, json=payload, timeout=self.timeout)
        data = r.json() if r.content else None
        api_log.info("RESPONSE POST %s  status=%s  body=%s", url, r.status_code, _safe_json(data))
        r.raise_for_status()
        if isinstance(data, dict) and data.get("status") == "error":
            raise HyperliquidAPIError(data.get("message", "info error"), response=data)
        return data

    def meta_and_asset_ctxs(self) -> dict:
        """获取 meta 与资产上下文，universe 下标即永续资产 id。"""
        return self._post_info({"type": "metaAndAssetCtxs"})

    def clearinghouse_state(self, user: Optional[str] = None) -> dict:
        """查询用户清算所状态（余额、持仓）。"""
        return self._post_info({"type": "clearinghouseState", "user": self._user(user)})

    def open_orders(self, user: Optional[str] = None) -> list:
        """查询用户当前挂单。"""
        return self._post_info({"type": "openOrders", "user": self._user(user)})

    def order_status(self, oid_or_cloid: int | str, user: Optional[str] = None) -> dict:
        """按订单 id(oid) 或客户订单 id(cloid) 查询订单状态。"""
        return self._post_info({"type": "orderStatus", "user": self._user(user), "oid": oid_or_cloid})

    def all_mids(self) -> dict:
        """获取各币种中间价。"""
        return self._post_info({"type": "allMids"})

    def historical_orders(self, user: Optional[str] = None) -> list:
        """获取用户历史委托（最多约 2000 条，含已成交/已撤/拒绝等）。"""
        return self._post_info({"type": "historicalOrders", "user": self._user(user)})

    def user_fills(self, user: Optional[str] = None, aggregate_by_time: bool = False) -> list:
        """获取用户成交记录（最多约 2000 条）。aggregate_by_time 为 True 时按时间合并部分成交。"""
        payload: dict = {"type": "userFills", "user": self._user(user)}
        if aggregate_by_time:
            payload["aggregateByTime"] = True
        return self._post_info(payload)

    def symbol_to_asset_id(self, symbol: str) -> int:
        """将永续合约符号（如 ETH）解析为资产索引。"""
        for i, u in enumerate(self._get_universe()):
            name = u.get("name") if isinstance(u, dict) else u
            if name == symbol:
                return i
        raise HyperliquidAPIError(f"Unknown symbol: {symbol}", response={"universe": self._get_universe()})

    def get_sz_decimals(self, symbol: str) -> int:
        """获取标的的数量精度（szDecimals），用于下单时四舍五入 size。"""
        for u in self._get_universe():
            name = u.get("name") if isinstance(u, dict) else u
            if name == symbol and isinstance(u, dict) and "szDecimals" in u:
                return int(u["szDecimals"])
        return 5

    def _round_price_perp(self, price: float, sz_decimals: int) -> float:
        """永续价格精度：5 位有效数字，小数位不超过 (6 - szDecimals)。"""
        if price == 0:
            return 0.0
        max_decimals = max(0, 6 - sz_decimals)
        magnitude = 10 ** (math.floor(math.log10(abs(price))) - 4)
        return round(round(price / magnitude) * magnitude, max_decimals)

    def round_order_price(self, symbol: str, price: float) -> float:
        """返回该标的下单时使用的价格（与 order() 内舍入一致）。"""
        return self._round_price_perp(price, self.get_sz_decimals(symbol))

    # ---------- Exchange 需签名接口 ----------

    def _post_exchange(self, action: dict, vault_address: Optional[str] = None, expires_after: Optional[int] = None) -> Any:
        nonce = get_timestamp_ms()
        sig = sign_l1_action(
            self._account,
            action,
            vault_address,
            nonce,
            expires_after,
            self._is_mainnet,
        )
        body = {
            "action": action,
            "nonce": nonce,
            "signature": sig,
        }
        if vault_address:
            body["vaultAddress"] = vault_address.lower()
        if expires_after is not None:
            body["expiresAfter"] = expires_after
        url = self._exchange_url()
        logger.debug("POST %s action=%s", url, action.get("type"))
        api_log.info("REQUEST  POST %s  body=%s", url, _safe_json(body))
        r = requests.post(url, json=body, timeout=self.timeout)
        data = r.json() if r.content else None
        api_log.info("RESPONSE POST %s  status=%s  body=%s", url, r.status_code, _safe_json(data))
        r.raise_for_status()
        if data.get("status") != "ok":
            raise HyperliquidAPIError(data.get("response", data), response=data)
        return data.get("response", data)

    def order(
        self,
        symbol: str,
        is_buy: bool,
        size: float,
        limit_px: Optional[float] = None,
        reduce_only: bool = False,
        tif: str = "Gtc",
        cloid: Optional[str] = None,
        grouping: str = "na",
        price_hint: Optional[float] = None,
    ) -> dict:
        """下限价单或市价单（市价单传 price_hint），返回交易所响应（如 statuses：resting/filled/error）。"""
        px = price_hint if price_hint is not None else limit_px
        if px is None:
            raise ValueError("limit_px or price_hint is required")
        asset = self.symbol_to_asset_id(symbol)
        sz_decimals = self.get_sz_decimals(symbol)
        size = round(size, sz_decimals)
        px = self._round_price_perp(px, sz_decimals)
        p_str, s_str = price_size_to_wire(px, size)
        action = build_order_action(
            asset=asset,
            is_buy=is_buy,
            price=p_str,
            size=s_str,
            reduce_only=reduce_only,
            tif=tif,
            cloid=cloid,
            grouping=grouping,
        )
        return self._post_exchange(action)

    def cancel(self, symbol: str, oid: int) -> dict:
        """按订单 id 撤单。"""
        asset = self.symbol_to_asset_id(symbol)
        action = build_cancel_action(asset=asset, oid=oid)
        return self._post_exchange(action)

    def cancel_by_cloid(self, symbol: str, cloid: str) -> dict:
        """按客户订单 id 撤单。"""
        asset = self.symbol_to_asset_id(symbol)
        action = build_cancel_by_cloid_action(asset=asset, cloid=cloid)
        return self._post_exchange(action)

