"""
钱包 fixture 辅助：从配置或环境变量加载地址与私钥。
由 conftest 通过 client fixture 使用，可扩展为多钱包测试。
"""
from typing import Optional

from config.loader import get_config


def get_wallet_address(override: Optional[str] = None) -> str:
    """获取钱包地址，可选覆盖值；未配置时抛出 ValueError。"""
    addr = override or get_config().get("wallet", {}).get("address")
    if not addr:
        raise ValueError("未配置 wallet.address，请在 config 或 HYPERLIQUID_WALLET_ADDRESS 中设置")
    return addr.lower() if addr.startswith("0x") else "0x" + addr


def get_private_key(override: Optional[str] = None) -> str:
    """获取私钥，可选覆盖值；未配置时抛出 ValueError。"""
    pk = override or get_config().get("wallet", {}).get("private_key")
    if not pk:
        raise ValueError("未配置 wallet.private_key，请在 config 或 HYPERLIQUID_PRIVATE_KEY 中设置")
    return pk
