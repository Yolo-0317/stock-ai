import os
import sys
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

def analyze_one_stock(code):
    print(f"🚀 开始对股票进行全维度分析: {code}...")
    
    # 1. 获取全局信息
    print("📊 获取大盘情绪...")
    market_sentiment = get_market_sentiment()
    
    code_6 = "".join(filter(str.isdigit, str(code)))[:6]
    full_code = f"{code_6}.SH" if code_6.startswith(('60', '688')) else f"{code_6}.SZ"
    
    print(f"\n🔍 正在深度挖掘: {full_code}...")
    
    # 2. 获取个股多维数据
    fundamental = get_stock_fundamental(code_6)
    fund_flow = get_stock_fund_flow(code_6)
    news = get_stock_news(code_6)
    
    # 技术面分析
    print(f"  📈 分析技术面...")
    try:
        tech_report = deepseek_trade_signal(full_code)
    except Exception as e:
        print(f"  ⚠️ 技术面分析失败: {e}")
        tech_report = "技术面数据获取失败"

    time.sleep(1)

    # 3. 整合 Prompt 发给 DeepSeek
    combined_prompt = f"""
    你是一个顶级的量化私募策略师。请根据以下【全维度数据】，给出该股票的最终投资决策。

    ## 1. 股票基础
    - 代码: {full_code} | 名称: {fundamental.get('名称', 'N/A')} | 行业: {fundamental.get('行业', 'N/A')}

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
    1. **真伪辨别**：结合资金流和新闻，判断技术面的“突破”或“走势”是主力真金白银建仓，还是诱多/利好兑现。
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
        print("\n" + "="*50)
        print(f"🚀 {fundamental.get('名称')} ({full_code}) 分析报告")
        print("="*50)
        print(final_report)
    except Exception as e:
        print(f"  ❌ AI 决策失败: {e}")

if __name__ == "__main__":
    analyze_one_stock("600098")
