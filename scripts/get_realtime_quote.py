import json
import re
import time
import requests
from dataclasses import dataclass

def normalize_code(code: str) -> str:
    s = str(code).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 6:
        raise ValueError(f"无法解析证券代码: {code}")
    return digits[:6]

def get_secid(code: str) -> str:
    code6 = normalize_code(code)
    if code6.startswith(("00", "30", "301", "002", "15", "16", "18", "8")):
        return f"0.{code6}"
    if code6.startswith(("60", "688", "50", "51", "56", "58")):
        return f"1.{code6}"
    raise ValueError(f"无法识别证券代码的市场类型: {code}")

def fetch_realtime_quote(code: str):
    secid = get_secid(code)
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f169,f170,f161,f162,f163,f164,f167,f168,f116,f117,f118,f119,f120,f121,f122,f135,f136,f137,f138,f139,f140,f141,f142,f143,f144,f145,f146,f147,f148,f149",
        "inv": "1",
        "cb": f"jQuery3510_{int(time.time() * 1000)}",
        "_": str(int(time.time() * 1000)),
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    match = re.search(r"jQuery\d+_\d+\((.*)\);?", resp.text)
    if not match:
        return None
    data = json.loads(match.group(1))
    return data.get("data")

if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "002266"
    quote = fetch_realtime_quote(code)
    if quote:
        # f43: 最新价, f170: 涨跌幅, f46: 今开, f44: 最高, f45: 最低, f60: 昨收, f47: 成交量, f48: 成交额
        # 东财字段含义可能需要微调，这里根据常见映射
        print(json.dumps(quote, indent=2, ensure_ascii=False))
    else:
        print("Failed to fetch quote")
