#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
两阶段选股策略：筑底 + 放量突破 + 东财浏览器多维增强

Step 1: 从 MySQL(stock_daily) 做技术面筛选（筑底 + 放量突破）
Step 2: 驱动浏览器访问东财页面补充基本面/财务面/资金面/消息面，并做综合评分
"""

import asyncio
import os
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# 添加项目目录路径
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

load_dotenv()

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False

from fetch_akshare_data import get_stock_fund_flow, get_stock_news
from get_fundamental_browser import get_fundamental_via_browser


# ============================================
# Step 1: 技术面参数
# ============================================
BOX_LOOKBACK = 120  # 筑底观察窗口（交易日）
BOX_SKIP_RECENT = 10  # 计算箱体时跳过最近N日，避免突破日污染
BOX_WIDTH_MAX = 45.0  # 箱体振幅上限（%）
DIST_TO_250D_LOW_MAX = 35.0  # 距离250日低点上限（%），越小越接近低位
BREAKOUT_MIN_PCT = 0.5  # 突破箱顶最小幅度（%）
VOLUME_RATIO_MIN = 1.5  # 当日成交额相对近20日均额倍数

MIN_PRICE = 4.0
MAX_PRICE = 30.0
MIN_AMOUNT = 5000.0  # 万

# ============================================
# Step 2: 浏览器增强参数
# ============================================
BROWSER_CONCURRENCY = 3
BROWSER_TIMEOUT_MS = 25000
NEWS_LIMIT = 3

# ============================================
# 综合评分权重（总计 1.0）
# ============================================
W_TECH = 0.5
W_FUNDAMENTAL = 0.2
W_CAPITAL = 0.2
W_NEWS = 0.1


def get_db_engine():
    mysql_url = os.getenv("MYSQL_URL")
    if not mysql_url:
        raise RuntimeError("MYSQL_URL 未设置，无法从 MySQL 读取日线数据")
    return create_engine(mysql_url)


def get_latest_trade_date(engine) -> str:
    query = "SELECT MAX(trade_date) FROM stock_daily"
    with engine.connect() as conn:
        latest = conn.execute(text(query)).scalar()
    if latest is None:
        raise RuntimeError("stock_daily 没有数据")
    return latest.strftime("%Y%m%d")


def normalize_code_6(ts_code: str) -> str:
    digits = "".join(filter(str.isdigit, str(ts_code)))
    return digits[:6]


def to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text_val = str(value).strip()
    if text_val in ("", "-", "--", "N/A", "None", "nan"):
        return None
    text_val = text_val.replace(",", "").replace("%", "")
    match = re.search(r"-?\d+(\.\d+)?", text_val)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None


def sanitize_text(value: Any, max_len: Optional[int] = None) -> str:
    """
    清洗文本，避免多行/超长错误信息破坏 CSV 可读性。
    """
    if value is None:
        return ""
    text_val = str(value).replace("\r", " ").replace("\n", " ")
    text_val = re.sub(r"\s+", " ", text_val).strip()
    if max_len and len(text_val) > max_len:
        return text_val[: max_len - 3] + "..."
    return text_val


def is_noise_text(text_val: Any) -> bool:
    s = sanitize_text(text_val, max_len=300)
    if not s:
        return True
    noise_keywords = (
        "扫一扫下载APP",
        "东方财富产品",
        "东方财富证券开户",
        "天天基金网",
        "网站首页",
        "加收藏",
        "移动客户端",
        "股吧",
        "登录",
        "我的菜单",
        "关于我们",
        "广告服务",
        "友情链接",
    )
    return any(k in s for k in noise_keywords)


def clean_numeric_like_text(value: Any, max_len: int = 48) -> str:
    s = sanitize_text(value, max_len=max_len)
    if not s:
        return "N/A"
    return s if to_float(s) is not None else "N/A"


def clean_name_text(value: Any) -> str:
    s = sanitize_text(value, max_len=30)
    if not s:
        return "N/A"
    if is_noise_text(s):
        return "N/A"
    if "东方财富" in s and len(s) > 10:
        return "N/A"
    return s


async def launch_browser_with_fallback(playwright_obj):
    """
    优先直接驱动本机已安装的 Chrome，失败后再回退到 Playwright 自带 Chromium。
    这样在未执行 playwright install 的环境下也尽量可运行。
    """
    # 1) 首选：系统 Chrome channel
    try:
        return await playwright_obj.chromium.launch(
            headless=True,
            channel="chrome",
        )
    except Exception:
        pass

    # 2) 次选：显式 executable_path（macOS 常见路径）
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(chrome_path):
        try:
            return await playwright_obj.chromium.launch(
                headless=True,
                executable_path=chrome_path,
            )
        except Exception:
            pass

    # 3) 回退：Playwright bundled Chromium（需要 playwright install）
    return await playwright_obj.chromium.launch(headless=True)


def score_fundamental(roe: Optional[float], profit_growth: Optional[float], debt_ratio: Optional[float], pe_ttm: Optional[float]) -> float:
    score = 0.0
    if roe is not None:
        if roe >= 15:
            score += 40
        elif roe >= 10:
            score += 30
        elif roe >= 5:
            score += 20
        elif roe >= 0:
            score += 10
    if profit_growth is not None:
        if profit_growth >= 40:
            score += 30
        elif profit_growth >= 20:
            score += 22
        elif profit_growth >= 0:
            score += 14
        elif profit_growth >= -20:
            score += 6
    if debt_ratio is not None:
        if debt_ratio <= 40:
            score += 20
        elif debt_ratio <= 60:
            score += 12
        elif debt_ratio <= 75:
            score += 6
    if pe_ttm is not None:
        if 0 < pe_ttm <= 30:
            score += 10
        elif pe_ttm <= 60:
            score += 6
    return round(min(100.0, score), 1)


def score_capital(main_inflow_ratio: Optional[float], super_large_inflow: Optional[float]) -> float:
    score = 0.0
    if main_inflow_ratio is not None:
        if main_inflow_ratio >= 10:
            score += 55
        elif main_inflow_ratio >= 5:
            score += 40
        elif main_inflow_ratio >= 0:
            score += 25
    if super_large_inflow is not None:
        # 这里按“万元”量纲评分；若来源字段无法确认量纲，至少仍可做相对排序
        if super_large_inflow >= 20000:
            score += 45
        elif super_large_inflow >= 5000:
            score += 30
        elif super_large_inflow > 0:
            score += 15
    return round(min(100.0, score), 1)


def score_news(headlines: List[str]) -> float:
    if not headlines:
        return 30.0
    positive_keywords = ("增长", "中标", "回购", "增持", "预增", "合作", "突破", "新品", "订单")
    negative_keywords = ("减持", "亏损", "问询", "处罚", "诉讼", "风险", "下滑", "违约", "退市")
    score = 50.0
    joined = " ".join(headlines)
    pos_count = sum(1 for kw in positive_keywords if kw in joined)
    neg_count = sum(1 for kw in negative_keywords if kw in joined)
    score += pos_count * 10
    score -= neg_count * 12
    return round(max(0.0, min(100.0, score)), 1)


def build_action(final_score: float) -> str:
    if final_score >= 80:
        return "强势关注"
    if final_score >= 65:
        return "观察买入"
    if final_score >= 50:
        return "继续观察"
    return "谨慎回避"


def load_daily_data(engine, trade_date: str) -> pd.DataFrame:
    end_date_obj = datetime.strptime(trade_date, "%Y%m%d")
    start_date_obj = end_date_obj - timedelta(days=1100)
    start_date = start_date_obj.strftime("%Y-%m-%d")
    end_date = end_date_obj.strftime("%Y-%m-%d")

    query = f"""
        SELECT ts_code, trade_date, open, high, low, close, pct_chg, vol, amount
        FROM stock_daily
        WHERE trade_date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY ts_code, trade_date
    """
    return pd.read_sql(text(query), engine)


def select_technical_candidates(df_all: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for ts_code, group in df_all.groupby("ts_code"):
        group = group.sort_values("trade_date")
        if len(group) < 260:
            continue

        latest = group.iloc[-1]
        close_today = float(latest["close"])
        amount_today = float(latest["amount"])
        pct_chg_today = float(latest["pct_chg"])

        if not (MIN_PRICE <= close_today <= MAX_PRICE):
            continue
        if amount_today < MIN_AMOUNT:
            continue

        ma5 = group["close"].tail(5).mean()
        ma10 = group["close"].tail(10).mean()
        ma20 = group["close"].tail(20).mean()

        if len(group) < BOX_LOOKBACK + BOX_SKIP_RECENT + 1:
            continue

        box_data = group.iloc[-(BOX_LOOKBACK + BOX_SKIP_RECENT):-BOX_SKIP_RECENT]
        box_high = float(box_data["high"].max())
        box_low = float(box_data["low"].min())
        if box_low <= 0:
            continue

        box_width = (box_high - box_low) / box_low * 100.0
        breakout_pct = (close_today - box_high) / box_high * 100.0
        avg_amount_20 = float(group["amount"].iloc[-21:-1].mean())
        volume_ratio = amount_today / avg_amount_20 if avg_amount_20 > 0 else 0.0

        high_250d = float(group["high"].tail(250).max())
        low_250d = float(group["low"].tail(250).min())
        dist_to_250d_low = (close_today - low_250d) / low_250d * 100.0 if low_250d > 0 else 999.0
        dist_to_250d_high = (close_today - high_250d) / high_250d * 100.0 if high_250d > 0 else 0.0

        cond_bottom = box_width <= BOX_WIDTH_MAX and dist_to_250d_low <= DIST_TO_250D_LOW_MAX
        cond_breakout = breakout_pct >= BREAKOUT_MIN_PCT and volume_ratio >= VOLUME_RATIO_MIN
        cond_trend = ma5 > ma10 > ma20 and close_today >= ma20
        cond_momentum = -1 <= pct_chg_today <= 9

        if not (cond_bottom and cond_breakout and cond_trend and cond_momentum):
            continue

        signal_score = 45.0
        trend_score = 0.0
        if ma5 > ma10:
            trend_score += 8
        if ma10 > ma20:
            trend_score += 8
        if close_today >= ma20:
            trend_score += 9

        breakout_score = 0.0
        if breakout_pct >= 3:
            breakout_score += 20
        elif breakout_pct >= 1:
            breakout_score += 16
        else:
            breakout_score += 12
        if volume_ratio >= 2.5:
            breakout_score += 20
        elif volume_ratio >= 1.8:
            breakout_score += 16
        else:
            breakout_score += 12

        location_score = 0.0
        if dist_to_250d_low <= 15:
            location_score += 15
        elif dist_to_250d_low <= 25:
            location_score += 10
        else:
            location_score += 6
        if dist_to_250d_high <= -15:
            location_score += 10
        elif dist_to_250d_high <= -5:
            location_score += 6

        technical_score = round(min(100.0, signal_score + trend_score + breakout_score + location_score), 1)
        tags = ["筑底", "放量突破"]
        if breakout_pct >= 3:
            tags.append("强突破")
        if volume_ratio >= 2:
            tags.append("显著放量")

        rows.append(
            {
                "代码": ts_code,
                "代码6位": normalize_code_6(ts_code),
                "收盘价": round(close_today, 2),
                "涨幅%": round(pct_chg_today, 2),
                "成交额(万)": round(amount_today, 1),
                "箱体宽度%": round(box_width, 2),
                "突破幅度%": round(breakout_pct, 2),
                "放量倍数": round(volume_ratio, 2),
                "距250日低点%": round(dist_to_250d_low, 2),
                "策略标签": ",".join(tags),
                "技术分": technical_score,
                "信号分": signal_score,
                "趋势分": trend_score,
                "突破分": breakout_score,
                "位置分": location_score,
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(by=["技术分", "放量倍数", "突破幅度%"], ascending=False)


async def _safe_text(locator) -> Optional[str]:
    try:
        value = (await locator.first.inner_text()).strip()
        return value if value else None
    except Exception:
        return None


async def _extract_table_value(page, table_selector: str, labels: List[str]) -> Optional[str]:
    js = """
    ([tableSelector, labels]) => {
      const table = document.querySelector(tableSelector);
      if (!table) return null;
      const rows = Array.from(table.querySelectorAll("tr"));
      for (const row of rows) {
        const cells = Array.from(row.querySelectorAll("th,td"));
        if (!cells.length) continue;
        const texts = cells.map(c => (c.innerText || "").trim());
        const labelIdx = texts.findIndex(t => labels.some(lb => t.includes(lb)));
        if (labelIdx >= 0) {
          for (let i = labelIdx + 1; i < texts.length; i++) {
            const v = texts[i];
            if (v && !/^[-—]+$/.test(v)) {
              return v;
            }
          }
        }
      }
      return null;
    }
    """
    try:
        return await page.evaluate(js, [table_selector, labels])
    except Exception:
        return None


async def fetch_eastmoney_enrichment(code_6: str, sem: asyncio.Semaphore) -> Dict[str, Any]:
    async with sem:
        result: Dict[str, Any] = {
            "代码6位": code_6,
            "名称": None,
            "市盈率(动)": None,
            "ROE": None,
            "净利润增长率": None,
            "资产负债率": None,
            "主力净流入占比": None,
            "超大单净流入": None,
            "新闻标题": [],
            "抓取状态": "ok",
            "抓取备注": "",
        }
        if not PLAYWRIGHT_AVAILABLE:
            result["抓取状态"] = "fallback"
            result["抓取备注"] = "playwright 不可用，使用 AkShare/curl 兜底"
            return result

        prefix = "sh" if code_6.startswith(("60", "68")) else "sz"
        code_full = ("SH" if prefix == "sh" else "SZ") + code_6
        quote_url = f"https://quote.eastmoney.com/{prefix}{code_6}.html"
        f10_url = f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={code_full}"
        news_url = f"https://quote.eastmoney.com/zx/unify_{prefix}{code_6}_1.html"

        try:
            async with async_playwright() as p:
                browser = await launch_browser_with_fallback(p)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 860},
                )
                page = await context.new_page()

                # 行情页：仅提取名称（避免误抓页脚导航）
                await page.goto(quote_url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1200)
                name_text = await _safe_text(page.locator(".quote-name"))
                if not name_text:
                    title = await page.title()
                    if title:
                        name_text = title.split("(")[0].split("_")[0].strip()
                result["名称"] = clean_name_text(name_text)

                # F10页：ROE、净利润增长、资产负债率
                await page.goto(f10_url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                try:
                    await page.wait_for_selector("#zyzb_table", timeout=12000)
                except Exception:
                    pass
                result["ROE"] = clean_numeric_like_text(
                    await _extract_table_value(page, "#zyzb_table", ["净资产收益率", "ROE"])
                )
                result["净利润增长率"] = clean_numeric_like_text(
                    await _extract_table_value(page, "#zyzb_table", ["净利润同比增长率", "净利润增长率"])
                )
                result["资产负债率"] = clean_numeric_like_text(
                    await _extract_table_value(page, "#zyzb_table", ["资产负债率"])
                )

                # 资讯页：只抓新闻正文链接标题，过滤导航/菜单文案
                await page.goto(news_url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                await page.wait_for_timeout(1200)
                titles = await page.evaluate(
                    """
                    (limit) => {
                      const out = [];
                      const links = Array.from(document.querySelectorAll("a[href]"));
                      const badWords = ["网站首页","加收藏","移动客户端","登录","股吧","东方财富","天天基金","下载APP","关于我们"];
                      for (const a of links) {
                        const txt = (a.innerText || "").trim();
                        const href = (a.getAttribute("href") || "").trim();
                        if (!txt) continue;
                        if (txt.length < 8 || txt.length > 80) continue;
                        if (badWords.some(w => txt.includes(w))) continue;
                        if (!(href.includes("finance.eastmoney.com/a/") || href.includes("/news/") || href.includes("/zx/"))) continue;
                        if (out.includes(txt)) continue;
                        out.push(txt);
                        if (out.length >= limit) break;
                      }
                      return out;
                    }
                    """,
                    NEWS_LIMIT,
                )
                result["新闻标题"] = titles if isinstance(titles, list) else []

                await context.close()
                await browser.close()
        except Exception as exc:
            result["抓取状态"] = "partial"
            result["抓取备注"] = sanitize_text(f"浏览器抓取异常: {exc}", max_len=280)
        return result


def fallback_enrich_if_needed(item: Dict[str, Any]) -> Dict[str, Any]:
    code_6 = item["代码6位"]

    # 财务基本面兜底（东财 push2）——并用于校正无效文本
    browser_fund = get_fundamental_via_browser(code_6)
    if clean_name_text(item.get("名称")) == "N/A":
        item["名称"] = clean_name_text(browser_fund.get("名称"))
    item["ROE"] = (
        item.get("ROE")
        if clean_numeric_like_text(item.get("ROE")) != "N/A"
        else clean_numeric_like_text(browser_fund.get("ROE"))
    )
    item["净利润增长率"] = (
        item.get("净利润增长率")
        if clean_numeric_like_text(item.get("净利润增长率")) != "N/A"
        else clean_numeric_like_text(browser_fund.get("净利润增长率"))
    )
    item["市盈率(动)"] = (
        item.get("市盈率(动)")
        if clean_numeric_like_text(item.get("市盈率(动)")) != "N/A"
        else clean_numeric_like_text(browser_fund.get("市盈率-动态"))
    )
    item["资产负债率"] = clean_numeric_like_text(item.get("资产负债率"))

    # 资金面兜底（AkShare）
    if clean_numeric_like_text(item.get("主力净流入占比")) == "N/A" or clean_numeric_like_text(item.get("超大单净流入")) == "N/A":
        fund_flow = get_stock_fund_flow(code_6)
        if clean_numeric_like_text(item.get("主力净流入占比")) == "N/A":
            item["主力净流入占比"] = clean_numeric_like_text(fund_flow.get("主力净流入占比"))
        else:
            item["主力净流入占比"] = clean_numeric_like_text(item.get("主力净流入占比"))
        if clean_numeric_like_text(item.get("超大单净流入")) == "N/A":
            item["超大单净流入"] = clean_numeric_like_text(fund_flow.get("今日超大单净流入"))
        else:
            item["超大单净流入"] = clean_numeric_like_text(item.get("超大单净流入"))
    else:
        item["主力净流入占比"] = clean_numeric_like_text(item.get("主力净流入占比"))
        item["超大单净流入"] = clean_numeric_like_text(item.get("超大单净流入"))

    # 消息面兜底（AkShare）
    if not item.get("新闻标题"):
        item["新闻标题"] = get_stock_news(code_6, limit=NEWS_LIMIT)
    # 过滤掉无效新闻文案
    cleaned_news = []
    for n in item.get("新闻标题", []):
        ns = sanitize_text(n, max_len=120)
        if not ns:
            continue
        if is_noise_text(ns):
            continue
        cleaned_news.append(ns)
        if len(cleaned_news) >= NEWS_LIMIT:
            break
    item["新闻标题"] = cleaned_news
    item["名称"] = clean_name_text(item.get("名称"))

    return item


async def enrich_candidates_async(candidates: pd.DataFrame, max_candidates: int) -> List[Dict[str, Any]]:
    if candidates.empty:
        return []
    top_df = candidates.head(max_candidates).copy()
    sem = asyncio.Semaphore(BROWSER_CONCURRENCY)
    tasks = [fetch_eastmoney_enrichment(code_6, sem) for code_6 in top_df["代码6位"].tolist()]
    results = await asyncio.gather(*tasks)
    return [fallback_enrich_if_needed(item) for item in results]


def run_async_safely(coro):
    """
    兼容两类运行环境：
    - 普通脚本：直接 asyncio.run
    - 已有运行中事件循环（如 MCP server）：在新线程中执行 asyncio.run
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: Dict[str, Any] = {}

    def _runner():
        try:
            box["result"] = asyncio.run(coro)
        except Exception as exc:
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()

    if "error" in box:
        raise box["error"]
    return box.get("result")


