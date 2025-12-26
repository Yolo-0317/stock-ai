# 📈 分钟线增强分析说明

## 🎯 功能升级

### 之前（仅历史日线 + 当前快照）

AI 只能看到：
- ✅ 历史 10 天的日线数据（OHLC + MA5/MA20）
- ✅ 当前时刻的价格快照（今开、当前价、最高、最低）

**问题**：
- ❌ 看不到日内的运行轨迹（是快速拉升还是缓慢爬升？）
- ❌ 看不到量价关系（放量上涨还是缩量上涨？）
- ❌ 看不到多空转换（是否反复测试高点？支撑是否有效？）

### 现在（增加分钟线数据）

AI 现在能看到：
- ✅ 历史 10 天的日线数据
- ✅ **今天的分钟级运行轨迹**（最近 30 分钟的 OHLC + 涨跌幅）
- ✅ 当前时刻的价格快照

**优势**：
- ✅ 能分析日内趋势（持续上涨/下跌/震荡）
- ✅ 能判断量价关系（成交量变化）
- ✅ 能识别支撑/压力的有效性（是否反复测试）
- ✅ 能评估多空力量对比

---

## 📊 数据来源

### 1. 历史日线数据
- **来源**：MySQL `stock_daily` 表
- **字段**：trade_date, open, high, low, close, vol, amount
- **用途**：计算 MA5/MA20，判断中期趋势

### 2. 当前实时数据
- **来源**：东方财富接口（`fetch_eastmoney_kline_daily`）
- **字段**：当前价、今开、最高、最低、成交量、成交额
- **用途**：获取实时价格和日内区间

### 3. 分钟线数据（新增）
- **来源**：MySQL `stock_intraday_snapshot` 表
- **字段**：bar_time, open, high, low, close, vol, pct_chg
- **采集**：通过 `poll_eastmoney_intraday_snapshot_to_mysql.py` 每分钟采集一次
- **用途**：分析日内运行轨迹、量价关系、多空力量

---

## 🔧 技术实现

### 1. 数据读取

```python
# 在 deepseek_intraday_t_signal() 函数中
intraday_bars = []
try:
    with engine.connect() as conn:
        sql = text("""
            SELECT bar_time, open, high, low, close, vol, pct_chg
            FROM stock_intraday_snapshot
            WHERE ts_code = :code AND DATE(bar_time) = :date
            ORDER BY bar_time
        """)
        result = conn.execute(sql, {"code": code6, "date": rt_date})
        for row in result:
            intraday_bars.append({
                "time": row[0].strftime("%H:%M"),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "vol": int(row[5]),
                "pct_chg": float(row[6]) if row[6] else 0,
            })
except Exception as e:
    print(f"[警告] 读取分钟线数据失败: {e}")
    intraday_bars = []
```

### 2. Prompt 构建

```python
# 在 _build_intraday_t_prompt() 函数中
if intraday_bars and len(intraday_bars) > 0:
    # 只展示最近 30 条，避免 token 过多
    recent_bars = intraday_bars[-30:] if len(intraday_bars) > 30 else intraday_bars
    bar_lines = ["时间 | 开盘 | 最高 | 最低 | 收盘 | 涨跌%"]
    bar_lines.append("--- | --- | --- | --- | --- | ---")
    for bar in recent_bars:
        bar_lines.append(
            f"{bar['time']} | {bar['open']:.3f} | {bar['high']:.3f} | "
            f"{bar['low']:.3f} | {bar['close']:.3f} | {bar['pct_chg']:.2f}%"
        )
    intraday_table = "\n".join(bar_lines)
```

### 3. AI 分析要求

在 prompt 中明确要求 AI 分析：
1. **日内趋势**：是持续上涨/下跌还是震荡反复？
2. **量价关系**：上涨/下跌时成交量如何变化？
3. **当前位置**：是第一次冲高还是反复测试？
4. **多空力量**：买盘强还是卖盘强？

---

## 🚀 使用方式

### 1. 确保分钟线数据采集

首先要运行分钟线采集脚本：

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 运行采集脚本（每分钟采集一次）
uv run python poll_eastmoney_intraday_snapshot_to_mysql.py
```

建议在后台持续运行，或使用 cron/launchd 定时任务。

### 2. 查看当前 AI 分析

```bash
# 单次测试
uv run python test_intraday_bars.py

