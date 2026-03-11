#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
底部启动策略

策略逻辑：
寻找"月线低位 + 日线多头启动"的股票（早期介入版）

核心特征：
1. 月线低位：经历长期下跌或横盘，筹码充分交换
2. 日线启动：短期技术面转好，开始出现多头趋势
3. 早期介入：不等完美形态，抓住启动初期
4. 空间大风险低：从底部启动，上涨空间充足

月线低位判断：
1. 距离250日高点：-20%到-55%（经历回调但不是暴跌）
2. 距离250日低点：+5%到+30%（刚从底部走出）
3. 近120日涨幅：-15%到+15%（长期横盘整理）
4. 价格在MA60：-5%到+10%（在长期支撑位附近）
5. MA60近20日涨幅：>-1%（长期趋势转好）

日线多头判断（早介入版）：
1. MA5 > MA10 > MA20（短中期多头）
2. MA5增长率 > 0.8%（短期加速）
3. MA10增长率 > 0.3%（中期转好）
4. 近5日涨幅：3%-12%（开始启动）
5. 近10日涨幅：5%-20%（持续上涨）
6. 量比 > 1.3（资金介入）
7. 近5日至少3天收阳（连续性）
8. 站上MA20（短期支撑）

筛选条件：
1. 基础过滤：只保留沪深主板、价格5-50元、成交额>5000万、至少250个交易日数据
2. 月线低位判断（5个条件）
3. 日线多头判断（8个条件）
4. 综合评分排序：从低点反弹25% + 日线强度25% + 成交额30% + 突破确认20%
5. 输出Top 30只

持有周期：10天左右
预期收益：5-8%（10天）
风险等级：中等

使用方法：
    # 在main函数中修改 target_date 变量
    # target_date = None  # 使用最新交易日
    # target_date = '20260109'  # 指定日期
    
    # 运行脚本
    uv run python scripts/stock_selection_bottom_breakout.py

输出：
    output/stock_selection_bottom_breakout_YYYYMMDD.csv
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
# 策略参数
# ============================================

# 月线箱体参数 (基于700日数据模拟3年级别历史大底)
BOX_PERIOD = 700                 # 箱体参考周期（约3年，预留余量）
BOX_WIDTH_MAX = 80               # 3年大底箱体震荡幅度上限（%），放宽到80%
BOX_BREAKOUT_THRESHOLD = 0       # 突破箱体上沿的比例（%）

# 底部位置参数
DIST_FROM_250D_HIGH_MAX = -2     # 距离250日高点至少还有2%空间，确保不是历史最高点
DIST_FROM_250D_LOW_MAX = 100     # 距离250日低点不超过100%（3年大底反弹空间更大）

# 趋势确认参数
MA_LONG_PERIOD = 60              # 长期趋势线
MA_SHORT_PERIOD = 20             # 中期趋势线

# 日线多头参数（早介入版）
MA5_GROWTH_RATE = 0.5            # MA5增长率（%）
MA10_GROWTH_RATE = 0.1           # MA10增长率（%）

MIN_5D_CHG = 0                   # 近5日涨幅最小值（%）
MAX_5D_CHG = 15                  # 近5日涨幅最大值（%）

MIN_10D_CHG = 0                  # 近10日涨幅最小值（%）
MAX_10D_CHG = 25                 # 近10日涨幅最大值（%）

MIN_VOLUME_RATIO = 0.8           # 最小量比（允许缩量回调启动）

MIN_UP_DAYS_IN_5 = 2             # 近5日最少收阳天数

# 基础过滤
MIN_PRICE = 5                    # 最低价格（元）
MAX_PRICE = 50                   # 最高价格（元）
MIN_AMOUNT = 5000                # 最小成交额（万）
MIN_DAYS_REQUIRED = 250          # 最少交易日数据

MAX_OUTPUT_COUNT = 30            # 最大输出数量


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


def get_stock_data(engine, trade_date: str, days_back: int = 400) -> pd.DataFrame:
    """
    获取股票数据
    需要更长的历史数据（400天，约250个交易日）以计算250日高低点
    """
    # 计算开始日期（往前推 days_back 天）
    end_date_obj = datetime.strptime(trade_date, "%Y%m%d")
    start_date_obj = end_date_obj - timedelta(days=days_back)
    
    # 转换为MySQL日期格式
    start_date = start_date_obj.strftime("%Y-%m-%d")
    end_date = end_date_obj.strftime("%Y-%m-%d")
    
    print(f"正在查询数据（{start_date_obj.strftime('%Y%m%d')} 至 {trade_date}）...")
    
    # 查询数据
    query = f"""
        SELECT 
            ts_code,
            trade_date,
            open,
            high,
            low,
            close,
            pct_chg,
            vol,
            amount
        FROM stock_daily
        WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY ts_code, trade_date
    """
    
    df = pd.read_sql(text(query), engine)
    
    if df.empty:
        raise ValueError(f"❌ 没有查询到数据（{start_date} 至 {trade_date}）")
    
    print(f"✓ 查询到 {len(df)} 条记录")
    
    return df


