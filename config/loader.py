"""
Load and merge configuration from config.yaml, config.local.yaml, and environment.
"""
from pathlib import Path
import os
import logging

import yaml

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent
CONFIG_FILE = CONFIG_DIR / "config.yaml"
CONFIG_EXAMPLE_FILE = CONFIG_DIR / "config.example.yaml"
CONFIG_LOCAL_FILE = CONFIG_DIR / "config.local.yaml"

ENV_PREFIX = "HYPERLIQUID_"
ENV_MAP = {
    "HYPERLIQUID_API_BASE_URL": ("api", "base_url"),
    "HYPERLIQUID_WALLET_ADDRESS": ("wallet", "address"),
    "HYPERLIQUID_PRIVATE_KEY": ("wallet", "private_key"),
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _set_nested(cfg: dict, path: tuple, value: str) -> None:
    d = cfg
    for key in path[:-1]:
        if key not in d:
            d[key] = {}
        d[key] = dict(d[key])
        d = d[key]
    d[path[-1]] = value


def load_config() -> dict:
    """Load config from files and environment. Local and env override base.
    config.yaml 不提交仓库时，若无该文件则从 config.example.yaml 加载默认模板。"""
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    elif CONFIG_EXAMPLE_FILE.exists():
        with open(CONFIG_EXAMPLE_FILE, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    if CONFIG_LOCAL_FILE.exists():
        with open(CONFIG_LOCAL_FILE, "r", encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        config = _deep_merge(config, local)
    for env_key, path in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val is not None and val.strip():
            _set_nested(config, path, val.strip())
            logger.debug("Config override from env %s", env_key)
    return config


def get_config() -> dict:
    """Cached config singleton."""
    if not hasattr(get_config, "_config"):
        get_config._config = load_config()
    return get_config._config


def reset_config() -> None:
    """Clear cached config (e.g. for tests)."""
    if hasattr(get_config, "_config"):
        del get_config._config
