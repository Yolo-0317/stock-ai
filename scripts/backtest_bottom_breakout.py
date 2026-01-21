#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
底部启动策略 - 回测脚本
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import subprocess

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


def get_next_n_trade_days(engine, start_date: str, n_days: int = 10) -> list:
    """获取指定日期后的N个交易日"""
    start_date_obj = datetime.strptime(start_date, '%Y%m%d').date()
    
    query = f"""
        SELECT DISTINCT trade_date
        FROM stock_daily
        WHERE trade_date > '{start_date_obj.strftime('%Y-%m-%d')}'
        ORDER BY trade_date
        LIMIT {n_days}
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        dates = [row[0] for row in result]
    
    return dates


def get_stock_data_between_dates(engine, ts_codes: list, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指定股票在指定日期范围的数据"""
    
    # 转换代码格式
    formatted_codes = []
    for code in ts_codes:
        code_str = str(code).split('.')[0].zfill(6)
        formatted_codes.append(code_str)
    
    codes_str = "','".join(formatted_codes)
    
    # 转换日期格式
    start_date_obj = datetime.strptime(start_date, '%Y%m%d').date()
    end_date_obj = datetime.strptime(end_date, '%Y%m%d').date()
    
    query = f"""
        SELECT 
            ts_code,
            trade_date,
            open,
            close,
            high,
            low,
            pct_chg
        FROM stock_daily
        WHERE ts_code IN ('{codes_str}')
            AND trade_date BETWEEN '{start_date_obj}' AND '{end_date_obj}'
        ORDER BY ts_code, trade_date
    """
    
    df = pd.read_sql(text(query), engine)
    return df


def run_strategy_for_date(selection_date: str):
    """运行指定日期的选股策略"""
    
    # 修改策略脚本的target_date
    script_path = Path(__file__).parent / "stock_selection_bottom_breakout.py"
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 备份原始内容
    original_content = content
    
    # 修改target_date
    content = content.replace(
        "target_date = None  # 格式：'YYYYMMDD'",
        f"target_date = '{selection_date}'  # 格式：'YYYYMMDD'"
    )
    
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    try:
        # 运行策略
        result = subprocess.run(
            ['uv', 'run', 'python', str(script_path)],
            cwd=script_path.parent.parent,
            capture_output=True,
            text=True
        )
        
        success = result.returncode == 0
    finally:
        # 恢复原始内容
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
    
    return success


