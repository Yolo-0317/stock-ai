#!/bin/bash

# ===================================
# 股票盯盘监控脚本启动器
# ===================================

# 1. 配置 MySQL 连接（必需）
# 请根据实际情况修改用户名、密码、主机、端口、数据库名
export MYSQL_URL="mysql+pymysql://root:password@localhost:3306/stock_data"

# 2. 配置 DeepSeek API Key（可选，如果启用了 DeepSeek AI 分析）
# 访问 https://platform.deepseek.com/ 获取
export DEEPSEEK_API_KEY="sk-your-api-key-here"

# 3. 验证配置
echo "========================================"
echo "环境变量配置："
echo "========================================"
if [ -n "$MYSQL_URL" ]; then
    echo "✓ MYSQL_URL: ${MYSQL_URL}"
else
    echo "✗ MYSQL_URL 未设置（必需）"
    exit 1
fi

if [ -n "$DEEPSEEK_API_KEY" ]; then
    echo "✓ DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY:0:10}..."
else
    echo "⚠ DEEPSEEK_API_KEY 未设置（如果启用了 DeepSeek AI 会报错）"
fi

echo "========================================"
echo ""

# 4. 启动监控
echo "正在启动盯盘监控..."
uv run python monitor_intraday_signals.py

