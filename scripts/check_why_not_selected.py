#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查某只股票为什么没被选出来
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from sqlalchemy import create_engine

# 策略参数（从stock_selection_ma5.py复制）
MIN_PRICE = 5.0
MAX_PRICE = 30.0
MIN_AMOUNT = 5000.0
MIN_DEVIATION_MA10 = 0.0
MAX_DEVIATION_MA10 = 3.0
MAX_MA5_MA10_GAP = 2.0
MIN_DAYS_ABOVE_MA10 = 4
MA10_GROWTH_RATE = 0.3
MIN_10D_CHG = 3.0
MAX_10D_CHG = 15.0

def check_stock(ts_code: str, trade_date: str = None):
    """检查某只股票是否符合策略条件"""
    engine = create_engine(os.getenv("MYSQL_URL"))
    
    # 确定交易日期
    if not trade_date:
        query = "SELECT MAX(trade_date) as latest_date FROM stock_daily"
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text(query))
            row = result.fetchone()
            trade_date_obj = row[0]
            trade_date = trade_date_obj.strftime("%Y%m%d")
    else:
        trade_date_obj = datetime.strptime(trade_date, "%Y%m%d").date()
    
    print(f"\n检查股票 {ts_code} 在 {trade_date} 的筛选情况")
    print("=" * 80)
    
    # 查询数据
    start_date = (trade_date_obj - timedelta(days=150)).strftime("%Y-%m-%d")
    end_date = trade_date_obj.strftime("%Y-%m-%d")
    
    query = f"""
    SELECT trade_date, open, high, low, close, pct_chg, vol, amount
    FROM stock_daily
    WHERE ts_code = '{ts_code}'
    AND trade_date BETWEEN '{start_date}' AND '{end_date}'
    ORDER BY trade_date
    """
    
    df = pd.read_sql(query, engine)
    
    if df.empty:
        print(f"❌ 未找到股票 {ts_code} 的数据")
        return
    
    # 找到目标日期
    target_row = df[df['trade_date'] == trade_date_obj]
    if target_row.empty:
        print(f"❌ 未找到 {trade_date} 的数据")
        return
    
    target_idx = target_row.index[0]
    target_row = target_row.iloc[0]
    
    # 计算指标
    hist_data = df.loc[:target_idx]
    
    # MA5, MA10, MA20, MA60
    ma5 = hist_data['close'].tail(5).mean()
    ma10 = hist_data['close'].tail(10).mean()
    ma20 = hist_data['close'].tail(20).mean()
    ma60 = hist_data['close'].tail(60).mean()
    
    # 乖离率
    dev_ma10 = ((target_row['close'] - ma10) / ma10 * 100)
    ma5_ma10_gap = ((ma5 - ma10) / ma10 * 100)
    
    # 近5日在MA10上方的天数
    if len(hist_data) >= 6:
        last_5d = df.loc[target_idx-5:target_idx-1]
        days_above_ma10 = 0
        for i, row in last_5d.iterrows():
            hist_for_ma10 = df.loc[:i]
            if len(hist_for_ma10) >= 10:
                ma10_that_day = hist_for_ma10['close'].tail(10).mean()
                if row['close'] > ma10_that_day:
                    days_above_ma10 += 1
    else:
        days_above_ma10 = 0
    
    # MA10增长率
    if len(hist_data) >= 20:
        ma10_10days_ago = df.loc[target_idx-19:target_idx-10, 'close'].mean()
        ma10_growth = ((ma10 - ma10_10days_ago) / ma10_10days_ago * 100)
    else:
        ma10_growth = 0
    
    # 近10日涨幅
    if len(hist_data) >= 11:
        close_10d_ago = df.iloc[target_idx-10]['close']
        pct_10d = ((target_row['close'] - close_10d_ago) / close_10d_ago * 100)
    else:
        pct_10d = 0
    
    # 打印结果
    print(f"\n📊 基本信息:")
    print(f"  收盘价: {target_row['close']:.2f}  涨幅: {target_row['pct_chg']:+.2f}%")
    print(f"  成交额: {target_row['amount']:.0f}万")
    
    print(f"\n📈 均线数据:")
    print(f"  MA5:  {ma5:.2f}")
    print(f"  MA10: {ma10:.2f}")
    print(f"  MA20: {ma20:.2f}")
    print(f"  MA60: {ma60:.2f}")
    
    print(f"\n🔍 策略条件检查:")
    
    # 1. 价格区间
    check1 = MIN_PRICE <= target_row['close'] <= MAX_PRICE
    print(f"  1. 价格区间({MIN_PRICE}-{MAX_PRICE}元): {target_row['close']:.2f}  {'✅' if check1 else '❌'}")
    
    # 2. 成交额
    check2 = target_row['amount'] > MIN_AMOUNT
    print(f"  2. 成交额(>{MIN_AMOUNT}万): {target_row['amount']:.0f}  {'✅' if check2 else '❌'}")
    
    # 3. 价格位置
    check3 = MIN_DEVIATION_MA10 <= dev_ma10 <= MAX_DEVIATION_MA10
    print(f"  3. 价格相对MA10({MIN_DEVIATION_MA10}%-{MAX_DEVIATION_MA10}%): {dev_ma10:+.2f}%  {'✅' if check3 else '❌'}")
    
    # 4. MA5-MA10距离
    check4 = ma5_ma10_gap <= MAX_MA5_MA10_GAP
    print(f"  4. MA5-MA10距离(<{MAX_MA5_MA10_GAP}%): {ma5_ma10_gap:.2f}%  {'✅' if check4 else '❌'}")
    
    # 5. 完美多头
    check5 = ma5 > ma10 > ma20 > ma60
    print(f"  5. 完美多头排列(MA5>MA10>MA20>MA60): {'✅' if check5 else '❌'}")
    if not check5:
        print(f"     实际: MA5({ma5:.2f}) {'>' if ma5>ma10 else '<'} MA10({ma10:.2f}) {'>' if ma10>ma20 else '<'} MA20({ma20:.2f}) {'>' if ma20>ma60 else '<'} MA60({ma60:.2f})")
    
    # 6. 近5日强势
    check6 = days_above_ma10 >= MIN_DAYS_ABOVE_MA10
    print(f"  6. 近5日强势(>={MIN_DAYS_ABOVE_MA10}天在MA10上方): {days_above_ma10}/5天  {'✅' if check6 else '❌'}")
    
    # 7. MA10向上
    check7 = ma10_growth > MA10_GROWTH_RATE
    print(f"  7. MA10向上(>{MA10_GROWTH_RATE}%): {ma10_growth:+.2f}%  {'✅' if check7 else '❌'}")
    
    # 8. 近10日涨幅
    check8 = MIN_10D_CHG <= pct_10d <= MAX_10D_CHG
    print(f"  8. 近10日涨幅({MIN_10D_CHG}%-{MAX_10D_CHG}%): {pct_10d:+.2f}%  {'✅' if check8 else '❌'}")
    
    # 总结
    all_checks = [check1, check2, check3, check4, check5, check6, check7, check8]
    passed = sum(all_checks)
    
    print(f"\n{'='*80}")
    print(f"✅ 通过: {passed}/8 个条件")
    
    if passed == 8:
        print(f"🎉 {ts_code} 符合所有条件！应该被选出")
    else:
        print(f"❌ {ts_code} 不符合条件，未通过:")
        if not check1: print("   - 价格区间")
        if not check2: print("   - 成交额")
        if not check3: print(f"   - 价格位置（{dev_ma10:+.2f}% 不在{MIN_DEVIATION_MA10}%-{MAX_DEVIATION_MA10}%范围）")
        if not check4: print(f"   - MA5-MA10距离（{ma5_ma10_gap:.2f}% > {MAX_MA5_MA10_GAP}%）")
        if not check5: print("   - 多头排列")
        if not check6: print(f"   - 近5日强势（只有{days_above_ma10}天）")
        if not check7: print(f"   - MA10向上（增长率{ma10_growth:+.2f}% < {MA10_GROWTH_RATE}%）")
        if not check8: print(f"   - 近10日涨幅（{pct_10d:+.2f}% 不在{MIN_10D_CHG}%-{MAX_10D_CHG}%范围）")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    ts_code = sys.argv[1] if len(sys.argv) > 1 else "600783"
    trade_date = sys.argv[2] if len(sys.argv) > 2 else None
    check_stock(ts_code, trade_date)

