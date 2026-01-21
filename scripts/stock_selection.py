#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
量价齐升突破选股策略

策略逻辑：
1. 基础过滤：排除北交所、价格区间5-30元、成交额>5000万、至少65个交易日数据
2. 今日涨幅：3% - 9%
3. 放量：今日量 > 近5日均量 × 1.5
4. 多头排列：收盘价 > MA5 > MA20 > MA60
5. 近5日累计涨幅 < 20%
6. 按量比降序排序

使用方法：
    # 默认使用最新交易日
    uv run python scripts/stock_selection.py
    
    # 指定交易日期
    uv run python scripts/stock_selection.py --date 20260107

输出：
    output/stock_selection_YYYYMMDD.csv
"""

from __future__ import annotations

import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

import pandas as pd
from sqlalchemy import create_engine, text


# ============================================
# 配置参数
# ============================================

# 策略参数
MIN_PRICE = 5.0              # 最低价格
MAX_PRICE = 30.0             # 最高价格
MIN_AMOUNT = 5000.0          # 最低成交额（万元）
MIN_PCT_CHG = 3.0            # 最低涨幅（%）
MAX_PCT_CHG = 9.0            # 最高涨幅（%）
VOLUME_RATIO = 1.5           # 量比阈值
MAX_5D_CHG = 20.0            # 近5日最大涨幅（%）
MIN_HISTORY_DAYS = 65        # 最少历史数据天数

# 输出目录
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"


# ============================================
# 数据库连接
# ============================================

def get_db_engine():
    """获取数据库连接"""
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        raise ValueError("❌ 环境变量 MYSQL_URL 未设置")
    return create_engine(mysql_url, pool_pre_ping=True, pool_recycle=3600)


# ============================================
# 数据获取
# ============================================

def get_latest_trade_date(engine) -> str:
    """获取数据库中最新的交易日期"""
    query = """
        SELECT MAX(trade_date) as latest_date
        FROM stock_daily
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        row = result.fetchone()
        if row and row[0]:
            return row[0].strftime("%Y%m%d")
        else:
            raise ValueError("❌ 数据库中没有数据")


