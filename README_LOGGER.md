# 📝 日志配置模块使用说明

## 📁 文件结构

```
tushare-mcp/
├── logger_config.py           # 日志配置模块（可复用）
├── monitor_intraday_signals.py  # 使用日志
├── feishu_notice.py            # 使用日志
└── logs/                       # 日志文件目录
    ├── monitor_20251226.log
    ├── ingest_20251226.log
    └── ...
```

---

## 🚀 快速开始

### 1. 基本使用

```python
from logger_config import setup_monitor_logging

# 初始化日志
logger = setup_monitor_logging()

# 使用日志
logger.info("这是信息日志")
logger.warning("这是警告日志")
logger.error("这是错误日志")
```

### 2. 自定义配置

```python
from logger_config import setup_logging

# 自定义配置
logger = setup_logging(
    name="my_script",          # 日志名称
    log_dir="logs",             # 日志目录
    log_level=logging.INFO,     # 文件日志级别
    console_level=logging.INFO, # 控制台日志级别
)

logger.info("开始运行")
```

### 3. 获取已配置的 Logger

```python
from logger_config import get_logger

# 获取已配置的 logger（如果不存在会自动创建）
logger = get_logger("monitor")

logger.info("使用已存在的 logger")
```

---

## 🎯 预设配置函数

### 监控脚本日志

```python
from logger_config import setup_monitor_logging

logger = setup_monitor_logging()
# 日志文件: logs/monitor_YYYYMMDD.log
```

### 数据导入脚本日志

```python
from logger_config import setup_ingest_logging

logger = setup_ingest_logging()
# 日志文件: logs/ingest_YYYYMMDD.log
```

### 调试模式日志

```python
from logger_config import setup_debug_logging

logger = setup_debug_logging()
# 输出 DEBUG 级别的详细信息
```

---

## 📊 日志级别

- **DEBUG**: 详细的调试信息
- **INFO**: 一般信息（默认）
- **WARNING**: 警告信息
- **ERROR**: 错误信息
- **CRITICAL**: 严重错误

---

## 🔧 高级配置

### 自定义日志格式

```python
logger = setup_logging(
    name="custom",
    log_format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    date_format="%Y-%m-%d %H:%M:%S.%f",
)
```

### 只输出到文件（不输出到控制台）

```python
import logging

logger = setup_logging(
    name="silent",
    console_level=logging.CRITICAL,  # 控制台只显示 CRITICAL 级别
)
```

### 只输出到控制台（不记录文件）

需要手动修改 `logger_config.py` 或者移除 file_handler：

```python
logger = setup_logging(name="console_only")
# 移除文件 handler
logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
```

---

## 📂 在其他脚本中使用

### 示例：在数据导入脚本中使用

```python
# ingest_eastmoney_daily_to_mysql.py

from logger_config import setup_ingest_logging

# 初始化日志
logger = setup_ingest_logging()

def main():
    logger.info("开始导入数据")
    
    try:
        # 数据导入逻辑
        logger.info("成功导入 100 条数据")
    except Exception as e:
        logger.error(f"导入失败: {e}")
    
    logger.info("数据导入完成")

if __name__ == "__main__":
    main()
```

### 示例：在测试脚本中使用

```python
# test_my_feature.py

from logger_config import setup_logging
import logging

# 调试模式：输出详细信息
logger = setup_logging(
    name="test",
    log_level=logging.DEBUG,
    console_level=logging.DEBUG,
)

logger.debug("开始测试")
logger.info("测试通过")
```

---

## 💡 最佳实践

### 1. 统一的日志名称

- **监控脚本**: `monitor`
- **数据导入**: `ingest`
- **测试脚本**: `test`
- **其他脚本**: 使用脚本名称

### 2. 合理使用日志级别

```python
# ✅ 正常流程
logger.info("开始盯盘")
logger.info("发现买入信号")

# ✅ 配置问题
logger.warning("未找到 .env 文件")

# ✅ 错误情况
logger.error("API 调用失败")

# ❌ 不要滥用 INFO
logger.info("变量 x = 123")  # 应该用 DEBUG
```

### 3. 日志文件管理

```bash
# 定期清理旧日志（保留 30 天）
find logs/ -name "*.log" -mtime +30 -delete

# 查看今天的日志
tail -f logs/monitor_$(date +%Y%m%d).log

# 搜索错误日志
grep "ERROR" logs/monitor_$(date +%Y%m%d).log
```

---

## 🔍 故障排查

### 问题 1：日志重复输出

**原因**：多次调用 `setup_logging()` 导致重复添加 handlers

**解决**：使用 `get_logger()` 获取已配置的 logger

```python
# ✅ 正确
from logger_config import get_logger
logger = get_logger("monitor")

# ❌ 错误（重复配置）
from logger_config import setup_monitor_logging
logger = setup_monitor_logging()  # 第一次
logger = setup_monitor_logging()  # 第二次（重复）
```

### 问题 2：日志文件未创建

**原因**：权限不足或目录不存在

**解决**：
```bash
# 检查目录权限
ls -la logs/

# 手动创建目录
mkdir -p logs/
chmod 755 logs/
```

### 问题 3：控制台不输出日志

**原因**：日志级别设置过高

**解决**：
```python
logger = setup_logging(
    console_level=logging.DEBUG,  # 降低级别
)
```

---

## 📚 相关文档

- [LOGGING_GUIDE.md](./LOGGING_GUIDE.md) - 详细的日志使用指南
- [CONFIG_GUIDE.md](./CONFIG_GUIDE.md) - 监控脚本配置说明

---

**通过模块化的日志配置，让代码更清晰、更易维护！** 🚀

