"""
从东方财富接口拉取日线历史行情，并落库到 MySQL。

使用场景：
- 每日定时跑一次，按证券代码列表抓取最近 N 条日线（默认 120 条）并 upsert 入库
- 支持股票/ETF（如 000592、159218、159218.SZ 等）

依赖：
- requests
- sqlalchemy
- pymysql

示例：
1) 指定代码（逗号分隔）：
   python ingest_eastmoney_daily_to_mysql.py --codes 000592,159218

2) 从文件读取代码（每行一个）：
   python ingest_eastmoney_daily_to_mysql.py --codes-file codes.txt

3) 指定 MySQL 连接串（也可用环境变量 MYSQL_URL）：
   python ingest_eastmoney_daily_to_mysql.py --mysql-url "mysql+pymysql://user:pass@localhost:3306/stock_data"
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable

import requests
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    MetaData,
    Numeric,
    String,
    Table,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.mysql import insert

DEFAULT_MYSQL_URL = "mysql+pymysql://user:pass@localhost:3306/stock_data"


def normalize_code(code: str) -> str:
    """规范化证券代码：支持 '159218' / '159218.SZ' / '159218.sz'，只保留 6 位数字。"""
    s = str(code).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 6:
        raise ValueError(f"无法解析证券代码: {code}")
    return digits[:6]


def get_secid(code: str) -> str:
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

    raise ValueError(f"无法识别证券代码的市场类型: {code}")


@dataclass(frozen=True)
class KlineDailyRow:
    code: str
    trade_date: str  # YYYY-MM-DD
    open: float
    close: float
    high: float
    low: float
    vol: float
    amount: float  # 成交额（元，接口原样）
    pct_chg: float | None  # 涨跌幅（%）


def fetch_eastmoney_kline_daily(code: str, limit: int = 120) -> list[KlineDailyRow]:
    """
    拉取指定证券最近 N 条日线（默认 120）。

    注意：
    - 东财接口返回为 JSONP，需要做一次正则剥离
    - 返回 trade_date 为 'YYYY-MM-DD'
    """
    secid = get_secid(code)
    _market_str, code6 = secid.split(".", 1)

    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "cb": f"jQuery3510_{int(time.time() * 1000)}",
        "secid": secid,
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",  # 日线
        "fqt": "1",  # 前复权
        "end": "20500101",
        "lmt": str(limit),
        "_": str(int(time.time() * 1000)),
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
        "Host": "push2his.eastmoney.com",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    text = resp.text

    match = re.search(r"jQuery\d+_\d+\((.*)\);?", text)
    if not match:
        raise ValueError("无法解析东财 JSONP 响应")

    payload = json.loads(match.group(1))
    if not payload or "data" not in payload or "klines" not in payload["data"]:
        raise ValueError("东财行情数据缺失")

    rows: list[KlineDailyRow] = []
    for item in payload["data"]["klines"] or []:
        parts = item.split(",")
        # 格式通常为：日期,开,收,高,低,量,额,振幅,涨跌幅,涨跌额,换手率
        if len(parts) < 7:
            continue
        trade_date = parts[0]
        open_ = float(parts[1])
        close_ = float(parts[2])
        high_ = float(parts[3])
        low_ = float(parts[4])
        vol_ = float(parts[5])
        amount_ = float(parts[6])
        pct_chg = None
        if len(parts) > 8:
            try:
                pct_chg = float(parts[8])
            except Exception:
                pct_chg = None

        rows.append(
            KlineDailyRow(
                code=code6,
                trade_date=trade_date,
                open=open_,
                close=close_,
                high=high_,
                low=low_,
                vol=vol_,
                amount=amount_,
                pct_chg=pct_chg,
            )
        )

    return rows


def build_table(metadata: MetaData) -> Table:
    """
    建表（如果不存在）：对齐 create_stock_daily_table.sql 的 stock_daily。

    设计说明：
    - 主键：ts_code + trade_date（同一标的同一天唯一）
    - ts_code：存 6 位纯数字（如 000001）
    - exch_code：SZ/SH/BJ
    """
    return Table(
        "stock_daily",
        metadata,
        Column("ts_code", String(10), primary_key=True, comment="股票代码"),
        Column(
            "exch_code", String(10), nullable=True, comment="交易所代码（SZ/SH/BJ）"
        ),
        Column("trade_date", Date, primary_key=True, comment="交易日期"),
        # 价格类字段保留 4 位小数，便于 ETF/基金等小数精度更高的场景
        Column("open", Numeric(10, 4), nullable=True, comment="开盘价"),
        Column("high", Numeric(10, 4), nullable=True, comment="最高价"),
        Column("low", Numeric(10, 4), nullable=True, comment="最低价"),
        Column("close", Numeric(10, 4), nullable=True, comment="收盘价"),
        Column("pre_close", Numeric(10, 4), nullable=True, comment="昨收价（除权价）"),
        Column("change_amount", Numeric(10, 4), nullable=True, comment="涨跌额"),
        Column("pct_chg", Numeric(8, 4), nullable=True, comment="涨跌幅（%）"),
        Column("vol", BigInteger, nullable=True, comment="成交量（手）"),
        # 成交额（千元）也保留 4 位小数，避免换算后截断
        Column("amount", Numeric(20, 4), nullable=True, comment="成交额（千元）"),
        Column(
            "update_time",
            DateTime,
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
            comment="更新时间",
        ),
        Column(
            "create_time",
            DateTime,
            nullable=False,
            server_default=func.now(),
            comment="创建时间",
        ),
        mysql_charset="utf8mb4",
    )


def upsert_daily_rows(mysql_url: str, rows: Iterable[KlineDailyRow]) -> int:
    """将日线数据 upsert 到 MySQL，返回写入行数（按输入计）。"""
    engine = create_engine(mysql_url, pool_pre_ping=True)
    metadata = MetaData()
    table = build_table(metadata)
    metadata.create_all(engine)

    # 统一使用北京时间写入 update_time/create_time，避免 MySQL 时区为 UTC 时显示不符合预期
    # 说明：不依赖 MySQL 时区表（CONVERT_TZ 可能返回 NULL），用 UTC_TIMESTAMP + 8 小时更稳
    beijing_now = text("DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)")

    # 为了计算 pre_close / change_amount，按日期升序处理（东财一般已是升序，这里显式排序更稳）
    row_list = sorted(list(rows), key=lambda x: x.trade_date)

    def infer_exch_code(code6: str) -> str:
        # 东财 market=0 可能是 SZ 或 BJ，这里用代码前缀区分；沪市统一为 SH
        if code6.startswith("8"):
            return "BJ"
        # 其它 6 位默认按深市/ETF
        return "SZ"

    # 如果是沪市代码前缀，覆盖 exch_code
    # 约定：60/688/50/51/56/58 -> SH（与 get_secid 一致）
    def fix_exch_code(code6: str, exch: str) -> str:
        if code6.startswith(("60", "688", "50", "51", "56", "58")):
            return "SH"
        return exch

    values = []
    prev_close = None
    for r in row_list:
        exch = fix_exch_code(r.code, infer_exch_code(r.code))
        pre_close = prev_close
        change_amount = None
        pct_chg = r.pct_chg

        if pre_close is not None:
            change_amount = r.close - pre_close
            # 优先用东财的 pct_chg；没有则用 pre_close 计算
            if pct_chg is None and pre_close != 0:
                pct_chg = (r.close - pre_close) / pre_close * 100

        # 表字段 amount 注释为“千元”，东财返回一般是“元”，这里做单位换算
        amount_k = r.amount / 1000 if r.amount is not None else None

        values.append(
            {
                "ts_code": r.code,  # 存 6 位纯数字（与 create_stock_daily_table.sql 的示例一致）
                "exch_code": exch,
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "pre_close": pre_close,
                "change_amount": change_amount,
                "pct_chg": pct_chg,
                "vol": int(r.vol) if r.vol is not None else None,
                "amount": amount_k,
                "update_time": beijing_now,
                "create_time": beijing_now,
            }
        )
        prev_close = r.close

    if not values:
        return 0

    stmt = insert(table).values(values)
    stmt = stmt.on_duplicate_key_update(
        exch_code=stmt.inserted.exch_code,
        open=stmt.inserted.open,
        high=stmt.inserted.high,
        low=stmt.inserted.low,
        close=stmt.inserted.close,
        pre_close=stmt.inserted.pre_close,
        change_amount=stmt.inserted.change_amount,
        pct_chg=stmt.inserted.pct_chg,
        vol=stmt.inserted.vol,
        amount=stmt.inserted.amount,
        # 只更新 update_time，不动 create_time
        update_time=beijing_now,
    )

    with engine.begin() as conn:
        conn.execute(stmt)

    return len(values)


def _parse_codes_from_file(path: str) -> list[str]:
    codes: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            codes.append(s)
    return codes


def main() -> int:
    MYSQL_URL = os.getenv("MYSQL_URL") or DEFAULT_MYSQL_URL
    # 示例：股票 / ETF 都支持
    CODES = ["159218", "159840", "512400"]
    CODES_FILE = ""  # 可选：代码文件路径（每行一个，支持 .SZ/.SH），例如 "codes.txt"
    LIMIT = 240  # 每个代码拉取的日线条数（默认 120）
    SLEEP_SECONDS = 0.2  # 每个代码请求间隔秒数（默认 0.2）

    codes: list[str] = []
    codes.extend([c for c in CODES if str(c).strip()])
    if CODES_FILE:
        codes.extend(_parse_codes_from_file(CODES_FILE))

    # 去重但保持顺序
    seen = set()
    uniq_codes = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        uniq_codes.append(c)

    if not uniq_codes:
        print("未提供 codes，请使用 --codes 或 --codes-file")
        return 2

    total = 0
    for c in uniq_codes:
        try:
            rows = fetch_eastmoney_kline_daily(code=c, limit=LIMIT)
            written = upsert_daily_rows(MYSQL_URL, rows)
            total += written
            print(f"[OK] {c} 获取 {len(rows)} 条，入库 {written} 条")
        except Exception as e:
            print(f"[FAIL] {c} -> {e}")
        time.sleep(max(0.0, float(SLEEP_SECONDS)))

    print(f"完成：共入库 {total} 条（按输入计，重复会被 upsert 覆盖）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
