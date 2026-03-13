#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单独读取策略选股结果，慢速、高可靠地获取基本面数据并保存
"""

import os
import sys
import time
import glob
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

load_dotenv()

try:
    import akshare as ak
except ImportError:
    print("❌ 错误：未安装 akshare")
    sys.exit(1)

def _latest_selection_file():
    files = glob.glob("output/stock_selection_combined_*.csv")
    if not files:
        return None, None
    files.sort(key=os.path.getmtime, reverse=True)
    latest = files[0]
    date_str = Path(latest).stem.split("_")[-1]
    return latest, date_str

def get_tushare_fallback(code):
    """Tushare 备份方案"""
    try:
        import tushare as ts
        token = os.getenv("TUSHARE_TOKEN")
        if not token: return None
        ts.set_token(token)
        pro = ts.pro_api()
        
        code_full = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
        
        # 获取基础信息 (这个接口通常权限要求低)
        df = pro.stock_basic(ts_code=code_full, fields='name,industry')
        if df is None or df.empty: return None
        
        res = {
            "名称": df.iloc[0]['name'],
            "行业": df.iloc[0]['industry']
        }
        return res
    except:
        return None

def get_robust_fundamental(code, market_df=None):
    # 统一转换为 6 位数字字符串
    if isinstance(code, (int, float)):
        code_6 = f"{int(code):06d}"
    else:
        code_6 = str(code).split('.')[0].zfill(6)
        
    res = {
        "代码": code_6, 
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "名称": "N/A",
        "行业": "N/A",
        "总市值": "N/A",
        "流通市值": "N/A",
        "市盈率-动态": "N/A",
        "市净率": "N/A",
        "ROE": "N/A",
        "净利润增长率": "N/A"
    }
    
    # 1. 尝试 AkShare 基础代码表获取名称（最稳，不依赖 EM）
    try:
        df_name = ak.stock_info_a_code_name()
        if df_name is not None and not df_name.empty:
            match = df_name[df_name['code'] == code_6]
            if not match.empty:
                res["名称"] = match.iloc[0]['name']
    except: pass

    # 2. 尝试从市场快照中提取 (如果之前获取成功)
    if market_df is not None and not market_df.empty:
        row = market_df[market_df['代码'] == code_6]
        if not row.empty:
            r = row.iloc[0]
            if res["名称"] == "N/A": res["名称"] = r.get("名称", "N/A")
            res["市盈率-动态"] = r.get("市盈率-动态", "N/A")
            res["市净率"] = r.get("市净率", "N/A")
            res["总市值"] = r.get("总市值", "N/A")
            res["流通市值"] = r.get("流通市值", "N/A")

    # 3. 如果还是没有名称，尝试 Tushare 备份
    if res["名称"] == "N/A":
        ts_res = get_tushare_fallback(code_6)
        if ts_res:
            res.update(ts_res)

    # 4. 财务指标 (ROE, 增长率) - 仅 AkShare EM 提供
    try:
        df_f = ak.stock_financial_analysis_indicator_em(symbol=code_6)
        if df_f is not None and not df_f.empty:
            latest = df_f.iloc[0]
            res["ROE"] = latest.get("净资产收益率(%)", "N/A")
            res["净利润增长率"] = latest.get("净利润比上年同期增长(%)", "N/A")
    except: pass

    return res

def main():
    csv_path, date_str = _latest_selection_file()
    if not csv_path:
        print("❌ 找不到选股文件")
        return

    print(f"🚀 读取选股结果: {csv_path}")
    df = pd.read_csv(csv_path)
    if df.empty:
        print("❌ 文件为空")
        return

    stocks = df.head(10)['代码'].tolist()
    
    print("🚀 获取全市场快照...")
    try:
        market_df = ak.stock_zh_a_spot_em()
    except:
        market_df = pd.DataFrame()

    all_data = {}
    for code in stocks:
        data = get_robust_fundamental(code, market_df=market_df)
        code_6 = data["代码"]
        all_data[code_6] = data
        print(f"✅ {code_6} ({data['名称']}) 完成")
        time.sleep(2)

    output_json = f"output/fundamentals_{date_str}.json"
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
    
    print(f"\n✨ 基本面数据已保存至: {output_json}")

if __name__ == "__main__":
    main()