def backtest_strategy(selection_date: str, hold_days: int = 10):
    """回测指定日期的选股策略"""
    
    output_dir = Path(__file__).parent.parent / "output"
    engine = get_db_engine()
    
    print("=" * 80)
    print(f"📊 回测底部启动策略")
    print("=" * 80)
    print(f"选股日期：{selection_date}")
    print(f"持有周期：{hold_days}天")
    print()
    
    # 1. 运行选股策略
    selection_file = output_dir / f"stock_selection_bottom_breakout_{selection_date}.csv"
    
    if not selection_file.exists():
        print(f"🔄 未找到选股结果，正在运行策略...")
        success = run_strategy_for_date(selection_date)
        if not success:
            print("❌ 策略运行失败")
            return
        print("✓ 策略运行成功\n")
    
    # 2. 读取选股结果
    if not selection_file.exists():
        print(f"⚠️  {selection_date} 选股文件不存在（可能没有选出股票）")
        return
    
    df_selected = pd.read_csv(selection_file, dtype={'代码': str})
    
    if df_selected.empty or len(df_selected) == 0:
        print(f"⚠️  {selection_date} 没有选出股票")
        return
    
    print(f"✓ 选出 {len(df_selected)} 只股票")
    
    # 3. 获取后续交易日
    trade_days = get_next_n_trade_days(engine, selection_date, hold_days + 1)
    
    if len(trade_days) < hold_days:
        print(f"⚠️  后续交易日不足{hold_days}天，只有{len(trade_days)}天")
        if len(trade_days) == 0:
            return
    
    buy_date = trade_days[0] if trade_days else None
    end_date = trade_days[min(hold_days - 1, len(trade_days) - 1)] if trade_days else None
    
    if not buy_date or not end_date:
        print("❌ 无法获取买入或卖出日期")
        return
    
    print(f"✓ 买入日期：{buy_date.strftime('%Y%m%d')}")
    print(f"✓ 卖出日期：{end_date.strftime('%Y%m%d')}")
    print(f"✓ 实际持有：{len(trade_days[:hold_days])}天")
    print()
    
    # 4. 获取股票数据
    codes = df_selected['代码'].tolist()
    df_data = get_stock_data_between_dates(
        engine, 
        codes, 
        selection_date,
        end_date.strftime('%Y%m%d')
    )
    
    # 5. 计算每只股票的表现
    results = []
    
    for idx, row in df_selected.iterrows():
        code = str(row['代码']).zfill(6)
        
        # 获取该股票的数据
        stock_data = df_data[df_data['ts_code'] == code].sort_values('trade_date')
        
        if stock_data.empty:
            print(f"  ⚠️  {code}: 无数据")
            continue
        
        # 买入价（次日开盘价）
        buy_data = stock_data[stock_data['trade_date'] == buy_date]
        if buy_data.empty:
            print(f"  ⚠️  {code}: 无买入日数据（可能停牌）")
            continue
        
        buy_price = buy_data.iloc[0]['open']
        
        # 卖出价（持有期结束日收盘价）
        sell_data = stock_data[stock_data['trade_date'] == end_date]
        if sell_data.empty:
            print(f"  ⚠️  {code}: 无卖出日数据")
            continue
        
        sell_price = sell_data.iloc[0]['close']
        
        # 期间最高最低价
        period_data = stock_data[
            (stock_data['trade_date'] >= buy_date) & 
            (stock_data['trade_date'] <= end_date)
        ]
        
        max_high = period_data['high'].max()
        min_low = period_data['low'].min()
        
        # 计算收益率
        profit = (sell_price - buy_price) / buy_price * 100
        max_profit = (max_high - buy_price) / buy_price * 100
        max_drawdown = (min_low - buy_price) / buy_price * 100
        
        # 每日涨跌
        daily_changes = []
        for _, day_row in period_data.iterrows():
            daily_changes.append(day_row['pct_chg'])
        
        results.append({
            '排名': row['排名'],
            '代码': code,
            '名称': row['名称'],
            '选股日收盘': row['收盘价'],
            '买入价': buy_price,
            '卖出价': sell_price,
            '期间最高': max_high,
            '期间最低': min_low,
            '持有收益%': profit,
            '最大收益%': max_profit,
            '最大回撤%': max_drawdown,
            '每日涨跌': daily_changes,
            '距250日高点%': row['距250日高点%'],
            '距250日低点%': row['距250日低点%'],
            '成交额(万)': row['成交额(万)'],
        })
    
    if not results:
        print("❌ 没有找到有效数据")
        return
    
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('持有收益%', ascending=False)
    
    # 6. 统计结果
    total_count = len(df_results)
    up_count = len(df_results[df_results['持有收益%'] > 0])
    down_count = len(df_results[df_results['持有收益%'] <= 0])
    avg_profit = df_results['持有收益%'].mean()
    best_profit = df_results['持有收益%'].max()
    worst_profit = df_results['持有收益%'].min()
    
    print("=" * 80)
    print("📊 回测结果")
    print("=" * 80)
    print(f"验证数量：{total_count} 只")
    print(f"上涨数量：{up_count} 只 ({up_count/total_count*100:.1f}%)")
    print(f"下跌数量：{down_count} 只 ({down_count/total_count*100:.1f}%)")
    print(f"平均收益：{avg_profit:+.2f}%")
    print(f"最佳收益：{best_profit:+.2f}%")
    print(f"最差收益：{worst_profit:+.2f}%")
    print()
    
    # 7. 打印详细结果
    print("=" * 80)
    print("🌟 详细表现")
    print("=" * 80)
    for idx, row in df_results.iterrows():
        print(f"#{int(row['排名']):2d} {row['代码']:>6s} | "
              f"买入:{row['买入价']:6.2f} → 卖出:{row['卖出价']:6.2f} | "
              f"收益:{row['持有收益%']:+6.2f}% | "
              f"最高:{row['最大收益%']:+6.2f}% | "
              f"最低:{row['最大回撤%']:+6.2f}% | "
              f"距低点:{row['距250日低点%']:+5.1f}%")
    print()
    
    # 8. 保存结果
    output_file = output_dir / f"backtest_bottom_{selection_date}_hold{hold_days}d.csv"
    df_results.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"✓ 详细结果已保存：{output_file}")
    
    # 9. 生成报告
    report_file = output_dir / f"backtest_bottom_{selection_date}_hold{hold_days}d.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# 底部启动策略 - 回测报告\n\n")
        f.write(f"**选股日期**：{selection_date}\n")
        f.write(f"**买入日期**：{buy_date.strftime('%Y%m%d')}\n")
        f.write(f"**卖出日期**：{end_date.strftime('%Y%m%d')}\n")
        f.write(f"**持有天数**：{len(trade_days[:hold_days])}天\n\n")
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
        
        f.write(f"## 📋 详细表现\n\n")
        f.write(f"| 排名 | 代码 | 买入价 | 卖出价 | 持有收益% | 最大收益% | 最大回撤% | 距250日低点% |\n")
        f.write(f"|------|------|--------|--------|-----------|-----------|-----------|-------------|\n")
        for idx, row in df_results.iterrows():
            f.write(f"| {int(row['排名'])} | {row['代码']} | {row['买入价']:.2f} | {row['卖出价']:.2f} | "
                   f"**{row['持有收益%']:+.2f}%** | {row['最大收益%']:+.2f}% | {row['最大回撤%']:+.2f}% | "
                   f"+{row['距250日低点%']:.1f}% |\n")
        f.write(f"\n---\n\n")
        
        f.write(f"## 💡 结论\n\n")
        if avg_profit > 0:
            f.write(f"✅ **策略有效**：平均收益 {avg_profit:+.2f}%，胜率 {up_count/total_count*100:.1f}%\n\n")
        else:
            f.write(f"⚠️ **需要改进**：平均收益 {avg_profit:+.2f}%，胜率 {up_count/total_count*100:.1f}%\n\n")
        
        f.write(f"**免责声明**：以上分析基于历史数据，不构成投资建议。股市有风险，投资需谨慎。\n")
    
    print(f"✓ 回测报告已保存：{report_file}")
    print("=" * 80)
    print()


def main():
    """主函数 - 回测多个日期"""
    
    # 要回测的日期列表
    test_dates = [
        '20251223',  # 回测1：约3周前
        '20251231',  # 回测2：约2周前
        '20260108',  # 回测3：约1周前
    ]
    
    print("=" * 80)
    print("🎯 底部启动策略 - 历史回测")
    print("=" * 80)
    print(f"回测日期数量：{len(test_dates)}")
    print(f"持有周期：10天")
    print("=" * 80)
    print()
    
    for test_date in test_dates:
        backtest_strategy(test_date, hold_days=10)
    
    print("=" * 80)
    print("✅ 全部回测完成！")
    print("=" * 80)


if __name__ == "__main__":
    main()