# ============================================
# 指标计算
# ============================================

def calculate_indicators(df: pd.DataFrame, trade_date: str) -> pd.DataFrame:
    """
    计算技术指标
    
    需要计算：
    - MA5, MA10, MA20, MA60
    - 距离250日高低点
    - 120日涨幅
    - 5日、10日涨幅
    - 量比
    - 近5日收阳天数
    - 各种增长率和乖离率
    """
    results = []
    
    # 按股票分组处理
    for ts_code, group in df.groupby('ts_code'):
        # 按日期排序
        group = group.sort_values('trade_date')
        
        # 只保留有足够数据的股票（至少250天）
        if len(group) < MIN_DAYS_REQUIRED:
            continue
        
        # 获取最新交易日的数据（转换trade_date为日期对象进行比较）
        trade_date_obj = datetime.strptime(trade_date, "%Y%m%d").date()
        latest = group[group['trade_date'] == trade_date_obj]
        if latest.empty:
            continue
        
        latest_idx = latest.index[0]
        
        # 基本信息
        close_today = latest['close'].iloc[0]
        pct_chg_today = latest['pct_chg'].iloc[0]
        amount_today = latest['amount'].iloc[0]
        vol_today = latest['vol'].iloc[0]
        
        # 计算均线（MA5, MA10, MA20, MA60）
        if len(group) < 60:
            continue
        
        ma5_today = group['close'].tail(5).mean()
        ma10_today = group['close'].tail(10).mean()
        ma20_today = group['close'].tail(20).mean()
        ma60_today = group['close'].tail(60).mean()
        
        # 计算250日高低点（模拟月线箱体）
        if len(group) < BOX_PERIOD:
            continue
        
        # 排除最近 10 天的数据来计算箱体上沿，避免突破本身拉高了箱体
        box_data = group.iloc[-BOX_PERIOD:-10]
        box_high = box_data['high'].max()
        box_low = box_data['low'].min()
        
        # 箱体宽度（%）
        box_width = (box_high - box_low) / box_low * 100
        
        # 突破确认：今日收盘价突破箱体上沿
        breakout_ratio = (close_today - box_high) / box_high * 100
        
        # 距离250日整体高低点（用于位置判断）
        high_250d = group['high'].tail(250).max()
        low_250d = group['low'].tail(250).min()
        dist_from_250d_high = (close_today - high_250d) / high_250d * 100
        dist_from_250d_low = (close_today - low_250d) / low_250d * 100
        
        # 计算价格乖离率
        deviation_from_ma60 = (close_today - ma60_today) / ma60_today * 100
        
        # 计算MA增长率
        if len(group) < 65:
            continue
        
        ma5_5days_ago = group['close'].iloc[-10:-5].mean()
        ma10_10days_ago = group['close'].iloc[-20:-10].mean()
        ma60_20days_ago = group['close'].iloc[-80:-60].mean()
        
        ma5_growth_rate = (ma5_today - ma5_5days_ago) / ma5_5days_ago * 100
        ma10_growth_rate = (ma10_today - ma10_10days_ago) / ma10_10days_ago * 100
        ma60_growth_rate = (ma60_today - ma60_20days_ago) / ma60_20days_ago * 100
        
        # 计算涨幅
        if len(group) < 120:
            continue
        
        close_5d_ago = group['close'].iloc[-6]
        close_10d_ago = group['close'].iloc[-11]
        close_20d_ago = group['close'].iloc[-21]
        close_120d_ago = group['close'].iloc[-121]
        
        pct_chg_5d = (close_today - close_5d_ago) / close_5d_ago * 100
        pct_chg_10d = (close_today - close_10d_ago) / close_10d_ago * 100
        pct_chg_20d = (close_today - close_20d_ago) / close_20d_ago * 100
        pct_chg_120d = (close_today - close_120d_ago) / close_120d_ago * 100
        
        # 计算量比（今日成交量 / 近5日平均成交量）
        avg_vol_5d = group['vol'].tail(6).iloc[:-1].mean()
        volume_ratio = vol_today / avg_vol_5d if avg_vol_5d > 0 else 0
        
        # 计算近5日收阳天数
        recent_5days = group.tail(5)
        up_days_in_5 = (recent_5days['pct_chg'] > 0).sum()
        
        # 保存结果
        results.append({
            'ts_code': ts_code,
            'close': close_today,
            'pct_chg': pct_chg_today,
            'amount': amount_today,
            'ma5_today': ma5_today,
            'ma10_today': ma10_today,
            'ma20_today': ma20_today,
            'ma60_today': ma60_today,
            'box_width': box_width,
            'breakout_ratio': breakout_ratio,
            'dist_from_250d_high': dist_from_250d_high,
            'dist_from_250d_low': dist_from_250d_low,
            'deviation_from_ma60': deviation_from_ma60,
            'ma5_growth_rate': ma5_growth_rate,
            'ma10_growth_rate': ma10_growth_rate,
            'ma60_growth_rate': ma60_growth_rate,
            'pct_chg_5d': pct_chg_5d,
            'pct_chg_10d': pct_chg_10d,
            'pct_chg_20d': pct_chg_20d,
            'pct_chg_120d': pct_chg_120d,
            'volume_ratio': volume_ratio,
            'up_days_in_5': up_days_in_5,
        })
    
    result_df = pd.DataFrame(results)
    print(f"✓ 计算了 {len(result_df)} 只股票的技术指标")
    
    return result_df


