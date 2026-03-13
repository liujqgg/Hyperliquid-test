"""
Pytest 公共 fixture：client、config、日志。各测试相互隔离（无共享状态）。
"""
import pytest
import uuid

from client.hyperliquid_client import HyperliquidClient
from config.loader import get_config, reset_config
from utils.log import setup_logging, get_api_logger


def pytest_configure(config):
    setup_logging()


@pytest.fixture(autouse=True)
def log_test_name(request):
    """每个用例开始时在日志文件中记录测试名称与节点 id。"""
    api_log = get_api_logger()
    api_log.info("========== TEST %s ==========", request.node.nodeid)
    yield
    api_log.info("---------- END %s ----------", request.node.nodeid)


@pytest.fixture(scope="session")
def config():
    """会话级配置。"""
    return get_config()


@pytest.fixture(scope="session")
def client(config):
    """会话级 API 客户端，所有测试共用一个 client。"""
    return HyperliquidClient()


@pytest.fixture
def unique_cloid():
    """每个用例唯一的客户订单 id（16 字节十六进制）。"""
    raw = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    return "0x" + raw[:32]


@pytest.fixture
def default_symbol(config):
    """默认测试标的。"""
    return config.get("test", {}).get("default_symbol", "ETH")


@pytest.fixture(autouse=True)
def reset_config_cache():
    """需要时可保证配置为最新（例如环境变量变更后）。"""
    yield
    # reset_config()
    # 若希望每次测试都重新加载配置，可在此取消注释 reset_config()
