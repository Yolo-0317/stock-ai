import os
import sys
import glob
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

from tushare_mcp import deepseek_trade_signal


def _latest_selection_file():
    files = glob.glob("output/stock_selection_combined_*.csv")
    if not files:
        return None, None
    files.sort(key=os.path.getmtime, reverse=True)
    latest = files[0]
    date_str = Path(latest).stem.split("_")[-1]
    return latest, date_str


def _to_full_code(code):
    if isinstance(code, (int, float)):
        code_str = f"{int(code):06d}"
    else:
        code_str = str(code).split('.')[0].zfill(6)
    if code_str.startswith(('60', '688')):
        return f"{code_str}.SH"
    return f"{code_str}.SZ"


def run_analysis():
    csv_path, date_str = _latest_selection_file()
    if not csv_path:
        print("❌ 找不到选股结果文件: output/stock_selection_combined_*.csv")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("❌ 选股结果为空")
        return

    # 按评分优先（兼容旧文件）
    if '总分' in df.columns:
        df = df.sort_values(by=['总分', '标签数', '成交额(万)'], ascending=False)

    # 选取前 5 只股票进行 AI 分析（控制 API 开销）
    top_stocks = df.head(5).copy()

    print(f"🚀 开始对前 {len(top_stocks)} 只股票进行 DeepSeek AI 分析...")

    reports = []
    for _, row in top_stocks.iterrows():
        full_code = _to_full_code(row['代码'])
        print(f"正在分析 {full_code}...")
        try:
            report = deepseek_trade_signal(full_code)
            reports.append((row, report, full_code))
        except Exception as e:
            print(f"❌ 分析 {full_code} 失败: {e}")

    output_md = f"output/deepseek_analysis_{date_str}.md"
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(f"# DeepSeek 综合选股 AI 分析报告 ({date_str})\n\n")

        # 新增：评分摘要
        f.write("## 评分摘要（Top 5）\n\n")
        f.write("| 代码 | 总分 | 建议动作 | 策略标签 |\n")
        f.write("|---|---:|---|---|\n")
        for _, row in top_stocks.iterrows():
            code = str(row['代码'])
            score = row['总分'] if '总分' in row else 'N/A'
            action = row['建议动作'] if '建议动作' in row else 'N/A'
            tags = row['策略标签'] if '策略标签' in row else ''
            f.write(f"| {code} | {score} | {action} | {tags} |\n")
        f.write("\n---\n\n")

        for row, report, full_code in reports:
            f.write(f"### 评分补充: {full_code}\n")
            if '总分' in row:
                f.write(f"- 总分: **{row['总分']}**\n")
            if '建议动作' in row:
                f.write(f"- 建议动作: **{row['建议动作']}**\n")
            if '策略标签' in row:
                f.write(f"- 策略标签: {row['策略标签']}\n")
            f.write("\n")
            f.write(report)
            f.write("\n\n---\n\n")

    print(f"✅ 分析完成！报告已保存至: {output_md}")


if __name__ == "__main__":
    run_analysis()
