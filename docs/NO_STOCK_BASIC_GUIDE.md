# 无需 stock_basic 接口的数据同步方案

## 🎉 好消息

脚本已经完全移除了对 `stock_basic` 接口的依赖！

**之前的问题：**
- `stock_basic` 接口限制：1 次/小时
- 触发限流需要等待 1 小时才能重试
- 不便于频繁测试和调试

**现在的方案：**
- ✅ **完全不需要 stock_basic 接口**
- ✅ **立即可用，无需等待**
- ✅ **所有模式都使用 daily 接口（50 次/分钟）**

---

## 📋 三种模式说明

### 1. by_date 模式（日常更新，推荐）

**原理：**
- 使用 `daily(trade_date='YYYYMMDD')` 按日期拉取全市场数据
- 一次 API 调用获取所有股票的数据

**使用场景：**
- 日常增量更新
- 补齐周末和节假日数据

**配置示例：**
```python
MODE = "by_date"
DAYS = 7  # 同步最近 7 天
```

**API 调用次数：**
- 7 天 = 7 次 API 调用
- 速度快，效率高

---

### 2. full 模式（全量初始化，推荐）

**原理：**
- 使用 `trade_cal` 接口获取交易日历（免费，无限制）
- 逐个交易日调用 `daily(trade_date='YYYYMMDD')` 拉取全市场数据
- 本质上是多天的 by_date 模式

**使用场景：**
- 首次初始化
- 拉取历史所有数据

**配置示例：**
```python
MODE = "full"
START_DATE = "20200101"  # 从 2020 年开始拉取
```

**API 调用次数：**
- 假设 2020-2025 约 1200 个交易日
- 1200 次 API 调用（约 40 分钟，按 2 秒/次计算）

---

### 3. incremental 模式（逐股票更新）

**原理：**
- 从数据库读取已有的股票列表（避免 stock_basic）
- 逐个股票检查最新日期，只拉取缺失的数据

**使用场景：**
- 需要精确控制每只股票的更新
- 特定股票的补齐

**前提条件：**
- 数据库中已有股票数据（需先运行 full 或 by_date 模式）

**配置示例：**
```python
MODE = "incremental"
CODES = None  # 从数据库读取所有股票
# 或指定股票：
CODES = "000001.SZ,600000.SH"
```

**API 调用次数：**
- N 只股票 = N 次 API 调用
- 如果所有股票都是最新，则不会调用 API

---

## 🚀 推荐使用流程

### 首次初始化

```python
# 修改配置
MODE = "full"
START_DATE = "20200101"  # 根据需要调整起始日期
SLEEP_SECONDS = 2.0
MAX_CALLS = 40

# 运行
uv run python scripts/sync_tushare_daily_to_mysql.py
```

**预计耗时：**
- 2020-2025（约 1200 个交易日）
- 1200 × 2 秒 = 40 分钟

### 日常更新

```python
# 修改配置
MODE = "by_date"
DAYS = 7  # 同步最近 7 天（补齐周末）
SLEEP_SECONDS = 2.0
MAX_CALLS = 40

# 运行（或使用便捷脚本）
uv run python scripts/sync_tushare_daily_to_mysql.py
# 或
./run_sync_daily.sh
```

**预计耗时：**
- 7 天 = 7 × 2 秒 = 14 秒

### 定时任务

```cron
# 每天 16:00 执行
0 16 * * 1-5 cd /path/to/stock-ai && ./run_sync_daily.sh >> logs/sync_daily.log 2>&1
```

---

## 💡 为什么不再需要 stock_basic？

### 之前的方式（需要 stock_basic）

```
1. 调用 stock_basic 获取所有股票列表（1 次/小时限制）
   ↓
2. 遍历股票列表
   ↓
3. 逐个调用 daily(ts_code='xxx') 拉取数据
```

**问题：**
- 第 1 步受限流限制（1 次/小时）
- 5000 股 × 50 次/分钟 = 约 100 分钟

### 现在的方式（无需 stock_basic）

```
1. 遍历日期列表
   ↓
2. 逐个调用 daily(trade_date='YYYYMMDD') 拉取全市场数据
```

**优势：**
- 无需 stock_basic 接口
- 7 天 × 50 次/分钟 = 不到 1 分钟
- 效率更高

---

## 📊 性能对比

| 场景 | 旧方案（需 stock_basic） | 新方案（无需 stock_basic） | 提升 |
|------|-------------------------|--------------------------|------|
| **首次初始化** | | | |
| API 调用 | 1（stock_basic）+ 5000（逐股票） | 1200（逐日期） | 减少 76% |
| 耗时 | 1 小时限制 + 2.5 小时 | 40 分钟 | 快 3 倍 |
| 限流风险 | 高（stock_basic 限制） | 无 | ✅ |
| **日常更新** | | | |
| API 调用 | 1（stock_basic）+ 5000（逐股票） | 7（逐日期） | 减少 99.9% |
| 耗时 | 1 小时限制 + 2.5 小时 | 14 秒 | 快 700 倍 |
| 限流风险 | 高 | 无 | ✅ |

---

## ✨ 关键优势

### 1. 无限流烦恼
- ❌ 不再需要等待 1 小时
- ✅ 立即可用，随时测试

### 2. 效率更高
- ❌ 不再需要逐个股票拉取
- ✅ 按日期批量拉取，一次获取全市场

### 3. 实现简单
- ❌ 不再需要维护股票列表
- ✅ 只需维护日期列表

### 4. 更加稳定
- ❌ 不再依赖 stock_basic 接口的可用性
- ✅ 只依赖 daily 接口（更稳定，限流更宽松）

---

## 🎯 常见问题

### Q: 如果我只想更新特定股票怎么办？

**A:** 使用 incremental 模式：

```python
MODE = "incremental"
CODES = "000001.SZ,600000.SH,159218.SZ"
```

### Q: by_date 模式会拉取所有股票吗？

**A:** 是的！`daily(trade_date='YYYYMMDD')` 会返回该日所有股票的数据。

### Q: full 模式和 by_date 模式有什么区别？

**A:** 
- `full`: 从指定起始日期到今天的所有交易日
- `by_date`: 从今天往前回溯指定天数

**示例：**
```python
# full 模式：拉取 2020-2025 所有数据
MODE = "full"
START_DATE = "20200101"

# by_date 模式：只拉取最近 7 天
MODE = "by_date"
DAYS = 7
```

### Q: 如果数据库是空的，应该用哪个模式？

**A:** 使用 `full` 模式初始化：

```python
MODE = "full"
START_DATE = "20200101"  # 根据需要调整
```

### Q: incremental 模式还有用吗？

**A:** 有！适用于以下场景：
- 精确控制每只股票的更新逻辑
- 补齐特定股票的历史数据
- 数据库已有部分股票，需要增量更新

---

## 📚 相关文档

- 完整使用指南：[TUSHARE_SYNC_GUIDE.md](TUSHARE_SYNC_GUIDE.md)
- 限流优化指南：[RATE_LIMIT_GUIDE.md](RATE_LIMIT_GUIDE.md)