def merge_and_score(candidates: pd.DataFrame, enrichments: List[Dict[str, Any]]) -> pd.DataFrame:
    if candidates.empty:
        return pd.DataFrame()

    enrich_df = pd.DataFrame(enrichments)
    merged = candidates.merge(enrich_df, on="代码6位", how="left")

    merged["fund_score"] = merged.apply(
        lambda r: score_fundamental(
            to_float(r.get("ROE")),
            to_float(r.get("净利润增长率")),
            to_float(r.get("资产负债率")),
            to_float(r.get("市盈率(动)")),
        ),
        axis=1,
    )
    merged["capital_score"] = merged.apply(
        lambda r: score_capital(
            to_float(r.get("主力净流入占比")),
            to_float(r.get("超大单净流入")),
        ),
        axis=1,
    )
    merged["news_score"] = merged.apply(
        lambda r: score_news(r.get("新闻标题") if isinstance(r.get("新闻标题"), list) else []),
        axis=1,
    )

    merged["最终分"] = (
        merged["技术分"] * W_TECH
        + merged["fund_score"] * W_FUNDAMENTAL
        + merged["capital_score"] * W_CAPITAL
        + merged["news_score"] * W_NEWS
    ).round(1)

    merged["建议动作"] = merged["最终分"].apply(build_action)
    merged["消息摘要"] = merged["新闻标题"].apply(
        lambda xs: " | ".join(xs) if isinstance(xs, list) and xs else "N/A"
    )
    merged["风险提示"] = merged.apply(
        lambda r: "注意财务/资金项缺失，建议人工复核"
        if (to_float(r.get("ROE")) is None or to_float(r.get("主力净流入占比")) is None)
        else "无明显硬伤，仍需结合仓位与止损纪律",
        axis=1,
    )

    # 为兼容全候选输出，对未进入 step2 的股票给默认值
    for col, val in [
        ("名称", "N/A"),
        ("抓取状态", "not_enriched"),
        ("抓取备注", "未进入浏览器增强TopN"),
        ("fund_score", 30.0),
        ("capital_score", 30.0),
        ("news_score", 30.0),
        ("最终分", None),
        ("建议动作", "继续观察"),
        ("消息摘要", "N/A"),
        ("风险提示", "东财增强未执行"),
    ]:
        if col in merged.columns:
            if val is None:
                continue
            merged[col] = merged[col].fillna(val)

    if merged["最终分"].isna().any():
        merged["最终分"] = (
            merged["技术分"] * W_TECH
            + merged["fund_score"] * W_FUNDAMENTAL
            + merged["capital_score"] * W_CAPITAL
            + merged["news_score"] * W_NEWS
        ).round(1)

    return merged.sort_values(by=["最终分", "技术分", "放量倍数"], ascending=False)


