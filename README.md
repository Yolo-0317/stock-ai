# tushare-mcp

## 数据入库（MySQL）

本目录提供两类脚本：

- **历史日线补齐（建议先跑一次）**：`scripts/ingest_eastmoney_daily_to_mysql.py`
- **盘中增量更新（每分钟 upsert 今日数据）**：`scripts/poll_eastmoney_intraday_to_mysql.py`
- **盘中快照（方案 A：每分钟留痕，不覆盖路径）**：`scripts/poll_eastmoney_intraday_snapshot_to_mysql.py`

### 1) 建表

执行 `sql/create_stock_daily_table.sql` 创建 `stock_daily`（主键：`(ts_code, trade_date)`）。

### 2) 先补历史（一次性）

使用东财接口拉取最近 N 条日线并入库：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/ingest_eastmoney_daily_to_mysql.py
```

你也可以改脚本里的 `CODES` 或自行扩展参数化（当前脚本示例默认包含 `159218/159840`）。

### 3) 盘中每分钟更新（常驻）

盘中东财“最新一根日线”会动态变化，本脚本会对同一天做 upsert，便于 `intraday_trade_signal` 使用 MySQL 历史做更稳定的盘中分析：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/poll_eastmoney_intraday_to_mysql.py --codes 159218,159840 --interval 60
```

如果你想用 `cron`，可以用单次模式：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/poll_eastmoney_intraday_to_mysql.py --codes 159218,159840 --once
```

### 4) 盘中快照表（方案 A：每分钟留痕）

如果你希望保留盘中轨迹（而不是不断覆盖 `stock_daily` 当天数据），可以建表并启动快照轮询：

- 建表：`sql/create_stock_intraday_snapshot_table.sql`
- 脚本：`scripts/poll_eastmoney_intraday_snapshot_to_mysql.py`

常驻轮询：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/poll_eastmoney_intraday_snapshot_to_mysql.py --codes 159218,159840 --interval 60
```

cron 单次：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/poll_eastmoney_intraday_snapshot_to_mysql.py --codes 159218,159840 --once
```

## 盘中盯盘监控（信号输出 + 可选飞书）

盯盘脚本会按你在脚本里配置的标的列表轮询信号，并输出到控制台与日志；当启用飞书且信号为“可执行信号”时才会推送（例如做T模式只推送“立即买入/立即卖出”，观望/暂不操作只记日志不推送）。

```bash
# 方式 A：直接运行
uv run python scripts/monitor_intraday_signals.py
```

也可以用启动器脚本（里面可以直接写死环境变量）：

```bash
# 方式 B：使用启动器
bash run_monitor.sh
```

## 盘前总结（开盘前）

```bash
uv run python scripts/run_premarket_analysis.py
```

## 盘后总结（收盘后）

```bash
uv run python scripts/run_aftermarket_analysis.py
```

## 午盘分析（午间）

```bash
uv run python scripts/run_midday_analysis.py
```
