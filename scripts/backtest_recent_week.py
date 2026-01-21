#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
近期回测：验证选股策略的实际表现

功能：
1. 在指定日期（如2025-12-31）运行选股策略
2. 获取选出股票在后续一周的实际表现
3. 生成对比报告

使用方法：
    # 2025-12-31选股，看2026-01-01到2026-01-08的表现
    uv run python scripts/backtest_recent_week.py --date 20251231
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
import pandas as pd
from sqlalchemy import create_engine, text

# 加载环境变量
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)


def get_db_engine():
    """获取数据库连接"""
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        raise ValueError("❌ 环境变量 MYSQL_URL 未设置")
    return create_engine(mysql_url, pool_pre_ping=True, pool_recycle=3600)


def run_strategy_for_date(engine, target_date: str):
    """在指定日期运行选股策略（简化版）"""
    print(f"\n📅 运行选股策略：{target_date}")
    
    # 这里直接复制策略逻辑，或者调用现有脚本
    # 为了简化，我们直接读取CSV（如果存在）或重新运行
    
    # 方案：调用现有脚本
    import subprocess
    csv_file = Path(__file__).resolve().parents[1] / "output" / f"stock_selection_ma5_{target_date}.csv"
    
    if csv_file.exists():
        print(f"✓ 找到已存在的选股结果：{csv_file}")
        df = pd.read_csv(csv_file, encoding='utf-8-sig')
    else:
        print(f"🔄 未找到选股结果，正在运行策略...")
        result = subprocess.run(
            ["uv", "run", "python", "scripts/stock_selection_ma5.py", "--date", target_date],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parents[1]
        )
        
        if result.returncode == 0:
            print("✓ 选股策略运行成功")
            df = pd.read_csv(csv_file, encoding='utf-8-sig')
        else:
            raise Exception(f"选股策略运行失败：{result.stderr}")
    
    # 清理数据
    if '排名' in df.columns:
        df = df.drop(columns=['排名'])
    
    # 确保代码列是字符串类型
    if '代码' in df.columns:
        df['代码'] = df['代码'].astype(str).str.replace('.0', '', regex=False)
    
    return df


def get_stock_performance(engine, stock_codes: list, start_date: str, end_date: str) -> pd.DataFrame:
    """获取股票在指定时间段的表现"""
    
    # 转换日期格式
    start_date_obj = datetime.strptime(start_date, "%Y%m%d").date()
    end_date_obj = datetime.strptime(end_date, "%Y%m%d").date()
    
    # 构建SQL查询
    codes_str = "','".join(stock_codes)
    
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
    
    print(f"\n📊 获取股票表现数据（{start_date} 到 {end_date}）...")
    df = pd.read_sql(query, engine)
    print(f"✓ 获取到 {len(df)} 条数据")
    
    return df


