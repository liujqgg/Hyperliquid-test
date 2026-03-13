# Hyperliquid Automated Testing Framework Challenge

## 一、背景

本挑战的目标是：

> 为 Hyperliquid Testnet API 构建一个自动化测试框架。

Hyperliquid 是一个高性能永续合约交易系统。

在真实交易系统中，自动化测试框架非常重要，需要能够验证：

- 账户状态
- 订单生命周期
- 仓位变化
- API错误处理
- 系统稳定性

本挑战将评估你在以下方面的能力：

- 自动化测试框架设计
- API测试能力
- 工程能力
- 使用AI辅助开发的能力

你的框架需要能够：

- 调用 Hyperliquid API
- 执行自动化测试
- 验证交易系统关键流程
- 支持扩展新的测试场景
---


# 二、技术栈

技术栈不限，但推荐使用

### 语言

```
Python
Typescript
```

### 测试框架

```
pytest
jest
playwright
```

---

# 三、项目结构要求

你的项目需要具备清晰结构。

推荐结构：

```
hyperliquid-test-framework/

README.md

client/
    hyperliquid_client.py

tests/
    test_account.py
    test_limit_orders.py
    test_market_orders.py
    test_positions.py

fixtures/
    wallet_fixture.py

utils/
    order_utils.py

config/
    config.yaml
```

你可以根据需要自行扩展。

---

# 四、API Client

首先需要实现一个 Hyperliquid API Client。

Client 至少应该封装：

```
账户查询
下单
撤单
订单查询
仓位查询
```

要求：
- 不可以使用HyperLiquid官方或社区提供的SDK
- 统一错误处理
- 日志输出尽可能清晰
- 可复用设计

---

# 五、核心测试场景

你的测试框架必须覆盖以下测试场景。

---

## 1 Account Tests

测试账户信息。

例如：

```
获取账户余额
验证返回字段结构
验证余额更新
```

---

## 2 Order Lifecycle Tests

测试订单完整生命周期：

```
创建订单
查询订单
撤销订单
验证订单状态
```

---

## 3 Position Tests

测试仓位相关逻辑：

```
开仓
平仓
查询仓位
```

验证：

```
position size
entry price
```

---

## 4 Error Handling Tests

测试错误场景：

```
非法symbol
非法价格
非法数量
```

验证：

```
API返回错误
错误码
```

---

## 5 Concurrent Tests（可选）

测试并发场景：

```
同时提交多个订单
验证系统稳定性
```

---

# 六、测试框架能力要求

你的框架需要具备以下能力：
- 重试机制
- 等待机制(订单状态可能存在延迟)
- 各项测试之间不相互影响
- 支持配置(如API Endpoint, Test Wallet, Private Key等)

---

# 七、CI（加分）

如果实现 CI 自动运行测试，将获得加分。

例如：

```
GitHub Actions
```

---

# 八、测试报告

你的框架应支持生成测试报告。如HTML格式。


---

# 九、HyperLiquid相关信息

HyperLiquid网站: https://app.hyperliquid.xyz/

HyperLiquid测试网: https://app.hyperliquid-testnet.xyz/ 

Hyperliquid文档: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api 

如果需要在hyperliquid testnet上下单但无法setup账号的,可以使用以下钱包:
```
地址: 0xa4022bdfa1e6d546f26905111fc62b0b8887d482
私钥: 0x25c86c1b938d513e89579f42cb1c527f3c179f6b1b9834a03ab880858bc5f10a
```
该钱包在Hyperliquid 主网有0.1 SOL, 测试网有999 USDC，请节省使用，为其他需要使用的同学提供便利

# 十、补充说明

本挑战的目标不是测试 Hyperliquid 是否正确，而是设计一个高质量自动化测试框架。所有未明确要求或说明的部分，允许且鼓励发挥自己的能力进行方案设计，考虑越充分，功能越完善，整体评分越高。
如果时间不足，建议优先完成：

```
1 API client
2 account tests
3 order tests
4 position tests
5 error tests
6 retry logic
7 CI
```