# ============================================
# 策略筛选
# ============================================

def apply_strategy(df: pd.DataFrame) -> pd.DataFrame:
    """
    应用底部启动策略
    
    策略条件：
    1. 板块筛选：只保留沪深主板
    2. 价格区间：5元-50元
    3. 成交额：> 5000万
    4. 月线低位判断（5个条件）
    5. 日线多头判断（8个条件）
    6. 综合评分排序
    7. 输出Top 30
    """
    print("\n应用选股策略（底部启动版）...")
    print(f"原始股票数：{len(df)}")
    
    # 1. 板块筛选：只保留沪深主板，排除创业板（300）和科创板（688）
    def is_main_board(ts_code):
        """判断是否为沪深主板股票"""
        code = str(ts_code).split('.')[0]
        return code.startswith(('600', '601', '603', '605', '000', '001', '002'))
    
    df = df[df['ts_code'].apply(is_main_board)]
    print(f"  板块筛选（只保留沪深主板）：{len(df)} 只")
    
    # 2. 价格区间
    df = df[(df['close'] >= MIN_PRICE) & (df['close'] <= MAX_PRICE)]
    print(f"  价格筛选（{MIN_PRICE}-{MAX_PRICE}元）：{len(df)} 只")
    
    # 3. 成交额
    df = df[df['amount'] > MIN_AMOUNT]
    print(f"  成交额筛选（>{MIN_AMOUNT}万）：{len(df)} 只")
    
    # ========== 月线箱体突破判断 ==========
    
    # 4. 箱体宽度筛选（确保是窄幅震荡箱体）
    df = df[df['box_width'] <= BOX_WIDTH_MAX]
    print(f"  箱体宽度筛选（<{BOX_WIDTH_MAX}%）：{len(df)} 只")
    
    # 5. 突破确认（今日收盘价突破箱体上沿）
    df = df[df['breakout_ratio'] >= 0]
    print(f"  箱体突破筛选（突破上沿）：{len(df)} 只")
    
    # 6. 底部位置确认（确保不是在高位突破）
    df = df[(df['dist_from_250d_high'] <= DIST_FROM_250D_HIGH_MAX) & 
            (df['dist_from_250d_low'] <= DIST_FROM_250D_LOW_MAX)]
    print(f"  底部位置筛选（距高点<{DIST_FROM_250D_HIGH_MAX}%且距低点<{DIST_FROM_250D_LOW_MAX}%）：{len(df)} 只")
    
    # ========== 日线多头确认 ==========
    
    # 7. 多头排列：MA5 > MA10 > MA20
    df = df[(df['ma5_today'] > df['ma10_today']) & 
            (df['ma10_today'] > df['ma20_today'])]
    print(f"  多头排列筛选（MA5>MA10>MA20）：{len(df)} 只")
    
    # 8. MA5增长率
    df = df[df['ma5_growth_rate'] > MA5_GROWTH_RATE]
    print(f"  MA5加速筛选（增长率>{MA5_GROWTH_RATE}%）：{len(df)} 只")
    
    # 9. 连续性筛选
    df = df[df['up_days_in_5'] >= MIN_UP_DAYS_IN_5]
    print(f"  连续性筛选（近5日至少{MIN_UP_DAYS_IN_5}天收阳）：{len(df)} 只")
    
    # 16. 计算综合评分并排序
    # 评分规则：突破强度40% + 箱体紧凑度30% + 成交额30%
    
    # 归一化各项指标到0-1
    df['score_breakout'] = df['breakout_ratio'] / 10  # 假设10%为满分
    df['score_breakout'] = df['score_breakout'].clip(0, 1)
    
    df['score_box_tightness'] = 1 - (df['box_width'] / BOX_WIDTH_MAX)
    
    df['score_amount'] = (df['amount'] - df['amount'].min()) / (df['amount'].max() - df['amount'].min())
    
    # 综合评分
    df['total_score'] = (
        df['score_breakout'] * 0.40 +
        df['score_box_tightness'] * 0.30 +
        df['score_amount'] * 0.30
    )
    
    # 按综合评分降序排序
    df = df.sort_values('total_score', ascending=False)
    print(f"  按综合评分排序（低位25% + 趋势25% + 成交额30% + 突破20%）")
    
    # 17. 限制输出数量
    if len(df) > MAX_OUTPUT_COUNT:
        print(f"  限制输出数量：{len(df)} 只 → {MAX_OUTPUT_COUNT} 只（保留最优）")
        df = df.head(MAX_OUTPUT_COUNT)
    
    # 18. 添加排名
    df.insert(0, 'rank', range(1, len(df) + 1))
    
    print(f"\n✓ 最终筛选出 {len(df)} 只股票")
    
    return df


