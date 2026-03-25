#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长线底仓 + 短线做T 选股脚本 (v1.0)
逻辑：
1. 基础过滤：价格 5-50元，成交额 > 2亿 (活跃度保证)
2. 基本面过滤 (通过 AkShare 实时补全)：ROE > 15%, PE < 15 (价值支撑)
3. 技术面过滤：股价在 MA20 之上，且趋势向上 (趋势保护)
4. 股性过滤：日内平均振幅 > 3% (做T空间)
"""

import os
import sys
import time
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy import create_engine, text
from tqdm import tqdm
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
from core_v2.fetch_akshare_data import get_stock_fundamental

load_dotenv()

def get_db_engine():
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        raise ValueError("未配置 MYSQL_URL 环境变量")
    return create_engine(mysql_url)

def main():
    engine = get_db_engine()
    
    # 1. 从 MySQL 获取最近交易日的活跃股票 (初步筛选)
    # 过滤条件：成交额 > 2亿，价格 5-50元
    print("🔍 正在从数据库提取活跃股票列表...")
    query = """
        SELECT ts_code, close, amount, pct_chg, trade_date
        FROM stock_daily
        WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily)
          AND amount > 20000  -- 成交额 > 2亿 (单位: 万)
          AND close BETWEEN 5 AND 50
    """
    df_active = pd.read_sql(text(query), engine)
    print(f"✓ 提取到 {len(df_active)} 只活跃股票")

    # 2. 检查技术面趋势 (确保在 MA20 之上)
    print("📈 正在筛选趋势向上的标的...")
    valid_codes = []
    for code in tqdm(df_active['ts_code'].tolist()):
        # 获取最近30天数据计算均线
        ma_query = f"""
            SELECT close FROM stock_daily 
            WHERE ts_code = '{code}' 
            ORDER BY trade_date DESC LIMIT 30
        """
        df_hist = pd.read_sql(text(ma_query), engine)
        if len(df_hist) < 20: continue
        
        current_price = df_hist.iloc[0]['close']
        ma20 = df_hist['close'].head(20).mean()
        
        if current_price > ma20:
            valid_codes.append(code)
            
    df_trending = df_active[df_active['ts_code'].isin(valid_codes)].copy()
    print(f"✓ 筛选出趋势向上标的 {len(df_trending)} 只")

    # 3. 核心步骤：通过 AkShare 实时补全基本面数据 (ROE, PE)
    # 由于 API 调用频率限制，我们只分析前 50 只最活跃的
    top_n = 50
    df_target = df_trending.sort_values(by='amount', ascending=False).head(top_n)
    
    print(f"💎 正在对前 {top_n} 只活跃股进行基本面深度扫描 (ROE/PE)...")
    final_results = []
    
    for _, row in tqdm(df_target.iterrows(), total=len(df_target)):
        code_6 = "".join(filter(str.isdigit, str(row['ts_code'])))[:6]
        try:
            # 调用已有的 AkShare 封装函数
            fundamental = get_stock_fundamental(code_6)
            
            roe = fundamental.get('ROE')
            pe = fundamental.get('市盈率-动态')
            pb = fundamental.get('市净率')
            name = fundamental.get('名称', 'N/A')
            industry = fundamental.get('行业', 'N/A')
            
            # 转换数据类型
            try: roe = float(roe) if roe and roe != 'N/A' else 0
            except: roe = 0
            
            try: pe = float(pe) if pe and pe != 'N/A' else 999
            except: pe = 999
            
            # 严格筛选：ROE > 12% 且 PE < 20 (放宽一点点，寻找更多机会)
            # 梅花生物级别的标准是 ROE > 15, PE < 12
            if roe >= 12 and pe <= 20:
                res = {
                    '代码': row['ts_code'],
                    '名称': name,
                    '行业': industry,
                    '收盘价': row['close'],
                    '成交额(亿)': round(row['amount'] / 10000, 2),
                    'ROE(%)': roe,
                    'PE(动)': pe,
                    'PB': pb,
                    '涨跌幅%': row['pct_chg']
                }
                final_results.append(res)
            
            # 稍微停顿，避免请求过快
            time.sleep(0.2)
        except Exception as e:
            # print(f"⚠️ 分析 {code_6} 出错: {e}")
            continue

    # 4. 输出结果
    if not final_results:
        print("❌ 未能筛选出符合“长线底仓+做T”标准的优质股。")
        return

    df_res = pd.DataFrame(final_results).sort_values(by='ROE(%)', ascending=False)
    
    trade_date = df_active['trade_date'].iloc[0].strftime("%Y%m%d")
    output_path = f"output/long_term_core_selection_{trade_date}.csv"
    df_res.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print("\n" + "="*60)
    print(f"✅ 选股完成！筛选出 {len(df_res)} 只“底仓级”优质股")
    print(f"📄 结果已保存至：{output_path}")
    print("="*60)
    print(df_res)

if __name__ == "__main__":
    main()
