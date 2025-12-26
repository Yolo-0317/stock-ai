import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv 未安装，跳过

import pandas as pd
import tushare as ts
from mcp.server.fastmcp import FastMCP

# 初始化 MCP Server
mcp = FastMCP("TushareStockAdvisor")

# 初始化 Tushare API (需从 tushare.pro 获取 Token)
# 建议通过环境变量设置 TUSHARE_TOKEN
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
if TUSHARE_TOKEN:
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
else:
    pro = None


def _normalize_code(code: str) -> str:
    """
    规范化证券代码（用于东财接口）。

    说明：
    - 支持 '159218' / '159218.SZ' / '159218.sz' 等形式
    - 只保留数字并取前 6 位
    """
    s = str(code).strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) < 6:
        raise ValueError(f"无法解析证券代码: {code}")
    return digits[:6]


def _get_eastmoney_secid(code: str) -> str:
    """
    根据证券代码推断东财 secid（市场前缀.代码）。

    说明：
    - 深市：0.xxxxxx（含深市股票、深市 ETF 如 159xxx、北交所 8xxxxx）
    - 沪市：1.xxxxxx（含沪市股票、沪市 ETF 如 510xxx/588xxx 等）
    """
    code6 = _normalize_code(code)

    # 深市：主板/中小板/创业板/ETF(159xxx 等)/北交所(8xxxxx)
    if code6.startswith(("00", "30", "301", "002", "15", "16", "18", "8")):
        return f"0.{code6}"

    # 沪市：主板/科创板/ETF(510xxx/588xxx/56xxxx 等)
    if code6.startswith(("60", "688", "50", "51", "56", "58")):
        return f"1.{code6}"

    raise ValueError(f"无法识别证券代码的市场类型: {code}")


def _eastmoney_fetch_kline_daily(code: str, limit: int = 120) -> list[list[str]]:
    """
    从东财拉取日线 K 线列表（用于“实时/准实时”分析）。

    返回格式：
    - 每一行是拆分后的字段数组（字符串），第 0 位为 'YYYY-MM-DD'
    - 常见字段：日期, 今开, 收盘/当前, 最高, 最低, 成交量, 成交额, ... , 换手率(第 10 位)
    """
    secid = _get_eastmoney_secid(code)
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        # cb 为 JSONP 包装名，任意字符串即可
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

    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Host": "push2his.eastmoney.com",
        },
        method="GET",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    # 注意：这里是解析 JSONP 包装，正则不需要写成双反斜杠
    match = re.search(r"jQuery\d+_\d+\((.*)\);?", text)
    if not match:
        raise ValueError("无法解析东财 JSONP 响应")

    payload = json.loads(match.group(1))
    if not payload or "data" not in payload or "klines" not in payload["data"]:
        raise ValueError("东财行情数据缺失")

    klines = payload["data"]["klines"] or []
    return [line.split(",") for line in klines]


def _mysql_load_close_history(
    code6: str, limit: int = 120, mysql_url: str | None = None
) -> pd.DataFrame:
    """
    从 MySQL 的 stock_daily 表读取历史收盘价（用于盘中分析基线）。

    说明：
    - 表结构来自 create_stock_daily_table.sql
    - 默认使用环境变量 MYSQL_URL；也可显式传 mysql_url
    - 返回字段：trade_date（datetime64）、close（float）
    """
    url = mysql_url or os.getenv("MYSQL_URL")
    if not url:
        raise ValueError("未配置 MYSQL_URL，无法从 MySQL 读取历史数据。")

    # 延迟导入，避免在未安装依赖时影响其他 MCP 工具
    from sqlalchemy import create_engine, text  # type: ignore

    engine = create_engine(url, pool_pre_ping=True)
    # MySQL 的 LIMIT 参数化在部分驱动上不稳定，这里用 int 拼接更稳（code 使用参数绑定防注入）
    limit_int = int(limit)
    sql = text(
        f"""
        SELECT trade_date, close
        FROM stock_daily
        WHERE ts_code = :code
        ORDER BY trade_date ASC
        LIMIT {limit_int}
        """
    )

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"code": code6})

    if df.empty:
        return df

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.dropna(subset=["trade_date", "close"])
    return df