def build_browser_focus_and_prompt(technical_df: pd.DataFrame, max_enrich: int) -> tuple[pd.DataFrame, str]:
    focus_df = technical_df.head(max_enrich).copy()
    if focus_df.empty:
        return focus_df, "无重点标的。"

    def _build_urls(code_6: str) -> tuple[str, str, str]:
        prefix = "sh" if str(code_6).startswith(("60", "68")) else "sz"
        quote_url = f"https://quote.eastmoney.com/{prefix}{code_6}.html"
        f10_url = (
            "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index"
            f"?type=web&code={prefix.upper()}{code_6}"
        )
        news_url = f"https://quote.eastmoney.com/zx/unify_{prefix}{code_6}_1.html"
        return quote_url, f10_url, news_url

    focus_df["代码6位"] = focus_df["代码6位"].astype(str).str.zfill(6)
    urls = focus_df["代码6位"].apply(_build_urls)
    focus_df["东财行情页"] = urls.apply(lambda x: x[0])
    focus_df["东财F10页"] = urls.apply(lambda x: x[1])
    focus_df["东财资讯页"] = urls.apply(lambda x: x[2])
    focus_df["浏览器分析状态"] = "待分析"
    focus_df["浏览器分析结论"] = "待补充"

    code_list = focus_df["代码6位"].tolist()
    prompt = f"""
=== Agent 任务指令：筑底+放量突破重点标的二次分析 ===
第一步（技术面）已完成，重点标的：{code_list}

请按顺序对每只股票执行浏览器分析：

1) 技术确认（行情页）
   - 查看分时与日K，确认突破是否有效（是否回踩不破、是否持续放量）。
   - 识别关键支撑位/压力位，评估次日追踪性。

2) 基本面与财务面（F10页）
   - 关注 ROE、净利润同比增长率、资产负债率、经营现金流相关指标。
   - 若财务指标明显恶化，标记为“技术可疑”。

3) 资金面与消息面（资讯+行情）
   - 观察主力资金净流入方向、强度变化。
   - 检查近3日新闻公告中是否存在减持、处罚、业绩暴雷等风险项。

4) 输出每只标的结论
   - 建议动作：[优先跟踪 / 观察等待 / 暂不参与]
   - 给出触发条件（买点/失效位/止损位）
"""
    return focus_df, prompt.strip()