# 或直接调用
uv run python -c "from tushare_mcp import deepseek_intraday_t_signal; print(deepseek_intraday_t_signal('159218', position_cost=1.55, position_ratio=0.5))"
```

### 3. 实时监控

```bash
# 运行监控脚本（会自动使用新的分钟线增强分析）
uv run python monitor_intraday_signals.py
```

---

## 📝 示例对比

### 示例 1：没有分钟线数据时

```
## 当前盘中实时数据
- 当前价: 1.625
- 今开: 1.568
- 最高/最低: 1.637 / 1.555

## 日内分钟线走势
暂无分钟线数据（可能尚未采集或盘前时段）
```

AI 只能基于"当前价位于日内 85% 高位"这种静态信息给出建议。

### 示例 2：有分钟线数据时

```
## 日内分钟线走势（最近 30 分钟）
时间 | 开盘 | 最高 | 最低 | 收盘 | 涨跌%
--- | --- | --- | --- | --- | ---
14:30 | 1.580 | 1.590 | 1.575 | 1.585 | 1.08%
14:31 | 1.585 | 1.595 | 1.580 | 1.590 | 1.40%
14:32 | 1.590 | 1.600 | 1.585 | 1.595 | 1.72%
...
14:58 | 1.620 | 1.637 | 1.615 | 1.625 | 3.64%
14:59 | 1.625 | 1.637 | 1.620 | 1.625 | 3.64%
```

AI 能看到：
- ✅ 从 14:30 的 1.585 持续上涨到 14:58 的 1.625
- ✅ 在 14:58 触及 1.637 高点后回落
- ✅ 最后几分钟在 1.625 附近震荡，说明上攻动能减弱

**更精准的建议**：
> 操作指令: 立即卖出
> 核心原因: 日内持续拉升后在高点反复震荡，上攻动能明显减弱，短期回调风险大

---

## ⚠️ 注意事项

### 1. 数据采集时机

- **盘中**：分钟线数据最有价值
- **盘前/盘后**：可能没有分钟线数据，AI 仍可基于日线分析
- **非交易日**：没有分钟线数据

### 2. Token 消耗

- 每次调用会传入最近 30 条分钟线数据
- 如果一整天有 240 条（4 小时交易 * 60 分钟），只取最后 30 条
- 避免 token 过多导致 API 成本增加

### 3. 数据质量

- 确保 `poll_eastmoney_intraday_snapshot_to_mysql.py` 正常运行
- 检查数据库连接是否正常
- 如果读取失败，AI 仍可基于日线 + 当前快照分析

---

## 🔧 故障排查

### 问题 1：提示"暂无分钟线数据"

**原因**：
- `stock_intraday_snapshot` 表中没有今天的数据
- 采集脚本未运行或运行失败

**解决方案**：
```bash
# 检查数据
uv run python -c "
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv('MYSQL_URL'))
with engine.connect() as conn:
    result = conn.execute(text('SELECT COUNT(*) FROM stock_intraday_snapshot WHERE DATE(bar_time) = CURDATE()'))
    print(f'今天的分钟数据: {result.scalar()} 条')
"

# 启动采集脚本
uv run python poll_eastmoney_intraday_snapshot_to_mysql.py
```

### 问题 2：AI 分析结果没有明显改善

**原因**：
- 数据量太少（如只有 2-3 条）
- 数据时间不连续（如采集中断）

**解决方案**：
- 确保采集脚本持续运行
- 等待积累更多分钟级数据（至少 10-15 条）

---

## 📚 相关文档

- [AI_SIGNAL_GUIDE.md](./AI_SIGNAL_GUIDE.md) - AI 操作指令使用指南
- [QUICKSTART.md](./QUICKSTART.md) - 完整的系统搭建指南
- [poll_eastmoney_intraday_snapshot_to_mysql.py](./poll_eastmoney_intraday_snapshot_to_mysql.py) - 分钟线采集脚本

---

**升级完成！现在你的 AI 助手能看到更多信息，给出更精准的操作建议了！** 🚀

