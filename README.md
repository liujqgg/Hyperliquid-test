# Hyperliquid Testnet API 自动化测试框架

Python 3.11 实现的 Hyperliquid Testnet API 自动化测试框架，使用 **pytest** 与 **Allure** 报告，**不依赖** Hyperliquid 官方/社区 SDK，直接调用 REST API 并自行实现 L1 签名。

---

## 功能概览

| 模块       | 内容 |
|------------|------|
| **账户**   | 余额查询、返回结构校验、withdrawable 与 assetPositions |
| **限价单** | 下单（限价远离市价 50%）、查询、撤单 |
| **市价单** | 市价开仓/减仓/平仓与持仓查询 |
| **历史委托** | historicalOrders、userFills 结构与条数校验 |
| **错误**   | 非法 symbol/价格/数量、缺参、撤单与查询非法 id、非法 user/tif/cloid 等 |
| **并发**   | 多订单并发提交、Info 接口并发读（笔数由 config 配置） |

## 技术栈

| 用途     | 技术 |
|----------|------|
| 测试框架 | pytest |
| 报告     | allure-pytest |
| 配置     | YAML + 环境变量（`config/loader.py` 合并） |
| 签名     | 自实现（msgpack + EIP-712 phantom agent，无 SDK） |

## 项目结构

```
config/
├── config.yaml          # 本地配置（gitignore，不提交）；可从 example 复制
├── config.example.yaml  # 仓库内模板，提交；无 config.yaml 时 loader 会用它
└── loader.py            # 配置加载与合并（本地 + 环境变量）
client/
├── signing.py           # L1 签名（phantom agent）
└── hyperliquid_client.py # Info / Exchange 封装，historicalOrders、userFills、价格与数量精度
utils/
├── exceptions.py        # 统一异常（HyperliquidAPIError）
├── log.py               # 控制台与文件日志，API 请求/响应写入文件
├── retry.py             # 重试装饰器（times/delay 未传时从 config.test 读取）
├── wait.py              # 轮询等待 wait_until（poll_timeout_seconds、poll_interval_ms）
└── order_utils.py       # 订单/撤单响应解析
tests/
├── test_account.py      # 账户测试
├── test_limit_orders.py # 限价单（下单/查询/撤单）
├── test_market_orders.py # 市价单（Ioc）
├── test_order_history.py # 历史委托与成交（historicalOrders、userFills）
├── test_errors.py       # 错误场景
└── test_concurrent.py   # 并发
scripts/
└── fetch_order_history.py # 命令行拉取历史委托/成交并保存 JSON
logs/                    # 测试运行日志（test_run.log），已 gitignore
conftest.py              # pytest 公共 fixture（client、default_symbol、unique_cloid、日志）
pytest.ini
requirements.txt
README.md
```

---

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖
python3.11 -m venv myvenv
source myvenv/bin/activate   # Windows: myvenv\Scripts\activate
pip install -r requirements.txt

# 2. 本地配置（config/config.yaml 已 gitignore，勿提交）
cp config/config.example.yaml config/config.yaml
# 编辑 config.yaml 填写 wallet.address / wallet.private_key
# 或仅用 config.local.yaml 覆盖钱包，或环境变量 HYPERLIQUID_WALLET_ADDRESS / HYPERLIQUID_PRIVATE_KEY

# 3. 运行测试
pytest
```

## 环境与依赖

- **Python**：3.11+
- **依赖**：`pip install -r requirements.txt`（含 pytest、allure-pytest、requests、eth-account、msgpack 等）

## 配置

- **`config/config.yaml`**：本地专用，**已加入 .gitignore，不提交仓库**。首次克隆后执行 `cp config/config.example.yaml config/config.yaml` 再改钱包等。
- **无 config.yaml 时**：`loader` 会回退读取 `config.example.yaml`（仅作模板，需自行填钱包或通过环境变量）。
- **`config/config.local.yaml`**：可选覆盖层，同样已 gitignore。
- **环境变量**（优先于配置文件）：
  - `HYPERLIQUID_API_BASE_URL`：API 根地址（默认 testnet）
  - `HYPERLIQUID_WALLET_ADDRESS`：钱包地址
  - `HYPERLIQUID_PRIVATE_KEY`：私钥

CI 请用 Secrets + 环境变量；本地开发用 `config.yaml` 或 `config.local.yaml`。

## 运行测试

```bash
# 全部测试
pytest

# 指定目录/文件、详细输出
pytest tests/test_account.py -v
pytest tests/ -v --tb=short

# 生成 Allure 结果并查看报告
pytest --alluredir=allure-results
allure serve allure-results
```

## 测试日志（请求/响应）

运行 pytest 时，**测试动作、请求与响应**会写入日志文件，便于排查与审计：

| 项     | 说明 |
|--------|------|
| **路径** | 默认 `logs/test_run.log`，可通过 `config.logging.dir`、`config.logging.file` 修改 |
| **内容** | 每条用例起止标记（`========== TEST ...` / `---------- END ...`），每次 API 调用的 `REQUEST  POST <url>  body=...` 与 `RESPONSE ...  status=...  body=...` |
| **忽略** | `logs/` 已加入 `.gitignore`，不会提交到仓库 |

## 框架能力

- **重试**：所有用例使用 `@retry(exceptions=(AssertionError, HyperliquidAPIError))`，次数与间隔从 `config.test.retry_times`、`retry_delay_seconds` 读取
- **等待**：`utils/wait.wait_until`，超时与轮询间隔由 `poll_timeout_seconds`、`poll_interval_ms` 配置
- **并发**：并发下单笔数、Info 并发读次数由 `concurrent_orders_n`、`concurrent_info_calls_n` 配置
- **隔离**：每用例独立 cloid/订单，下单用例自行撤单，不共享状态
- **日志**：统一格式，控制台 + 文件；级别与格式由 `config.logging` 控制
- **错误**：`HyperliquidAPIError` 统一封装 API 错误与 response
- **精度**：下单时按 meta 的 szDecimals 与 tick size（永续 5 位有效数字、6-szDecimals 位小数）自动处理价格与数量

## 脚本

| 脚本 | 说明 |
|------|------|
| `scripts/fetch_order_history.py` | 拉取当前配置用户的历史委托（historicalOrders）及可选成交（userFills），可输出 JSON 文件 |

```bash
# 使用 config 钱包，控制台打印前 50 条
python scripts/fetch_order_history.py

# 写入 JSON，并同时拉取成交记录
python scripts/fetch_order_history.py --fills -o logs/order_history.json

# 指定用户、限制打印条数
python scripts/fetch_order_history.py --user 0x... --limit 20
```

## 扩展新场景

1. 在 `client/hyperliquid_client.py` 增加新 Info/Exchange 方法。
2. 在 `tests/` 下新增 `test_*.py`，使用 `@allure`、`@retry` 与 `client` fixture。
3. 在 `config/config.yaml` 的 `test` 下增加新参数（如 `default_symbol`、超时、并发数等）。

## CI

`.github/workflows/test.yml`：在 push/PR 到 `main` 或 `master` 时自动安装依赖、运行 pytest、上传 Allure 结果（Artifact）。  
如需完整跑通（含下单等），请在仓库 Settings → Secrets 中配置 `HYPERLIQUID_WALLET_ADDRESS`、`HYPERLIQUID_PRIVATE_KEY`。

## 参考

- **测试网**：https://app.hyperliquid-testnet.xyz/
- **API 文档**：https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
