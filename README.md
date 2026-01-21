# tushare-mcp

## 数据入库（MySQL）

本目录提供三类数据入库方案：

### 方案 1：Tushare 全量日线同步（推荐✨）

**适用场景**：需要全市场股票的完整历史数据

- **特点**：
  - ✅ 免费（Tushare `daily` 接口，不需要积分）
  - ✅ **无需 stock_basic 接口**（避免 1 次/小时限制）
  - ✅ 数据完整（覆盖全部 A 股）
  - ✅ 效率极高（按日期批量拉取，7 天只需 7 次 API 调用）
  - ✅ 自动增量更新
  - ✅ 支持定时任务

详细文档：
- [Tushare 同步指南](docs/TUSHARE_SYNC_GUIDE.md)
- [无需 stock_basic 说明](docs/NO_STOCK_BASIC_GUIDE.md)

### 方案 2：东财接口（快速补齐特定股票）

**适用场景**：只需要少数几只股票的数据，或作为 Tushare 的补充

- **历史日线补齐**：`scripts/ingest_eastmoney_daily_to_mysql.py`
- **盘中增量更新**：`scripts/poll_eastmoney_intraday_to_mysql.py`
- **盘中快照**：`scripts/poll_eastmoney_intraday_snapshot_to_mysql.py`

#### 快速开始（方案 1：Tushare，推荐）

```bash
# 1. 建表
mysql -u user -p database < sql/create_stock_daily_table.sql

# 2. 配置环境变量
export TUSHARE_TOKEN="your_token"
export MYSQL_URL="mysql+pymysql://user:pass@host/db"

# 3. 修改脚本配置
# 打开 scripts/sync_tushare_daily_to_mysql.py
# 在文件底部修改：
# MODE = "full"  # 首次运行用 full 模式
# START_DATE = "20200101"  # 从 2020 年开始

# 4. 运行同步
uv run python scripts/sync_tushare_daily_to_mysql.py

# 5. 日常更新（每天运行）
# 修改配置：MODE = "by_date", DAYS = 7
# 或直接使用便捷脚本（已配置好）
./run_sync_daily.sh
```

**优势：**
- 无需 `stock_basic` 接口（避免 1 次/小时限制）
- 按日期批量拉取，效率极高
- 立即可用，无需等待

#### 方案 2 使用方法（东财接口）

##### 1) 建表

执行 `sql/create_stock_daily_table.sql` 创建 `stock_daily`（主键：`(ts_code, trade_date)`）。

##### 2) 先补历史（一次性）

使用东财接口拉取最近 N 条日线并入库：

```bash
MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
uv run python scripts/ingest_eastmoney_daily_to_mysql.py
```

你也可以改脚本里的 `CODES` 或自行扩展参数化（当前脚本示例默认包含 `159218/159840`）。

##### 3) 盘中每分钟更新（常驻）

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

##### 4) 盘中快照表（方案 A：每分钟留痕）

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

## 选股策略（盘后运行）

基于日线数据的选股策略，每日收盘后运行，筛选符合条件的强势股。

### 策略一：量价齐升突破选股 🚀

**特点**：捕捉放量突破的股票，适合短线波段

- ✅ 量价齐升（放量突破）
- ✅ 多头排列（MA5 > MA20 > MA60）
- ✅ 防止追高（近5日涨幅<20%）
- ✅ 按量比排序（主力活跃度）

```bash
# 使用最新交易日数据
uv run python scripts/stock_selection.py

# 指定历史日期
uv run python scripts/stock_selection.py --date 20260107
```

**输出**：`output/stock_selection_YYYYMMDD.csv`

### 策略二：沿MA5上行回调买入 📈

**特点**：寻找刚好回踩MA5准备反弹的股票，买点精准

- ✅ 今日回踩MA5（乖离率-2%~+1%）
- ✅ 今日收阳线（尾盘拉起）
- ✅ 近期强势（近5日至少3天在MA5上方）
- ✅ MA5向上（趋势明确）
- ✅ 按乖离率排序（越接近MA5越好）

```bash
# 使用最新交易日数据
uv run python scripts/stock_selection_ma5.py

# 指定历史日期
uv run python scripts/stock_selection_ma5.py --date 20260107
```

**输出**：`output/stock_selection_ma5_YYYYMMDD.csv`

**策略对比**：
- **策略一**：找启动点，适合追涨，短线操作
- **策略二**：找买点，适合低吸，波段持有

## 盘中盯盘监控（信号输出 + 可选飞书）

盯盘脚本会按你在脚本里配置的标的列表轮询信号，并输出到控制台与日志；当启用飞书且信号为"可执行信号"时才会推送（例如做T模式只推送"立即买入/立即卖出"，观望/暂不操作只记日志不推送）。

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

## 在 Cursor 里启用 MCP（可选）

如果你想把 `tushare_mcp.py` 作为 Cursor 的 MCP 工具使用，参考：
- `docs/CURSOR_MCP_SETUP.md`
- `cursor-mcp.example.json`
