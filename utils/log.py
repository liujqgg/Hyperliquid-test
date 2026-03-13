"""
测试与客户端使用的结构化日志。支持控制台与文件，并将测试/请求/响应写入日志文件。
"""
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from config.loader import get_config

# 用于记录请求/响应与测试动作的专用 logger 名称
API_LOG_NAME = "hyperliquid.test.api"

# 全局 file handler，供 setup_logging 添加后由 get_api_logger 使用
_file_handler: Optional[logging.FileHandler] = None


def setup_logging(level: Optional[str] = None, format_string: Optional[str] = None) -> None:
    global _file_handler
    cfg = get_config()
    log_cfg = cfg.get("logging", {})
    lvl = level or log_cfg.get("level", "INFO")
    fmt = format_string or log_cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    logging.basicConfig(
        level=getattr(logging, lvl.upper(), logging.INFO),
        format=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )
    # 请求/响应与测试动作写入日志文件
    log_dir = Path(log_cfg.get("dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / log_cfg.get("file", "test_run.log")
    _file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    _file_handler.setLevel(logging.INFO)
    _file_handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    api_logger = logging.getLogger(API_LOG_NAME)
    api_logger.setLevel(logging.INFO)
    api_logger.addHandler(_file_handler)
    api_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def get_api_logger() -> logging.Logger:
    """返回用于记录测试动作、请求与响应的 logger，会写入日志文件。"""
    return logging.getLogger(API_LOG_NAME)