def calculate_returns(selected_stocks: pd.DataFrame, performance_data: pd.DataFrame, strategy_date: str) -> pd.DataFrame:
    """计算每只股票的收益率"""
    
    results = []
    
    for idx, stock in selected_stocks.iterrows():
        stock_code = stock['代码']
        
        # 获取该股票的交易数据
        stock_data = performance_data[performance_data['ts_code'] == stock_code].sort_values('trade_date')
        
        if len(stock_data) == 0:
            print(f"  ⚠️  {stock_code}: 无后续交易数据")
            continue
        
        # 获取次日开盘价（买入价）
        first_day = stock_data.iloc[0]
        buy_price = first_day['open']
        buy_date = first_day['trade_date']
        
        # 获取最后一天收盘价（当前价）
        last_day = stock_data.iloc[-1]
        current_price = last_day['close']
        current_date = last_day['trade_date']
        
        # 获取期间最高价和最低价
        max_price = stock_data['high'].max()
        min_price = stock_data['low'].min()
        
        # 计算收益率
        total_return = ((current_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
        max_return = ((max_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
        max_drawdown = ((min_price - buy_price) / buy_price * 100) if buy_price > 0 else 0
        
        # 计算每日涨跌
        daily_changes = stock_data['pct_chg'].tolist()
        
        results.append({
            '排名': idx + 1,
            '代码': stock_code,
            '选股日': strategy_date,
            '买入日': buy_date.strftime('%Y-%m-%d'),
            '买入价': f"{buy_price:.2f}",
            '当前日': current_date.strftime('%Y-%m-%d'),
            '当前价': f"{current_price:.2f}",
            '收益率': f"{total_return:.2f}%",
            '期间最高': f"{max_price:.2f}",
            '最大盈利': f"{max_return:.2f}%",
            '期间最低': f"{min_price:.2f}",
            '最大回撤': f"{max_drawdown:.2f}%",
            '交易天数': len(stock_data),
            '每日涨跌': ' | '.join([f"{x:+.2f}%" for x in daily_changes]),
            '原始收盘价': stock['收盘价'],
            '原始涨幅': stock['今日涨幅%'],
            '原始量比': stock['量比'],
            '原始成交额': stock['成交额(万)'],
        })
    
    return pd.DataFrame(results)


def generate_report(results: pd.DataFrame, strategy_date: str, end_date: str) -> str:
    """生成回测报告"""
    
    # 计算统计数据
    total_count = len(results)
    
    # 转换收益率为浮点数
    results['收益率_float'] = results['收益率'].str.rstrip('%').astype(float)
    
    win_count = len(results[results['收益率_float'] > 0])
    lose_count = len(results[results['收益率_float'] < 0])
    win_rate = (win_count / total_count * 100) if total_count > 0 else 0
    
    avg_return = results['收益率_float'].mean()
    best_return = results['收益率_float'].max()
    worst_return = results['收益率_float'].min()
    
    best_stock = results[results['收益率_float'] == best_return].iloc[0]
    worst_stock = results[results['收益率_float'] == worst_return].iloc[0]
    
    # 生成Markdown报告
    report = f"""# 启动初期选股策略 - 近期回测报告

**回测说明**：
- 选股日期：{strategy_date}
- 买入时机：次日开盘价
- 统计截止：{end_date}
- 持有天数：约{results['交易天数'].iloc[0] if len(results) > 0 else 0}个交易日

---

## 📊 整体统计

| 指标 | 数值 |
|------|------|
| 选股数量 | {total_count} 只 |
| 上涨数量 | {win_count} 只 ({win_rate:.1f}%) |
| 下跌数量 | {lose_count} 只 |
| **平均收益率** | **{avg_return:+.2f}%** |
| 最佳收益率 | {best_return:+.2f}% |
| 最差收益率 | {worst_return:+.2f}% |

---

## 🌟 最佳表现

**{best_stock['代码']}**：{best_stock['收益率']}
- 买入价：{best_stock['买入价']}元
- 当前价：{best_stock['当前价']}元
- 期间最高：{best_stock['期间最高']}元（最大盈利{best_stock['最大盈利']}）

---

## 💔 最差表现

**{worst_stock['代码']}**：{worst_stock['收益率']}
- 买入价：{worst_stock['买入价']}元
- 当前价：{worst_stock['当前价']}元
- 期间最低：{worst_stock['期间最低']}元（最大回撤{worst_stock['最大回撤']}）

---

## 📋 详细表现（按收益率排序）

"""
    
    # 添加详细表格
    results_sorted = results.sort_values('收益率_float', ascending=False)
    
    for idx, row in results_sorted.iterrows():
        profit_emoji = "📈" if row['收益率_float'] > 0 else "📉"
        report += f"""
### {profit_emoji} {row['排名']}. {row['代码']} ({row['收益率']})

| 项目 | 数值 |
|------|------|
| 买入价格 | {row['买入价']}元（{row['买入日']}开盘） |
| 当前价格 | {row['当前价']}元（{row['当前日']}收盘） |
| **收益率** | **{row['收益率']}** |
| 期间最高 | {row['期间最高']}元（最大盈利{row['最大盈利']}） |
| 期间最低 | {row['期间最低']}元（最大回撤{row['最大回撤']}） |
| 每日涨跌 | {row['每日涨跌']} |

**选股时数据**：
- 收盘价：{row['原始收盘价']}元，涨幅：{row['原始涨幅']}%
- 量比：{row['原始量比']}，成交额：{float(row['原始成交额'])/10000:.2f}亿

---
"""
    
    report += f"""
## 💡 结论

### ✅ 策略优势
"""
    
    if win_rate >= 60:
        report += f"- **胜率较高**：{win_rate:.1f}%的股票上涨，说明策略选股质量不错\n"
    
    if avg_return > 0:
        report += f"- **平均盈利**：平均收益率{avg_return:+.2f}%，在{results['交易天数'].iloc[0]}个交易日内获得正收益\n"
    
    if best_return > 10:
        report += f"- **有爆发股**：最佳表现{best_return:+.2f}%，说明策略能捕捉到强势股\n"
    
    report += f"""
### ⚠️  风险提示
"""
    
    if lose_count > 0:
        report += f"- 仍有{lose_count}只股票下跌，需要严格止损\n"
    
    if worst_return < -5:
        report += f"- 最大亏损达到{worst_return:.2f}%，风险控制很重要\n"
    
    report += f"""
### 📈 操作建议

基于本次回测结果：
1. **选股有效性**：{"较好" if win_rate >= 55 and avg_return > 0 else "需改进"}
2. **仓位管理**：建议Top3分别配置30%仓位
3. **止损设置**：建议跌破买入价-5%或跌破MA10时止损
4. **止盈设置**：建议盈利>8-10%时分批止盈

---

**免责声明**：本报告仅供参考，不构成投资建议。股市有风险，投资需谨慎。
"""
    
    return report


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='近期回测：验证选股策略')
    parser.add_argument('--date', type=str, default='20251231', help='选股日期（默认20251231）')
    parser.add_argument('--end-date', type=str, default=None, help='统计截止日期（默认最新交易日）')
    parser.add_argument('--top', type=int, default=None, help='只统计TopN股票（默认全部）')
    
    args = parser.parse_args()
    
    try:
        print("=" * 80)
        print("📊 启动初期选股策略 - 近期回测")
        print("=" * 80)
        
        # 1. 连接数据库
        engine = get_db_engine()
        print("✓ 数据库连接成功")
        
        # 2. 运行选股策略
        selected_stocks = run_strategy_for_date(engine, args.date)
        
        # 3. 如果指定了top，只取TopN
        if args.top:
            selected_stocks = selected_stocks.head(args.top)
            print(f"\n✓ 只统计Top{args.top}股票")
        
        print(f"\n✓ 选出 {len(selected_stocks)} 只股票")
        
        # 4. 获取股票代码列表
        stock_codes = selected_stocks['代码'].tolist()
        
        # 5. 确定统计截止日期
        if args.end_date:
            end_date = args.end_date
        else:
            # 使用数据库最新日期
            with engine.connect() as conn:
                result = conn.execute(text("SELECT MAX(trade_date) FROM stock_daily"))
                latest_date = result.fetchone()[0]
                end_date = latest_date.strftime("%Y%m%d")
        
        print(f"✓ 统计截止日期：{end_date}")
        
        # 6. 获取这些股票的后续表现
        performance_data = get_stock_performance(engine, stock_codes, args.date, end_date)
        
        # 7. 计算收益率
        results = calculate_returns(selected_stocks, performance_data, args.date)
        
        # 8. 生成报告
        report = generate_report(results, args.date, end_date)
        
        # 9. 保存报告
        output_dir = Path(__file__).resolve().parents[1] / "output"
        report_file = output_dir / f"backtest_{args.date}_to_{end_date}.md"
        report_file.write_text(report, encoding='utf-8')
        
        # 10. 保存CSV
        csv_file = output_dir / f"backtest_{args.date}_to_{end_date}.csv"
        results.to_csv(csv_file, index=False, encoding='utf-8-sig')
        
        print("\n" + "=" * 80)
        print("✅ 回测完成！")
        print(f"📄 报告文件：{report_file}")
        print(f"📊 数据文件：{csv_file}")
        print("=" * 80)
        
        # 打印简要统计
        results['收益率_float'] = results['收益率'].str.rstrip('%').astype(float)
        print(f"\n📊 快速统计：")
        print(f"  选股数量：{len(results)} 只")
        print(f"  平均收益率：{results['收益率_float'].mean():+.2f}%")
        print(f"  胜率：{len(results[results['收益率_float'] > 0]) / len(results) * 100:.1f}%")
        print(f"  最佳：{results['收益率_float'].max():+.2f}%")
        print(f"  最差：{results['收益率_float'].min():+.2f}%")
        
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

