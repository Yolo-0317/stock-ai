# Tushare 日线数据同步指南

## 📖 功能说明

本工具用于从 Tushare 拉取全部 A 股的历史日线数据，并支持增量更新。

**特点：**
- ✅ 免费接口（Tushare `daily` 接口不需要积分）
- ✅ 支持全量初始化和增量更新
- ✅ 自动去重（基于主键：股票代码 + 交易日期）
- ✅ 断点续传（失败后可继续）
- ✅ API 限流保护（避免触发 Tushare 限制）

---

## 🚀 快速开始

### 1. 环境配置

确保在 `.env` 文件中配置了以下环境变量：

```bash
# Tushare API Token（在 https://tushare.pro 注册获取）
TUSHARE_TOKEN=your_tushare_token_here

# MySQL 连接字符串
MYSQL_URL=mysql+pymysql://user:password@localhost:3306/stock_data
```

### 2. 首次运行（推荐使用按日期批量拉取）

**方式 1：按日期批量拉取（推荐，无需 stock_basic 接口）**

修改脚本中的配置：

```python
# 打开 scripts/sync_tushare_daily_to_mysql.py
# 在文件底部修改配置：

MODE = "by_date"
DAYS = 365  # 拉取最近 365 天的数据
SLEEP_SECONDS = 2.0
MAX_CALLS = 40
```

然后运行：

```bash
uv run python scripts/sync_tushare_daily_to_mysql.py
```

**预计耗时：**
- 365 天 × 2 秒/天 ≈ 12 分钟
- 无需等待 stock_basic 接口限制

**方式 2：使用便捷脚本（推荐用于日常更新）**

```bash
./run_sync_daily.sh
```

### 3. 增量更新（每日定时运行）

**使用默认配置即可：**

```bash
# 直接运行（默认配置已优化）
uv run python scripts/sync_tushare_daily_to_mysql.py

# 或使用便捷脚本
./run_sync_daily.sh
```

**预计耗时（使用默认配置 --sleep 1.5）：**
- 首次增量更新：10-15 分钟（补齐周末和节假日数据）
- 日常增量更新：5-10 分钟（只更新 1 天数据，5000+ 只股票）

---

## 📅 定时任务配置

### 使用 crontab（Linux/macOS）

编辑 crontab：

```bash
crontab -e
```

添加定时任务（每个交易日 16:00 执行）：

```cron
# Tushare 日线数据增量更新（每天 16:00）
0 16 * * 1-5 cd /path/to/stock-ai && ./run_sync_daily.sh >> logs/sync_daily.log 2>&1
```

查看定时任务：

```bash
crontab -l
```

### 使用 systemd timer（Linux）

创建服务文件 `/etc/systemd/system/sync-tushare-daily.service`：

```ini
[Unit]
Description=Sync Tushare Daily Data
After=network.target

[Service]
Type=oneshot
User=your_username
WorkingDirectory=/path/to/stock-ai
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
ExecStart=/path/to/stock-ai/run_sync_daily.sh
StandardOutput=append:/path/to/stock-ai/logs/sync_daily.log
StandardError=append:/path/to/stock-ai/logs/sync_daily.log

[Install]
WantedBy=multi-user.target
```

创建定时器文件 `/etc/systemd/system/sync-tushare-daily.timer`：

```ini
[Unit]
Description=Sync Tushare Daily Data Timer

[Timer]
# 每天 16:00 执行
OnCalendar=*-*-* 16:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

启用定时器：

```bash
sudo systemctl daemon-reload
sudo systemctl enable sync-tushare-daily.timer
sudo systemctl start sync-tushare-daily.timer

# 查看定时器状态
sudo systemctl status sync-tushare-daily.timer
```

---

## 🔧 高级用法

### 1. 更新指定股票

修改脚本配置：

```python
# 打开 scripts/sync_tushare_daily_to_mysql.py
# 修改配置：

MODE = "incremental"
CODES = "000001.SZ,600000.SH,159218.SZ"  # 指定要更新的股票
SLEEP_SECONDS = 1.5
```

然后运行：

```bash
uv run python scripts/sync_tushare_daily_to_mysql.py
```

### 2. 调整 API 调用参数

修改脚本配置：

```python
# 打开 scripts/sync_tushare_daily_to_mysql.py
# 修改配置：

SLEEP_SECONDS = 2.0  # 调整调用间隔
MAX_CALLS = 40       # 调整每分钟最大调用次数
```

### 3. 测试模式

修改脚本配置：

```python
# 打开 scripts/sync_tushare_daily_to_mysql.py
# 修改配置：