def _get_daily_like_data(
    ts_code: str | None,
    start_date: str | None,
    end_date: str | None,
    trade_date: str | None = None,
) -> tuple[pd.DataFrame, str]:
    """
    获取“日线类”数据的统一入口。

    说明：
    - A 股股票：优先使用 pro.daily
    - ETF/基金等：pro.daily 通常查不到，兜底使用 pro.fund_daily
    - 返回值包含数据源标识，便于排查（不在对外接口中暴露，避免破坏兼容性）
    """
    # trade_date 模式：按交易日获取全市场或单个标的历史
    if trade_date:
        # 1) 全市场：pro.daily(trade_date='YYYYMMDD')
        if ts_code is None or ts_code.strip() == "" or ts_code.strip().upper() == "ALL":
            df_all = pro.daily(trade_date=trade_date)
            if df_all is not None and not df_all.empty:
                return df_all, "daily_trade_date"
            return pd.DataFrame(), "empty"

        # 2) 指定标的：优先走 daily；必要时再兜底 fund_daily
        df_td = pro.daily(ts_code=ts_code, trade_date=trade_date)
        if df_td is not None and not df_td.empty:
            return df_td, "daily_trade_date"

        # fund_daily 是否支持 trade_date 取决于账号权限/接口能力，失败则静默兜底为空
        try:
            # 多标的逗号分隔时，fund_daily 往往不支持，避免误调用
            if "," not in ts_code:
                df_td2 = pro.fund_daily(ts_code=ts_code, trade_date=trade_date)
                if df_td2 is not None and not df_td2.empty:
                    return df_td2, "fund_daily_trade_date"
        except Exception:
            pass

        return pd.DataFrame(), "empty"

    # 时间区间模式：支持单/多标的（逗号分隔）
    # 先按股票日线尝试（也等价于 pro.query('daily', ...)）
    df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is not None and not df.empty:
        return df, "daily"

    # 再按基金/ETF 日线尝试（159xxx 等 ETF 常见）
    try:
        # 多标的逗号分隔时，fund_daily 往往不支持，避免误调用
        if ts_code is not None and "," not in ts_code:
            df2 = pro.fund_daily(
                ts_code=ts_code, start_date=start_date, end_date=end_date
            )
            if df2 is not None and not df2.empty:
                return df2, "fund_daily"
    except Exception:
        # fund_daily 可能因权限/接口不存在/参数不匹配而报错，这里不打断主流程
        pass

    # 仍然没有数据
    return pd.DataFrame(), "empty"


@mcp.tool()
def get_daily_data(
    ts_code: str = None,
    start_date: str = None,
    end_date: str = None,
    trade_date: str = None,
) -> str:
    """
    获取日线行情（兼容 Tushare 官方示例）。

    用法示例（与 Tushare 一致）：
    - 单个股票：ts_code='000001.SZ', start_date='20180701', end_date='20180718'
    - 多个股票：ts_code='000001.SZ,600000.SH', start_date='20180701', end_date='20180718'
    - 某天全市场：trade_date='20180810'（ts_code 可不传或传 'ALL'）

    参数说明：
    :param ts_code: 股票/ETF/基金代码，可用逗号分隔多个代码
    :param start_date: 开始日期 (YYYYMMDD)
    :param end_date: 结束日期 (YYYYMMDD)
    :param trade_date: 交易日 (YYYYMMDD)，传入后优先生效
    """
    if pro is None:
        return "错误：未配置 TUSHARE_TOKEN 环境变量。"

    # 默认日期：与之前 get_stock_daily_data 保持一致（最近 30 天）
    if not trade_date:
        if not end_date:
            end_date = datetime.datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (
                datetime.datetime.now() - datetime.timedelta(days=30)
            ).strftime("%Y%m%d")

    try:
        df, _source = _get_daily_like_data(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            trade_date=trade_date,
        )
        if df.empty:
            return "未查询到相关数据，请检查股票代码或日期。"
        return df.to_json(orient="records", force_ascii=False)
    except Exception as e:
        return f"查询出错: {str(e)}"


@mcp.tool()
def get_stock_daily_data(
    stock_code: str, start_date: str = None, end_date: str = None
) -> str:
    """
    获取个股历史日线行情。
    :param stock_code: 股票代码 (如 000001.SZ)
    :param start_date: 开始日期 (YYYYMMDD)
    :param end_date: 结束日期 (YYYYMMDD)
    """
    if pro is None:
        return "错误：未配置 TUSHARE_TOKEN 环境变量。"

    if not end_date:
        end_date = datetime.datetime.now().strftime("%Y%m%d")
    if not start_date:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime(
            "%Y%m%d"
        )

    try:
        # 兼容旧接口：内部复用通用的 get_daily_data
        return get_daily_data(
            ts_code=stock_code, start_date=start_date, end_date=end_date
        )
    except Exception as e:
        return f"查询出错: {str(e)}"


@mcp.tool()
def analyze_and_suggest(stock_code: str) -> str:
    """
    分析个股涨跌趋势并提供投资建议（基于 MA5/MA20 均线策略）。
    """
    if pro is None:
        return "错误：未配置 TUSHARE_TOKEN"

    # 获取最近 60 天的数据以便计算均线
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime(
        "%Y%m%d"
    )

    try:
        # 该工具只支持单个标的分析，多标的请用 get_daily_data 拉数据自行分析
        if "," in stock_code:
            return "错误：analyze_and_suggest 仅支持单个 ts_code，请勿传入逗号分隔的多个代码。"

        df, _source = _get_daily_like_data(
            ts_code=stock_code,
            start_date=start_date,
            end_date=end_date,
            trade_date=None,
        )
        if df.empty:
            return "未查询到相关数据，请检查股票代码或日期。"
        df = df.sort_values("trade_date")  # 按日期升序

        # 数据不足时避免越界/均线无意义
        if len(df) < 20:
            return (
                f"数据量不足（仅 {len(df)} 条），无法计算 MA20，请扩大日期范围后重试。"
            )

        # 计算均线
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest

        # 简单逻辑判断
        price_trend = "上涨" if latest["pct_chg"] > 0 else "下跌"
        ma_signal = (
            "金叉（买入信号）"
            if (prev["ma5"] <= prev["ma20"] and latest["ma5"] > latest["ma20"])
            else (
                "死叉（卖出信号）"
                if (prev["ma5"] >= prev["ma20"] and latest["ma5"] < latest["ma20"])
                else "多头排列" if latest["ma5"] > latest["ma20"] else "空头排列"
            )
        )

        suggestion = f"""
        ### 股票分析报告: {stock_code}
        - **最新收盘价**: {latest['close']} (涨跌幅: {latest['pct_chg']}%)
        - **当前趋势**: {price_trend}
        - **均线状态**: {ma_signal}
        - **技术指标**: MA5={latest['ma5']:.2f}, MA20={latest['ma20']:.2f}

        **投资建议**:
        {"建议关注买入机会，趋势走强。" if "金叉" in ma_signal or "多头" in ma_signal else "建议观望或减仓，趋势偏弱。"}
        (注：本分析仅供参考，股市有风险，入市需谨慎。)
        """
        return suggestion
    except Exception as e:
        return f"分析过程中出错: {str(e)}"


