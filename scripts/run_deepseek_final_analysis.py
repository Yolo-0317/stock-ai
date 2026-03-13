import os
import sys
import glob
import pandas as pd
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
load_dotenv()

from tushare_mcp import deepseek_trade_signal, _call_deepseek_api
from scripts.fetch_akshare_data import (
    get_stock_fundamental, 
    get_market_sentiment, 
    get_stock_fund_flow, 
    get_stock_news
)

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
        print("❌ 找不到选股结果文件")
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print("❌ 选股结果为空")
        return

    # 按评分优先
    if '总分' in df.columns:
        df = df.sort_values(by=['总分', '标签数', '成交额(万)'], ascending=False)

    # 选取前 5 只股票进行 AI 分析
    top_stocks = df.head(5).copy()

    print(f"🚀 开始全维度 DeepSeek AI 分析 (基准日期: {date_str})...")

    # 1. 获取全局信息（只获取一次）
    print("📊 获取大盘情绪与资金流向排名...")
    market_sentiment = get_market_sentiment()
    
    # 预先加载基本面缓存（如果存在）
    fundamentals_cache = {}
    cache_path = f"output/fundamentals_{date_str}.json"
    if os.path.exists(cache_path):
        with open(cache_path, 'r', encoding='utf-8') as f:
            fundamentals_cache = json.load(f)

    reports = []
    for _, row in top_stocks.iterrows():
        full_code = _to_full_code(row['代码'])
        code_6 = full_code.split('.')[0]
        
        print(f"\n🔍 正在深度挖掘: {full_code}...")
        
        # 2. 获取个股多维数据
        # 基本面
        if code_6 in fundamentals_cache:
            fundamental = fundamentals_cache[code_6]
        else:
            fundamental = get_stock_fundamental(code_6)
        
        # 资金流
        fund_flow = get_stock_fund_flow(code_6)
        
        # 新闻舆情
        news = get_stock_news(code_6)
        
        # 技术面分析 (AI 预处理)
        print(f"  📈 分析技术面...")
        try:
            tech_report = deepseek_trade_signal(full_code)
        except Exception as e:
            print(f"  ⚠️ 技术面分析失败: {e}")
            tech_report = "技术面数据获取失败"

        time.sleep(1) # 增加延迟，防止被封

        # 3. 整合 Prompt 发给 DeepSeek
        combined_prompt = f"""
        你是一个顶级的量化私募策略师。请根据以下【全维度数据】，给出该股票的最终投资决策。

        ## 1. 股票基础
        - 代码: {full_code} | 名称: {fundamental.get('名称', 'N/A')} | 行业: {fundamental.get('行业', 'N/A')}
        - 策略评分: {row.get('总分', 'N/A')} | 标签: {row.get('策略标签', 'N/A')}

        ## 2. 资金流向 (AkShare)
        - 主力净流入: {fund_flow.get('今日主力净流入', 'N/A')}
        - 超大单/大单: {fund_flow.get('今日超大单净流入', 'N/A')} / {fund_flow.get('今日大单净流入', 'N/A')}
        - 净流入占比: {fund_flow.get('主力净流入占比', 'N/A')}

        ## 3. 舆情新闻 (最近 5 条)
        {chr(10).join(['- ' + n for n in news]) if news else '暂无重大新闻'}

        ## 4. 基本面指标
        - PE(动): {fundamental.get('市盈率-动态', 'N/A')} | PB: {fundamental.get('市净率', 'N/A')}
        - ROE: {fundamental.get('ROE', 'N/A')}% | 净利增长: {fundamental.get('净利润增长率', 'N/A')}%
        - 总市值: {fundamental.get('总市值', 'N/A')}

        ## 5. 大盘背景
        - 指数: {market_sentiment.get('上证指数', 'N/A')}
        - 涨跌分布: {market_sentiment.get('涨跌分布', 'N/A')}
        - 热门板块: {', '.join(market_sentiment.get('热门板块', []))}

        ## 6. 技术面预分析
        {tech_report}

        ## 任务要求
        1. **真伪辨别**：结合资金流和新闻，判断技术面的“突破”是主力真金白银建仓，还是诱多/利好兑现。
        2. **风险评估**：结合大盘情绪 and *ST 风险（如有），给出该股的防御性评价。
        3. **最终结论**：强烈推荐 / 建议关注 / 继续观望 / 回避。
        4. **操盘计划**：给出精确的买入区间、止损位、目标位、预期持有周期。

        ## 输出格式
        最终结论: [结论]
        确定性评分: [0-100]
        核心逻辑: [1. 资金面; 2. 消息面; 3. 技术面共振点]
        操盘计划: [买入/止损/目标/周期]
        """
        
        print(f"  🧠 DeepSeek 综合决策中...")
        try:
            final_report = _call_deepseek_api(combined_prompt, temperature=0.3)
            reports.append({
                'row': row,
                'final_report': final_report,
                'full_code': full_code,
                'fundamental': fundamental,
                'fund_flow': fund_flow,
                'news': news
            })
        except Exception as e:
            print(f"  ❌ AI 决策失败: {e}")

    # 4. 生成 Markdown 报告
    output_md = f"output/deepseek_full_v2_analysis_{date_str}.md"
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(f"# 🚀 DeepSeek 全维度选股决策报告 ({date_str})\n\n")
        
        # 宏观摘要
        f.write(f"## 🌍 市场环境摘要\n")
        f.write(f"- **上证指数**: {market_sentiment.get('上证指数')}\n")
        f.write(f"- **涨跌分布**: {market_sentiment.get('涨跌分布')}\n")
        f.write(f"- **热门板块**: {', '.join(market_sentiment.get('热门板块'))}\n\n")
        
        # 摘要表格
        f.write("## 📊 选股池综合摘要\n\n")
        f.write("| 名称 | 代码 | 总分 | 主力流入 | 建议动作 | AI 结论 |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in reports:
            name = r['fundamental'].get('名称', 'N/A')
            flow = r['fund_flow'].get('今日主力净流入', 'N/A')
            # 提取 AI 结论中的第一行
            ai_conclusion = r['final_report'].split('\n')[0].replace('最终结论:', '').strip()
            f.write(f"| {name} | {r['full_code']} | {r['row'].get('总分')} | {flow} | {r['row'].get('建议动作')} | {ai_conclusion} |\n")
        
        f.write("\n---\n\n")

        # 详细分析
        for r in reports:
            f.write(f"### 🎯 {r['fundamental'].get('名称')} ({r['full_code']})\n\n")
            
            # 核心指标快照
            f.write("#### 💡 核心指标快照\n")
            f.write(f"- **资金面**: 主力净流入 {r['fund_flow'].get('今日主力净流入')} ({r['fund_flow'].get('主力净流入占比')})\n")
            if r['news']:
                f.write(f"- **消息面**: {r['news'][0]} (等 {len(r['news'])} 条)\n")
            f.write(f"- **估值面**: PE {r['fundamental'].get('市盈率-动态')} | ROE {r['fundamental'].get('ROE')}% | 市值 {r['fundamental'].get('总市值')}\n\n")
            
            f.write("#### 📝 AI 深度决策\n")
            f.write(r['final_report'])
            f.write("\n\n---\n\n")

    print(f"\n✨ 全维度分析完成！报告已保存至: {output_md}")

if __name__ == "__main__":
    run_analysis()