MODE = "by_date"
DAYS = 3      # 只测试 3 天
LIMIT = None  # by_date 模式不需要 LIMIT
```

---

## 📊 数据说明

### 数据表结构

脚本会将数据写入 `stock_daily` 表，表结构如下：

```sql
CREATE TABLE stock_daily (
    ts_code VARCHAR(10) NOT NULL,      -- 股票代码（纯数字，如：000001）
    exch_code VARCHAR(10),             -- 交易所代码（SZ/SH/BJ）
    trade_date DATE NOT NULL,          -- 交易日期
    open DECIMAL(10, 4),               -- 开盘价
    high DECIMAL(10, 4),               -- 最高价
    low DECIMAL(10, 4),                -- 最低价
    close DECIMAL(10, 4),              -- 收盘价
    pre_close DECIMAL(10, 4),          -- 昨收价
    change_amount DECIMAL(10, 4),      -- 涨跌额
    pct_chg DECIMAL(8, 4),            -- 涨跌幅（%）
    vol BIGINT,                        -- 成交量（手）
    amount DECIMAL(20, 4),             -- 成交额（千元）
    update_time DATETIME,              -- 更新时间
    create_time DATETIME,              -- 创建时间
    PRIMARY KEY (ts_code, trade_date)
);
```

### 数据来源

- **股票列表**：`stock_basic` 接口（包含所有 A 股）
- **日线数据**：`daily` 接口（免费，不需要积分）

### 去重机制

- 使用联合主键 `(ts_code, trade_date)` 自动去重
- 相同股票和日期的数据会更新而不是重复插入

---

## 🔍 常见问题

### 1. Tushare API 限流怎么办？

**症状：**
```
❌ 拉取失败: 抱歉，您每分钟最多访问该接口50次
```

**原因：**
- Tushare 免费账户限制：50 次/分钟
- 脚本调用过快，超过限流阈值

**解决方案（已内置智能限流控制）：**

脚本已经内置了智能限流控制，会自动：
- 监控每分钟的 API 调用次数
- 达到阈值时自动等待
- 遇到限流错误时自动重试

**手动调整参数：**

```bash
# 方案 1：增加调用间隔（推荐）
uv run python scripts/sync_tushare_daily_to_mysql.py --sleep 2.0

# 方案 2：降低每分钟最大调用次数
uv run python scripts/sync_tushare_daily_to_mysql.py --max-calls 40

# 方案 3：组合调整（最稳定）
uv run python scripts/sync_tushare_daily_to_mysql.py --sleep 2.0 --max-calls 40

# 方案 4：分批处理（适合首次全量同步）
uv run python scripts/sync_tushare_daily_to_mysql.py --mode full --limit 1000 --sleep 2.0
```

**性能对比：**

| 配置 | 速度 | 稳定性 | 适用场景 |
|------|------|--------|----------|
| `--sleep 1.5 --max-calls 45` | 快 | 中等 | 网络好、增量更新 |
| `--sleep 2.0 --max-calls 40` | 中等 | 高 | 日常使用（推荐）|
| `--sleep 3.0 --max-calls 30` | 慢 | 极高 | 网络差、大量数据 |

### 2. 数据库连接失败

**症状：**
```
❌ 错误：未设置 MYSQL_URL 环境变量
```

**解决方案：**
- 检查 `.env` 文件是否正确配置
- 确认 MySQL 服务是否正常运行
- 测试连接字符串是否正确

### 3. 某些股票拉取失败

**症状：**
```
⚠️ 无数据
```

**可能原因：**
- 股票已退市或暂停上市
- Tushare 接口暂时无数据
- 网络连接问题

**解决方案：**
- 检查失败股票列表，确认是否为正常情况
- 可以手动重新拉取：`--codes 失败的代码`

### 4. 增量更新没有拉取到最新数据

**可能原因：**
- Tushare 数据更新延迟（通常收盘后 1-2 小时更新）
- 当天不是交易日（周末、节假日）

**解决方案：**
- 等待 Tushare 数据更新后再运行
- 建议定时任务设置在每日 16:30 或 17:00 执行

---

## 📈 性能优化

### 1. 批量插入

脚本使用 `method='multi'` 进行批量插入，大幅提升性能。

### 2. 索引优化

数据表已创建以下索引：
- 主键索引：`(ts_code, trade_date)`
- 按日期查询：`idx_trade_date`
- 按代码查询：`idx_ts_code`

### 3. 连接池

使用 SQLAlchemy 连接池，避免频繁创建/销毁连接。

---

## 🎯 最佳实践

### 1. 首次初始化

```bash
# 1. 测试模式（10 只股票）
uv run python scripts/sync_tushare_daily_to_mysql.py --mode full --limit 10

# 2. 确认无误后，全量初始化
uv run python scripts/sync_tushare_daily_to_mysql.py --mode full
```

### 2. 日常维护

```bash
# 每日定时运行增量更新（crontab）
0 16 * * 1-5 cd /path/to/stock-ai && ./run_sync_daily.sh >> logs/sync_daily.log 2>&1
```

### 3. 监控日志

```bash
# 实时查看同步日志
tail -f logs/sync_daily.log

# 查看最近的同步结果
tail -100 logs/sync_daily.log
```

---

## 📞 技术支持

如遇问题，请检查：
1. 环境变量配置（`.env` 文件）
2. Tushare API 是否正常（访问 https://tushare.pro）
3. MySQL 数据库是否正常
4. 网络连接是否正常

---

## 📝 更新日志

### v1.0.0 (2025-01-07)
- ✨ 初始版本
- ✅ 支持全量初始化
- ✅ 支持增量更新
- ✅ 支持断点续传
- ✅ API 限流保护

