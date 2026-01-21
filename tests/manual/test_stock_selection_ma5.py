#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试沿MA5上行回调买入选股策略

使用方法：
    # 测试最新交易日
    uv run python tests/manual/test_stock_selection_ma5.py
    
    # 测试指定日期
    uv run python tests/manual/test_stock_selection_ma5.py --date 20260107
"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.stock_selection_ma5 import main

if __name__ == "__main__":
    main()