@mcp.tool()
def realtime_trade_signal(code: str, trade_date: str = None) -> str:
    """
    基于东财“日线级”K 线做实时买入/卖出信号分析（MA5/MA20 策略）。

    说明：
    - 适用：A 股/ETF（例如 000592、159218 等）
    - trade_date：
      - 不传：使用东财返回的最新一根日线（通常为最近交易日，盘中会动态变化）
      - 传入：YYYYMMDD，例如 '20251225'
    """
    try:
        rows = _eastmoney_fetch_kline_daily(code=code, limit=120)
        if not rows:
            return "未查询到相关数据，请检查证券代码。"

        # 找到目标日期或取最新
        target_row = None
        if trade_date:
            target = datetime.datetime.strptime(trade_date, "%Y%m%d").strftime(
                "%Y-%m-%d"
            )
            for r in rows:
                if r and r[0] == target:
                    target_row = r
                    break
            if target_row is None:
                return f"未找到指定交易日 {trade_date} 的行情数据。"
        else:
            target_row = rows[-1]

        # 解析 close 序列用于均线（第 2 位为收盘/当前）
        closes = []
        dates = []
        for r in rows:
            if len(r) < 3:
                continue
            dates.append(r[0])
            try:
                closes.append(float(r[2]))
            except Exception:
                closes.append(float("nan"))

        df = pd.DataFrame({"date": dates, "close": closes}).dropna()
        if df.empty:
            return "行情数据解析失败，请稍后重试。"

        # 取出目标日期所在位置（用于 prev/最新判断）
        target_date = target_row[0]
        idx_list = df.index[df["date"] == target_date].tolist()
        if not idx_list:
            # 兼容：目标日期可能被 dropna 过滤
            return f"未找到指定日期 {target_date} 的有效收盘价数据。"
        idx = idx_list[0]

        # 均线计算（与现有策略一致）
        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()

        latest_close = float(target_row[2])
        latest_open = float(target_row[1])
        latest_high = float(target_row[3])
        latest_low = float(target_row[4])

        # 计算涨跌幅：使用上一交易日收盘（如果存在）
        prev_close = None
        pct_chg = None
        if idx - 1 in df.index:
            prev_close = float(df.loc[idx - 1, "close"])
            if prev_close != 0:
                pct_chg = (latest_close - prev_close) / prev_close * 100

        ma5 = df.loc[idx, "ma5"]
        ma20 = df.loc[idx, "ma20"]
        prev_ma5 = df.loc[idx - 1, "ma5"] if idx - 1 in df.index else None
        prev_ma20 = df.loc[idx - 1, "ma20"] if idx - 1 in df.index else None

        # 信号判定：金叉/死叉优先，其次多空排列
        signal = "观望"
        reason = []
        if (
            prev_ma5 is not None
            and prev_ma20 is not None
            and pd.notna(prev_ma5)
            and pd.notna(prev_ma20)
        ):
            if (
                pd.notna(ma5)
                and pd.notna(ma20)
                and prev_ma5 <= prev_ma20
                and ma5 > ma20
            ):
                signal = "买入"
                reason.append("MA5 上穿 MA20（金叉）")
            elif (
                pd.notna(ma5)
                and pd.notna(ma20)
                and prev_ma5 >= prev_ma20
                and ma5 < ma20
            ):
                signal = "卖出"
                reason.append("MA5 下穿 MA20（死叉）")

        if signal == "观望" and pd.notna(ma5) and pd.notna(ma20):
            if ma5 > ma20:
                signal = "偏买入"
                reason.append("均线多头（MA5 > MA20）")
            else:
                signal = "偏卖出"
                reason.append("均线空头（MA5 < MA20）")

        # 价格位置辅助（不改变主信号，只做解释）
        if pd.notna(ma20):
            if latest_close >= ma20:
                reason.append("价格在 MA20 之上")
            else:
                reason.append("价格在 MA20 之下")

        # 当日强弱：收盘相对开盘
        if latest_close > latest_open:
            reason.append("当日收盘强于开盘")
        elif latest_close < latest_open:
            reason.append("当日收盘弱于开盘")

        # 组装输出（中文）
        pct_str = f"{pct_chg:.2f}%" if pct_chg is not None else "未知"
        ma5_str = f"{ma5:.4f}" if pd.notna(ma5) else "未知"
        ma20_str = f"{ma20:.4f}" if pd.notna(ma20) else "未知"

        suggestion = f"""
            ### 实时买卖信号报告: {code}
            - **日期**: {target_date}
            - **今开/当前/最高/最低**: {latest_open} / {latest_close} / {latest_high} / {latest_low}
            - **涨跌幅(相对昨收)**: {pct_str}
            - **技术指标**: MA5={ma5_str}, MA20={ma20_str}
            - **信号**: {signal}
            - **依据**: {"；".join(reason) if reason else "无"}

            **提示**:
            - 本信号为均线策略的简化版，仅供参考；盘中数据会变化，建议结合成交量、指数环境与基本面共同判断。
            """
        return suggestion
    except Exception as e:
        return f"分析过程中出错: {str(e)}"


