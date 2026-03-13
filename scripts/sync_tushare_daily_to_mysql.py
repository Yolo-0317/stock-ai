#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Tushare 拉取全部 A 股日线数据并入库 MySQL

功能说明：
1. 首次运行：拉取所有 A 股的历史日线数据（可指定起始日期）
2. 增量更新：自动检测每只股票的最新日期，只拉取缺失的数据
3. 支持断点续传：记录处理进度，失败后可继续

数据来源：
- 股票列表：Tushare stock_basic 接口（免费，1次/小时限制）
- 日线数据：Tushare daily 接口（免费，50次/分钟）

使用方法：
修改脚本底部 if __name__ == "__main__" 中的参数，然后运行：
   TUSHARE_TOKEN="your_token" MYSQL_URL="mysql+pymysql://user:pass@host/db" \\
   python sync_tushare_daily_to_mysql.py

或作为模块导入：
   from scripts.sync_tushare_daily_to_mysql import sync_daily_data
   sync_daily_data(mode="by_date", days=7)

环境变量：
- TUSHARE_TOKEN: Tushare API Token（必需）
- MYSQL_URL: MySQL 连接字符串（必需）
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from collections import deque

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dotenv import load_dotenv

# 加载环境变量
env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=env_path)

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

# 导入 tushare
try:
    import tushare as ts
except ImportError:
    print("❌ 错误：未安装 tushare，请运行：uv sync 或 pip install tushare")
    sys.exit(1)


# 默认配置
DEFAULT_START_DATE = "20240101"  # 默认拉取起始日期（2024年至今）
DEFAULT_SLEEP_SECONDS = 1.5  # API 调用间隔（避免触发限流，建议 1.5 秒以上）
MAX_CALLS_PER_MINUTE = 45  # 每分钟最大调用次数（留余量，Tushare 限制是 50 次/分钟）


@dataclass
class SyncStats:
    """同步统计信息"""

    total_stocks: int = 0  # 总股票数
    processed_stocks: int = 0  # 已处理股票数
    total_records: int = 0  # 总入库记录数
    failed_stocks: list[str] = field(default_factory=list)  # 失败的股票列表
    start_time: datetime = None
    end_time: datetime = None
    api_calls: int = 0  # API 调用次数
    rate_limit_hits: int = 0  # 触发限流次数

    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now()


class RateLimiter:
    """API 限流控制器"""

    def __init__(self, max_calls_per_minute: int = MAX_CALLS_PER_MINUTE):
        self.max_calls = max_calls_per_minute
        self.call_times = deque()  # 记录每次调用的时间戳

    def wait_if_needed(self):
        """如果需要，等待以避免超过限流"""
        now = time.time()

        # 移除 1 分钟前的调用记录
        while self.call_times and now - self.call_times[0] > 60:
            self.call_times.popleft()

        # 如果当前分钟内调用次数已达上限，等待到最早的调用过期
        if len(self.call_times) >= self.max_calls:
            sleep_time = 60 - (now - self.call_times[0]) + 1  # 多等 1 秒确保安全
            if sleep_time > 0:
                print(f"  ⏳ 已达限流阈值（{self.max_calls} 次/分钟），等待 {sleep_time:.1f} 秒...")
                time.sleep(sleep_time)
                # 清理过期记录
                now = time.time()
                while self.call_times and now - self.call_times[0] > 60:
                    self.call_times.popleft()

        # 记录本次调用
        self.call_times.append(now)

    def get_current_rate(self) -> int:
        """获取当前分钟内的调用次数"""
        now = time.time()
        # 移除 1 分钟前的调用记录
        while self.call_times and now - self.call_times[0] > 60:
            self.call_times.popleft()
        return len(self.call_times)


def init_tushare() -> ts.pro_api:
    """初始化 Tushare API"""
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("❌ 错误：未设置 TUSHARE_TOKEN 环境变量")
        print("请在 .env 文件中设置：TUSHARE_TOKEN=your_token")
        sys.exit(1)

    ts.set_token(token)
    return ts.pro_api()


def get_mysql_engine():
    """获取 MySQL 数据库连接"""
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        print("❌ 错误：未设置 MYSQL_URL 环境变量")
        print("请在 .env 文件中设置：MYSQL_URL=mysql+pymysql://user:pass@host/db")
        sys.exit(1)

    return create_engine(mysql_url, pool_pre_ping=True, pool_recycle=3600)


