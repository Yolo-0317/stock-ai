import akshare as ak
from datetime import datetime
import time
import sys

def fetch_data(code):
    print(f"DEBUG: Starting fetch for {code} at {datetime.now()}")
    for i in range(3):
        try:
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                row = df[df['代码'] == code]
                if not row.empty:
                    return row[['代码', '名称', '最新价', '涨跌幅', '成交额']].to_dict('records')[0]
            print(f"DEBUG: Attempt {i+1} failed, retrying...")
        except Exception as e:
            print(f"DEBUG: Attempt {i+1} error: {e}")
        time.sleep(2)
    return None

if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else '600098'
    data = fetch_data(code)
    print(f"RESULT_DATE: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"RESULT_DATA: {data}")
