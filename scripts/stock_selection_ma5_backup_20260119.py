#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动初期选股策略

策略逻辑：
寻找"前期横盘、刚刚启动、刚开始放量"的股票（最佳买点）

核心特征（提高标准，减少假突破）：
1. 前期平稳：近20日涨幅较小（0-15%），避免追高
2. 近期启动：近5日涨幅5-15%（明确启动，避免假突破）
3. 均线发散：MA5-MA10距离1-8%（明确发散，不是试探）
4. 价格站稳：收盘价在MA10上方0-10%（刚脱离）
5. 明显放量：量比>1.8（资金明确介入，不是试探）
6. 趋势确立：MA5 > MA10 > MA20（多头排列）
7. 今日上涨：今日涨幅>0%（必须上涨，不接受回调）

筛选条件（提高标准版）：
1. 基础过滤：只保留沪深主板（排除创业板300/科创板688）、价格区间5-30元、成交额>5000万、至少65个交易日数据 ⭐
2. 前期平稳：近20日涨幅0-15%（不要涨太多的）
3. 近期启动：近5日涨幅5-15%（明确启动）⭐
4. 价格刚站上：收盘价在MA10上方0-10%
5. MA5-MA10距离：1-8%（明确发散）⭐
6. 多头排列：MA5 > MA10 > MA20
7. 今日必须上涨：今日涨幅>0%（不接受回调）⭐
8. 明显放量：量比>1.8（强势确认）⭐
9. MA10向上（增长率>0.5%）⭐
10. 按成交额降序排序（流动性优先）⭐
11. 限制输出前30只

使用方法：
    # 在main函数中修改 target_date 变量
    # target_date = None  # 使用最新交易日
    # target_date = '20260107'  # 指定日期
    
    # 运行脚本
    uv run python scripts/stock_selection_ma5.py

输出：
    output/stock_selection_ma5_YYYYMMDD.csv
    
排序规则：
    综合评分 = MA5-MA10距离40% + 成交额40% + 量比20%
    既要加速明显（技术形态好），又要有流动性（成交额大、量比高）
