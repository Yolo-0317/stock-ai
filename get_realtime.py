import json
import re
import time
from datetime import datetime

import requests


def normalize_code(code: str) -> str:
    """
    规范化证券代码。

    说明：
    - 支持传入 '159218' / '159218.SZ' / '159218.sz' 等形式
    - 只保留数字并取前 6 位
    """
    s = str(code).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 6:
        raise ValueError(f"无法解析证券代码: {code}")
    return digits[:6]


def get_secid(code):
    """
    根据证券代码推断东财 secid（市场前缀.代码）。

    说明：
    - 深市：0.xxxxxx（含深市股票、深市 ETF 如 159xxx、北交所 8xxxxx）
    - 沪市：1.xxxxxx（含沪市股票、沪市 ETF 如 510xxx/588xxx 等）
    """
    code6 = normalize_code(code)

    # 深市：主板/中小板/创业板/ETF(159xxx 等)/北交所(8xxxxx)
    if code6.startswith(("00", "30", "301", "002", "15", "16", "18", "8")):
        return f"0.{code6}"

    # 沪市：主板/科创板/ETF(510xxx/588xxx/56xxxx 等)
    if code6.startswith(("60", "688", "50", "51", "56", "58")):
        return f"1.{code6}"
    else:
        raise ValueError(f"无法识别股票代码的市场类型: {code}")


def get_realtime_info(code, trade_date):
    """
    获取指定股票代码和交易日的实时行情信息（模拟K线形式）
    :param code: 股票代码，如 '301590'
    :param trade_date: 日期字符串，如 '2025-06-05'
    :return: 字典包含今开、当前、最高、最低、成交量等行情数据
    """
    # 自动判断深市 or 沪市（默认创业板和主板）
    secid = get_secid(code)

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "cb": "jQuery351041896365820735604_1749096885374",  # 任意字符串也行
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",  # 日线
        "fqt": "1",  # 前复权
        "end": "20500101",  # 截止日期
        "lmt": "120",  # 最多120条
        "_": str(int(time.time() * 1000)),
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "host": "push2his.eastmoney.com",
    }

    response = requests.get(url, params=params, headers=headers)
    match = re.search(r"jQuery\d+_\d+\((.*)\);?", response.text)
    if not match:
        raise ValueError("无法解析 JSONP 响应")

    data = json.loads(match.group(1))
    if not data or "data" not in data or "klines" not in data["data"]:
        raise ValueError("行情数据缺失")

    # 找到指定交易日的行情数据
    for item in data["data"]["klines"]:
        parts = item.split(",")
        if parts[0] == datetime.strptime(trade_date, "%Y%m%d").strftime("%Y-%m-%d"):
            return {
                "trade_date": parts[0],
                "今开": float(parts[1]),
                "当前": float(parts[2]),
                "最高": float(parts[3]),
                "最低": float(parts[4]),
                "成交量": float(parts[5]),
                "成交额": float(parts[6]),
                "换手率": float(parts[10]),
            }

    raise ValueError(f"{code} 未找到指定交易日 {trade_date} 的行情数据")


if __name__ == "__main__":
    print(get_realtime_info("873527", "20250605"))
