#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
综合选股策略：全周期牛股捕捉系统
集成三个核心逻辑：
1. 3年大底箱体突破 (Macro Breakout) - 宏观趋势反转
2. 低位放量三连阳 (Volume Surge) - 主力建仓异动
3. 空中加油 (MA20 Pullback) - 强势股二次拉升
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

load_dotenv()

# ============================================
# 策略参数
# ============================================

# 1. 3年大底参数
BOX_PERIOD = 700
BOX_WIDTH_MAX = 80
DIST_FROM_250D_HIGH_MAX = -2
DIST_FROM_250D_LOW_MAX = 100

# 2. 三连阳参数
THREE_UP_MIN_CHG = 1.0           # 每日最小涨幅
THREE_UP_TOTAL_CHG_MAX = 15.0    # 3日累计最大涨幅（避免追高）
THREE_UP_VOL_RATIO = 1.5         # 成交额相对于5日均值的倍数

# 3. 空中加油参数
PULLBACK_MA20_DIST = 3.0         # 距离MA20的最大距离（%）
PULLBACK_PREV_STRENGTH = 20.0    # 前期20日涨幅要求（%）
PULLBACK_VOL_DECREASE = 0.8      # 回调时成交量相对于5日均值的比例（缩量）

# 基础过滤
MIN_PRICE = 5
MAX_PRICE = 100
MIN_AMOUNT = 5000  # 万

def get_db_engine():
    mysql_url = os.getenv("MYSQL_URL")
    return create_engine(mysql_url)

def get_latest_trade_date(engine):
    query = "SELECT MAX(trade_date) FROM stock_daily"
    with engine.connect() as conn:
        return conn.execute(text(query)).scalar().strftime("%Y%m%d")

def main(target_date=None):
    engine = get_db_engine()
    if target_date:
        trade_date = target_date
    else:
        trade_date = get_latest_trade_date(engine)
    print(f"🚀 开始综合选股扫描，基准日期：{trade_date}")
    
    # 获取1100天数据以支持3年大底计算
    end_date_obj = datetime.strptime(trade_date, "%Y%m%d")
    start_date_obj = end_date_obj - timedelta(days=1100)
    start_date = start_date_obj.strftime("%Y-%m-%d")
    end_date = end_date_obj.strftime("%Y-%m-%d")
    
    query = f"""
        SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
        FROM stock_daily
        WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY ts_code, trade_date
    """
    df_all = pd.read_sql(text(query), engine)
    print(f"✓ 已加载 {len(df_all)} 条记录")

    results = []
    for ts_code, group in df_all.groupby('ts_code'):
        group = group.sort_values('trade_date')
        if len(group) < 60: continue
        
        latest = group.iloc[-1]
        close_today = latest['close']
        amount_today = latest['amount']
        
        # 基础过滤
        if not (MIN_PRICE <= close_today <= MAX_PRICE): continue
        if amount_today < MIN_AMOUNT: continue
        
        # 均线计算
        ma5 = group['close'].tail(5).mean()
        ma10 = group['close'].tail(10).mean()
        ma20 = group['close'].tail(20).mean()
        ma60 = group['close'].tail(60).mean()
        
        # --- 策略1: 3年大底突破 ---
        is_breakout = False
        box_width = 0
        breakout_ratio = 0
        if len(group) >= BOX_PERIOD:
            box_data = group.iloc[-BOX_PERIOD:-10]
            box_high = box_data['high'].max()
            box_low = box_data['low'].min()
            box_width = (box_high - box_low) / box_low * 100
            breakout_ratio = (close_today - box_high) / box_high * 100
            
            high_250d = group['high'].tail(250).max()
            low_250d = group['low'].tail(250).min()
            dist_from_high = (close_today - high_250d) / high_250d * 100
            dist_from_low = (close_today - low_250d) / low_250d * 100
            
            if (box_width <= BOX_WIDTH_MAX and breakout_ratio >= 0 and 
                dist_from_high <= DIST_FROM_250D_HIGH_MAX and dist_from_low <= DIST_FROM_250D_LOW_MAX and
                ma5 > ma10 > ma20):
                is_breakout = True

        # --- 策略2: 低位放量三连阳 ---
        is_three_up = False
        if len(group) >= 10:
            recent_3 = group.tail(3)
            avg_amount_5 = group['amount'].iloc[-8:-3].mean()
            
            cond1 = (recent_3['pct_chg'] >= THREE_UP_MIN_CHG).all()
            cond2 = (recent_3['close'] > recent_3['open']).all()
            cond3 = (recent_3['amount'] > avg_amount_5 * THREE_UP_VOL_RATIO).any()
            cond4 = (close_today - group['close'].iloc[-4]) / group['close'].iloc[-4] * 100 <= THREE_UP_TOTAL_CHG_MAX
            
            # 确保是在相对低位（距250日高点跌幅超过30%）
            high_250d = group['high'].tail(250).max()
            is_low = (close_today - high_250d) / high_250d * 100 < -30
            
            if cond1 and cond2 and cond3 and cond4 and is_low:
                is_three_up = True

        # --- 策略3: 空中加油 (MA20回踩) ---
        is_pullback = False
        if len(group) >= 30:
            prev_20d_chg = (group['close'].iloc[-5] - group['close'].iloc[-25]) / group['close'].iloc[-25] * 100
            dist_to_ma20 = abs(close_today - ma20) / ma20 * 100
            avg_amount_5 = group['amount'].iloc[-10:-5].mean()
            vol_ratio = amount_today / avg_amount_5
            
            if (prev_20d_chg >= PULLBACK_PREV_STRENGTH and 
                dist_to_ma20 <= PULLBACK_MA20_DIST and 
                vol_ratio <= PULLBACK_VOL_DECREASE and
                close_today >= ma20):
                is_pullback = True

        # 记录结果
        if is_breakout or is_three_up or is_pullback:
            tags = []
            if is_breakout: tags.append("大底突破")
            if is_three_up: tags.append("三连阳")
            if is_pullback: tags.append("空中加油")
            
            results.append({
                '代码': ts_code,
                '收盘价': close_today,
                '涨幅%': latest['pct_chg'],
                '成交额(万)': amount_today,
                '策略标签': ",".join(tags),
                '标签数': len(tags)
            })

    if not results:
        print("❌ 未筛选出符合任何策略的股票")
        return

    res_df = pd.DataFrame(results).sort_values(by=['标签数', '成交额(万)'], ascending=False)
    output_path = f"output/stock_selection_combined_{trade_date}.csv"
    res_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print("\n" + "="*50)
    print(f"✅ 综合选股完成！共筛选出 {len(res_df)} 只股票")
    print(f"📄 结果已保存至：{output_path}")
    print("="*50)
    print(res_df.head(20))

if __name__ == "__main__":
    # 如果想跑历史某一天，可以在这里指定，例如：
    # main("20260120")
    main()