def save_outputs(
    technical_df: pd.DataFrame,
    final_df: pd.DataFrame,
    focus_df: pd.DataFrame,
    browser_prompt: str,
    trade_date: str,
) -> Dict[str, Path]:
    project_root = os.getenv("PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    output_dir = Path(project_root) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    technical_path = output_dir / f"technical_candidates_{trade_date}.csv"
    final_path = output_dir / f"stock_selection_bottom_breakout_eastmoney_{trade_date}.csv"
    focus_path = output_dir / f"bottom_breakout_focus_targets_{trade_date}.csv"
    task_path = output_dir / f"bottom_breakout_browser_tasks_{trade_date}.md"

    if not technical_df.empty:
        technical_df.to_csv(str(technical_path), index=False, encoding="utf-8-sig")
    if not final_df.empty:
        final_df.to_csv(str(final_path), index=False, encoding="utf-8-sig")
    if not focus_df.empty:
        focus_df.to_csv(str(focus_path), index=False, encoding="utf-8-sig")
    task_path.write_text(browser_prompt, encoding="utf-8")

    return {
        "technical": technical_path,
        "final": final_path,
        "focus": focus_path,
        "tasks": task_path,
    }


def main(target_date: Optional[str] = None, max_enrich: int = 20):
    engine = get_db_engine()
    trade_date = target_date or get_latest_trade_date(engine)
    print(f"🚀 两阶段策略启动，基准日期：{trade_date}")
    print("Step1/2: 正在执行 MySQL 技术面筛选（筑底+放量突破）...")

    df_all = load_daily_data(engine, trade_date)
    print(f"✓ 已加载日线记录: {len(df_all)}")

    technical_df = select_technical_candidates(df_all)
    if technical_df.empty:
        print("❌ 技术面未筛到候选股票")
        return

    print(f"✓ 技术候选数量: {len(technical_df)}")
    print(f"Step2/2: 正在生成东财浏览器分析任务（Top {max_enrich}）...")
    focus_df, browser_prompt = build_browser_focus_and_prompt(technical_df, max_enrich)

    # “最终结果文件”保留纯技术筛选结果，二次分析结果由浏览器任务单独承载
    final_df = technical_df.copy()
    final_df["二次分析状态"] = "待浏览器分析"
    paths = save_outputs(technical_df, final_df, focus_df, browser_prompt, trade_date)

    print("\n" + "=" * 60)
    print(f"✅ 两阶段选股完成，技术输出: {len(final_df)} 只")
    print(f"📄 技术中间文件: {paths['technical']}")
    print(f"📄 最终结果文件: {paths['final']}")
    print(f"📄 重点标的清单: {paths['focus']}")
    print(f"🧭 浏览器任务文档: {paths['tasks']}")
    print("=" * 60)
    print(focus_df.head(20))


if __name__ == "__main__":
    arg_date = sys.argv[1] if len(sys.argv) > 1 else None
    arg_max = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    main(arg_date, arg_max)
