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
from pathlib import Path
from datetime import datetime, timedelta, timezone

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

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
    all_day: bool


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


def _beijing_now() -> datetime:
    """获取北京时间（不带时区信息，便于比较）。"""
    now_utc = datetime.now(timezone.utc)
    bj = now_utc + timedelta(hours=8)
    return bj.replace(tzinfo=None)


def _is_trading_time_bj(dt: datetime) -> bool:
    """A 股交易时段（北京时间）：9:30-11:30，13:00-15:00。"""
    t = dt.time()
    am = (t.hour > 9 or (t.hour == 9 and t.minute >= 30)) and (
        t.hour < 11 or (t.hour == 11 and t.minute <= 30)
    )
    pm = (t.hour > 13 or (t.hour == 13 and t.minute >= 0)) and (
        t.hour < 15 or (t.hour == 15 and t.minute <= 0)
    )
    return am or pm


def _seconds_until_next_trading_window(now_bj: datetime) -> float:
    """非交易时段：计算距离下一次交易窗口开始的秒数（不处理节假日，足够日常使用）。"""
    today = now_bj.date()
    t = now_bj.time()

    def at(h: int, m: int) -> datetime:
        return datetime(today.year, today.month, today.day, h, m)

    start_am = at(9, 30)
    start_pm = at(13, 0)
    end_am = at(11, 30)
    end_pm = at(15, 0)

    if now_bj < start_am:
        return max(1.0, (start_am - now_bj).total_seconds())
    if end_am < now_bj < start_pm:
        return max(1.0, (start_pm - now_bj).total_seconds())
    if now_bj > end_pm:
        next_day = today + timedelta(days=1)
        next_start = datetime(next_day.year, next_day.month, next_day.day, 9, 30)
        return max(1.0, (next_start - now_bj).total_seconds())

    # 兜底：如果恰好在边界附近
    return 60.0


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
    parser.add_argument(
        "--all-day",
        action="store_true",
        help="全天运行（默认仅交易时段抓取，非交易时段会跳过/休眠）",
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
        all_day=bool(args.all_day),
    )


def main() -> int:
    cfg = _parse_args()
    if not cfg.all_day:
        now_bj = _beijing_now()
        if not _is_trading_time_bj(now_bj):
            if cfg.once:
                print(
                    f"非交易时段（{now_bj.strftime('%Y-%m-%d %H:%M:%S')}），跳过本次抓取（--once）。"
                )
                return 0
            sleep_s = _seconds_until_next_trading_window(now_bj)
            print(
                f"非交易时段（{now_bj.strftime('%Y-%m-%d %H:%M:%S')}），休眠 {int(sleep_s)}s 等待下一交易窗口..."
            )
            time.sleep(sleep_s)

    if cfg.once:
        _poll_once(cfg)
        return 0

    print(
        f"开始轮询：codes={cfg.codes} interval={cfg.interval_seconds}s mysql_url={'已配置' if cfg.mysql_url else '未配置'}"
    )
    while True:
        start = time.time()
        if not cfg.all_day:
            now_bj = _beijing_now()
            if not _is_trading_time_bj(now_bj):
                sleep_s = _seconds_until_next_trading_window(now_bj)
                print(
                    f"非交易时段（{now_bj.strftime('%Y-%m-%d %H:%M:%S')}），休眠 {int(sleep_s)}s..."
                )
                time.sleep(sleep_s)
                continue
        _poll_once(cfg)
        cost = time.time() - start
        sleep_s = max(0.0, cfg.interval_seconds - cost)
        time.sleep(sleep_s)


if __name__ == "__main__":
    raise SystemExit(main())


