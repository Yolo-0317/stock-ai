# 📝 日志系统说明

## 🎯 升级内容

所有 `print` 语句已替换为标准的 `logging` 系统，提供更专业的日志管理。

### 模块化设计

日志配置已提取到独立的 `logger_config.py` 模块，方便在多个脚本中复用：
- ✅ `logger_config.py` - 统一的日志配置模块
- ✅ `monitor_intraday_signals.py` - 使用日志
- ✅ `feishu_notice.py` - 使用日志
- ✅ 其他脚本也可以轻松集成日志功能

详细的模块使用说明请参考 [README_LOGGER.md](./README_LOGGER.md)

### 主要改进

1. **双输出**：日志同时输出到文件和控制台
2. **自动归档**：按日期创建日志文件（`monitor_YYYYMMDD.log`）
3. **日志级别**：区分 INFO、WARNING、ERROR 等不同级别
4. **文件持久化**：所有日志都保存在 `logs/` 目录中

---

## 📂 日志文件位置

```
tushare-mcp/
├── logs/                          # 日志目录
│   ├── monitor_20251226.log      # 今天的日志
│   ├── monitor_20251225.log      # 昨天的日志
│   └── ...
├── monitor_intraday_signals.py
└── ...
```

---

## 📊 日志级别说明

### INFO（信息）
- 启动信息、配置信息
- 信号输出
- AI 分析结果

**示例**：
```
2025-12-26 18:10:29 - INFO - 开始盯盘：codes=['159218', '159840'] interval=60.0s
2025-12-26 18:10:29 - INFO - 模式：盘中做T信号（专注日内波动）
```

### WARNING（警告）
- 模块未安装
- 配置缺失
- AI 信号与规则不一致

**示例**：
```
2025-12-26 18:10:30 - WARNING - ⚠️ 规则策略与 AI 信号不一致，建议谨慎决策
```

### ERROR（错误）
- 获取信号失败
- API 调用失败
- 数据库连接失败

**示例**：
```
2025-12-26 18:10:35 - ERROR - [2025-12-26 18:10:35] 159218 获取信号失败: 连接超时
```

### DEBUG（调试）
- 飞书通知发送详情

---

## 🔍 日志格式

### 文件日志格式
```
2025-12-26 18:10:29 - INFO - 开始盯盘：codes=['159218', '159840']
│                      │      │
│                      │      └─ 日志内容
│                      └─ 日志级别
└─ 时间戳
```

### 控制台日志格式
```
开始盯盘：codes=['159218', '159840']
```
**注**：控制台只显示日志内容，不显示时间戳和级别，保持清爽。

---

## 📖 查看日志

### 1. 实时查看（tail）

```bash
cd /Users/huan.yu/dev/demo/stock/tushare-mcp

# 实时查看今天的日志
tail -f logs/monitor_$(date +%Y%m%d).log
```

### 2. 查看完整日志

```bash
# 查看今天的完整日志
cat logs/monitor_$(date +%Y%m%d).log

# 查看最近100行
tail -n 100 logs/monitor_$(date +%Y%m%d).log

# 搜索特定内容
grep "立即卖出" logs/monitor_$(date +%Y%m%d).log
```

### 3. 查看错误日志

```bash
# 只看错误和警告
grep -E "ERROR|WARNING" logs/monitor_$(date +%Y%m%d).log
```

---

## 📁 日志文件管理

### 自动清理旧日志

日志文件会持续积累，建议定期清理：

```bash
# 删除30天前的日志
find logs/ -name "monitor_*.log" -mtime +30 -delete

# 或者手动删除指定日期的日志
rm logs/monitor_20251120.log
```

### 定时清理（可选）

创建定时任务，每月清理一次：

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每月1号凌晨3点清理30天前的日志）
0 3 1 * * find /Users/huan.yu/dev/demo/stock/tushare-mcp/logs/ -name "monitor_*.log" -mtime +30 -delete
```

---

## 🔧 日志配置

### 修改日志级别

如果需要更详细的调试信息，可以修改 `monitor_intraday_signals.py` 中的配置：

```python
def setup_logging(log_dir: str = "logs") -> logging.Logger:
    # ...
    logger.setLevel(logging.DEBUG)  # 改为 DEBUG 级别
    # ...
    console_handler.setLevel(logging.DEBUG)  # 控制台也显示 DEBUG
```

### 修改日志格式

```python
file_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',  # 添加 name
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

### 修改日志文件名

```python
# 按小时创建日志文件
log_file = log_path / f"monitor_{datetime.now().strftime('%Y%m%d_%H')}.log"

# 或者统一的日志文件（会持续追加）
log_file = log_path / "monitor.log"
```

---

## 💡 使用场景

### 场景 1：监控运行状态

```bash
# 实时查看监控输出
cd /Users/huan.yu/dev/demo/stock/tushare-mcp
uv run python monitor_intraday_signals.py

# 另开一个终端，实时查看日志文件
tail -f logs/monitor_$(date +%Y%m%d).log
```

### 场景 2：分析历史信号

```bash
# 查看今天所有的买卖信号
grep -E "立即买入|立即卖出" logs/monitor_$(date +%Y%m%d).log

# 查看某个标的的所有信号
grep "159218" logs/monitor_$(date +%Y%m%d).log | grep -E "立即买入|立即卖出"
```

### 场景 3：排查问题

```bash
# 查看所有错误
grep "ERROR" logs/monitor_$(date +%Y%m%d).log

# 查看 API 调用失败的记录
grep "DeepSeek AI 调用失败" logs/monitor_$(date +%Y%m%d).log
```

### 场景 4：统计分析

```bash
# 统计今天触发了多少次买入信号
grep -c "立即买入" logs/monitor_$(date +%Y%m%d).log

# 统计今天触发了多少次卖出信号
grep -c "立即卖出" logs/monitor_$(date +%Y%m%d).log
```

---

## 📊 日志示例

### 完整的信号日志

```
2025-12-26 18:10:29 - INFO - 开始盯盘：codes=['159218', '159840'] interval=60.0s
2025-12-26 18:10:29 - INFO - 模式：盘中做T信号（专注日内波动）
2025-12-26 18:10:29 - INFO - 打印模式：仅显示买入/卖出信号
2025-12-26 18:10:29 - INFO - 飞书通知已启用
2025-12-26 18:10:29 - INFO - DeepSeek AI 辅助分析已启用
2025-12-26 18:10:35 - INFO - 
==================================================
⏰ 18:10:35  |  159218
==================================================
🔴 卖出  【立即卖出】
──────────────────────────────────────────────────
💰 执行价格: 1.625
📊 建议数量: 23.7%
🛡️ 止损价格: 1.640
🎯 目标价格: 1.510
──────────────────────────────────────────────────
💡 原因: 价格已大幅偏离均线，日内冲高后高位滞涨
==================================================

2025-12-26 18:10:36 - DEBUG - 给 Lark 机器人发送推送
```

---

## 🚀 最佳实践

1. **每日检查日志**：查看是否有错误或警告
2. **定期清理**：避免日志文件占用过多磁盘空间
3. **备份重要日志**：有重要信号时，备份当天的日志文件
4. **分析历史**：回顾历史信号，优化策略

---

## 📚 相关文档

- [CONFIG_GUIDE.md](./CONFIG_GUIDE.md) - 配置说明
- [AI_SIGNAL_GUIDE.md](./AI_SIGNAL_GUIDE.md) - AI 信号指南
- [QUICKSTART.md](./QUICKSTART.md) - 快速开始

---

**日志系统让你的监控更专业、更可靠！** 📝

