"""
每分钟拉取东方财富“日线级”最新一根 K 线（盘中会动态变化）并落库到 MySQL。

用途：
- 为 `tushare_mcp.py` 的 `intraday_trade_signal` 提供更稳定的盘中历史基线
- 让盘中 MA5/MA20 的计算能直接复用 MySQL `stock_daily` 的历史 close

注意事项：
- 本脚本写入的是 `stock_daily` 表（主键：ts_code + trade_date）
- 东财返回的“最新一根日线”在盘中会变化；脚本每次会 upsert 同一天的记录
- 建议先跑一次 `ingest_eastmoney_daily_to_mysql.py` 把历史日线补齐，再启动本脚本做增量更新

依赖：
- requests / sqlalchemy / pymysql（与 ingest_eastmoney_daily_to_mysql.py 相同）

示例：
1) 单次执行（便于接入 cron）：
   MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
   python poll_eastmoney_intraday_to_mysql.py --codes 159218,159840 --once

2) 常驻轮询（每 60 秒更新一次）：
   MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
   python poll_eastmoney_intraday_to_mysql.py --codes 159218,159840 --interval 60
"""

from __future__ import annotations

import argparse
import os
import time
from dataclasses import dataclass

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.dialects.mysql import insert

from ingest_eastmoney_daily_to_mysql import (
    DEFAULT_MYSQL_URL,
    KlineDailyRow,
    build_table,
    fetch_eastmoney_kline_daily,
)


@dataclass(frozen=True)
class PollConfig:
    mysql_url: str
    codes: list[str]
    interval_seconds: float
    per_code_sleep_seconds: float
    once: bool


def _infer_exch_code(code6: str) -> str:
    """根据 6 位代码推断交易所代码（仅用于落库标识）。"""
    # 沪市（与 get_secid / tushare_mcp.py 的判断保持一致）
    if code6.startswith(("60", "688", "50", "51", "56", "58")):
        return "SH"
    # 北交所
    if code6.startswith("8"):
        return "BJ"
    # 其它默认深市（含深市 ETF 159xxx）
    return "SZ"


def _get_prev_close(conn, code6: str, trade_date: str) -> float | None:
    """
    查询指定标的在 trade_date 之前最近一个交易日的 close。

    说明：
    - trade_date 为 'YYYY-MM-DD'
    - 用于推导 pre_close / change_amount / pct_chg（若东财未返回 pct_chg）
    """
    sql = text(
        """
        SELECT close
        FROM stock_daily
        WHERE ts_code = :code
          AND trade_date < :trade_date
        ORDER BY trade_date DESC
        LIMIT 1
        """
    )
    row = conn.execute(sql, {"code": code6, "trade_date": trade_date}).fetchone()
    if not row:
        return None
    try:
        return float(row[0])
    except Exception:
        return None


def _upsert_intraday_row(conn, table, kline: KlineDailyRow) -> None:
    """
    将“盘中最新一根日线”写入 stock_daily（主键冲突则更新）。

    设计：
    - 同一天会不断更新 close/high/low/vol/amount/pct_chg 等字段
    - pre_close 来自 MySQL 历史最近一日收盘（如果能查到）
    """
    exch_code = _infer_exch_code(kline.code)
    pre_close = _get_prev_close(conn, code6=kline.code, trade_date=kline.trade_date)

    change_amount = None
    pct_chg = kline.pct_chg
    if pre_close is not None:
        change_amount = kline.close - pre_close
        # 优先使用东财 pct_chg；没有则用 pre_close 推导
        if pct_chg is None and pre_close != 0:
            pct_chg = (kline.close - pre_close) / pre_close * 100

    # 表字段 amount 注释为“千元”，东财一般返回“元”，这里做单位换算
    amount_k = kline.amount / 1000 if kline.amount is not None else None

    # 统一使用北京时间写入 update_time/create_time（不依赖 MySQL 时区表）
    beijing_now = text("DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)")

    values = {
        "ts_code": kline.code,
        "exch_code": exch_code,
        "trade_date": kline.trade_date,
        "open": kline.open,
        "high": kline.high,
        "low": kline.low,
        "close": kline.close,
        "pre_close": pre_close,
        "change_amount": change_amount,
        "pct_chg": pct_chg,
        "vol": int(kline.vol) if kline.vol is not None else None,
        "amount": amount_k,
        "update_time": beijing_now,
        "create_time": beijing_now,
    }

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
        update_time=beijing_now,
    )
    conn.execute(stmt)


def _poll_once(cfg: PollConfig) -> None:
    engine = create_engine(cfg.mysql_url, pool_pre_ping=True)
    metadata = MetaData()
    table = build_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        for code in cfg.codes:
            try:
                rows = fetch_eastmoney_kline_daily(code=code, limit=2)
                if not rows:
                    print(f"[WARN] {code} 未拉到行情数据")
                    continue

                latest = rows[-1]
                _upsert_intraday_row(conn, table, latest)
                print(
                    f"[OK] {code} {latest.trade_date} close={latest.close} high={latest.high} low={latest.low}"
                )
            except Exception as e:
                print(f"[FAIL] {code} -> {e}")
            time.sleep(max(0.0, float(cfg.per_code_sleep_seconds)))


def _parse_args() -> PollConfig:
    parser = argparse.ArgumentParser(
        description="每分钟拉取东财盘中日线并 upsert 入 MySQL（用于盘中均线分析）。"
    )
    parser.add_argument(
        "--mysql-url",
        default=os.getenv("MYSQL_URL") or DEFAULT_MYSQL_URL,
        help='MySQL 连接串（也可用环境变量 MYSQL_URL），例如 "mysql+pymysql://user:pass@localhost:3306/stock_data"',
    )
    parser.add_argument(
        "--codes",
        default=os.getenv("CODES") or "159218,159840",
        help="证券代码列表（逗号分隔），支持 159840 或 159840.SZ 等",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.getenv("INTERVAL_SECONDS") or 60),
        help="轮询间隔秒数（默认 60 秒）",
    )
    parser.add_argument(
        "--per-code-sleep",
        type=float,
        default=float(os.getenv("PER_CODE_SLEEP_SECONDS") or 0.2),
        help="每个 code 请求后的 sleep（避免过于频繁，默认 0.2 秒）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只执行一次（适合 cron）；不传则常驻轮询",
    )

    args = parser.parse_args()
    codes = [c.strip() for c in str(args.codes).split(",") if c.strip()]
    if not codes:
        raise SystemExit("未提供 codes，请使用 --codes 或环境变量 CODES")

    return PollConfig(
        mysql_url=str(args.mysql_url),
        codes=codes,
        interval_seconds=float(args.interval),
        per_code_sleep_seconds=float(args.per_code_sleep),
        once=bool(args.once),
    )


def main() -> int:
    cfg = _parse_args()
    if cfg.once:
        _poll_once(cfg)
        return 0

    print(
        f"开始轮询：codes={cfg.codes} interval={cfg.interval_seconds}s mysql_url={'已配置' if cfg.mysql_url else '未配置'}"
    )
    while True:
        start = time.time()
        _poll_once(cfg)
        cost = time.time() - start
        sleep_s = max(0.0, cfg.interval_seconds - cost)
        time.sleep(sleep_s)


if __name__ == "__main__":
    raise SystemExit(main())


