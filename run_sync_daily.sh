#!/bin/bash
# -*- coding: utf-8 -*-
#
# Tushare 日线数据同步脚本
# 建议使用 crontab 定时执行（每日收盘后）
#
# crontab 示例（每个交易日 16:00 执行）：
# 0 16 * * 1-5 cd /path/to/stock-ai && ./run_sync_daily.sh >> logs/sync_daily.log 2>&1
#

set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 加载环境变量（如果存在 .env 文件）
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# 检查必需的环境变量
if [ -z "$TUSHARE_TOKEN" ]; then
    echo "❌ 错误：未设置 TUSHARE_TOKEN 环境变量"
    exit 1
fi

if [ -z "$MYSQL_URL" ]; then
    echo "❌ 错误：未设置 MYSQL_URL 环境变量"
    exit 1
fi

# 执行增量同步
echo "=========================================="
echo "开始同步 Tushare 日线数据..."
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 使用推荐的按日期批量拉取模式（无需 stock_basic 接口）
# --mode by_date: 按日期批量拉取全市场数据
# --days 7: 回溯 7 天（补齐周末和节假日数据）
# --sleep 2.0: 每次调用间隔 2 秒
# --max-calls 40: 每分钟最多 40 次调用（Tushare 限制 50 次）
uv run python scripts/sync_tushare_daily_to_mysql.py \
    --mode by_date \
    --days 7 \
    --sleep 2.0 \
    --max-calls 40

echo ""
echo "=========================================="
echo "同步完成"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