# ============================================
# 结果保存
# ============================================

def save_results(df: pd.DataFrame, trade_date: str) -> Path:
    """保存结果到CSV文件"""
    
    # 创建输出目录
    output_dir = Path(__file__).resolve().parents[1] / "output"
    output_dir.mkdir(exist_ok=True)
    
    # 准备输出数据
    output_df = pd.DataFrame({
        '排名': df['rank'],
        '代码': df['ts_code'].str.split('.').str[0],  # 去掉后缀
        '名称': '',  # 暂时为空
        '收盘价': df['close'].round(2),
        '今日涨幅%': df['pct_chg'].round(2),
        '箱体宽度%': df['box_width'].round(2),
        '突破比例%': df['breakout_ratio'].round(2),
        'MA5': df['ma5_today'].round(2),
        'MA10': df['ma10_today'].round(2),
        'MA20': df['ma20_today'].round(2),
        'MA60': df['ma60_today'].round(2),
        '距250日高点%': df['dist_from_250d_high'].round(2),
        '距250日低点%': df['dist_from_250d_low'].round(2),
        '距MA60%': df['deviation_from_ma60'].round(2),
        '120日涨幅%': df['pct_chg_120d'].round(2),
        '20日涨幅%': df['pct_chg_20d'].round(2),
        '10日涨幅%': df['pct_chg_10d'].round(2),
        '5日涨幅%': df['pct_chg_5d'].round(2),
        '量比': df['volume_ratio'].round(2),
        '5日收阳': df['up_days_in_5'].astype(int),
        '成交额(万)': df['amount'].round(0).astype(int),
        '综合评分': df['total_score'].round(4),
    })
    
    # 保存文件
    filepath = output_dir / f"stock_selection_bottom_breakout_{trade_date}.csv"
    output_df.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    print(f"\n✓ 结果已保存至：{filepath}")
    
    return filepath


# ============================================
# 主流程
# ============================================

def main():
    """主函数"""
    # 配置参数：可以在这里修改日期
    target_date = '20260226'  # 格式：'YYYYMMDD'，如 '20260109'；None 表示使用最新交易日
    
    try:
        # 1. 连接数据库
        print("=" * 80)
        print("📊 底部启动选股策略")
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
        
        # 3. 获取数据（需要1100天数据，约750个交易日，以计算3年大底指标）
        df = get_stock_data(engine, trade_date, days_back=1100)
        
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
        print("\n💡 策略说明（3年大底箱体突破版）：")
        print(f"   - 长期箱体震荡（{BOX_PERIOD}日，约3年）+ 日线多头突破")
        print("   - 排序规则：突破强度40% + 箱体紧凑度30% + 成交额30%")
        print(f"   - 箱体宽度限制：<{BOX_WIDTH_MAX}%")
        print(f"   - 底部位置限制：距250日高点<{DIST_FROM_250D_HIGH_MAX}%，距低点<{DIST_FROM_250D_LOW_MAX}%")
        print(f"   - 日线启动：MA5>MA10>MA20，MA5加速>{MA5_GROWTH_RATE}%")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
