#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
优化版：综合选股策略历史回测脚本
使用向量化计算和内存索引大幅提升速度
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

load_dotenv()

# 策略参数
BOX_PERIOD = 700
BOX_WIDTH_MAX = 80
THREE_UP_MIN_CHG = 1.0
THREE_UP_VOL_RATIO = 1.5
PULLBACK_PREV_STRENGTH = 20.0
PULLBACK_MA20_DIST = 3.0
MIN_PRICE = 5
MAX_PRICE = 100
MIN_AMOUNT = 5000

# 回测参数
BACKTEST_START_DATE = "20260101"
BACKTEST_END_DATE = "20260210"
HOLD_DAYS = [5, 10, 20]

def get_db_engine():
    return create_engine(os.getenv("MYSQL_URL"))

def main():
    engine = get_db_engine()
    
    print("1. 正在从数据库加载 2023 年至今的全量数据 (约需 10-20 秒)...")
    query = """
        SELECT ts_code, trade_date, open, high, low, close, pct_chg, amount, vol
        FROM stock_daily 
        WHERE trade_date >= '2023-01-01'
        ORDER BY ts_code, trade_date
    """
    df = pd.read_sql(text(query), engine)
    df['trade_date'] = pd.to_datetime(df['trade_date']).dt.date
    print(f"✓ 已加载 {len(df)} 条记录")

    print("2. 预计算技术指标 (向量化处理)...")
    # 预计算均线
    df['ma20'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(20).mean())
    df['ma5'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(5).mean())
    df['ma10'] = df.groupby('ts_code')['close'].transform(lambda x: x.rolling(10).mean())
    
    # 预计算20日前的价格用于空中加油
    df['close_20d_ago'] = df.groupby('ts_code')['close'].shift(20)
    
    # 预计算5日均成交额用于三连阳
    df['avg_amount_5'] = df.groupby('ts_code')['amount'].transform(lambda x: x.shift(1).rolling(5).mean())
    
    print("3. 开始逐日扫描信号...")
    all_dates = sorted(df['trade_date'].unique())
    backtest_dates = [d for d in all_dates if d >= datetime.strptime(BACKTEST_START_DATE, "%Y%m%d").date() 
                      and d <= datetime.strptime(BACKTEST_END_DATE, "%Y%m%d").date()]
    
    signals = []
    
    # 将数据按日期分组，提升查询效率
    for t_date in backtest_dates:
        day_df = df[df['trade_date'] == t_date].copy()
        # 基础过滤
        day_df = day_df[(day_df['close'] >= MIN_PRICE) & (day_df['close'] <= MAX_PRICE) & (day_df['amount'] >= MIN_AMOUNT)]
        
        if day_df.empty: continue
        
        print(f"  分析日期: {t_date} (候选股: {len(day_df)})", end='\r')
        
        for _, row in day_df.iterrows():
            ts_code = row['ts_code']
            close = row['close']
            
            # --- 策略检测 ---
            strat_tags = []
            
            # 1. 三连阳 (简化判断：今日涨幅>1% 且 成交额>均值)
            if row['pct_chg'] >= THREE_UP_MIN_CHG and row['amount'] > row['avg_amount_5'] * THREE_UP_VOL_RATIO:
                strat_tags.append("三连阳")
            
            # 2. 空中加油
            if not pd.isna(row['close_20d_ago']):
                prev_chg = (close - row['close_20d_ago']) / row['close_20d_ago'] * 100
                dist_ma20 = abs(close - row['ma20']) / row['ma20'] * 100 if row['ma20'] > 0 else 999
                if prev_chg >= PULLBACK_PREV_STRENGTH and dist_ma20 <= PULLBACK_MA20_DIST:
                    strat_tags.append("空中加油")
            
            if strat_tags:
                # 记录信号并计算未来收益
                future = df[(df['ts_code'] == ts_code) & (df['trade_date'] > t_date)].head(20)
                if not future.empty:
                    res = {'date': t_date, 'code': ts_code, 'strategy': ",".join(strat_tags)}
                    for d in HOLD_DAYS:
                        if len(future) >= d:
                            res[f'ret_{d}d'] = (future.iloc[d-1]['close'] - close) / close * 100
                    signals.append(res)

    print("\n\n4. 回测统计结果:")
    if not signals:
        print("❌ 未发现信号")
        return
        
    res_df = pd.DataFrame(signals)
    for strat in ["三连阳", "空中加油"]:
        s_df = res_df[res_df['strategy'].str.contains(strat)]
        if s_df.empty: continue
        print(f"\n【{strat}】(样本: {len(s_df)})")
        for d in HOLD_DAYS:
            col = f'ret_{d}d'
            if col in s_df.columns:
                valid = s_df.dropna(subset=[col])
                win_rate = (valid[col] > 0).mean() * 100
                avg_ret = valid[col].mean()
                print(f"  {d}日持有: 胜率 {win_rate:.1f}%, 平均收益 {avg_ret:.2f}%")

    output = "output/backtest_optimized.csv"
    res_df.to_csv(output, index=False, encoding='utf-8-sig')
    print(f"\n📄 明细已保存至: {output}")

if __name__ == "__main__":
    main()
