import akshare as ak
import pandas as pd

code = "601330"

print("=== 1. 技术面 ===")
try:
    df_k = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20240101", adjust="qfq")
    if not df_k.empty:
        closes = df_k['收盘'].tail(20).values
        ma5 = sum(closes[-5:])/5
        ma10 = sum(closes[-10:])/10
        ma20 = sum(closes[-20:])/20
        current_price = closes[-1]
        print(f"最新价: {current_price}")
        print(f"MA5: {ma5:.2f}, MA10: {ma10:.2f}, MA20: {ma20:.2f}")
        print(f"近期支撑(20日最低): {min(closes):.2f}")
        print(f"近期压力(20日最高): {max(closes):.2f}")
except Exception as e:
    print("技术面获取失败:", e)

print("\n=== 3. 财务面 ===")
try:
    df_fin = ak.stock_financial_abstract_th(symbol=code)
    if not df_fin.empty:
        latest = df_fin.iloc[0]
        print(f"最新财报指标:")
        for k, v in latest.items():
            if k != '股票代码':
                print(f"  {k}: {v}")
except Exception as e:
    print("财务面获取失败:", e)

