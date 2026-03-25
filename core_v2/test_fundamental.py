import akshare as ak
import pandas as pd
import time
import subprocess
import json

def _fetch_with_retry(func, name, max_retries=3, delay=2, **kwargs):
    for i in range(max_retries):
        try:
            df = func(**kwargs)
            if df is not None and not df.empty:
                return df
        except Exception as e:
            if i < max_retries - 1:
                time.sleep(delay)
    return None

def get_stock_fundamental(code):
    code_6 = "".join(filter(str.isdigit, str(code)))[:6]
    result = {
        "代码": code_6,
        "名称": "N/A",
        "ROE": "N/A",
        "净利润增长率": "N/A"
    }
    
    # 1. 基础信息
    try:
        info_df = ak.stock_individual_info_em(symbol=code_6)
        if info_df is not None:
            info_dict = dict(zip(info_df['item'], info_df['value']))
            result["名称"] = info_dict.get("股票简称", "N/A")
    except:
        pass

    # 2. 东方财富 F10 API (ROE, 增长率)
    try:
        market = "SH" if code_6.startswith(('60', '688')) else "SZ"
        full_code = f"{market}{code_6}"
        api_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZB_Ajax?code={full_code}"
        
        cmd = [
            "curl", "-s",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "-H", "Referer: https://emweb.securities.eastmoney.com/",
            api_url
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if stdout:
            text = stdout.decode('utf-8', errors='ignore').strip()
            if text.startswith('\ufeff'): text = text[1:]
            data = json.loads(text)
            if data and "ZYZB" in data and len(data["ZYZB"]) > 0:
                latest = data["ZYZB"][0]
                result["ROE"] = latest.get("JQJZCSYLR", "N/A")
                result["净利润增长率"] = latest.get("SJLYZTZZL", "N/A")
    except Exception as e:
        print(f"Error: {e}")
        
    return result

if __name__ == "__main__":
    print(get_stock_fundamental("600873"))