def get_stock_data(engine, trade_date: str, days_back: int = 90) -> pd.DataFrame:
    """
    获取指定交易日及之前N天的股票数据
    
    参数：
    - trade_date: 目标交易日（YYYYMMDD）
    - days_back: 向前查询天数（默认90天，确保有足够数据计算MA60）
    
    返回：
    - DataFrame: 包含股票代码、交易日期、价格、成交量等字段
    """
    target_date = datetime.strptime(trade_date, "%Y%m%d").date()
    start_date = (target_date - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end_date = target_date.strftime("%Y-%m-%d")
    
    query = f"""
        SELECT 
            ts_code,
            exch_code,
            trade_date,
            open,
            high,
            low,
            close,
            pre_close,
            pct_chg,
            vol,
            amount
        FROM stock_daily
        WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'
        AND exch_code IN ('SZ', 'SH')  -- 只选沪深股票，排除北交所
        ORDER BY ts_code, trade_date
    """
    
    print(f"正在查询数据（{start_date} 至 {end_date}）...")
    df = pd.read_sql(query, engine)
    print(f"✓ 查询到 {len(df)} 条记录")
    
    return df


# ============================================
# 技术指标计算
# ============================================

def calculate_indicators(df: pd.DataFrame, target_date: str) -> pd.DataFrame:
    """
    计算技术指标
    
    参数：
    - df: 原始数据（包含历史数据）
    - target_date: 目标交易日（YYYYMMDD）
    
    返回：
    - DataFrame: 目标交易日的数据 + 技术指标
    """
    target_date_obj = datetime.strptime(target_date, "%Y%m%d").date()
    
    # 按股票分组计算指标
    results = []
    
    for ts_code, group in df.groupby('ts_code'):
        # 按日期排序
        group = group.sort_values('trade_date')
        
        # 检查是否有足够的历史数据（至少65个交易日）
        if len(group) < MIN_HISTORY_DAYS:
            continue
        
        # 获取目标日期的数据
        target_row = group[group['trade_date'] == target_date_obj]
        if target_row.empty:
            continue
        
        target_row = target_row.iloc[0]
        
        # 计算均线（使用目标日期之前的数据，包括目标日期）
        target_idx = group[group['trade_date'] == target_date_obj].index[0]
        hist_data = group.loc[:target_idx]
        
        # MA5, MA20, MA60
        ma5 = hist_data['close'].tail(5).mean() if len(hist_data) >= 5 else None
        ma20 = hist_data['close'].tail(20).mean() if len(hist_data) >= 20 else None
        ma60 = hist_data['close'].tail(60).mean() if len(hist_data) >= 60 else None
        
        # 量比：今日成交量 / 近5日平均成交量
        avg_vol_5d = hist_data['vol'].tail(6).iloc[:-1].mean() if len(hist_data) >= 6 else None  # 不包括今天
        volume_ratio = target_row['vol'] / avg_vol_5d if avg_vol_5d and avg_vol_5d > 0 else None
        
        # 近5日涨幅（不包括今天）
        last_5d = hist_data['close'].tail(6).iloc[:-1]  # 取前5天
        pct_chg_5d = ((target_row['close'] - last_5d.iloc[0]) / last_5d.iloc[0] * 100) if len(last_5d) >= 5 else None
        
        # 近30日最高价
        high_30d = hist_data['high'].tail(30).max() if len(hist_data) >= 30 else None
        dist_from_high_30d = ((target_row['close'] - high_30d) / high_30d * 100) if high_30d else None
        
        # 跳过指标不全的股票
        if None in [ma5, ma20, ma60, volume_ratio, pct_chg_5d, dist_from_high_30d]:
            continue
        
        results.append({
            'ts_code': ts_code,
            'exch_code': target_row['exch_code'],
            'trade_date': target_row['trade_date'],
            'close': float(target_row['close']),
            'pct_chg': float(target_row['pct_chg']),
            'vol': int(target_row['vol']),
            'amount': float(target_row['amount']),
            'ma5': round(ma5, 4),
            'ma20': round(ma20, 4),
            'ma60': round(ma60, 4),
            'volume_ratio': round(volume_ratio, 2),
            'pct_chg_5d': round(pct_chg_5d, 2),
            'dist_from_high_30d': round(dist_from_high_30d, 2),
        })
    
    result_df = pd.DataFrame(results)
    print(f"✓ 计算了 {len(result_df)} 只股票的技术指标")
    
    return result_df


# ============================================
# 策略筛选
# ============================================

def apply_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    应用选股策略
    
    策略条件：
    1. 价格区间：5元 ≤ 收盘价 ≤ 30元
    2. 成交额：> 5000万
    3. 今日涨幅：3% - 9%
    4. 放量：量比 > 1.5
    5. 多头排列：收盘价 > MA5 > MA20 > MA60
    6. 近5日涨幅 < 20%
    """
    print("\n应用选股策略...")
    print(f"原始股票数：{len(df)}")
    
    # 1. 价格区间
    df = df[(df['close'] >= MIN_PRICE) & (df['close'] <= MAX_PRICE)]
    print(f"  价格筛选（{MIN_PRICE}-{MAX_PRICE}元）：{len(df)} 只")
    
    # 2. 成交额
    df = df[df['amount'] > MIN_AMOUNT]
    print(f"  成交额筛选（>{MIN_AMOUNT}万）：{len(df)} 只")
    
    # 3. 今日涨幅
    df = df[(df['pct_chg'] >= MIN_PCT_CHG) & (df['pct_chg'] <= MAX_PCT_CHG)]
    print(f"  涨幅筛选（{MIN_PCT_CHG}%-{MAX_PCT_CHG}%）：{len(df)} 只")
    
    # 4. 放量
    df = df[df['volume_ratio'] > VOLUME_RATIO]
    print(f"  放量筛选（量比>{VOLUME_RATIO}）：{len(df)} 只")
    
    # 5. 多头排列
    df = df[(df['close'] > df['ma5']) & (df['ma5'] > df['ma20']) & (df['ma20'] > df['ma60'])]
    print(f"  多头排列筛选：{len(df)} 只")
    
    # 6. 近5日涨幅
    df = df[df['pct_chg_5d'] < MAX_5D_CHG]
    print(f"  近5日涨幅筛选（<{MAX_5D_CHG}%）：{len(df)} 只")
    
    # 7. 按量比降序排序
    df = df.sort_values('volume_ratio', ascending=False)
    
    # 8. 添加排名
    df.insert(0, 'rank', range(1, len(df) + 1))
    
    print(f"\n✓ 最终筛选出 {len(df)} 只股票")
    
    return df


# ============================================
# 结果输出
# ============================================

def save_results(df: pd.DataFrame, trade_date: str) -> str:
    """
    保存选股结果为CSV文件
    
    返回：输出文件路径
    """
    # 创建输出目录
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # 生成文件名
    filename = f"stock_selection_{trade_date}.csv"
    filepath = OUTPUT_DIR / filename
    
    # 准备输出数据（添加股票名称列，暂时为空）
    output_df = df[[
        'rank', 'ts_code', 'close', 'pct_chg', 'volume_ratio',
        'ma5', 'ma20', 'ma60', 'pct_chg_5d', 'dist_from_high_30d', 'amount'
    ]].copy()
    
    # 插入名称列（占位）
    output_df.insert(2, 'name', '')
    
    # 重命名列（中文表头）
    output_df.columns = [
        '排名', '代码', '名称', '收盘价', '涨幅%', '量比',
        'MA5', 'MA20', 'MA60', '5日涨幅%', '距30日高点%', '成交额(万)'
    ]
    
    # 格式化数值
    output_df['收盘价'] = output_df['收盘价'].map('{:.2f}'.format)
    output_df['涨幅%'] = output_df['涨幅%'].map('{:.2f}'.format)
    output_df['量比'] = output_df['量比'].map('{:.2f}'.format)
    output_df['MA5'] = output_df['MA5'].map('{:.2f}'.format)
    output_df['MA20'] = output_df['MA20'].map('{:.2f}'.format)
    output_df['MA60'] = output_df['MA60'].map('{:.2f}'.format)
    output_df['5日涨幅%'] = output_df['5日涨幅%'].map('{:.2f}'.format)
    output_df['距30日高点%'] = output_df['距30日高点%'].map('{:.2f}'.format)
    output_df['成交额(万)'] = output_df['成交额(万)'].map('{:.0f}'.format)
    
    # 保存为CSV
    output_df.to_csv(filepath, index=False, encoding='utf-8-sig')  # utf-8-sig 确保Excel正确显示中文
    
    print(f"\n✓ 结果已保存至：{filepath}")
    return str(filepath)


# ============================================
# 主流程
# ============================================

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='量价齐升突破选股策略')
    parser.add_argument(
        '--date',
        type=str,
        help='交易日期（YYYYMMDD），不指定则使用最新交易日'
    )
    args = parser.parse_args()
    
    try:
        # 1. 连接数据库
        print("=" * 80)
        print("📊 量价齐升突破选股策略")
        print("=" * 80)
        
        engine = get_db_engine()
        print("✓ 数据库连接成功")
        
        # 2. 确定交易日期
        if args.date:
            trade_date = args.date
            print(f"✓ 使用指定日期：{trade_date}")
        else:
            trade_date = get_latest_trade_date(engine)
            print(f"✓ 使用最新交易日：{trade_date}")
        
        # 3. 获取数据
        df = get_stock_data(engine, trade_date, days_back=120)
        
        if df.empty:
            print("❌ 没有查询到数据")
            return
        
        # 4. 计算技术指标
        df_indicators = calculate_indicators(df, trade_date)
        
        if df_indicators.empty:
            print("❌ 没有计算出技术指标（可能数据不足）")
            return
        
        # 5. 应用策略
        df_selected = apply_strategy(df_indicators)
        
        if df_selected.empty:
            print("❌ 没有符合条件的股票")
            return
        
        # 6. 保存结果
        filepath = save_results(df_selected, trade_date)
        
        # 7. 打印摘要
        print("\n" + "=" * 80)
        print(f"✅ 选股完成！共筛选出 {len(df_selected)} 只股票")
        print(f"📄 结果文件：{filepath}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