def generate_date_range(start_date: str, end_date: str) -> list[str]:
    """
    生成日期范围（包含所有日期，非交易日会在数据拉取时自动过滤）
    
    参数：
    - start_date: 开始日期（YYYYMMDD）
    - end_date: 结束日期（YYYYMMDD）
    
    返回：日期列表（YYYYMMDD 格式）
    """
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def get_stock_list_from_db(engine) -> pd.DataFrame:
    """
    从数据库中获取已有的股票列表（避免调用 stock_basic 接口）
    
    返回：包含 ts_code 的 DataFrame
    """
    print("从数据库获取股票列表...")
    
    sql = text(
        """
        SELECT DISTINCT ts_code, exch_code
        FROM stock_daily
        ORDER BY ts_code
        """
    )
    
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    
    if df.empty:
        print("⚠️  数据库中没有股票数据")
        return pd.DataFrame()
    
    # 转换为 Tushare 格式（添加后缀）
    df["ts_code_full"] = df.apply(
        lambda row: f"{row['ts_code']}.{row['exch_code']}" if pd.notna(row['exch_code']) else row['ts_code'],
        axis=1
    )
    
    result = pd.DataFrame({
        "ts_code": df["ts_code_full"],
        "name": "从数据库获取"
    })
    
    print(f"✓ 从数据库获取到 {len(result)} 只股票")
    return result


def get_latest_trade_date_from_db(
    engine, ts_code: str
) -> str | None:
    """
    从数据库查询某只股票的最新交易日期

    返回：YYYYMMDD 格式的日期字符串，如果没有数据则返回 None
    """
    sql = text(
        """
        SELECT MAX(trade_date) as latest_date
        FROM stock_daily
        WHERE ts_code = :ts_code
        """
    )

    with engine.connect() as conn:
        result = conn.execute(sql, {"ts_code": ts_code.split(".")[0]}).fetchone()
        if result and result[0]:
            # 将 date 转换为 YYYYMMDD 格式
            return result[0].strftime("%Y%m%d")
        return None


