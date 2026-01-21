#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证选股结果的后续表现
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

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


def get_db_engine():
    """获取数据库连接"""
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        raise ValueError("❌ 环境变量 MYSQL_URL 未设置")
    return create_engine(mysql_url, pool_pre_ping=True, pool_recycle=3600)


def get_stock_data_on_date(engine, ts_codes: list, target_date: str) -> pd.DataFrame:
    """获取指定股票在指定日期的数据"""
    
    # 代码列表（不需要后缀）
    codes_list = [str(code).split('.')[0].zfill(6) for code in ts_codes]
    codes_str = "','".join(codes_list)
    
    # 转换日期格式 (20260109 -> 2026-01-09)
    date_obj = datetime.strptime(target_date, '%Y%m%d')
    formatted_date = date_obj.strftime('%Y-%m-%d')
    
    query = f"""
    SELECT 
        ts_code,
        trade_date,
        open,
        close,
        high,
        low,
        pct_chg,
        vol,
        amount
    FROM stock_daily
    WHERE ts_code IN ('{codes_str}')
        AND trade_date = '{formatted_date}'
    ORDER BY ts_code
    """
    
    df = pd.read_sql(text(query), engine)
    return df


def verify_performance(selection_date: str, verify_date: str):
    """验证选股结果的表现"""
    
    output_dir = Path(__file__).parent.parent / "output"
    
    # 读取选股结果（代码列作为字符串读取，保留前导零）
    selection_file = output_dir / f"stock_selection_ma5_{selection_date}.csv"
    if not selection_file.exists():
        print(f"❌ 选股结果文件不存在：{selection_file}")
        return
    
    df_selected = pd.read_csv(selection_file, dtype={'代码': str})
    
    print("=" * 80)
    print(f"📊 验证选股表现")
    print("=" * 80)
    print(f"选股日期：{selection_date}")
    print(f"验证日期：{verify_date}")
    print(f"选股数量：{len(df_selected)} 只")
    print()
    
    # 连接数据库
    engine = get_db_engine()
    
    # 获取选股日期和验证日期的数据
    codes = df_selected['代码'].tolist()
    
    print("🔄 查询股票数据...")
    df_selection_day = get_stock_data_on_date(engine, codes, selection_date)
    df_verify_day = get_stock_data_on_date(engine, codes, verify_date)
    
    # 合并数据
    results = []
    for idx, row in df_selected.iterrows():
        code = str(row['代码']).split('.')[0]
        
        # 查找选股日数据
        selection_data = df_selection_day[df_selection_day['ts_code'].str.contains(code)]
        if selection_data.empty:
            print(f"  ⚠️  {code}: 未找到选股日数据")
            continue
        
        selection_close = selection_data.iloc[0]['close']
        
        # 查找验证日数据
        verify_data = df_verify_day[df_verify_day['ts_code'].str.contains(code)]
        if verify_data.empty:
            print(f"  ⚠️  {code}: 未找到验证日数据（可能停牌）")
            continue
        
        verify_open = verify_data.iloc[0]['open']
        verify_close = verify_data.iloc[0]['close']
        verify_high = verify_data.iloc[0]['high']
        verify_low = verify_data.iloc[0]['low']
        verify_pct = verify_data.iloc[0]['pct_chg']
        
        # 计算收益率（从选股日收盘到验证日收盘）
        profit = (verify_close - selection_close) / selection_close * 100
        
        # 计算从选股日收盘到验证日最高的最大收益
        max_profit = (verify_high - selection_close) / selection_close * 100
        
        # 计算从选股日收盘到验证日最低的最大回撤
        max_drawdown = (verify_low - selection_close) / selection_close * 100
        
        results.append({
            '排名': row['排名'],
            '代码': code,
            '名称': row['名称'],
            '选股日收盘': selection_close,
            '验证日开盘': verify_open,
            '验证日收盘': verify_close,
            '验证日最高': verify_high,
            '验证日最低': verify_low,
            '验证日涨幅%': verify_pct,
            '持有收益%': profit,
            '最大收益%': max_profit,
            '最大回撤%': max_drawdown,
            '成交额(万)': row['成交额(万)'],
        })
    
    if not results:
        print("❌ 没有找到有效数据")
        return
    
    df_results = pd.DataFrame(results)
    
    # 排序（按持有收益降序）
    df_results = df_results.sort_values('持有收益%', ascending=False)
    
    # 统计
    total_count = len(df_results)
    up_count = len(df_results[df_results['持有收益%'] > 0])
    down_count = len(df_results[df_results['持有收益%'] < 0])
    avg_profit = df_results['持有收益%'].mean()
    best_profit = df_results['持有收益%'].max()
    worst_profit = df_results['持有收益%'].min()
    
    print(f"✓ 成功获取 {total_count} 只股票数据")
    print()
    
    # 打印统计结果
    print("=" * 80)
    print("📊 整体统计")
    print("=" * 80)
    print(f"验证数量：{total_count} 只")
    print(f"上涨数量：{up_count} 只 ({up_count/total_count*100:.1f}%)")
    print(f"下跌数量：{down_count} 只 ({down_count/total_count*100:.1f}%)")
    print(f"平均收益：{avg_profit:+.2f}%")
    print(f"最佳收益：{best_profit:+.2f}%")
    print(f"最差收益：{worst_profit:+.2f}%")
    print()
    
    # 打印最佳表现
    print("=" * 80)
    print("🌟 最佳表现（Top 10）")
    print("=" * 80)
    for idx, row in df_results.head(10).iterrows():
        print(f"#{row['排名']:2d} {row['代码']:>6s} | "
              f"选股日:{row['选股日收盘']:6.2f} → 验证日:{row['验证日收盘']:6.2f} | "
              f"收益:{row['持有收益%']:+6.2f}% | "
              f"最高:{row['最大收益%']:+6.2f}% | "
              f"最低:{row['最大回撤%']:+6.2f}%")
    print()
    
    # 打印最差表现
    print("=" * 80)
    print("💔 最差表现（Bottom 5）")
    print("=" * 80)
    for idx, row in df_results.tail(5).iterrows():
        print(f"#{row['排名']:2d} {row['代码']:>6s} | "
              f"选股日:{row['选股日收盘']:6.2f} → 验证日:{row['验证日收盘']:6.2f} | "
              f"收益:{row['持有收益%']:+6.2f}% | "
              f"最高:{row['最大收益%']:+6.2f}% | "
              f"最低:{row['最大回撤%']:+6.2f}%")
    print()
    
    # 保存详细结果
    output_file = output_dir / f"verify_{selection_date}_to_{verify_date}.csv"
    df_results.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"✓ 详细结果已保存：{output_file}")
    print()
    
    # 生成报告
    report_file = output_dir / f"verify_{selection_date}_to_{verify_date}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# 选股验证报告\n\n")
        f.write(f"**选股日期**：{selection_date}\n")
        f.write(f"**验证日期**：{verify_date}\n")
        f.write(f"**持有周期**：约{(datetime.strptime(verify_date, '%Y%m%d') - datetime.strptime(selection_date, '%Y%m%d')).days}天\n\n")
        f.write(f"---\n\n")
        
        f.write(f"## 📊 整体统计\n\n")
        f.write(f"| 指标 | 数值 |\n")
        f.write(f"|------|------|\n")
        f.write(f"| 验证数量 | {total_count} 只 |\n")
        f.write(f"| 上涨数量 | {up_count} 只 ({up_count/total_count*100:.1f}%) |\n")
        f.write(f"| 下跌数量 | {down_count} 只 ({down_count/total_count*100:.1f}%) |\n")
        f.write(f"| **平均收益** | **{avg_profit:+.2f}%** |\n")
        f.write(f"| 最佳收益 | {best_profit:+.2f}% |\n")
        f.write(f"| 最差收益 | {worst_profit:+.2f}% |\n\n")
        f.write(f"---\n\n")
        
        f.write(f"## 🌟 最佳表现（Top 10）\n\n")
        f.write(f"| 排名 | 代码 | 选股日收盘 | 验证日收盘 | 持有收益% | 最大收益% | 最大回撤% |\n")
        f.write(f"|------|------|------------|------------|-----------|-----------|----------|\n")
        for idx, row in df_results.head(10).iterrows():
            f.write(f"| {row['排名']} | {row['代码']} | {row['选股日收盘']:.2f} | {row['验证日收盘']:.2f} | "
                   f"**{row['持有收益%']:+.2f}%** | {row['最大收益%']:+.2f}% | {row['最大回撤%']:+.2f}% |\n")
        f.write(f"\n---\n\n")
        
        f.write(f"## 💔 最差表现（Bottom 5）\n\n")
        f.write(f"| 排名 | 代码 | 选股日收盘 | 验证日收盘 | 持有收益% | 最大收益% | 最大回撤% |\n")
        f.write(f"|------|------|------------|------------|-----------|-----------|----------|\n")
        for idx, row in df_results.tail(5).iterrows():
            f.write(f"| {row['排名']} | {row['代码']} | {row['选股日收盘']:.2f} | {row['验证日收盘']:.2f} | "
                   f"**{row['持有收益%']:+.2f}%** | {row['最大收益%']:+.2f}% | {row['最大回撤%']:+.2f}% |\n")
        f.write(f"\n---\n\n")
        
        f.write(f"## 💡 结论\n\n")
        if avg_profit > 0:
            f.write(f"✅ **策略有效**：平均收益 {avg_profit:+.2f}%，胜率 {up_count/total_count*100:.1f}%\n\n")
        else:
            f.write(f"⚠️ **需要改进**：平均收益 {avg_profit:+.2f}%，胜率 {up_count/total_count*100:.1f}%\n\n")
        
        f.write(f"**免责声明**：以上分析基于历史数据，不构成投资建议。股市有风险，投资需谨慎。\n")
    
    print(f"✓ 验证报告已保存：{report_file}")
    print()
    print("=" * 80)


if __name__ == "__main__":
    # 验证20260109选出的股票在20260112的表现
    verify_performance("20260109", "20260112")
