#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI深度分析Top5股票（结合东方财富网站信息）

功能：
1. 读取选股结果CSV的Top5
2. 访问东方财富网站获取实时信息
3. 使用DeepSeek AI进行深度分析
4. 输出Markdown报告

使用方法：
    uv run python scripts/ai_review_top5.py output/stock_selection_ma5_20260108.csv
"""

from __future__ import annotations

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

from dotenv import load_dotenv
import pandas as pd
import requests

# 加载环境变量
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)


def read_top5_stocks(csv_path: str, top_n: int = 5) -> pd.DataFrame:
    """读取CSV文件的TopN股票"""
    print(f"📖 读取选股结果：{csv_path}")
    df = pd.read_csv(csv_path, encoding='utf-8-sig')
    
    # 去掉排名列
    if '排名' in df.columns:
        df = df.drop(columns=['排名'])
    
    # 确保代码列是字符串类型
    if '代码' in df.columns:
        df['代码'] = df['代码'].astype(str).str.replace('.0', '', regex=False)
    
    # 只取前N只
    top_stocks = df.head(top_n)
    print(f"✓ 成功读取Top{top_n}股票")
    
    return top_stocks


def get_stock_info_from_eastmoney(ts_code) -> dict:
    """
    从东方财富获取股票信息（通过浏览器）
    
    注：这个函数返回的是需要从浏览器获取的信息的URL
    实际获取需要使用browser工具
    """
    # 将数字转为字符串并补齐6位
    code = str(int(ts_code)).zfill(6)
    
    # 判断市场（根据代码规则）
    if code.startswith('6'):  # 上海
        market_prefix = 'sh'
        market_code = '1'
    elif code.startswith('688'):  # 科创板
        market_prefix = 'sh'
        market_code = '1'
    elif code.startswith('000') or code.startswith('001'):  # 深圳主板
        market_prefix = 'sz'
        market_code = '0'
    elif code.startswith('002'):  # 中小板
        market_prefix = 'sz'
        market_code = '0'
    elif code.startswith('300') or code.startswith('301'):  # 创业板
        market_prefix = 'sz'
        market_code = '0'
    else:
        market_prefix = 'sz'
        market_code = '0'
    
    # 东方财富个股页面URL
    url = f"https://quote.eastmoney.com/{market_prefix}{code}.html"
    
    return {
        'url': url,
        'code': code,
        'market': market_code
    }


def call_deepseek_api(messages: list, max_retries: int = 3) -> str:
    """调用DeepSeek API进行分析（带重试机制）"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        raise ValueError("❌ 环境变量 DEEPSEEK_API_KEY 未设置")
    
    url = "https://api.deepseek.com/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 4000
    }
    
    print("🤖 正在调用DeepSeek AI分析...")
    print("💡 提示：AI深度分析可能需要1-2分钟，请耐心等待...")
    
    # 重试机制
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=data, timeout=120)
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                print("✅ AI分析完成")
                return content
            else:
                error_msg = f"API调用失败: {response.status_code} - {response.text}"
                if attempt < max_retries - 1:
                    print(f"⚠️ {error_msg}，正在重试（{attempt + 1}/{max_retries}）...")
                    continue
                else:
                    raise Exception(error_msg)
        
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"⚠️ API调用超时，正在重试（{attempt + 1}/{max_retries}）...")
                print("   提示：网络可能较慢，请耐心等待...")
                continue
            else:
                raise Exception(f"API调用超时（已重试{max_retries}次）。可能原因：\n"
                              "  1. 网络连接不稳定\n"
                              "  2. DeepSeek服务器响应慢\n"
                              "  建议：稍后再试或检查网络连接")
        
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ 发生错误：{e}，正在重试（{attempt + 1}/{max_retries}）...")
                continue
            else:
                raise
    
    raise Exception("API调用失败（已达到最大重试次数）")


