"""
方案 A：每分钟拉取东方财富“日线级”最新一根 K 线，并写入“盘中快照表”。

为什么需要这张表？
- `stock_daily` 的主键是 (ts_code, trade_date)，盘中写入会不断覆盖同一天记录，导致丢失盘中轨迹
- 盘中快照表按分钟保留路径，后续可用于：
  - 盘中回放（某天从开盘到收盘的价格/高低点变化）
  - 风控触发点记录（跌破某均线/某价位的时间点）
  - 在不引入真正分钟 K 线接口的情况下，快速补齐盘中“轨迹数据”

数据来源说明：
- 仍然使用东财日线 K 线接口的“最新一根”（盘中动态变化）
- 该接口的 close 字段在盘中代表“当前价/最新价”

写入策略：
- bar_time：用北京时间“当前时间”对齐到分钟（秒置 0）
- 主键：(ts_code, bar_time)
- 同一分钟写多次会覆盖（ON DUPLICATE KEY UPDATE）

示例：
1) 单次执行（适合 cron）：
   MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
   python poll_eastmoney_intraday_snapshot_to_mysql.py --codes 159218,159840 --once

2) 常驻轮询（默认每 60 秒写一次）：
   MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data" \
   python poll_eastmoney_intraday_snapshot_to_mysql.py --codes 159218,159840 --interval 60
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ingest_eastmoney_daily_to_mysql import (
    DEFAULT_MYSQL_URL,
    fetch_eastmoney_kline_daily,
    normalize_code,
)
from sqlalchemy import DateTime  # type: ignore
from sqlalchemy import MetaData  # type: ignore
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    Numeric,
    String,
    Table,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.mysql import insert  # type: ignore


@dataclass(frozen=True)
class PollConfig:
    mysql_url: str
    codes: list[str]
    interval_seconds: float
    per_code_sleep_seconds: float
    once: bool


def build_snapshot_table(metadata: MetaData) -> Table:
    """建表（如果不存在）：stock_intraday_snapshot（分钟级快照）。"""
    return Table(
        "stock_intraday_snapshot",
        metadata,
        Column("ts_code", String(10), primary_key=True, comment="证券代码（6 位）"),
        Column(
            "bar_time",
            DateTime,
            primary_key=True,
            comment="快照时间（北京时间，分钟级）",
        ),
        Column("trade_date", Date, nullable=False, comment="交易日期（来自东财）"),
        Column("open", Numeric(10, 4), nullable=True, comment="今开"),
        Column("high", Numeric(10, 4), nullable=True, comment="当日最高（盘中动态）"),
        Column("low", Numeric(10, 4), nullable=True, comment="当日最低（盘中动态）"),
        Column(
            "close",
            Numeric(10, 4),
            nullable=True,
            comment="盘中最新价（东财 close/当前）",
        ),
        Column("vol", BigInteger, nullable=True, comment="成交量（手，盘中累计）"),
        Column(
            "amount", Numeric(20, 4), nullable=True, comment="成交额（千元，盘中累计）"
        ),
        Column("pct_chg", Numeric(8, 4), nullable=True, comment="涨跌幅（%）"),
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


def _beijing_now_minute() -> datetime:
    """获取北京时间并对齐到分钟（秒、微秒置 0）。"""
    now_utc = datetime.now(timezone.utc)
    bj = now_utc + timedelta(hours=8)
    return bj.replace(second=0, microsecond=0, tzinfo=None)


def _upsert_snapshot(conn, table: Table, code: str) -> None:
    """
    拉取东财最新一根日线（盘中动态），并写入分钟快照表。
    """
    code6 = normalize_code(code)
    rows = fetch_eastmoney_kline_daily(code=code, limit=2)
    if not rows:
        raise ValueError("未拉到东财行情数据")

    latest = rows[-1]
    bar_time = _beijing_now_minute()

    # 表字段 amount 注释为“千元”，东财一般返回“元”，这里换算
    amount_k = latest.amount / 1000 if latest.amount is not None else None

    # 统一使用北京时间写入 update_time/create_time（不依赖 MySQL 时区表）
    beijing_now_expr = text("DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)")

    values = {
        "ts_code": code6,
        "bar_time": bar_time,
        "trade_date": latest.trade_date,
        "open": latest.open,
        "high": latest.high,
        "low": latest.low,
        "close": latest.close,
        "vol": int(latest.vol) if latest.vol is not None else None,
        "amount": amount_k,
        "pct_chg": latest.pct_chg,
        "update_time": beijing_now_expr,
        "create_time": beijing_now_expr,
    }

    stmt = insert(table).values(values)
    stmt = stmt.on_duplicate_key_update(
        trade_date=stmt.inserted.trade_date,
        open=stmt.inserted.open,
        high=stmt.inserted.high,
        low=stmt.inserted.low,
        close=stmt.inserted.close,
        vol=stmt.inserted.vol,
        amount=stmt.inserted.amount,
        pct_chg=stmt.inserted.pct_chg,
        update_time=beijing_now_expr,
    )
    conn.execute(stmt)

    print(
        f"[OK] {code6} bar_time={bar_time} trade_date={latest.trade_date} close={latest.close}"
    )


def _poll_once(cfg: PollConfig) -> None:
    engine = create_engine(cfg.mysql_url, pool_pre_ping=True)
    metadata = MetaData()
    table = build_snapshot_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as conn:
        for c in cfg.codes:
            try:
                _upsert_snapshot(conn, table, c)
            except Exception as e:
                print(f"[FAIL] {c} -> {e}")
            time.sleep(max(0.0, float(cfg.per_code_sleep_seconds)))


def main() -> int:
    # =========================
    # 配置区：按需修改即可
    # =========================
    MYSQL_URL = os.getenv("MYSQL_URL") or DEFAULT_MYSQL_URL
    CODES = ["159218", "159840"]  # 支持 '159840' / '159840.SZ' 等
    INTERVAL_SECONDS = 60.0  # 每轮间隔秒数（默认 60 秒）
    PER_CODE_SLEEP_SECONDS = 0.2  # 每个 code 请求后的 sleep（默认 0.2 秒）
    ONCE = False  # True：只跑一轮就退出（适合 cron）；False：常驻轮询

    cfg = PollConfig(
        mysql_url=MYSQL_URL,
        codes=CODES,
        interval_seconds=INTERVAL_SECONDS,
        per_code_sleep_seconds=PER_CODE_SLEEP_SECONDS,
        once=ONCE,
    )
    if cfg.once:
        _poll_once(cfg)
        return 0

    print(f"开始轮询快照：codes={cfg.codes} interval={cfg.interval_seconds}s")
    while True:
        start = time.time()
        _poll_once(cfg)
        cost = time.time() - start
        time.sleep(max(0.0, cfg.interval_seconds - cost))


if __name__ == "__main__":
    raise SystemExit(main())
