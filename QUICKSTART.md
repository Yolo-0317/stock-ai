# 快速开始指南

## 问题诊断：为什么显示"未知"？

当你看到以下输出时：

```
[2025-12-26 15:49:33] 159218 未知
【规则策略】信号=
依据=
```

**原因**：`intraday_trade_signal()` 返回了错误信息（如"未配置 MYSQL_URL"），而不是正常的报告格式，导致无法提取字段。

---

## 完整测试步骤

### 步骤 1：配置 MySQL 数据库（必需）

#### 1.1 创建数据库

```sql
CREATE DATABASE IF NOT EXISTS stock_data 
  DEFAULT CHARACTER SET utf8mb4 
  COLLATE utf8mb4_unicode_ci;
```

#### 1.2 创建表结构

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 创建日线表
mysql -u root -p stock_data < create_stock_daily_table.sql

# （可选）创建分钟快照表
mysql -u root -p stock_data < create_stock_intraday_snapshot_table.sql
```

#### 1.3 补齐历史数据

```bash
# 修改 run_monitor.sh 里的 MYSQL_URL
# 然后运行：
export MYSQL_URL="mysql+pymysql://root:your_password@localhost:3306/stock_data"
uv run python ingest_eastmoney_daily_to_mysql.py
```

这会拉取 159218 和 159840 的最近 120 天日线数据并入库。

---

### 步骤 2：配置启动脚本

编辑 `run_monitor.sh`，修改以下两行：

```bash
# 1. 修改 MySQL 连接（必需）
export MYSQL_URL="mysql+pymysql://你的用户名:你的密码@localhost:3306/stock_data"

# 2. 修改 DeepSeek API Key（可选，如果你启用了 AI 分析）
export DEEPSEEK_API_KEY="sk-你的API密钥"
```

---

### 步骤 3：单次测试（推荐）

先运行单次测试，确保配置正确：

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 测试规则策略信号
./run_monitor.sh
```

**预期输出**：

```
========================================
环境变量配置：
========================================
✓ MYSQL_URL: mysql+pymysql://root:***@localhost:3306/stock_data
⚠ DEEPSEEK_API_KEY 未设置（如果启用了 DeepSeek AI 会报错）
========================================

正在启动盯盘监控...
开始盯盘：codes=['159218', '159840'] interval=60.0s
飞书通知已启用
DeepSeek AI 辅助分析已启用

[2025-12-26 15:52:00] 159218 2025-12-26
【规则策略】信号=偏买入
依据=均线多头（MA5 > MA20）；价格在 MA20 之上；盘中强于开盘
```

---

### 步骤 4：测试 DeepSeek AI（可选）

如果你想测试 AI 分析功能：

```bash
# 1. 获取 DeepSeek API Key
# 访问 https://platform.deepseek.com/
# 注册 -> API Keys -> 创建新密钥

# 2. 设置环境变量并测试
export DEEPSEEK_API_KEY="sk-your-key"
export MYSQL_URL="mysql+pymysql://root:password@localhost:3306/stock_data"
uv run python test_deepseek_signal.py
```

---

## 常见问题排查

### Q1: 提示"未配置 MYSQL_URL"

**A**: 确保在运行脚本前设置了环境变量：

```bash
export MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data"
```

### Q2: 提示"未在 MySQL 中找到 xxx 的历史数据"

**A**: 需要先补齐历史数据：

```bash
uv run python ingest_eastmoney_daily_to_mysql.py
```

### Q3: 提示"ModuleNotFoundError: No module named 'mcp'"

**A**: 使用 `uv run` 而不是直接 `python`：

```bash
uv run python monitor_intraday_signals.py
```

### Q4: 想禁用 DeepSeek AI（省钱）

**A**: 修改 `monitor_intraday_signals.py` 第 56 行：

```python
enable_deepseek = False  # 改为 False
```

### Q5: 想禁用飞书通知

**A**: 修改 `monitor_intraday_signals.py` 第 55 行：

```python
enable_feishu = False  # 改为 False
```

---

## 最小配置快速测试

如果你只想快速测试规则策略（不用 AI、不用飞书），最简单的方式：

```bash
# 1. 安装依赖
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv sync

# 2. 设置 MySQL（必需）
export MYSQL_URL="mysql+pymysql://root:password@localhost:3306/stock_data"

# 3. 补历史数据
uv run python ingest_eastmoney_daily_to_mysql.py

# 4. 修改配置（禁用飞书和 AI）
# 编辑 monitor_intraday_signals.py：
#   enable_feishu = False
#   enable_deepseek = False

# 5. 运行
uv run python monitor_intraday_signals.py
```

---

## 验证是否配置成功

运行调试脚本：

```bash
export MYSQL_URL="mysql+pymysql://root:password@localhost:3306/stock_data"
uv run python debug_signal.py
```

**成功输出示例**：

```
正在获取 159218 的信号...
================================================================================
原始返回内容：

### 盘中买卖信号报告: 159218
- **盘中日期**: 2025-12-26
- **今开/当前/最高/最低**: 1.568 / 1.625 / 1.637 / 1.555
...
```

**失败输出示例**：

```
原始返回内容：
分析过程中出错: 未配置 MYSQL_URL，无法从 MySQL 读取历史数据。
```

---

## 下一步

配置成功后，你可以：

1. **盯盘模式**：让脚本持续运行，每分钟自动检测信号
2. **回测模式**：修改历史数据，测试策略有效性
3. **添加新品种**：在 `monitor_intraday_signals.py` 的 `codes` 列表里加入更多代码
4. **优化策略**：修改 `tushare_mcp.py` 里的信号逻辑（如加入成交量过滤）

有问题随时问我！
