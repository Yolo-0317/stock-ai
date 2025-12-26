# ⚙️ 监控脚本配置指南

## 📋 配置说明

在 `monitor_intraday_signals.py` 的 `main()` 函数中，有以下配置选项：

### 基础配置

```python
codes = ["159218", "159840"]  # 关注标的
interval = 60.0  # 轮询间隔（秒）
all_day = True  # True：全天都跑；False：只在交易时段判断
```

### 打印配置

```python
print_bias = False  # True：也打印"偏买入/偏卖出"
print_all_signals = False  # True：打印所有信号（包括"暂不操作"）；False：只打印买入/卖出
```

**重要**：
- `print_all_signals = False`（默认）：**只打印"立即买入"和"立即卖出"**，不打印"暂不操作"
- `print_all_signals = True`：**打印所有标的的所有信号**，包括"暂不操作"

### 通知配置

```python
enable_feishu = True  # True：启用飞书通知；False：仅控制台打印
enable_deepseek = True  # True：启用 DeepSeek AI 辅助分析
```

### 做T配置

```python
use_t_signal = True  # True：使用做T信号（专注盘中波动）；False：使用标准买卖信号

position_costs = {  # 各品种的持仓成本（可选，用于计算盈亏）
    "159218": 1.197,
    "159840": 0.869,
}

position_ratios = {  # 各品种的当前仓位比例 0-1（可选）
    "159218": 0.2374,  # 23.74% 仓位
    "159840": 0.1058,  # 10.58% 仓位
}
```

---

## 📊 为什么没有打印某个标的？

### 默认行为（`print_all_signals = False`）

**只打印有明确操作建议的信号**：
- ✅ 打印："立即买入"、"立即卖出"
- ❌ 不打印："暂不操作"

**原因**：避免信息过载，只在需要操作时通知你。

### 示例

假设监控两个标的：
- **159218**：AI 分析后给出 "立即卖出" → ✅ **会打印**
- **159840**：AI 分析后给出 "暂不操作" → ❌ **不打印**

输出：
```
==================================================
⏰ 18:10:29  |  159218
==================================================
🔴 卖出  【立即卖出】
...
```

**159840 没有输出，因为它的信号是"暂不操作"。**

---

## 🔍 如何查看所有标的的分析？

### 方法 1：修改配置（推荐调试时使用）

在 `monitor_intraday_signals.py` 中修改：

```python
print_all_signals = True  # 改为 True
```

重新运行后，会打印所有标的的信号：

```
==================================================
⏰ 18:10:29  |  159218
==================================================
🔴 卖出  【立即卖出】
...

==================================================
⏰ 18:10:29  |  159840
==================================================
⚪ 观望  【暂不操作】
...
```

### 方法 2：单独查询（推荐）

如果只是想看某个标的当前的分析，可以单独运行：

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 查询 159840
uv run python -c "from tushare_mcp import deepseek_intraday_t_signal; print(deepseek_intraday_t_signal('159840', position_cost=0.869, position_ratio=0.1058))"
```

---

## 🔔 飞书通知逻辑

飞书通知遵循与控制台打印相同的逻辑：
- `print_all_signals = False`：只发送买入/卖出通知
- `print_all_signals = True`：发送所有信号通知（包括"暂不操作"）

---

## 💡 最佳实践

### 日常监控（生产环境）

```python
print_all_signals = False  # 只打印买入/卖出
enable_feishu = True      # 启用飞书通知
```

**优点**：
- ✅ 清爽，只在需要操作时收到通知
- ✅ 不会被"暂不操作"刷屏
- ✅ 节省流量和 API 调用

### 调试分析（开发环境）

```python
print_all_signals = True   # 打印所有信号
enable_feishu = False     # 关闭飞书通知
```

**优点**：
- ✅ 能看到每个标的的完整分析
- ✅ 方便对比和调试
- ✅ 不会发送过多飞书通知

---

## 📝 启动信息说明

运行监控脚本时，会显示当前配置：

```
开始盯盘：codes=['159218', '159840'] interval=60.0s
模式：盘中做T信号（专注日内波动）
打印模式：仅显示买入/卖出信号  ← 这里显示当前的打印模式
飞书通知已启用
DeepSeek AI 辅助分析已启用
```

如果 `print_all_signals = True`，会显示：
```
打印模式：显示所有信号（包括"暂不操作"）
```

---

## 🚀 快速测试

### 测试单个标的

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 测试 159218
uv run python -c "from tushare_mcp import deepseek_intraday_t_signal; print(deepseek_intraday_t_signal('159218', position_cost=1.197, position_ratio=0.2374))"

# 测试 159840
uv run python -c "from tushare_mcp import deepseek_intraday_t_signal; print(deepseek_intraday_t_signal('159840', position_cost=0.869, position_ratio=0.1058))"
```

### 运行监控

```bash
# 默认模式（只打印买入/卖出）
uv run python monitor_intraday_signals.py

# 如果需要看所有信号，先修改配置后再运行
```

---

## 📚 相关文档

- [AI_SIGNAL_GUIDE.md](./AI_SIGNAL_GUIDE.md) - AI 操作指令详细说明
- [QUICKSTART.md](./QUICKSTART.md) - 完整的系统搭建指南
- [INTRADAY_BARS_ANALYSIS.md](./INTRADAY_BARS_ANALYSIS.md) - 分钟线增强分析说明

---

**记住：默认只打印买入/卖出信号，避免信息过载！** 🎯

