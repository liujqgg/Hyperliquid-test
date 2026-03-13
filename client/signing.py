"""
Hyperliquid 交易所 L1 动作签名（不依赖 SDK）。
实现 phantom agent 构造：msgpack(action) + nonce + vault -> keccak -> EIP-712 Agent。
"""
import time
from decimal import Decimal
from typing import Any, Optional

import msgpack
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak, to_hex

# -----------------------------------------------------------------------------
# 线格式辅助：价格/数量为字符串；msgpack 键顺序敏感
# -----------------------------------------------------------------------------


def _float_to_wire(x: float) -> str:
    """将浮点数格式化为 API 要求的字符串（最多 8 位小数、无多余尾零）。先四舍五入到 8 位小数，避免浮点精度导致报错。"""
    x_8 = round(x, 8)
    rounded = f"{x_8:.8f}"
    if rounded == "-0":
        rounded = "0"
    normalized = Decimal(rounded).normalize()
    return f"{normalized:f}"


def _address_to_bytes(address: str) -> bytes:
    """
    将以太坊地址字符串（如 "0xabc123..."）转换为 20 字节的 bytes 格式。
    - 支持有无 "0x" 前缀，忽略大小写。
    - 用于 Phantom agent 签名原始字节拼接。
    """
    addr = address.lower()
    if addr.startswith("0x"):
        addr = addr[2:]
    return bytes.fromhex(addr)


def action_hash(
    action: dict,
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
) -> bytes:
    """
    生成 Phantom agent 所需的哈希（connectionId hash）。
    拼接顺序如下：
      1. msgpack(action)      - action 字典用 msgpack 序列化，保证顺序一致。
      2. nonce (8字节大端)    - 防重放攻击，8字节（uint64）大端序。
      3. vault marker         - 是否带 vault address，\x00 表示无，\x01 后跟 20字节 address。
      4. expires (可选)       - \x00 后接 8字节大端的 expires_after（uint64），表示过期时间戳。
    拼接后整体 keccak(256) 哈希，作为连接 ID。
    """
    data = msgpack.packb(action)  # 1. msgpack 序列化 action
    data += nonce.to_bytes(8, "big")  # 2. 加 nonce，8字节大端
    if vault_address is None:
        data += b"\x00"  # 3a. 没有 vault，用 \x00 标记
    else:
        data += b"\x01"  # 3b. 有 vault, \x01 + 20字节地址
        data += _address_to_bytes(vault_address)
    if expires_after is not None:
        data += b"\x00"  # 4. expires 字段出现时，加前缀 \x00
        data += expires_after.to_bytes(8, "big")  # 后面拼接 8字节大端的 expires
    return keccak(data)  # 返回 keccak256 哈希结果


def construct_phantom_agent(connection_id_hash: bytes, is_mainnet: bool) -> dict:
    """
    构造 Phantom agent 的参数字典。
    - source: "a" 表示主网（mainnet），"b" 表示测试网（testnet）。
    - connectionId: 由 action_hash 哈希得到的 bytes32。
    """
    return {
        "source": "a" if is_mainnet else "b",  # 主网用 "a"，测试网用 "b"
        "connectionId": connection_id_hash,     # 连接ID哈希，用于身份绑定
    }


def _eip712_payload(phantom_agent: dict) -> dict:
    return {
        "domain": {
            "chainId": 1337,
            "name": "Exchange",
            "verifyingContract": "0x0000000000000000000000000000000000000000",
            "version": "1",
        },
        "types": {
            "Agent": [
                {"name": "source", "type": "string"},
                {"name": "connectionId", "type": "bytes32"},
            ],
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
        },
        "primaryType": "Agent",
        "message": phantom_agent,
    }


def sign_l1_action(
    wallet: Account,
    action: dict,
    vault_address: Optional[str],
    nonce: int,
    expires_after: Optional[int],
    is_mainnet: bool,
) -> dict:
    """为 exchange 接口签发 L1 动作（下单、撤单等）。"""
    h = action_hash(action, vault_address, nonce, expires_after)
    phantom = construct_phantom_agent(h, is_mainnet)
    payload = _eip712_payload(phantom)
    structured = encode_typed_data(full_message=payload)
    signed = wallet.sign_message(structured)
    return {"r": to_hex(signed["r"]), "s": to_hex(signed["s"]), "v": signed["v"]}


def get_timestamp_ms() -> int:
    return int(time.time() * 1000)


# -----------------------------------------------------------------------------
# 构造线格式 action（键顺序影响 msgpack 序列化）
# -----------------------------------------------------------------------------


def build_order_action(
    asset: int,
    is_buy: bool,
    price: str,
    size: str,
    reduce_only: bool = False,
    tif: str = "Gtc",
    cloid: Optional[str] = None,
    grouping: str = "na",
) -> dict:
    """构造下单用的 action 字典，价格与数量必须为字符串。
    Hyperliquid 仅支持 limit（tif: Gtc|Ioc|Alo|FrontendMarket）与 trigger；
    无单独市价单类型，市价行为 = limit + FrontendMarket（或 Ioc）+ 激进价格。
    """
    order: dict = {
        "a": asset,
        "b": is_buy,
        "p": price,
        "s": size,
        "r": reduce_only,
        "t": {"limit": {"tif": tif}},
    }
    if cloid is not None:
        order["c"] = cloid
    return {"type": "order", "orders": [order], "grouping": grouping}


def build_cancel_action(asset: int, oid: int) -> dict:
    return {"type": "cancel", "cancels": [{"a": asset, "o": oid}]}


def build_cancel_by_cloid_action(asset: int, cloid: str) -> dict:
    return {"type": "cancelByCloid", "cancels": [{"asset": asset, "cloid": cloid}]}


def price_size_to_wire(price: float, size: float) -> tuple[str, str]:
    """将价格、数量转为下单线格式的 (price_str, size_str)。"""
    return _float_to_wire(price), _float_to_wire(size)