def analyze_top5_with_ai(top5_df: pd.DataFrame, eastmoney_data: list) -> str:
    """使用AI分析TopN股票"""
    
    stock_count = len(top5_df)
    
    # 构建提示词
    stocks_info = []
    for idx, row in top5_df.iterrows():
        stock_data = {
            '代码': row['代码'],
            '收盘价': row['收盘价'],
            '今日涨幅': f"{row['今日涨幅%']}%",
            'MA5': row['MA5'],
            'MA10': row['MA10'],
            'MA20': row['MA20'],
            '价格乖离MA10': f"{row['价格乖离MA10%']}%",
            'MA5-MA10距离': f"{row['MA5-MA10距离%']}%",
            '量比': row['量比'],
            'MA10增长率': f"{row['MA10增长率%']}%",
            '20日涨幅': f"{row['20日涨幅%']}%",
            '10日涨幅': f"{row['10日涨幅%']}%",
            '5日涨幅': f"{row['5日涨幅%']}%",
            '距30日高点': f"{row['距30日高点%']}%",
            '成交额': f"{row['成交额(万)']/10000:.2f}亿"
        }
        stocks_info.append(stock_data)
    
    # 构建AI提示词
    prompt = f"""你是一个专业的股票分析师。我刚通过技术选股筛选出了Top{stock_count}股票（按成交额排序），请你深度分析这{stock_count}只股票。

# 选股策略说明
这些股票都符合"启动初期"特征（提高标准版）：
- 前期平稳：近20日涨幅0-15%（避免追高）
- 明确启动：近5日涨幅5-15%（避免假突破）
- 价格站稳：在MA10上方0-10%
- 明确发散：MA5-MA10距离1-8%
- 明显放量：量比>1.8（强势确认）
- 今日上涨：今日涨幅>0%
- 多头排列：MA5>MA10>MA20，MA10增长率>0.5%

# Top{stock_count}股票技术数据

{json.dumps(stocks_info, ensure_ascii=False, indent=2)}

# 分析要求

请对每只股票进行深度分析，输出Markdown格式报告，包含：

## 🌟 Top{stock_count}深度分析

### 🥇 第1推荐：[股票代码]（成交额XXX亿）

**技术面分析**：
- 启动确定性：高/中/低（基于量比、涨幅、均线）
- 形态评价：[均线形态、价格位置评价]
- 量价配合：[是否放量上涨]

**优势**：
- [列出2-3个优势]

**风险点**：
- [列出1-2个风险]

**操作建议**：
- 买入时机：[现在/回调到XX/突破XX]
- 建议仓位：[30%试探 / 50%标准 / 等等]
- 止损位：[具体价格或MA10等]
- 止盈目标：[具体价格或涨幅]

**综合评分**：★★★★★（满分5星）

---

[对其他{stock_count-1}只股票做同样分析]

## 📊 Top{stock_count}对比

| 排名 | 代码 | 启动确定性 | 风险级别 | 推荐度 |
|------|------|------------|----------|--------|
| 1 | XXX | 高 | 中 | ★★★★★ |
...

## ⚠️ 整体风险提示

1. [整体市场风险]
2. [技术风险]
3. [操作建议]

## 💡 优先级建议

如果只选1-2只，建议优先关注：
1. [股票代码]：[理由]
2. [股票代码]：[理由]

---

请用专业、客观的语言分析，给出实用的操作建议。"""

    messages = [
        {"role": "system", "content": "你是一个专业的股票分析师，擅长技术分析和风险控制。"},
        {"role": "user", "content": prompt}
    ]
    
    analysis = call_deepseek_api(messages)
    
    return analysis


def save_analysis_report(analysis: str, csv_path: str) -> str:
    """保存分析报告"""
    # 生成报告文件名
    csv_file = Path(csv_path)
    report_file = csv_file.parent / f"{csv_file.stem}_ai_review.md"
    
    # 添加报告头部
    header = f"""# 启动初期选股 - AI深度分析报告

**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**数据来源**：{csv_file.name}  
**分析模型**：DeepSeek AI

---

"""
    
    full_report = header + analysis
    
    # 保存
    report_file.write_text(full_report, encoding='utf-8')
    
    print(f"\n✅ AI分析报告已保存：{report_file}")
    
    return str(report_file)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AI深度分析Top5股票')
    parser.add_argument('csv_file', type=str, help='选股结果CSV文件路径')
    parser.add_argument('--top', type=int, default=5, help='分析股票数量（默认5只）')
    parser.add_argument('--timeout', type=int, default=120, help='API超时时间（秒，默认120）')
    
    args = parser.parse_args()
    
    try:
        print("=" * 80)
        print(f"📊 AI深度分析Top{args.top}股票（结合东方财富网站）")
        print("=" * 80)
        
        # 1. 读取TopN
        top5_df = read_top5_stocks(args.csv_file, args.top)
        
        print(f"\n📋 Top{args.top}股票列表：")
        for idx, row in top5_df.iterrows():
            print(f"  {idx+1}. {row['代码']} - 成交额{row['成交额(万)']/10000:.2f}亿")
        
        # 2. 获取东方财富信息（URL）
        print("\n🌐 准备东方财富网站信息...")
        eastmoney_data = []
        for idx, row in top5_df.iterrows():
            info = get_stock_info_from_eastmoney(row['代码'])
            eastmoney_data.append(info)
            print(f"  {row['代码']}: {info['url']}")
        
        print("\n💡 提示：AI将基于技术指标进行分析")
        print("  （如需获取东方财富实时数据，需要使用浏览器工具）")
        
        # 3. AI分析
        analysis = analyze_top5_with_ai(top5_df, eastmoney_data)
        
        # 4. 保存报告
        report_path = save_analysis_report(analysis, args.csv_file)
        
        print("\n" + "=" * 80)
        print(f"✅ 分析完成！")
        print(f"📄 报告路径：{report_path}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

