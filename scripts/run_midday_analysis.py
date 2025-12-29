#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
午盘分析脚本 - 每日午间运行（建议 11:30-12:00）

目标：基于盘中实时数据给出“午盘总结 + 午后操盘位置”。
实现上复用做T信号 `deepseek_intraday_t_signal`，其输出已包含：
- 操作指令（立即买入/立即卖出/暂不操作）
- 执行价/止损/目标
- 支撑/压力、买入/卖出区间
"""

import logging
import sys
from pathlib import Path

# 让 scripts/ 目录可 import _bootstrap
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dotenv import load_dotenv

from logger_config import setup_logging
from tushare_mcp import deepseek_intraday_t_signal
from code_names import code_label

# 加载环境变量（优先读取仓库根目录 .env）
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

# 配置
CODES = ["159218", "159840", "512400"]

# 是否发送飞书通知（午盘一般不需要推送，仅记录日志）
ENABLE_FEISHU = False


def main() -> int:
    logger = setup_logging(name="midday", log_level=logging.INFO, console_level=logging.INFO)

    logger.info("=" * 60)
    logger.info("☀️ 开始执行午盘分析...")
    logger.info("=" * 60)

    for code in CODES:
        logger.info(f"\n正在分析 {code_label(code)}...")
        try:
            report = deepseek_intraday_t_signal(code=code, position_cost=None, position_ratio=0.0)
            cleaned = "\n".join([ln.lstrip() for ln in str(report).splitlines()]).strip()
            logger.info(f"\n{cleaned}\n")
        except Exception as e:
            logger.error(f"❌ {code_label(code)} 午盘分析失败: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("✅ 午盘分析完成")
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