@mcp.tool()
def intraday_trade_signal(code: str, mysql_url: str = None) -> str:
    """
    盘中买卖信号（结合 MySQL 历史 + 东财盘中最新价）。

    数据来源：
    - 历史：MySQL `stock_daily`（ts_code 为 6 位数字）
    - 盘中：东财日线 K 线接口最新一根（盘中会动态变化）

    信号逻辑：
    - 以 MA5/MA20 为主（与 analyze_and_suggest 保持一致的均线策略）
    - 用“盘中最新价”替换/补齐“今天这一根”的 close，再计算均线与金叉/死叉

    参数：
    - code：支持 '000592' / '000592.SZ' / '159218' 等
    - mysql_url：可选，不传则读取环境变量 MYSQL_URL
    """
    try:
        code6 = _normalize_code(code)

        # 1) 读历史收盘（用于均线基线）
        hist = _mysql_load_close_history(code6=code6, limit=200, mysql_url=mysql_url)
        if hist.empty:
            return f"未在 MySQL 中找到 {code6} 的历史数据，请先入库后再分析。"

        # 2) 取东财最新一根（日线级，盘中动态）
        rows = _eastmoney_fetch_kline_daily(code=code, limit=120)
        if not rows:
            return "未查询到东财行情数据，请检查证券代码。"
        latest = rows[-1]
        if len(latest) < 7:
            return "东财行情数据解析失败，请稍后重试。"

        rt_date = latest[0]  # YYYY-MM-DD
        rt_open = float(latest[1])
        rt_close = float(latest[2])  # 盘中“当前/收盘”
        rt_high = float(latest[3])
        rt_low = float(latest[4])
        rt_vol = float(latest[5])
        rt_amount = float(latest[6])

        # 3) 组装用于均线计算的序列：用实时价替换同日 close；否则 append 一天
        df = hist.copy()
        df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

        if (df["date_str"] == rt_date).any():
            df.loc[df["date_str"] == rt_date, "close"] = rt_close
        else:
            df = pd.concat(
                [
                    df,
                    pd.DataFrame(
                        {
                            "trade_date": [pd.to_datetime(rt_date)],
                            "close": [rt_close],
                            "date_str": [rt_date],
                        }
                    ),
                ],
                ignore_index=True,
            )

        df = df.sort_values("trade_date")
        if len(df) < 20:
            return f"历史数据量不足（仅 {len(df)} 条），无法计算 MA20。"

        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()

        latest_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        ma5 = float(latest_row["ma5"])
        ma20 = float(latest_row["ma20"])
        prev_ma5 = float(prev_row["ma5"])
        prev_ma20 = float(prev_row["ma20"])

        # 4) 计算涨跌幅：用“昨收”（历史上一条 close）作为基准
        y_close = float(prev_row["close"])
        pct_chg = (rt_close - y_close) / y_close * 100 if y_close else None

        # 5) 信号判断（与 realtime_trade_signal 一致：金叉/死叉优先）
        signal = "观望"
        reasons: list[str] = []

        if prev_ma5 <= prev_ma20 and ma5 > ma20:
            signal = "买入"
            reasons.append("盘中 MA5 上穿 MA20（金叉）")
        elif prev_ma5 >= prev_ma20 and ma5 < ma20:
            signal = "卖出"
            reasons.append("盘中 MA5 下穿 MA20（死叉）")
        else:
            if ma5 > ma20:
                signal = "偏买入"
                reasons.append("均线多头（MA5 > MA20）")
            else:
                signal = "偏卖出"
                reasons.append("均线空头（MA5 < MA20）")

        if rt_close >= ma20:
            reasons.append("价格在 MA20 之上")
        else:
            reasons.append("价格在 MA20 之下")

        if rt_close > rt_open:
            reasons.append("盘中强于开盘")
        elif rt_close < rt_open:
            reasons.append("盘中弱于开盘")

        pct_str = f"{pct_chg:.2f}%" if pct_chg is not None else "未知"

        report = f"""
            ### 盘中买卖信号报告: {code6}
            - **盘中日期**: {rt_date}
            - **今开/当前/最高/最低**: {rt_open} / {rt_close} / {rt_high} / {rt_low}
            - **成交量/成交额**: {rt_vol} / {rt_amount}
            - **涨跌幅(相对昨收)**: {pct_str}
            - **技术指标(含盘中价)**: MA5={ma5:.4f}, MA20={ma20:.4f}
            - **信号**: {signal}
            - **依据**: {"；".join(reasons)}

            **提示**:
            - 历史基线来自 MySQL `stock_daily`，盘中价来自东财接口；盘中信号会随价格波动而变化。
            """
        return report
    except Exception as e:
        return f"分析过程中出错: {str(e)}"