"""

from __future__ import annotations

import os
import sys
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

# 策略参数（提高标准，减少假突破）
MIN_PRICE = 5.0              # 最低价格
MAX_PRICE = 30.0             # 最高价格
MIN_AMOUNT = 5000.0          # 最低成交额（万元）
MIN_DEVIATION_MA10 = 0.0     # 相对MA10最小乖离率（%）- 刚站上MA10
MAX_DEVIATION_MA10 = 10.0    # 相对MA10最大乖离率（%）- 不要离太远
MIN_MA5_MA10_GAP = 1.0       # MA5与MA10最小距离（%）- 明确发散（从0.5提高）
MAX_MA5_MA10_GAP = 8.0       # MA5与MA10最大距离（%）- 不要发散太多
MA10_GROWTH_RATE = 0.5       # MA10增长率（%）- 趋势明确向上（从0.3提高）
MIN_20D_CHG = 0.0            # 近20日最小涨幅（%）- 前期不能跌
MAX_20D_CHG = 15.0           # 近20日最大涨幅（%）- 前期不能涨太多
MIN_5D_CHG = 5.0             # 近5日最小涨幅（%）- 涨幅更明确（从3提高到5）
MAX_5D_CHG = 15.0            # 近5日最大涨幅（%）- 不要涨太猛
MIN_TODAY_CHG = 0.0          # 今日最小涨幅（%）- 今日必须上涨（从-1提高到0）
MIN_VOLUME_RATIO = 1.8       # 最小量比 - 明显放量（从1.3提高到1.8）
MIN_HISTORY_DAYS = 65        # 最少历史数据天数
MAX_OUTPUT_COUNT = 30        # 最多输出股票数量

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


def get_stock_data(engine, trade_date: str, days_back: int = 120) -> pd.DataFrame:
    """
    获取指定交易日及之前N天的股票数据
    
    参数：
    - trade_date: 目标交易日（YYYYMMDD）
    - days_back: 向前查询天数（默认120天，确保有足够数据计算MA60）
    
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
        group = group.sort_values('trade_date').reset_index(drop=True)
        
        # 检查是否有足够的历史数据（至少65个交易日）
        if len(group) < MIN_HISTORY_DAYS:
            continue
        
        # 获取目标日期的数据
        target_row_df = group[group['trade_date'] == target_date_obj]
        if target_row_df.empty:
            continue
        
        target_idx = target_row_df.index[0]
        target_row = target_row_df.iloc[0]
        
        # 计算均线（使用目标日期之前的数据，不包括目标日期，更客观）
        hist_data_excl_today = group.loc[:target_idx-1] if target_idx > 0 else pd.DataFrame()
        
        if len(hist_data_excl_today) < 60:
            continue
        
        # 昨日的MA5, MA10, MA20, MA60（不包括今天）
        ma5_yesterday = hist_data_excl_today['close'].tail(5).mean()
        ma10_yesterday = hist_data_excl_today['close'].tail(10).mean()
        ma20_yesterday = hist_data_excl_today['close'].tail(20).mean()
        ma60_yesterday = hist_data_excl_today['close'].tail(60).mean()
        
        # 今日的MA5, MA10, MA20, MA60（包括今天，用于排序展示）
        hist_data_incl_today = group.loc[:target_idx]
        ma5_today = hist_data_incl_today['close'].tail(5).mean() if len(hist_data_incl_today) >= 5 else None
        ma10_today = hist_data_incl_today['close'].tail(10).mean() if len(hist_data_incl_today) >= 10 else None
        ma20_today = hist_data_incl_today['close'].tail(20).mean() if len(hist_data_incl_today) >= 20 else None
        ma60_today = hist_data_incl_today['close'].tail(60).mean() if len(hist_data_incl_today) >= 60 else None
        
        if None in [ma5_today, ma10_today, ma20_today, ma60_today]:
            continue
        
        # 计算乖离率（相对于昨日MA10）
        deviation_from_ma10 = ((target_row['close'] - ma10_yesterday) / ma10_yesterday * 100)
        
        # MA5与MA10的距离（越近说明贴得越紧）
        ma5_ma10_gap = ((ma5_today - ma10_today) / ma10_today * 100)
        
        # 近5日中，有多少天在MA10上方（不包括今天）
        if len(hist_data_excl_today) >= 5:
            last_5d_data = group.loc[max(0, target_idx-5):target_idx-1]
            
            # 计算每天的MA10
            days_above_ma10 = 0
            for i in range(len(last_5d_data)):
                day_idx = last_5d_data.index[i]
                if day_idx >= 10:
                    day_ma10 = group.loc[day_idx-10:day_idx-1, 'close'].mean()
                    day_close = group.loc[day_idx, 'close']
                    if day_close > day_ma10:
                        days_above_ma10 += 1
        else:
            days_above_ma10 = 0
        
        # MA10向上（今日MA10 vs 10日前的MA10）
        if target_idx >= 19:  # 需要至少20天数据
            ma10_10days_ago = group.loc[target_idx-19:target_idx-10, 'close'].mean()
            ma10_growth_rate = ((ma10_yesterday - ma10_10days_ago) / ma10_10days_ago * 100) if ma10_10days_ago > 0 else 0
        else:
            ma10_growth_rate = 0
        
        # 近20日涨幅（不包括今天）- 用于确认前期加速
        if len(hist_data_excl_today) >= 20:
            close_20d_ago = hist_data_excl_today['close'].iloc[-20]
            pct_chg_20d = ((target_row['close'] - close_20d_ago) / close_20d_ago * 100)
        else:
            pct_chg_20d = 0
        
        # 近10日涨幅（不包括今天）
        if len(hist_data_excl_today) >= 10:
            close_10d_ago = hist_data_excl_today['close'].iloc[-10]
            pct_chg_10d = ((target_row['close'] - close_10d_ago) / close_10d_ago * 100)
        else:
            pct_chg_10d = 0
        
        # 近5日涨幅（用于判断回调程度）
        if len(hist_data_excl_today) >= 5:
            close_5d_ago = hist_data_excl_today['close'].iloc[-5]
            pct_chg_5d = ((target_row['close'] - close_5d_ago) / close_5d_ago * 100)
        else:
            pct_chg_5d = 0
        
        # 量比：今日成交量 / 近5日平均成交量
        if len(hist_data_excl_today) >= 5:
            avg_vol_5d = hist_data_excl_today['vol'].tail(5).mean()
            volume_ratio = (target_row['vol'] / avg_vol_5d) if avg_vol_5d > 0 else 0
        else:
            volume_ratio = 0
        
        # 距离30日最高价
        if len(hist_data_incl_today) >= 30:
            high_30d = hist_data_incl_today['high'].tail(30).max()
            dist_from_high_30d = ((target_row['close'] - high_30d) / high_30d * 100)
        else:
            dist_from_high_30d = 0
        
        results.append({
            'ts_code': ts_code,
            'exch_code': target_row['exch_code'],
            'trade_date': target_row['trade_date'],
            'open': float(target_row['open']),
            'close': float(target_row['close']),
            'pct_chg': float(target_row['pct_chg']),
            'amount': float(target_row['amount']),
            'ma5_today': round(ma5_today, 4),
            'ma10_today': round(ma10_today, 4),
            'ma20_today': round(ma20_today, 4),
            'ma60_today': round(ma60_today, 4),
            'deviation_from_ma10': round(deviation_from_ma10, 2),
            'ma5_ma10_gap': round(ma5_ma10_gap, 2),
            'volume_ratio': round(volume_ratio, 2),
            'days_above_ma10': days_above_ma10,
            'ma10_growth_rate': round(ma10_growth_rate, 2),
            'pct_chg_20d': round(pct_chg_20d, 2),
            'pct_chg_10d': round(pct_chg_10d, 2),
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
    应用选股策略（启动初期版）
    
    策略条件：
    1. 板块筛选：只保留沪深主板（排除创业板300/科创板688）
    2. 价格区间：5元 ≤ 收盘价 ≤ 30元
    3. 成交额：> 5000万
    4. 价格位置：收盘价在MA10上方0-10%（刚站上）
    5. MA5-MA10距离：1%-8%（明确发散）
    6. 多头排列：MA5 > MA10 > MA20
    7. 前期平稳：近20日涨幅0-15%
    8. 近期启动：近5日涨幅5-15%
    9. 今日上涨：今日涨幅 > 0%
    10. 明显放量：量比 > 1.8
    11. MA10向上：增长率 > 0.5%
    12. 按成交额降序排序
    13. 限制输出前30只
    """
    print("\n应用选股策略（启动初期版）...")
    print(f"原始股票数：{len(df)}")
    
    # 1. 板块筛选：只保留沪深主板，排除创业板（300）和科创板（688）
    def is_main_board(ts_code):
        """判断是否为沪深主板股票"""
        code = str(ts_code).split('.')[0]  # 提取代码部分
        # 沪市主板：600、601、603、605
        # 深市主板：000、001、002
        return code.startswith(('600', '601', '603', '605', '000', '001', '002'))
    
    df = df[df['ts_code'].apply(is_main_board)]
    print(f"  板块筛选（只保留沪深主板，排除创业板300/科创板688）：{len(df)} 只")
    
    # 2. 价格区间
    df = df[(df['close'] >= MIN_PRICE) & (df['close'] <= MAX_PRICE)]
    print(f"  价格筛选（{MIN_PRICE}-{MAX_PRICE}元）：{len(df)} 只")
    
    # 3. 成交额
    df = df[df['amount'] > MIN_AMOUNT]
    print(f"  成交额筛选（>{MIN_AMOUNT}万）：{len(df)} 只")
    
    # 4. 价格位置（刚站上MA10，0-10%）
    df = df[(df['deviation_from_ma10'] >= MIN_DEVIATION_MA10) & (df['deviation_from_ma10'] <= MAX_DEVIATION_MA10)]
    print(f"  价格位置筛选（MA10上方{MIN_DEVIATION_MA10}%-{MAX_DEVIATION_MA10}%）：{len(df)} 只")
    
    # 5. MA5-MA10距离（1%-8%，明确发散，避免假突破）
    df = df[(df['ma5_ma10_gap'] >= MIN_MA5_MA10_GAP) & (df['ma5_ma10_gap'] <= MAX_MA5_MA10_GAP)]
    print(f"  MA5-MA10距离筛选（{MIN_MA5_MA10_GAP}%-{MAX_MA5_MA10_GAP}%）：{len(df)} 只")
    
    # 6. 多头排列：MA5 > MA10 > MA20
    df = df[(df['ma5_today'] > df['ma10_today']) & (df['ma10_today'] > df['ma20_today'])]
    print(f"  多头排列筛选（MA5>MA10>MA20）：{len(df)} 只")
    
    # 7. 前期平稳：近20日涨幅0-15%（不要涨太多）
    df = df[(df['pct_chg_20d'] >= MIN_20D_CHG) & (df['pct_chg_20d'] <= MAX_20D_CHG)]
    print(f"  近20日涨幅筛选（{MIN_20D_CHG}%-{MAX_20D_CHG}%）：{len(df)} 只")
    
    # 8. 近期启动：近5日涨幅5-15%（明确启动，避免假突破）
    df = df[(df['pct_chg_5d'] >= MIN_5D_CHG) & (df['pct_chg_5d'] <= MAX_5D_CHG)]
    print(f"  近5日涨幅筛选（{MIN_5D_CHG}%-{MAX_5D_CHG}%）：{len(df)} 只")
    
    # 9. 今日必须上涨（今日涨幅 > 0%，避免假突破）
    df = df[df['pct_chg'] > MIN_TODAY_CHG]
    print(f"  今日必须上涨筛选（>{MIN_TODAY_CHG}%）：{len(df)} 只")
    
    # 10. 明显放量（量比 > 1.8，强势确认，避免假突破）
    df = df[df['volume_ratio'] > MIN_VOLUME_RATIO]
    print(f"  明显放量筛选（量比>{MIN_VOLUME_RATIO}）：{len(df)} 只")
    
    # 11. MA10向上（增长率 > 0.5%，趋势明确）
    df = df[df['ma10_growth_rate'] > MA10_GROWTH_RATE]
    print(f"  MA10向上筛选（增长率>{MA10_GROWTH_RATE}%）：{len(df)} 只")
    
    # 12. 按成交额降序排序（流动性优先）
    df = df.sort_values('amount', ascending=False)
    print(f"  按成交额降序排序（流动性优先）")
    
    # 13. 限制输出数量（只保留最优的前N只）
    if len(df) > MAX_OUTPUT_COUNT:
        print(f"  限制输出数量：{len(df)} 只 → {MAX_OUTPUT_COUNT} 只（保留最优）")
        df = df.head(MAX_OUTPUT_COUNT)
    
    # 14. 添加排名
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
    filename = f"stock_selection_ma5_{trade_date}.csv"
    filepath = OUTPUT_DIR / filename
    
    # 准备输出数据
    output_df = df[[
        'rank', 'ts_code', 'close', 'pct_chg', 
        'ma5_today', 'ma10_today', 'ma20_today',
        'deviation_from_ma10', 'ma5_ma10_gap', 'volume_ratio',
        'ma10_growth_rate', 'pct_chg_20d', 'pct_chg_10d', 'pct_chg_5d',
        'dist_from_high_30d', 'amount'
    ]].copy()
    
    # 插入名称列（占位）
    output_df.insert(2, 'name', '')
    
    # 重命名列（中文表头）
    output_df.columns = [
        '排名', '代码', '名称', '收盘价', '今日涨幅%',
        'MA5', 'MA10', 'MA20',
        '价格乖离MA10%', 'MA5-MA10距离%', '量比',
        'MA10增长率%', '20日涨幅%', '10日涨幅%', '5日涨幅%',
        '距30日高点%', '成交额(万)'
    ]
    
    # 格式化数值
    output_df['收盘价'] = output_df['收盘价'].map('{:.2f}'.format)
    output_df['今日涨幅%'] = output_df['今日涨幅%'].map('{:.2f}'.format)
    output_df['MA5'] = output_df['MA5'].map('{:.2f}'.format)
    output_df['MA10'] = output_df['MA10'].map('{:.2f}'.format)
    output_df['MA20'] = output_df['MA20'].map('{:.2f}'.format)
    output_df['价格乖离MA10%'] = output_df['价格乖离MA10%'].map('{:.2f}'.format)
    output_df['MA5-MA10距离%'] = output_df['MA5-MA10距离%'].map('{:.2f}'.format)
    output_df['量比'] = output_df['量比'].map('{:.2f}'.format)
    output_df['MA10增长率%'] = output_df['MA10增长率%'].map('{:.2f}'.format)
    output_df['20日涨幅%'] = output_df['20日涨幅%'].map('{:.2f}'.format)
    output_df['10日涨幅%'] = output_df['10日涨幅%'].map('{:.2f}'.format)
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
    # 配置参数：可以在这里修改日期
    target_date = None  # 格式：'YYYYMMDD'，如 '20251231'；None 表示使用最新交易日
    
    try:
        # 1. 连接数据库
        print("=" * 80)
        print("📊 启动初期选股策略")
        print("=" * 80)
        
        engine = get_db_engine()
        print("✓ 数据库连接成功")
        
        # 2. 确定交易日期
        if target_date:
            trade_date = target_date
            print(f"✓ 使用指定日期：{trade_date}")
        else:
            trade_date = get_latest_trade_date(engine)
            print(f"✓ 使用最新交易日：{trade_date}")
        
        # 3. 获取数据
        df = get_stock_data(engine, trade_date, days_back=150)
        
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
        print("\n💡 策略说明（提高标准版）：")
        print("   - 启动初期策略：前期横盘、明确启动、强势放量（减少假突破）")
        print("   - 排序规则：按成交额降序（流动性优先）⭐")
        print(f"   - 前期平稳：近20日涨幅{MIN_20D_CHG}%-{MAX_20D_CHG}%（避免追高）")
        print(f"   - 明确启动：近5日涨幅{MIN_5D_CHG}%-{MAX_5D_CHG}%（避免假突破）⭐")
        print(f"   - 价格站稳：在MA10上方{MIN_DEVIATION_MA10}%-{MAX_DEVIATION_MA10}%")
        print(f"   - 明确发散：MA5-MA10距离{MIN_MA5_MA10_GAP}%-{MAX_MA5_MA10_GAP}%（避免试探）⭐")
        print(f"   - 明显放量：量比>{MIN_VOLUME_RATIO}（强势确认）⭐")
        print(f"   - 今日上涨：今日涨幅>{MIN_TODAY_CHG}%（不接受回调）⭐")
        print(f"   - 多头排列：MA5>MA10>MA20，MA10增长率>{MA10_GROWTH_RATE}%⭐")
        print("   - 适合短中线操作，低位启动买点，真突破概率更高")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

