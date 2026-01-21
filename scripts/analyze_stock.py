#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析指定股票的MA特征
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine

def analyze_stock(ts_code: str):
    """分析股票的MA特征"""
    engine = create_engine(os.getenv("MYSQL_URL"))
    
    # 查询最近60天的数据
    query = f"""
    SELECT 
        trade_date,
        open,
        high,
        low,
        close,
        pct_chg,
        vol,
        amount
    FROM stock_daily
    WHERE ts_code = '{ts_code}'
    ORDER BY trade_date DESC
    LIMIT 60
    """
    
    df = pd.read_sql(query, engine)
    df = df.sort_values('trade_date').reset_index(drop=True)
    
    if df.empty:
        print(f"❌ 未找到股票 {ts_code} 的数据")
        return
    
    # 计算MA5, MA10, MA20, MA60
    df['MA5'] = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    
    # 计算乖离率
    df['dev_ma5'] = ((df['close'] - df['MA5']) / df['MA5'] * 100)
    df['dev_ma10'] = ((df['close'] - df['MA10']) / df['MA10'] * 100)
    df['dev_ma20'] = ((df['close'] - df['MA20']) / df['MA20'] * 100)
    
    # 最近10天
    print("=" * 100)
    print(f"{ts_code} 最近10个交易日数据")
    print("=" * 100)
    recent = df.tail(10)
    for idx, row in recent.iterrows():
        print(f"\n{row['trade_date'].strftime('%Y-%m-%d')}  收盘: {row['close']:.2f}  涨幅: {row['pct_chg']:+.2f}%")
        print(f"  MA5: {row['MA5']:.2f}  MA10: {row['MA10']:.2f}  MA20: {row['MA20']:.2f}")
        print(f"  乖离率 MA5: {row['dev_ma5']:+.2f}%  MA10: {row['dev_ma10']:+.2f}%  MA20: {row['dev_ma20']:+.2f}%")
        print(f"  最高: {row['high']:.2f}  最低: {row['low']:.2f}  成交额: {row['amount']:.0f}万")
    
    # 当前特征
    latest = df.iloc[-1]
    print("\n" + "=" * 100)
    print(f"{ts_code} 当前特征分析（{latest['trade_date'].strftime('%Y-%m-%d')}）")
    print("=" * 100)
    
    print(f"\n📊 价格与均线:")
    print(f"  收盘价: {latest['close']:.2f}")
    print(f"  MA5:   {latest['MA5']:.2f}  (乖离: {latest['dev_ma5']:+.2f}%)")
    print(f"  MA10:  {latest['MA10']:.2f}  (乖离: {latest['dev_ma10']:+.2f}%)")
    print(f"  MA20:  {latest['MA20']:.2f}  (乖离: {latest['dev_ma20']:+.2f}%)")
    
    print(f"\n📈 均线排列:")
    if latest['MA5'] > latest['MA10'] > latest['MA20']:
        print(f"  ✅ 完美多头 (MA5 > MA10 > MA20)")
    elif latest['close'] > latest['MA5'] > latest['MA10']:
        print(f"  ✅ 强势多头 (价格 > MA5 > MA10)")
    elif latest['MA5'] > latest['MA10']:
        print(f"  ⚠️  MA5 > MA10, 但MA10未高于MA20")
    else:
        print(f"  ❌ 非多头排列")
    
    print(f"\n  MA5 vs MA10: {((latest['MA5'] - latest['MA10']) / latest['MA10'] * 100):+.2f}%")
    print(f"  MA10 vs MA20: {((latest['MA10'] - latest['MA20']) / latest['MA20'] * 100):+.2f}%")
    
    # 近期涨幅
    print(f"\n📊 近期涨幅:")
    if len(df) >= 6:
        pct_5d = ((latest['close'] - df.iloc[-6]['close']) / df.iloc[-6]['close'] * 100)
        print(f"  近5日:  {pct_5d:+.2f}%")
    
    if len(df) >= 11:
        pct_10d = ((latest['close'] - df.iloc[-11]['close']) / df.iloc[-11]['close'] * 100)
        print(f"  近10日: {pct_10d:+.2f}%")
    
    if len(df) >= 21:
        pct_20d = ((latest['close'] - df.iloc[-21]['close']) / df.iloc[-21]['close'] * 100)
        print(f"  近20日: {pct_20d:+.2f}%")
    
    # MA增长率
    print(f"\n📈 均线增长率:")
    if len(df) >= 6:
        ma5_5days_ago = df.iloc[-6]['MA5']
        ma5_growth = ((latest['MA5'] - ma5_5days_ago) / ma5_5days_ago * 100) if pd.notna(ma5_5days_ago) else 0
        print(f"  MA5 (5日):  {ma5_growth:+.2f}%")
    
    if len(df) >= 11:
        ma10_10days_ago = df.iloc[-11]['MA10']
        ma10_growth = ((latest['MA10'] - ma10_10days_ago) / ma10_10days_ago * 100) if pd.notna(ma10_10days_ago) else 0
        print(f"  MA10 (10日): {ma10_growth:+.2f}%")
    
    # 近5日在MA5上方的天数
    print(f"\n📊 近期强势:")
    if len(df) >= 5:
        last_5_days = df.tail(6).iloc[:-1]  # 不包括今天
        days_above_ma5 = 0
        for i, row in last_5_days.iterrows():
            if pd.notna(row['MA5']) and row['close'] > row['MA5']:
                days_above_ma5 += 1
        print(f"  近5日在MA5上方: {days_above_ma5}/5 天")
    
    # 是否收阳线
    print(f"\n💹 今日K线:")
    is_yang = latest['close'] > latest['open']
    print(f"  开盘: {latest['open']:.2f}  收盘: {latest['close']:.2f}  {'✅ 阳线' if is_yang else '❌ 阴线'}")
    
    # 今日最低价是否触碰MA5
    if pd.notna(latest['MA5']):
        low_dev = ((latest['low'] - latest['MA5']) / latest['MA5'] * 100)
        print(f"  今日最低价相对MA5: {low_dev:+.2f}%")
        if abs(low_dev) <= 1.5:
            print(f"  ✅ 今日触碰MA5（±1.5%以内）")
        else:
            print(f"  ❌ 今日未触碰MA5")
    
    print("\n" + "=" * 100)

if __name__ == "__main__":
    import sys
    ts_code = sys.argv[1] if len(sys.argv) > 1 else "600783"
    analyze_stock(ts_code)

