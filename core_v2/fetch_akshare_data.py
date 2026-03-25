#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 AkShare 获取股票全维度数据（基本面、资金流、新闻、大盘情绪）
优化版：增加重试机制、备选数据源和异常处理
"""

import os
import sys
import time
import random
import pandas as pd
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

try:
    import akshare as ak
except ImportError:
    print("❌ 错误：未安装 akshare，请运行：pip install akshare")
    sys.exit(1)

def _fetch_with_retry(func, name, max_retries=3, delay_range=(1, 3), **kwargs):
    """
    通用抓取重试装饰器/包装器
    """
    for i in range(max_retries):
        try:
            # 随机延迟，模拟人类行为
            wait_time = random.uniform(*delay_range)
            time.sleep(wait_time)
            
            df = func(**kwargs)
            if df is not None and not df.empty:
                return df
            print(f"    ⚠️ {name} 第 {i+1} 次尝试结果为空...")
        except Exception as e:
            print(f"    ⚠️ {name} 第 {i+1} 次抓取异常: {e}")
            if i == max_retries - 1:
                break
            # 遇到连接重置等问题，增加等待时间
            time.sleep(wait_time * 2)
    return None

def get_stock_fundamental(code, delay=1.0):
    """
    获取单只股票的基本面数据 (增强版：优先通过浏览器从东方财富获取)
    """
    code_6 = "".join(filter(str.isdigit, str(code)))[:6]
    result = {
        "代码": code_6,
        "名称": "N/A",
        "行业": "N/A",
        "市盈率-动态": "N/A",
        "市净率": "N/A",
        "总市值": "N/A",
        "流通市值": "N/A",
        "ROE": "N/A",
        "净利润增长率": "N/A",
        "最新价": 0.0
    }
    
    try:
        # 1. 基础信息 (行业、市值、最新价) - 东方财富接口
        info_df = _fetch_with_retry(ak.stock_individual_info_em, f"{code_6} 基础信息", symbol=code_6)
        if info_df is not None:
            info_dict = dict(zip(info_df['item'], info_df['value']))
            if result["名称"] == "N/A":
                result["名称"] = info_dict.get("股票简称", result["名称"])
            result["总市值"] = info_dict.get("总市值", "N/A")
            result["流通市值"] = info_dict.get("流通市值", "N/A")
            result["行业"] = info_dict.get("行业", "N/A")
            result["最新价"] = float(info_dict.get("最新", 0.0))

        # 尝试通过东方财富 F10 接口获取 (ROE, 增长率)
        try:
            # 尝试使用 akshare 提供的同花顺财务摘要接口，这通常比东财 Ajax 接口在脚本中更稳定
            ths_df = _fetch_with_retry(ak.stock_financial_abstract_ths, f"{code_6} 财务摘要", symbol=code_6)
            if ths_df is not None and not ths_df.empty:
                latest = ths_df.iloc[-1]
                result["ROE"] = str(latest.get("净资产收益率", "N/A")).replace("%", "")
                result["净利润增长率"] = str(latest.get("净利润同比增长率", "N/A")).replace("%", "")
                print(f"    ✅ 成功通过同花顺 F10 获取基本面: {code_6} (ROE: {result['ROE']}%, 增长率: {result['净利润增长率']}%)")
        except Exception as e:
            print(f"    ⚠️ 同花顺 F10 获取失败: {e}")

        # 如果同花顺没拿到，再尝试新浪财务指标 (作为最后兜底)
        if result["ROE"] in ["N/A", "-", None]:
            ths_df = _fetch_with_retry(ak.stock_financial_abstract_ths, f"{code_6} 财务摘要", symbol=code_6)
            if ths_df is not None:
                latest = ths_df.iloc[-1]
                result["ROE"] = str(latest.get("净资产收益率", "N/A")).replace("%", "")
                result["净利润增长率"] = str(latest.get("净利润同比增长率", "N/A")).replace("%", "")
                
                if result["最新价"] > 0:
                    bps = latest.get("每股净资产")
                    eps = latest.get("基本每股收益")
                    report_date = latest.get("报告期", "")
                    
                    if bps and float(bps) > 0:
                        result["市净率"] = round(result["最新价"] / float(bps), 2)
                    if eps and float(eps) != 0:
                        month = int(report_date.split("-")[1]) if "-" in report_date else 12
                        ann_factor = 12.0 / month
                        ann_eps = float(eps) * ann_factor
                        result["市盈率-动态"] = round(result["最新价"] / ann_eps, 2)

    except Exception as e:
        print(f"  ⚠️ 获取 {code_6} 基本面异常: {e}")
        
    return result

def get_stock_fund_flow(code):
    """
    获取主力资金流向
    """
    code_6 = "".join(filter(str.isdigit, str(code)))[:6]
    market = "sh" if code_6.startswith("6") else "sz"
    flow_data = {
        "今日主力净流入": "N/A",
        "今日超大单净流入": "N/A",
        "今日大单净流入": "N/A",
        "主力净流入占比": "N/A"
    }
    
    df = _fetch_with_retry(ak.stock_individual_fund_flow, f"{code_6} 资金流", stock=code_6, market=market)
    if df is not None:
        latest = df.iloc[-1]
        flow_data["今日主力净流入"] = f"{latest['主力净流入-净额']}元"
        flow_data["今日超大单净流入"] = f"{latest['超大单净流入-净额']}元"
        flow_data["今日大单净流入"] = f"{latest['大单净流入-净额']}元"
        flow_data["主力净流入占比"] = f"{latest['主力净流入-净占比']}%"
    
    return flow_data

def get_stock_news(code, limit=5):
    """
    获取个股最新新闻标题
    """
    code_6 = "".join(filter(str.isdigit, str(code)))[:6]
    df = _fetch_with_retry(ak.stock_news_em, f"{code_6} 新闻", symbol=code_6)
    if df is not None:
        return df['新闻标题'].head(limit).tolist()
    return []

def get_market_sentiment():
    """
    获取大盘情绪（优化版：多源兜底）
    """
    sentiment = {
        "上证指数": "N/A",
        "涨跌分布": "N/A",
        "热门板块": []
    }
    
    # 1. 指数行情 (尝试东财，不行换新浪)
    print("    📡 获取指数行情...")
    index_df = _fetch_with_retry(ak.stock_zh_index_spot_em, "东财指数接口")
    if index_df is None:
        print("    🔄 尝试新浪指数接口...")
        index_df = _fetch_with_retry(ak.stock_zh_index_spot_sina, "新浪指数接口")
        
    if index_df is not None:
        # 东财和新浪的列名可能不同，做个兼容
        name_col = '名称' if '名称' in index_df.columns else 'name'
        price_col = '最新价' if '最新价' in index_df.columns else 'last'
        pct_col = '涨跌幅' if '涨跌幅' in index_df.columns else 'pct_change'
        
        sh = index_df[index_df[name_col] == '上证指数']
        if not sh.empty:
            sentiment["上证指数"] = f"{sh.iloc[0][price_col]} ({sh.iloc[0][pct_col]}%)"

    # 2. 涨跌分布
    print("    📡 获取涨跌分布...")
    df_spot = _fetch_with_retry(ak.stock_zh_a_spot_em, "全A股快照")
    if df_spot is not None:
        up = len(df_spot[df_spot['涨跌幅'] > 0])
        down = len(df_spot[df_spot['涨跌幅'] < 0])
        flat = len(df_spot[df_spot['涨跌幅'] == 0])
        sentiment["涨跌分布"] = f"上涨:{up} | 下跌:{down} | 平盘:{flat}"

    # 3. 热门板块
    print("    📡 获取热门板块...")
    sector_df = _fetch_with_retry(ak.stock_board_industry_name_em, "行业板块排名")
    if sector_df is not None:
        top_5 = sector_df.head(5)
        for _, row in top_5.iterrows():
            sentiment["热门板块"].append(f"{row['板块名称']}({row['涨跌幅']}%)")
            
    return sentiment

if __name__ == "__main__":
    # 测试
    code = "601857"
    print(f"--- {code} 测试 ---")
    print(get_stock_fundamental(code))
    print(get_stock_fund_flow(code))
    print(get_stock_news(code))
    print("--- 大盘测试 ---")
    print(get_market_sentiment())