def fetch_daily_data(
    pro: ts.pro_api,
    ts_code: str,
    start_date: str,
    end_date: str | None = None,
    max_retries: int = 3,
) -> tuple[pd.DataFrame, bool]:
    """
    拉取单只股票的日线数据（带重试机制）

    参数：
    - ts_code: 股票代码（如 000001.SZ）
    - start_date: 开始日期（YYYYMMDD）
    - end_date: 结束日期（YYYYMMDD），为 None 则拉取到最新
    - max_retries: 最大重试次数

    返回：
    - (DataFrame, is_rate_limited): 数据和是否触发限流
    """
    for retry in range(max_retries):
        try:
            df = pro.daily(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
            )

            if df is None or df.empty:
                return pd.DataFrame(), False

            return df, False

        except Exception as e:
            error_msg = str(e)

            # 检查是否为限流错误
            if "每分钟最多访问" in error_msg or "访问过于频繁" in error_msg:
                if retry < max_retries - 1:
                    wait_time = 60  # 遇到限流错误，等待 60 秒
                    print(f"  ⚠️  触发限流，等待 {wait_time} 秒后重试（{retry + 1}/{max_retries}）...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"  ❌ 限流重试次数已用尽: {error_msg}")
                    return pd.DataFrame(), True

            # 其他错误
            if retry < max_retries - 1:
                wait_time = 2 ** retry  # 指数退避：2, 4, 8 秒
                print(f"  ⚠️  拉取失败，{wait_time} 秒后重试（{retry + 1}/{max_retries}）: {error_msg}")
                time.sleep(wait_time)
                continue
            else:
                print(f"  ❌ 拉取失败: {error_msg}")
                return pd.DataFrame(), False

    return pd.DataFrame(), False


def save_daily_data_to_db(engine, df: pd.DataFrame, ts_code: str) -> int:
    """
    保存日线数据到数据库

    返回：成功入库的记录数
    """
    if df.empty:
        return 0

    try:
        # 数据预处理
        df_clean = df.copy()

        # 1. 提取纯代码（去掉 .SZ/.SH 后缀）
        df_clean["ts_code"] = df_clean["ts_code"].str.split(".").str[0]

        # 2. 提取交易所代码
        df_clean["exch_code"] = df["ts_code"].str.split(".").str[1]

        # 3. 转换日期格式：YYYYMMDD -> YYYY-MM-DD
        df_clean["trade_date"] = pd.to_datetime(df_clean["trade_date"]).dt.date

        # 4. 选择需要的字段（与数据库表结构对应）
        columns_map = {
            "ts_code": "ts_code",
            "exch_code": "exch_code",
            "trade_date": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "pre_close": "pre_close",
            "change": "change_amount",
            "pct_chg": "pct_chg",
            "vol": "vol",
            "amount": "amount",
        }

        df_to_save = df_clean.rename(columns=columns_map)[columns_map.values()]

        # 5. 使用 INSERT ... ON DUPLICATE KEY UPDATE 实现 upsert
        # 这里使用 pandas to_sql 的 if_exists='append'，依赖主键约束自动去重
        with engine.connect() as conn:
            # 使用事务确保原子性
            trans = conn.begin()
            try:
                df_to_save.to_sql(
                    name="stock_daily",
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",  # 批量插入，提升性能
                )
                trans.commit()
                return len(df_to_save)
            except IntegrityError:
                # 主键冲突，使用逐条 upsert
                trans.rollback()
                return _upsert_records(conn, df_to_save)
            except Exception as e:
                trans.rollback()
                print(f"  ❌ 入库失败: {e}")
                return 0

    except Exception as e:
        print(f"  ❌ 数据处理失败: {e}")
        return 0


def _upsert_records(conn, df: pd.DataFrame) -> int:
    """
    逐条执行 UPSERT（用于处理主键冲突）

    使用 INSERT ... ON DUPLICATE KEY UPDATE
    """
    count = 0
    sql = text(
        """
        INSERT INTO stock_daily 
        (ts_code, exch_code, trade_date, open, high, low, close, pre_close, 
         change_amount, pct_chg, vol, amount)
        VALUES 
        (:ts_code, :exch_code, :trade_date, :open, :high, :low, :close, :pre_close,
         :change_amount, :pct_chg, :vol, :amount)
        ON DUPLICATE KEY UPDATE
            open = VALUES(open),
            high = VALUES(high),
            low = VALUES(low),
            close = VALUES(close),
            pre_close = VALUES(pre_close),
            change_amount = VALUES(change_amount),
            pct_chg = VALUES(pct_chg),
            vol = VALUES(vol),
            amount = VALUES(amount),
            update_time = CURRENT_TIMESTAMP
        """
    )

    for _, row in df.iterrows():
        try:
            conn.execute(sql, row.to_dict())
            count += 1
        except Exception as e:
            print(f"  ⚠️  记录入库失败（{row['ts_code']}/{row['trade_date']}): {e}")
            continue

    conn.commit()
    return count


def sync_by_trade_date(
    pro: ts.pro_api,
    engine,
    trade_date: str,
    rate_limiter: RateLimiter,
    sleep_seconds: float,
    stats: SyncStats,
) -> int:
    """
    按交易日期批量同步全市场数据（推荐用于增量更新）
    
    优点：
    - 一次 API 调用获取全市场数据（不需要 stock_basic 接口）
    - 避免 stock_basic 的 1 次/小时限制
    - 适合增量更新场景
    
    参数：
    - trade_date: 交易日期（YYYYMMDD）
    
    返回：入库记录数
    """
    print(f"  拉取 {trade_date} 全市场数据...")
    
    # 限流控制
    rate_limiter.wait_if_needed()
    
    # 按日期获取全市场数据
    df, is_rate_limited = fetch_daily_data(
        pro, 
        ts_code=None,  # 不指定股票代码
        start_date=None,
        end_date=None,
    )
    
    # 注意：需要修改 fetch_daily_data 支持 trade_date 参数
    # 这里先用一个临时方案
    try:
        rate_limiter.wait_if_needed()
        df = pro.daily(trade_date=trade_date)
        stats.api_calls += 1
        is_rate_limited = False
        
        if df is None or df.empty:
            print(f"  ⚠️  {trade_date} 无交易数据（可能是非交易日）")
            return 0
            
    except Exception as e:
        error_msg = str(e)
        if "每分钟最多访问" in error_msg or "访问过于频繁" in error_msg:
            print(f"  ⚠️  触发限流: {error_msg}")
            stats.rate_limit_hits += 1
            is_rate_limited = True
            return 0
        else:
            print(f"  ❌ 拉取失败: {error_msg}")
            return 0
    
    if is_rate_limited:
        stats.rate_limit_hits += 1
    
    # 批量入库
    count = 0
    for ts_code in df['ts_code'].unique():
        stock_df = df[df['ts_code'] == ts_code]
        count += save_daily_data_to_db(engine, stock_df, ts_code)
    
    print(f"  ✓ {trade_date} 入库 {count} 条记录（{len(df['ts_code'].unique())} 只股票）")
    
    # 额外的间隔保护
    time.sleep(sleep_seconds)
    
    return count


def sync_stock_incremental(
    pro: ts.pro_api,
    engine,
    ts_code: str,
    stock_name: str,
    rate_limiter: RateLimiter,
    sleep_seconds: float,
    stats: SyncStats,
) -> int:
    """
    增量同步单只股票（只拉取缺失的数据）

    返回：入库记录数
    """
    # 1. 查询数据库中的最新日期
    latest_date = get_latest_trade_date_from_db(engine, ts_code)

    if latest_date is None:
        # 数据库中没有数据，使用默认起始日期
        start_date = DEFAULT_START_DATE
        print(f"  {ts_code}（{stock_name}）无历史数据，从 {start_date} 开始拉取...")
    else:
        # 从最新日期的下一天开始拉取
        start_date_obj = datetime.strptime(latest_date, "%Y%m%d") + timedelta(days=1)
        start_date = start_date_obj.strftime("%Y%m%d")

        # 检查是否已经是最新
        today = datetime.now().strftime("%Y%m%d")
        if start_date > today:
            # 已经是最新，无需更新
            return 0

        print(f"  {ts_code}（{stock_name}）从 {start_date} 开始增量更新...")

    # 2. 限流控制
    rate_limiter.wait_if_needed()

    # 3. 拉取数据
    df, is_rate_limited = fetch_daily_data(pro, ts_code, start_date=start_date)
    stats.api_calls += 1

    if is_rate_limited:
        stats.rate_limit_hits += 1

    if df.empty:
        return 0

    # 4. 入库
    count = save_daily_data_to_db(engine, df, ts_code)
    if count > 0:
        print(f"  ✓ 新增 {count} 条记录")

    # 额外的间隔保护
    time.sleep(sleep_seconds)

    return count


def sync_daily_data(
    mode: str = "by_date",
    start_date: str = DEFAULT_START_DATE,
    codes: str | None = None,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    max_calls_per_minute: int = MAX_CALLS_PER_MINUTE,
    limit: int | None = None,
    days: int = 7,
    use_db_list: bool = False,
) -> int:
    """
    同步日线数据到 MySQL
    
    参数：
    - mode: 同步模式
      - "by_date": 按日期批量拉取（推荐，回溯指定天数）
      - "full": 全量初始化（按日期范围批量拉取，从 start_date 到今天）
      - "incremental": 逐股票增量更新（从数据库读取股票列表）
    - start_date: full 模式的起始日期（YYYYMMDD）
    - codes: 指定股票代码（多个用逗号分隔，如 "000001.SZ,600000.SH"）
    - sleep_seconds: API 调用间隔秒数（建议 ≥ 1.5）
    - max_calls_per_minute: 每分钟最大 API 调用次数（Tushare 限制 50）
    - limit: 限制处理股票数量（用于测试，仅 incremental 模式）
    - days: by_date 模式的回溯天数（默认 7 天）
    - use_db_list: 保留参数（兼容性，incremental 模式自动从数据库读取）
    
    返回：
    - 0: 成功
    - 1: 失败
    """

    print("=" * 80)
    print("🚀 Tushare 日线数据同步工具")
    print("=" * 80)
    print(f"模式：{mode}")
    
    if mode == "by_date":
        print(f"回溯天数：{days} 天")
        print("💡 按日期批量拉取，无需 stock_basic 接口")
    elif mode == "full":
        today = datetime.now().strftime("%Y%m%d")
        print(f"日期范围：{start_date} 至 {today}")
        print("💡 按日期批量拉取全量数据，无需 stock_basic 接口")
    else:  # incremental
        print("💡 从数据库读取股票列表，逐股票增量更新")
    
    print(f"API 间隔：{sleep_seconds} 秒")
    print(f"限流控制：{max_calls_per_minute} 次/分钟（Tushare 限制：50 次/分钟）")
    print("=" * 80)
    
    # 检查配置是否合理
    if sleep_seconds < 1.0:
        print("⚠️  警告：API 间隔小于 1 秒，可能触发限流")
        print("   建议使用 1.5 秒或更大的值")
    
    if max_calls_per_minute > 50:
        print("⚠️  警告：每分钟调用次数设置过高，Tushare 限制是 50 次/分钟")
        max_calls_per_minute = 45  # 自动调整为安全值
        print(f"   已自动调整为：{max_calls_per_minute} 次/分钟")

    # 初始化
    pro = init_tushare()
    engine = get_mysql_engine()
    stats = SyncStats()
    rate_limiter = RateLimiter(max_calls_per_minute=max_calls_per_minute)

    # 按日期批量拉取模式（推荐，无需股票列表）
    if mode == "by_date" or mode == "full":
        if mode == "by_date":
            print(f"\n开始按日期批量同步（最近 {days} 天）...")
            print("-" * 80)
            
            # 生成日期列表（最近 N 天）
            end_date = datetime.now()
            dates_to_sync = []
            
            for i in range(days):
                date = end_date - timedelta(days=i)
                date_str = date.strftime("%Y%m%d")
                dates_to_sync.append(date_str)
            
            dates_to_sync.reverse()  # 从旧到新
        else:  # full 模式
            print(f"\n开始全量初始化（从 {start_date} 到今天）...")
            print("-" * 80)
            
            # 生成日期范围（包含所有日期，非交易日会在数据拉取时自动跳过）
            today = datetime.now().strftime("%Y%m%d")
            print(f"正在生成日期范围...")
            dates_to_sync = generate_date_range(start_date, today)
            
            print(f"✓ 共 {len(dates_to_sync)} 个日期需要同步（包含周末和节假日，无数据的会自动跳过）")
        
        stats.total_stocks = len(dates_to_sync)  # 这里用日期数代替股票数
        
        for trade_date in dates_to_sync:
            print(f"\n[{stats.processed_stocks + 1}/{stats.total_stocks}] {trade_date}")
            
            try:
                count = sync_by_trade_date(
                    pro,
                    engine,
                    trade_date,
                    rate_limiter,
                    sleep_seconds,
                    stats,
                )
                
                stats.total_records += count
                stats.processed_stocks += 1
                
            except Exception as e:
                print(f"  ❌ 处理失败: {e}")
                stats.failed_stocks.append(trade_date)
                continue
        
        # 跳到统计结果
        stats.end_time = datetime.now()
        elapsed = (stats.end_time - stats.start_time).total_seconds()
        
        print("\n" + "=" * 80)
        print("✅ 同步完成")
        print("=" * 80)
        print(f"处理日期：{stats.processed_stocks}/{stats.total_stocks}")
        print(f"入库记录：{stats.total_records:,}")
        print(f"API 调用：{stats.api_calls} 次")
        print(f"限流次数：{stats.rate_limit_hits} 次")
        print(f"失败日期：{len(stats.failed_stocks)}")
        if stats.failed_stocks:
            print(f"  {', '.join(stats.failed_stocks[:10])}")
            if len(stats.failed_stocks) > 10:
                print(f"  ... 还有 {len(stats.failed_stocks) - 10} 个")
        print(f"耗时：{elapsed:.1f} 秒 ({elapsed / 60:.1f} 分钟)")
        
        if stats.api_calls > 0:
            avg_time = elapsed / stats.api_calls
            print(f"平均速度：{avg_time:.2f} 秒/次")
        
        if stats.rate_limit_hits > 0:
            print(f"\n⚠️  提示：触发了 {stats.rate_limit_hits} 次限流")
            print("   建议增加 --sleep 参数或减少 --max-calls 参数")
        
        print("=" * 80)
        
        return 0
    
    # 获取股票列表（仅用于 incremental 模式）
    if codes:
        # 手动指定股票
        codes_list = [c.strip() for c in codes.split(",")]
        stock_df = pd.DataFrame(
            {
                "ts_code": codes_list,
                "name": ["手动指定"] * len(codes_list),
            }
        )
    else:
        # 从数据库获取股票列表
        print("\n从数据库获取股票列表...")
        stock_df = get_stock_list_from_db(engine)
        if stock_df.empty:
            print("❌ 数据库中没有股票数据")
            print("💡 建议：")
            print("   1. 先使用 mode='full' 或 mode='by_date' 初始化数据")
            print("   2. 或使用 codes 参数指定股票代码")
            return 1

    # 应用数量限制（用于测试）
    if limit:
        stock_df = stock_df.head(limit)
        print(f"⚠️  测试模式：仅处理前 {limit} 只股票")

    stats.total_stocks = len(stock_df)

    print(f"\n开始同步 {stats.total_stocks} 只股票...")
    print("-" * 80)

    # 逐个处理股票
    for idx, row in stock_df.iterrows():
        ts_code = row["ts_code"]
        stock_name = row.get("name", "")

        # 显示进度和当前限流状态
        current_rate = rate_limiter.get_current_rate()
        print(
            f"\n[{stats.processed_stocks + 1}/{stats.total_stocks}] {ts_code} "
            f"（当前速率：{current_rate}/{max_calls_per_minute} 次/分钟）"
        )

        try:
            # incremental 模式：增量同步
            count = sync_stock_incremental(
                pro,
                engine,
                ts_code,
                stock_name,
                rate_limiter,
                sleep_seconds,
                stats,
            )

            stats.total_records += count
            stats.processed_stocks += 1

        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            stats.failed_stocks.append(ts_code)
            continue

    # 统计结果
    stats.end_time = datetime.now()
    elapsed = (stats.end_time - stats.start_time).total_seconds()

    print("\n" + "=" * 80)
    print("✅ 同步完成")
    print("=" * 80)
    print(f"处理股票：{stats.processed_stocks}/{stats.total_stocks}")
    print(f"入库记录：{stats.total_records:,}")
    print(f"API 调用：{stats.api_calls} 次")
    print(f"限流次数：{stats.rate_limit_hits} 次")
    print(f"失败股票：{len(stats.failed_stocks)}")
    if stats.failed_stocks:
        print(f"  {', '.join(stats.failed_stocks[:10])}")
        if len(stats.failed_stocks) > 10:
            print(f"  ... 还有 {len(stats.failed_stocks) - 10} 只")
    print(f"耗时：{elapsed:.1f} 秒 ({elapsed / 60:.1f} 分钟)")
    
    if stats.api_calls > 0:
        avg_time = elapsed / stats.api_calls
        print(f"平均速度：{avg_time:.2f} 秒/次")
    
    if stats.rate_limit_hits > 0:
        print(f"\n⚠️  提示：触发了 {stats.rate_limit_hits} 次限流")
        print("   建议增加 --sleep 参数或减少 --max-calls 参数")
    
    print("=" * 80)

    return 0


if __name__ == "__main__":
    # ========================================
    # 配置区：根据需要修改以下参数
    # ========================================
    
    # 同步模式（推荐使用 by_date 或 full）
    # - "by_date": 按日期批量拉取（回溯指定天数，推荐用于日常更新）
    # - "full": 全量初始化（从 start_date 到今天，按日期批量拉取）
    # - "incremental": 逐股票增量更新（从数据库读取股票列表）
    MODE = "by_date"
    
    # 回溯天数（仅 by_date 模式）
    DAYS = 2  # 同步最近 7 天的数据（补齐周末和节假日）
    
    # 全量模式的起始日期（仅 full 模式）
    # 示例：START_DATE = "20200101"  # 从 2020 年开始
    START_DATE = "20230101"  # 默认 20240101
    
    # 指定股票代码（可选，多个用逗号分隔）
    # 示例：CODES = "000001.SZ,600000.SH,159218.SZ"
    CODES = None  # None 表示处理所有股票
    
    # API 调用间隔（秒）
    SLEEP_SECONDS = 2.0  # 建议 1.5-2.0 秒
    
    # 每分钟最大 API 调用次数
    MAX_CALLS = 40  # Tushare 限制 50 次/分钟，建议设置 40-45
    
    # 限制处理数量（用于测试，仅 incremental 模式）
    LIMIT = None  # None 表示不限制
    
    # 是否从数据库获取股票列表（保留参数，兼容性）
    USE_DB_LIST = True  # incremental 模式自动从数据库读取
    
    # ========================================
    # 执行同步
    # ========================================
    
    result = sync_daily_data(
        mode=MODE,
        start_date=START_DATE,
        codes=CODES,
        sleep_seconds=SLEEP_SECONDS,
        max_calls_per_minute=MAX_CALLS,
        limit=LIMIT,
        days=DAYS,
        use_db_list=USE_DB_LIST,
    )
    
    sys.exit(result)