def _call_deepseek_api(prompt: str, temperature: float = 0.3) -> str:
    """
    调用 DeepSeek API 进行推理。

    参数：
    - prompt: 用户输入的 prompt
    - temperature: 温度参数（0-1），越低越确定性，推荐 0.3

    返回：
    - AI 的文本回复

    环境变量：
    - DEEPSEEK_API_KEY: DeepSeek API 密钥
    """
    import requests

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("未配置 DEEPSEEK_API_KEY 环境变量")

    api_url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的量化交易分析师，擅长技术分析和量价分析。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 800,
    }

    resp = requests.post(api_url, json=data, headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    return result["choices"][0]["message"]["content"]


def _build_deepseek_prompt(code: str, hist_df: pd.DataFrame, latest_data: dict) -> str:
    """
    构建喂给 DeepSeek 的 prompt。

    参数：
    - code: 证券代码（6 位）
    - hist_df: 历史日线 DataFrame（包含 trade_date/close/ma5/ma20）
    - latest_data: 当前盘中数据 dict

    返回：
    - 格式化的 prompt 字符串
    """
    # 取最近 20 天历史（避免 prompt 过长）
    recent_hist = hist_df.tail(20).copy()
    recent_hist["date_str"] = recent_hist["trade_date"].dt.strftime("%Y-%m-%d")

    # 构建历史数据表格（markdown 格式）
    hist_lines = ["日期 | 收盘价 | MA5 | MA20"]
    hist_lines.append("--- | --- | --- | ---")
    for _, row in recent_hist.iterrows():
        ma5_str = f"{row['ma5']:.4f}" if pd.notna(row["ma5"]) else "N/A"
        ma20_str = f"{row['ma20']:.4f}" if pd.notna(row["ma20"]) else "N/A"
        hist_lines.append(
            f"{row['date_str']} | {row['close']:.4f} | {ma5_str} | {ma20_str}"
        )
    hist_table = "\n".join(hist_lines)

    prompt = f"""
        你是一个量化交易分析师。请根据以下信息，给出 **{code}** 的交易信号。

        ## 历史日线（最近 20 天）
        {hist_table}

        ## 当前盘中实时数据
        - **日期**: {latest_data['date']}
        - **当前价**: {latest_data['close']}
        - **今开**: {latest_data['open']}
        - **最高**: {latest_data['high']}
        - **最低**: {latest_data['low']}
        - **成交量（手）**: {latest_data['vol']}
        - **成交额（元）**: {latest_data['amount']}
        - **涨跌幅**: {latest_data['pct_chg']}%
        - **MA5**: {latest_data['ma5']:.4f}
        - **MA20**: {latest_data['ma20']:.4f}
        - **昨收**: {latest_data['pre_close']}

        ## 分析要求
        1. 综合考虑：趋势（均线）、量能、价格形态、支撑/压力位
        2. 给出明确信号：**买入** / **卖出** / **观望**
        3. 说明核心理由（3 条以内，简明扼要）
        4. 如果是买入/卖出，建议止损位和目标位（基于技术分析）

        ## 回答格式（严格按以下格式输出）
        信号: [买入/卖出/观望]
        理由: [理由1; 理由2; 理由3]
        止损位: [价格或 N/A]
        目标位: [价格或 N/A]
        """
    return prompt


def _parse_deepseek_response(response: str) -> dict:
    """
    解析 DeepSeek 返回的交易信号。

    返回格式：
    {
        "signal": "买入/卖出/观望",
        "reason": "理由文本",
        "stop_loss": "止损位或 N/A",
        "target": "目标位或 N/A",
        "raw": "原始完整回复"
    }
    """
    result = {
        "signal": "未知",
        "reason": "",
        "stop_loss": "N/A",
        "target": "N/A",
        "raw": response,
    }

    lines = response.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.startswith("信号:") or line.startswith("信号："):
            result["signal"] = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif line.startswith("理由:") or line.startswith("理由："):
            result["reason"] = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif line.startswith("止损位:") or line.startswith("止损位："):
            result["stop_loss"] = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif line.startswith("目标位:") or line.startswith("目标位："):
            result["target"] = line.split(":", 1)[-1].split("：", 1)[-1].strip()

    return result


@mcp.tool()
def deepseek_trade_signal(code: str, mysql_url: str = None) -> str:
    """
    使用 DeepSeek AI 分析盘中交易信号（结合 MySQL 历史 + 东财实时数据）。

    数据来源：
    - 历史：MySQL `stock_daily`（ts_code 为 6 位数字）
    - 盘中：东财日线 K 线接口最新一根（盘中会动态变化）

    AI 分析：
    - 综合考虑趋势、量能、价格形态、技术指标（MA5/MA20 等）
    - 给出买入/卖出/观望信号及理由
    - 建议止损位和目标位

    参数：
    - code：支持 '000592' / '000592.SZ' / '159218' 等
    - mysql_url：可选，不传则读取环境变量 MYSQL_URL

    环境变量：
    - DEEPSEEK_API_KEY：DeepSeek API 密钥（必需）
    - MYSQL_URL：MySQL 连接串（必需）
    """
    try:
        code6 = _normalize_code(code)

        # 1) 读历史收盘（用于均线基线 + 喂给 AI）
        hist = _mysql_load_close_history(code6=code6, limit=200, mysql_url=mysql_url)
        if hist.empty:
            return f"未在 MySQL 中找到 {code6} 的历史数据，请先入库后再分析。"

        # 2) 取东财最新一根（日线级，盘中动态）
        rows = _eastmoney_fetch_kline_daily(code=code, limit=120)
        if not rows:
            return "未查询到东财行情数据，请检查证券代码。"
        latest = rows[-1]
        if len(latest) < 7:
            return "东财行情数据解析失败，请稍后重试。"

        rt_date = latest[0]  # YYYY-MM-DD
        rt_open = float(latest[1])
        rt_close = float(latest[2])  # 盘中"当前/收盘"
        rt_high = float(latest[3])
        rt_low = float(latest[4])
        rt_vol = float(latest[5])
        rt_amount = float(latest[6])

        # 3) 组装用于均线计算的序列：用实时价替换同日 close；否则 append 一天
        df = hist.copy()
        df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

        if (df["date_str"] == rt_date).any():
            df.loc[df["date_str"] == rt_date, "close"] = rt_close
        else:
            df = pd.concat(
                [
                    df,
                    pd.DataFrame(
                        {
                            "trade_date": [pd.to_datetime(rt_date)],
                            "close": [rt_close],
                            "date_str": [rt_date],
                        }
                    ),
                ],
                ignore_index=True,
            )

        df = df.sort_values("trade_date")
        if len(df) < 20:
            return f"历史数据量不足（仅 {len(df)} 条），无法计算 MA20。"

        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()

        latest_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        ma5 = float(latest_row["ma5"])
        ma20 = float(latest_row["ma20"])
        y_close = float(prev_row["close"])
        pct_chg = (rt_close - y_close) / y_close * 100 if y_close else None

        # 4) 构建 DeepSeek prompt
        latest_data = {
            "date": rt_date,
            "open": rt_open,
            "close": rt_close,
            "high": rt_high,
            "low": rt_low,
            "vol": rt_vol,
            "amount": rt_amount,
            "pct_chg": f"{pct_chg:.2f}" if pct_chg is not None else "N/A",
            "ma5": ma5,
            "ma20": ma20,
            "pre_close": y_close,
        }

        prompt = _build_deepseek_prompt(code=code6, hist_df=df, latest_data=latest_data)

        # 5) 调用 DeepSeek API
        ai_response = _call_deepseek_api(prompt, temperature=0.3)

        # 6) 解析 AI 返回
        parsed = _parse_deepseek_response(ai_response)

        # 7) 格式化输出报告
        pct_str = f"{pct_chg:.2f}%" if pct_chg is not None else "未知"

        report = f"""
            ### DeepSeek AI 交易信号报告: {code6}
            - **盘中日期**: {rt_date}
            - **今开/当前/最高/最低**: {rt_open} / {rt_close} / {rt_high} / {rt_low}
            - **成交量/成交额**: {rt_vol} / {rt_amount}
            - **涨跌幅(相对昨收)**: {pct_str}
            - **技术指标(含盘中价)**: MA5={ma5:.4f}, MA20={ma20:.4f}

            ---

            - **AI 信号**: {parsed['signal']}
            - **核心理由**: {parsed['reason']}
            - **止损位**: {parsed['stop_loss']}
            - **目标位**: {parsed['target']}

            ---

            **AI 完整分析**:
            {parsed['raw']}

            **提示**:
            - AI 分析基于历史日线 + 盘中实时数据，结合技术指标与量价关系
            - 信号仅供参考，实盘操作需结合市场环境、仓位管理与风险控制
            """
        return report

    except Exception as e:
        return f"DeepSeek 分析过程中出错: {str(e)}"


@mcp.tool()
def deepseek_intraday_t_signal(
    code: str,
    position_cost: float = None,
    position_ratio: float = 0.0,
    mysql_url: str = None,
) -> str:
    """
    使用 DeepSeek AI 分析盘中做T信号（专注于日内波段交易）。

    数据来源：
    - 历史：MySQL `stock_daily`（ts_code 为 6 位数字）
    - 盘中：东财日线 K 线接口最新一根（盘中会动态变化）

    AI 分析重点：
    - 盘中波动节奏：当前是否处于低点（适合加仓/做T买入）或高点（适合减仓/做T卖出）
    - 日内支撑/压力位：基于今日开盘价、昨收、均线等
    - 量能配合：放量突破 vs 缩量回调
    - 持仓管理：根据当前仓位给出加仓/减仓/做T建议

    信号类型：
    - 做T买入：盘中回调到支撑位，适合低吸
    - 做T卖出：盘中拉升到压力位，适合高抛
    - 加仓：趋势向上且回调不深，适合增加底仓
    - 减仓：趋势转弱或涨幅过大，适合降低仓位
    - 持仓不动：震荡整理，观望为主

    参数：
    - code：支持 '000592' / '000592.SZ' / '159218' 等
    - position_cost：持仓成本价（可选，用于计算盈亏）
    - position_ratio：当前仓位比例 0-1（如 0.5 表示半仓，用于决策加减仓幅度）
    - mysql_url：可选，不传则读取环境变量 MYSQL_URL

    环境变量：
    - DEEPSEEK_API_KEY：DeepSeek API 密钥（必需）
    - MYSQL_URL：MySQL 连接串（必需）
    """
    try:
        code6 = _normalize_code(code)

        # 1) 读历史收盘（用于均线基线 + 喂给 AI）
        hist = _mysql_load_close_history(code6=code6, limit=200, mysql_url=mysql_url)
        if hist.empty:
            return f"未在 MySQL 中找到 {code6} 的历史数据，请先入库后再分析。"

        # 2) 取东财最新一根（日线级，盘中动态）
        rows = _eastmoney_fetch_kline_daily(code=code, limit=120)
        if not rows:
            return "未查询到东财行情数据，请检查证券代码。"
        latest = rows[-1]
        if len(latest) < 7:
            return "东财行情数据解析失败，请稍后重试。"

        rt_date = latest[0]  # YYYY-MM-DD
        rt_open = float(latest[1])
        rt_close = float(latest[2])  # 盘中"当前/收盘"
        rt_high = float(latest[3])
        rt_low = float(latest[4])
        rt_vol = float(latest[5])
        rt_amount = float(latest[6])

        # 3) 组装用于均线计算的序列
        df = hist.copy()
        df["date_str"] = df["trade_date"].dt.strftime("%Y-%m-%d")

        if (df["date_str"] == rt_date).any():
            df.loc[df["date_str"] == rt_date, "close"] = rt_close
        else:
            df = pd.concat(
                [
                    df,
                    pd.DataFrame(
                        {
                            "trade_date": [pd.to_datetime(rt_date)],
                            "close": [rt_close],
                            "date_str": [rt_date],
                        }
                    ),
                ],
                ignore_index=True,
            )

        df = df.sort_values("trade_date")
        if len(df) < 20:
            return f"历史数据量不足（仅 {len(df)} 条），无法计算 MA20。"

        df["ma5"] = df["close"].rolling(5).mean()
        df["ma20"] = df["close"].rolling(20).mean()

        latest_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        ma5 = float(latest_row["ma5"])
        ma20 = float(latest_row["ma20"])
        y_close = float(prev_row["close"])
        pct_chg = (rt_close - y_close) / y_close * 100 if y_close else None

        # 4) 计算盘中关键位置
        # 日内振幅
        intraday_range = ((rt_high - rt_low) / y_close * 100) if y_close else 0
        # 当前价格在日内区间的位置（0-1，0.5表示中轴）
        position_in_range = (
            ((rt_close - rt_low) / (rt_high - rt_low)) if (rt_high > rt_low) else 0.5
        )
        # 相对昨收的位置
        vs_pre_close = ((rt_close - y_close) / y_close * 100) if y_close else 0

        # 5) 构建专门用于做T的 prompt
        prompt = _build_intraday_t_prompt(
            code=code6,
            hist_df=df.tail(10),  # 只取最近10天，减少token消耗
            current_data={
                "date": rt_date,
                "open": rt_open,
                "close": rt_close,
                "high": rt_high,
                "low": rt_low,
                "vol": rt_vol,
                "amount": rt_amount,
                "pct_chg": f"{pct_chg:.2f}" if pct_chg is not None else "N/A",
                "ma5": ma5,
                "ma20": ma20,
                "pre_close": y_close,
                "intraday_range": f"{intraday_range:.2f}%",
                "position_in_range": f"{position_in_range:.1%}",
                "vs_pre_close": f"{vs_pre_close:.2f}%",
            },
            position_info={
                "cost": position_cost,
                "ratio": position_ratio,
            },
        )

        # 6) 调用 DeepSeek API
        ai_response = _call_deepseek_api(prompt, temperature=0.2)  # 温度更低，更确定性

        # 7) 解析 AI 返回
        parsed = _parse_intraday_t_response(ai_response)

        # 8) 格式化输出报告
        pct_str = f"{pct_chg:.2f}%" if pct_chg is not None else "未知"

        position_info_str = ""
        if position_cost:
            profit_pct = (rt_close - position_cost) / position_cost * 100
            position_info_str = (
                f"\n- **持仓成本**: {position_cost} (浮动盈亏: {profit_pct:+.2f}%)"
            )
        if position_ratio > 0:
            position_info_str += f"\n- **当前仓位**: {position_ratio:.1%}"

        report = f"""
### DeepSeek AI 盘中做T信号: {code6}
- **盘中日期**: {rt_date}
- **今开/当前/最高/最低**: {rt_open} / {rt_close} / {rt_high} / {rt_low}
- **日内振幅**: {intraday_range:.2f}% (当前位于日内区间 {position_in_range:.1%} 位置)
- **涨跌幅(相对昨收)**: {pct_str}
- **技术指标**: MA5={ma5:.4f}, MA20={ma20:.4f}{position_info_str}

---

- **AI 操作建议**: {parsed['action']}
- **核心理由**: {parsed['reason']}
- **建议操作量**: {parsed['size']}
- **目标价位**: {parsed['target']}
- **止损价位**: {parsed['stop_loss']}

---

**AI 完整分析**:
{parsed['raw']}

**提示**:
- 做T操作需快进快出，严格止损
- 建议单次操作量不超过总仓位的 20-30%
- 盘中波动剧烈时，优先保本，不强求盈利
"""
        return report

    except Exception as e:
        return f"DeepSeek 盘中做T分析过程中出错: {str(e)}"


def _build_intraday_t_prompt(
    code: str, hist_df: pd.DataFrame, current_data: dict, position_info: dict
) -> str:
    """
    构建专门用于盘中做T的 prompt。
    """
    # 历史数据表格（精简版）
    recent_hist = hist_df.copy()
    recent_hist["date_str"] = recent_hist["trade_date"].dt.strftime("%Y-%m-%d")

    hist_lines = ["日期 | 收盘 | MA5 | MA20"]
    hist_lines.append("--- | --- | --- | ---")
    for _, row in recent_hist.iterrows():
        ma5_str = f"{row['ma5']:.3f}" if pd.notna(row["ma5"]) else "N/A"
        ma20_str = f"{row['ma20']:.3f}" if pd.notna(row["ma20"]) else "N/A"
        hist_lines.append(
            f"{row['date_str']} | {row['close']:.3f} | {ma5_str} | {ma20_str}"
        )
    hist_table = "\n".join(hist_lines)

    position_text = ""
    if position_info.get("cost"):
        profit = (
            (current_data["close"] - position_info["cost"])
            / position_info["cost"]
            * 100
        )
        position_text = f"""
## 当前持仓
- **成本价**: {position_info['cost']:.3f}
- **当前仓位**: {position_info['ratio']:.1%}
- **浮动盈亏**: {profit:+.2f}%
"""

    prompt = f"""
你是一个盘中交易专家，擅长日内波段操作（做T）。请分析 **{code}** 的盘中做T机会。

## 历史日线（最近 10 天）
{hist_table}

## 当前盘中实时数据
- **日期**: {current_data['date']}
- **今开**: {current_data['open']}
- **当前价**: {current_data['close']}
- **最高**: {current_data['high']}
- **最低**: {current_data['low']}
- **日内振幅**: {current_data['intraday_range']}
- **当前位于日内区间**: {current_data['position_in_range']} (0%=最低点, 100%=最高点)
- **涨跌幅(相对昨收)**: {current_data['pct_chg']}
- **MA5**: {current_data['ma5']:.4f}
- **MA20**: {current_data['ma20']:.4f}
- **昨收**: {current_data['pre_close']}
{position_text}

## 分析要求（重点关注盘中做T机会）

1. **判断当前位置**：是处于日内低点（适合买入）、高点（适合卖出）、还是中继整理？
2. **支撑/压力位**：基于昨收、今开、均线、日内高低点，给出关键价位
3. **操作建议**：从以下选择一个
   - **做T买入**：盘中回调到支撑位，适合低吸（短线持有，目标快速上涨后卖出）
   - **做T卖出**：盘中拉升到压力位，适合高抛（已有持仓时）
   - **加仓**：趋势向上且位置不高，可增加底仓（中长线持有）
   - **减仓**：涨幅较大或趋势转弱，适合降低仓位
   - **持仓不动**：震荡整理，暂无明确方向
4. **操作量建议**：轻仓试探 / 标准仓位 / 重仓（考虑当前仓位比例）
5. **目标价位**：做T的目标卖出价（买入时）或回补价（卖出时）
6. **止损价位**：快进快出，止损要严格

## 回答格式（严格按以下格式输出）
操作建议: [做T买入/做T卖出/加仓/减仓/持仓不动]
核心理由: [简明理由，3条以内]
建议操作量: [轻仓试探10-20% / 标准仓位20-30% / 重仓30-50%]
目标价位: [具体价格]
止损价位: [具体价格]
"""
    return prompt


def _parse_intraday_t_response(response: str) -> dict:
    """
    解析 DeepSeek 盘中做T信号。
    """
    result = {
        "action": "未知",
        "reason": "",
        "size": "标准仓位",
        "target": "N/A",
        "stop_loss": "N/A",
        "raw": response,
    }

    lines = response.strip().split("\n")
    current_field = None
    reason_lines = []

    for line in lines:
        line_stripped = line.strip()

        if line_stripped.startswith("操作建议:") or line_stripped.startswith(
            "操作建议："
        ):
            result["action"] = (
                line_stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            )
            current_field = None
        elif line_stripped.startswith("核心理由:") or line_stripped.startswith(
            "核心理由："
        ):
            # 提取第一行理由
            first_line_reason = (
                line_stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            )
            if first_line_reason:
                reason_lines = [first_line_reason]
            current_field = "reason"
        elif line_stripped.startswith("建议操作量:") or line_stripped.startswith(
            "建议操作量："
        ):
            result["size"] = line_stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            current_field = None
        elif line_stripped.startswith("目标价位:") or line_stripped.startswith(
            "目标价位："
        ):
            result["target"] = (
                line_stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            )
            current_field = None
        elif line_stripped.startswith("止损价位:") or line_stripped.startswith(
            "止损价位："
        ):
            result["stop_loss"] = (
                line_stripped.split(":", 1)[-1].split("：", 1)[-1].strip()
            )
            current_field = None
        elif current_field == "reason" and line_stripped:
            # 继续收集多行理由（以数字或符号开头的）
            if line_stripped[0].isdigit() or line_stripped.startswith(
                ("1.", "2.", "3.", "-", "•")
            ):
                reason_lines.append(line_stripped)

    # 合并多行理由
    if reason_lines:
        result["reason"] = "; ".join(reason_lines)

    return result


if __name__ == "__main__":
    mcp.run()
