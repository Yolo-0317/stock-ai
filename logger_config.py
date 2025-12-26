"""
日志配置模块
提供统一的日志配置，支持同时输出到文件和控制台
"""

import logging
from pathlib import Path
from datetime import datetime


def setup_logging(
    name: str = "stock_monitor",
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    console_level: int = logging.INFO,
    log_format: str = "%(asctime)s - %(levelname)s - %(message)s",
    date_format: str = "%Y-%m-%d %H:%M:%S",
) -> logging.Logger:
    """
    配置日志系统，同时输出到文件和控制台
    
    Args:
        name: logger 名称
        log_dir: 日志目录（相对于脚本所在目录）
        log_level: 文件日志级别
        console_level: 控制台日志级别
        log_format: 日志格式
        date_format: 时间格式
    
    Returns:
        配置好的 logger 对象
    
    示例:
        >>> from logger_config import setup_logging
        >>> logger = setup_logging("my_script")
        >>> logger.info("开始运行")
    """
    # 创建日志目录（在调用者的目录中创建）
    import inspect
    caller_frame = inspect.stack()[1]
    caller_file = Path(caller_frame.filename)
    log_path = caller_file.parent / log_dir
    log_path.mkdir(exist_ok=True)

    # 日志文件名：{name}_YYYYMMDD.log
    log_file = log_path / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

    # 创建或获取 logger
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # 清除所有已存在的 handlers，避免重复
    logger.handlers.clear()

    # 文件 handler（记录所有日志）
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_formatter = logging.Formatter(log_format, datefmt=date_format)
    file_handler.setFormatter(file_formatter)

    # 控制台 handler（只显示重要信息，格式简洁）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # 阻止日志传播到根 logger，避免重复输出
    logger.propagate = False

    return logger


def get_logger(name: str = "stock_monitor") -> logging.Logger:
    """
    获取已配置的 logger，如果不存在则创建新的
    
    Args:
        name: logger 名称
    
    Returns:
        logger 对象
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        # 如果 logger 还没有配置，则使用默认配置
        return setup_logging(name)
    return logger


# 预设配置函数

def setup_monitor_logging() -> logging.Logger:
    """监控脚本的日志配置"""
    return setup_logging(
        name="monitor",
        log_dir="logs",
        log_level=logging.INFO,
        console_level=logging.INFO,
    )


def setup_ingest_logging() -> logging.Logger:
    """数据导入脚本的日志配置"""
    return setup_logging(
        name="ingest",
        log_dir="logs",
        log_level=logging.INFO,
        console_level=logging.INFO,
    )


def setup_debug_logging() -> logging.Logger:
    """调试模式的日志配置（输出更详细的信息）"""
    return setup_logging(
        name="debug",
        log_dir="logs",
        log_level=logging.DEBUG,
        console_level=logging.DEBUG,
    )


if __name__ == "__main__":
    # 测试日志配置
    logger = setup_logging("test")
    
    logger.debug("这是 DEBUG 级别日志")
    logger.info("这是 INFO 级别日志")
    logger.warning("这是 WARNING 级别日志")
    logger.error("这是 ERROR 级别日志")
    
    print(f"\n日志文件已创建：logs/test_{datetime.now().strftime('%Y%m%d')}.log")
    print(f"Logger handlers 数量: {len(logger.handlers)}")
    print(f"Logger propagate: {logger.propagate}")

