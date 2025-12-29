#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘后分析脚本 - 每日收盘后运行

建议运行时间：每个交易日 15:30 - 16:00
"""

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

from feishu_notice import send_to_lark
from logger_config import setup_logging
from code_names import code_label

# 导入分析函数
from tushare_mcp import deepseek_aftermarket_analysis

# 配置
CODES = ["159218", "159840", "512400"]  # 关注的股票
# 持仓成本
POSITION_COSTS = {
    "159218": 1.197,
    "512400": None,
    "159840": 0.869,
}
# 仓位比例
POSITION_RATIOS = {
    "159218": 0.2374,
    "512400": None,
    "159840": 0.1058,
}

# 是否发送飞书通知（盘后分析不需要推送，仅记录日志）
ENABLE_FEISHU = False


def main():
    """执行盘后分析"""
    # 初始化日志
    logger = setup_logging(
        name="aftermarket",
        log_level=logging.INFO,
        console_level=logging.INFO,
    )

    logger.info("=" * 60)
    logger.info("🌙 开始执行盘后分析...")
    logger.info("=" * 60)

    results = []

    for code in CODES:
        logger.info(f"\n正在分析 {code_label(code)}...")

        try:
            # 执行盘后分析
            report = deepseek_aftermarket_analysis(
                code=code,
                position_cost=POSITION_COSTS.get(code),
                position_ratio=POSITION_RATIOS.get(code, 0.0),
            )

            # 打印到控制台和日志
            logger.info(f"\n{report}")
            results.append(report)

        except Exception as e:
            error_msg = f"❌ {code_label(code)} 盘后分析失败: {e}"
            logger.error(error_msg)
            results.append(error_msg)

    # 发送飞书通知（合并所有结果）
    if ENABLE_FEISHU:
        combined_report = "\n\n".join(results)
        try:
            send_to_lark(combined_report, is_error=False)
            logger.info("\n✅ 已发送飞书通知")
        except Exception as e:
            logger.error(f"\n❌ 发送飞书通知失败: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 盘后分析完成")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
