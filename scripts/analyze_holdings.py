import os
import sys
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

from scripts.sync_tushare_daily_to_mysql import init_tushare, get_mysql_engine, fetch_daily_data, save_daily_data_to_db
from tushare_mcp import deepseek_trade_signal

def analyze_holdings():
    holdings = ["000060","000630","000791","000981","002131","002165","002218","002258","002259","002266","002340","002342","002427","002716","600108","600236","600428","600531","600583","600610","603466"]
    
    pro = init_tushare()
    engine = get_mysql_engine()
    
    # 1. 同步持仓股最新数据
    print(f"🚀 正在同步 {len(holdings)} 只持仓股的最新数据...")
    for code in holdings:
        full_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        df, _ = fetch_daily_data(pro, full_code, "20260201") # 同步最近一个月
        if not df.empty:
            save_daily_data_to_db(engine, df, full_code)
    
    # 2. 检查是否在今日选股结果中
    date_str = "20260306"
    strategy_csv = f"output/stock_selection_combined_{date_str}.csv"
    strategy_codes = []
    if os.path.exists(strategy_csv):
        strategy_df = pd.read_csv(strategy_csv)
        strategy_codes = [f"{int(c):06d}" if isinstance(c, (int, float)) else str(c).split('.')[0].zfill(6) for c in strategy_df['代码']]
    
    # 3. AI 分析
    print(f"🚀 正在对持仓股进行 AI 分析...")
    reports = []
    for code in holdings:
        full_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        in_strategy = "【今日选股入选】" if code in strategy_codes else ""
        print(f"分析 {full_code} {in_strategy}...")
        try:
            report = deepseek_trade_signal(full_code)
            reports.append(f"## {full_code} {in_strategy}\n{report}")
        except Exception as e:
            reports.append(f"## {full_code} {in_strategy}\n分析失败: {e}")

    # 保存报告
    output_md = f"output/holdings_analysis_{date_str}.md"
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(f"# 持仓股深度分析报告 ({date_str})\n\n")
        f.write(f"持仓总数: {len(holdings)} 只\n")
        f.write(f"今日选股入选: {len([c for c in holdings if c in strategy_codes])} 只\n\n")
        f.write("\n\n---\n\n".join(reports))
            
    print(f"✅ 持仓分析完成！报告已保存至: {output_md}")

if __name__ == "__main__":
    analyze_holdings()
