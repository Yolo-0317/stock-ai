#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从东方财富抓取全市场当日资金流向数据并入库 MySQL
"""

import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path
ensure_repo_root_on_path()

load_dotenv()

def get_db_engine():
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        print("❌ 错误：未设置 MYSQL_URL 环境变量")
        sys.exit(1)
    return create_engine(mysql_url, pool_pre_ping=True)

def create_table_if_not_exists(engine):
    sql = """
    CREATE TABLE IF NOT EXISTS capital_flow (
        ts_code     VARCHAR(10)  NOT NULL,
        trade_date  DATE         NOT NULL,
        main_net    FLOAT,   -- 主力净流入（万元）
        main_pct    FLOAT,   -- 主力净占比（%）
        big_net     FLOAT,   -- 超大单净流入（万元）
        big_pct     FLOAT,   -- 超大单净占比（%）
        mid_net     FLOAT,   -- 大单净流入（万元）
        mid_pct     FLOAT,   -- 大单净占比（%）
        PRIMARY KEY (ts_code, trade_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()

def fetch_eastmoney_capital_flow():
    """
    从东方财富接口抓取全市场资金流向 (分多页抓取以获取全市场)
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    all_diff = []
    
    for page in range(1, 60):  # 5000+ 股票，每页 100，约 50-60 页
        params = {
            "pn": page,
            "pz": 100,
            "po": 1,
            "np": 1,
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "fltt": 2,
            "invt": 2,
            "fid": "f62",
            "fs": "m:0+t:6,m:0+t:13,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f62,f184,f66,f69,f72,f75,f124",
        }
        
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data and "data" in data and "diff" in data["data"]:
                diff = data["data"]["diff"]
                if not diff: break
                all_diff.extend(diff)
                if len(diff) < 100: break
            else:
                break
        except Exception as e:
            print(f"❌ 抓取东方财富资金流数据失败 (Page {page}): {e}")
            break
        
        # 稍微停顿一下，避免过于频繁
        time.sleep(0.1)
        
    return all_diff

def sync_capital_flow(trade_date: str = None):
    """
    同步资金流向数据到数据库
    :param trade_date: YYYYMMDD 格式日期，若为空则使用今日
    """
    engine = get_db_engine()
    create_table_if_not_exists(engine)
    
    print("📡 正在从东方财富获取实时资金流向数据...")
    raw_data = fetch_eastmoney_capital_flow()
    if not raw_data:
        print("⚠️ 未获取到有效数据")
        return
    
    # 确定交易日期
    if trade_date:
        dt = datetime.strptime(trade_date, "%Y%m%d").date()
    else:
        # 如果接口返回了时间戳(f124)，优先使用
        if raw_data and raw_data[0].get("f124"):
            dt = datetime.fromtimestamp(raw_data[0]["f124"]).date()
        else:
            dt = datetime.now().date()
    
    print(f"📅 目标日期: {dt}")
    
    records = []
    for item in raw_data:
        # f12: 代码, f62: 主力净流入, f184: 主力占比, f66: 超大单净, f69: 超大单占比, f72: 大单净, f75: 大单占比
        code = item.get("f12")
        if not code: continue
        
        records.append({
            "ts_code": code,
            "trade_date": dt,
            "main_net": round(float(item.get("f62", 0)) / 10000, 2) if item.get("f62") != "-" else 0,
            "main_pct": float(item.get("f184", 0)) if item.get("f184") != "-" else 0,
            "big_net": round(float(item.get("f66", 0)) / 10000, 2) if item.get("f66") != "-" else 0,
            "big_pct": float(item.get("f69", 0)) if item.get("f69") != "-" else 0,
            "mid_net": round(float(item.get("f72", 0)) / 10000, 2) if item.get("f72") != "-" else 0,
            "mid_pct": float(item.get("f75", 0)) if item.get("f75") != "-" else 0,
        })
    
    if not records:
        print("⚠️ 无有效记录可入库")
        return

    df = pd.DataFrame(records)
    
    # 使用 INSERT IGNORE 入库
    sql = """
    INSERT IGNORE INTO capital_flow 
    (ts_code, trade_date, main_net, main_pct, big_net, big_pct, mid_net, mid_pct)
    VALUES (:ts_code, :trade_date, :main_net, :main_pct, :big_net, :big_pct, :mid_net, :mid_pct)
    """
    
    count = 0
    with engine.connect() as conn:
        # 批量执行
        for i in range(0, len(df), 500):
            batch = df.iloc[i:i+500].to_dict('records')
            conn.execute(text(sql), batch)
            count += len(batch)
        conn.commit()
    
    print(f"✅ 资金流向同步完成！入库 {count} 条记录")

if __name__ == "__main__":
    sync_capital_flow()
