from __future__ import annotations

import re
import time
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

# 统一的代码名称映射
from code_names import code_label, CODES

# 导入日志配置
from logger_config import setup_monitor_logging

# 初始化日志
logger = setup_monitor_logging()

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"✓ 已加载环境变量：{env_path}")
except ImportError:
    logger.warning("⚠ python-dotenv 未安装，跳过 .env 加载（请使用 uv sync 安装依赖）")

from tushare_mcp import (
    deepseek_intraday_t_signal,
    deepseek_trade_signal,
    intraday_trade_signal,
)

# 导入飞书通知
from feishu_notice import send_to_lark



def _beijing_now() -> datetime:
    """获取北京时间（不带时区信息，便于打印和比较）。"""
    now_utc = datetime.now(timezone.utc)
    bj = now_utc + timedelta(hours=8)
    return bj.replace(tzinfo=None)


def _is_trading_time_bj(dt: datetime) -> bool:
    """判断是否处于交易时段（北京时间）。"""
    t = dt.time()
    am = dtime(9, 30) <= t <= dtime(11, 30)
    pm = dtime(13, 0) <= t <= dtime(15, 0)
    return am or pm


def _extract_field(report: str, field_name: str) -> str | None:
    """
    从报告里提取字段。
    支持两种格式：
    1. Markdown: '- **信号**: 买入'
    2. 纯文本: '📍 执行价格: 1.625'
    """
    # 尝试匹配 markdown 格式：**field_name**: value
    pattern1 = rf"\*\*{re.escape(field_name)}\*\*:\s*([^\n]+)"
    m = re.search(pattern1, report)
    if m:
        value = m.group(1).strip()
        if value and not value.startswith("- **"):
            return value

    # 尝试匹配纯文本格式（可能带图标）：执行价格: value 或 📍 执行价格: value
    pattern2 = rf"(?:^|[\s\-📍💰📊🛡️🎯💡])\s*{re.escape(field_name)}:\s*([^\n]+)"
    m = re.search(pattern2, report, re.MULTILINE)
    if m:
        value = m.group(1).strip()
        if value:
            return value

    return None


def _is_actionable_signal(signal: str, use_t_signal: bool) -> bool:
    """
    是否属于需要推送飞书的“可执行”信号。

    需求：像“暂不操作/观望”这类信号只打印到日志，不推送飞书，避免打扰。
    """
    s = (signal or "").strip()
    if not s:
        return False
    if use_t_signal:
        # 做T模式只推送立即买/卖
        return s in ("立即买入", "立即卖出")
    # 标准模式只推送买/卖
    return s in ("买入", "卖出")


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(s))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def _log_block_marker(logger, when_str: str, code: str, label: str) -> None:
    """
    在日志里打印清晰的分隔标识，方便肉眼扫描 monitor_*.log。
    """
    bar = "=" * 72
    logger.info(f"\n{bar}\n[MONITOR] {when_str} | {code} | {label}\n{bar}")


def main() -> int:
    # =========================
    # 配置区：按需修改即可（不通过命令行传参）
    # =========================
    # 从统一位置导入codes（若需要自定义，可在此处覆盖）
    codes = CODES
    interval = 60.0  # 轮询间隔（秒）
    print_bias = False  # True：也打印"偏买入/偏卖出"
    all_day = False  # True：全天都跑；False：只在交易时段判断
    enable_feishu = True  # True：启用飞书通知；False：仅控制台打印
    enable_deepseek = True  # True：启用 DeepSeek AI 辅助分析（需要 DEEPSEEK_API_KEY）

    # 做T专用配置
    use_t_signal = True  # True：使用做T信号（专注盘中波动）；False：使用标准买卖信号
    # DeepSeek 调用策略：
    # - "always": 每次轮询都调用 AI（最耗配额）
    # - "on_rule_change": 只有当“规则信号”变化时才调用 AI（显著降频）
    # - "on_rule_actionable_change": 只有当“规则信号”变化，且变成买/卖（或偏买/偏卖）时才调用 AI（最省）
    # 说明：不调用 AI 时无法得知 AI 信号是否变化，因此这里用“规则信号变化”作为触发器。
    deepseek_call_policy = "on_rule_change"
    # 即使信号没变，也定期刷新一次 AI（秒）
    # 0/None 表示关闭；例如 300 表示每 5 分钟强制跑一次 AI
    ai_refresh_every_seconds = 300.0
    # 定期刷新时是否在日志里打印一行“刷新摘要”（不会推飞书）
    ai_refresh_log_summary = True
    # 是否把“持仓成本/仓位”信息传给 AI
    # - False：不传持仓，仅让 AI 基于行情给出买/卖/观望信号（更通用）
    # - True：传持仓，AI 能给出更贴合的减仓/清仓/加仓幅度与盈亏相关建议
    pass_position_to_ai = False
    # 卖出过滤器（减少“随便卖出/卖飞”）
    # - 当规则信号仍偏多（买入/偏买入）时，AI 的“立即卖出”默认需要更强确认才允许执行
    enable_sell_guard = True
    sell_guard_open_minutes = 5  # 开盘后前 N 分钟更容易被噪声误导，卖出更保守
    sell_guard_support_buffer = 0.001  # 未跌破支撑位前，不允许逆势卖出（0.1% 缓冲）
    # True：打印所有信号（包括"暂不操作"）；False：只打印买入/卖出
    print_all_signals = True
    log_ai_detail = True  # True：在日志文件中记录AI完整分析；False：只记录简洁信号
    position_costs = {  # 各品种的持仓成本（可选，用于计算盈亏）
        "159218": 1.197,
        "159840": 0.852,
        "512400": 1.907,
    }
    position_ratios = {  # 各品种的当前仓位比例 0-1（可选）
        "159218": 4.03/100,  # 50% 仓位
        "159840": 12.44/100,  # 空仓
        "512400": 22.89/100,
    }

    if not codes:
        logger.error("未提供 codes")
        return 2

    last_printed: dict[str, str] = {}  # code -> last_signal_printed（以 AI/最终信号为准）
    last_rule_signal: dict[str, str] = {}  # code -> last_rule_signal（用于触发 DeepSeek 调用）
    last_ai_ts: dict[str, float] = {}  # code -> last_ai_call_unix_ts（用于定期刷新 AI）

    logger.info(f"开始盯盘：codes={codes} interval={interval}s")
    if use_t_signal:
        logger.info("模式：盘中做T信号（专注日内波动）")
    else:
        logger.info("模式：标准买卖信号（趋势跟踪）")
    if print_all_signals:
        logger.info('打印模式：显示所有信号（包括"暂不操作"）')
    else:
        logger.info("打印模式：仅显示买入/卖出信号")
    if enable_feishu:
        logger.info("飞书通知已启用")
    if enable_deepseek:
        logger.info("DeepSeek AI 辅助分析已启用")

    while True:
        start = time.time()
        now_bj = _beijing_now()

        if all_day or _is_trading_time_bj(now_bj):
            for code in codes:
                try:
                    now_ts = time.time()
                    # 打印多行空格
                    logger.info("\n" * 10)

                    # 先跑“规则信号”（无 AI / 无外部调用）作为触发器与兜底输出
                    rule_report = intraday_trade_signal(code=code)
                    rule_signal = _extract_field(rule_report, "信号") or ""
                    rule_reason = _extract_field(rule_report, "依据") or ""

                    prev_rule = last_rule_signal.get(code)
                    last_rule_signal[code] = rule_signal

                    should_call_ai = False
                    is_ai_refresh = False
                    if use_t_signal and enable_deepseek:
                        # 定期刷新：即使信号没变也会调用 AI（用于持续跟踪盘中变化）
                        refresh_due = False
                        if ai_refresh_every_seconds and ai_refresh_every_seconds > 0:
                            last_ts = float(last_ai_ts.get(code, 0.0) or 0.0)
                            refresh_due = last_ts == 0.0 or (now_ts - last_ts) >= float(
                                ai_refresh_every_seconds
                            )

                        # 策略触发：根据规则信号变化触发 AI
                        policy_due = False
                        if deepseek_call_policy == "always":
                            policy_due = True
                        elif deepseek_call_policy == "on_rule_change":
                            policy_due = (prev_rule != rule_signal)
                        elif deepseek_call_policy == "on_rule_actionable_change":
                            if prev_rule != rule_signal:
                                actionable_rule = rule_signal in ("买入", "卖出") or (
                                    print_bias and rule_signal in ("偏买入", "偏卖出")
                                )
                                policy_due = actionable_rule
                        else:
                            policy_due = False

                        # 最终触发：定时刷新 OR 策略触发
                        should_call_ai = bool(refresh_due or policy_due)
                        # 仅当“信号没变但到点了”才算 refresh（用于日志标记）
                        is_ai_refresh = bool(refresh_due and not policy_due)

                    # 根据策略决定本轮使用 AI report 还是规则 report
                    if should_call_ai:
                        # 标记本次已触发 AI（用于下一次定时刷新）
                        last_ai_ts[code] = now_ts

                        if pass_position_to_ai:
                            report = deepseek_intraday_t_signal(
                                code=code,
                                position_cost=position_costs.get(code),
                                position_ratio=(position_ratios.get(code) or 0.0),
                            )
                        else:
                            report = deepseek_intraday_t_signal(code=code)
                        signal_field = "操作指令"
                        reason_field = "核心原因"
                    else:
                        report = rule_report
                        signal_field = "信号"
                        reason_field = "依据"

                    # 检查是否是错误信息
                    if (
                        "分析过程中出错" in report
                        or "未在 MySQL 中找到" in report
                        or "未查询到东财行情数据" in report
                    ):
                        error_msg = f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] {code} 获取信号失败: {report}"
                        logger.error(error_msg)
                        if enable_feishu:
                            send_to_lark(error_msg, is_error=True)
                        continue

                    signal = _extract_field(report, signal_field) or ""
                    reason = _extract_field(report, reason_field) or ""
                    rt_date = (
                        _extract_field(report, "盘中日期")
                        or _extract_field(report, "日期")
                        or "未知"
                    )

                    # 卖出过滤：规则偏多时，避免被早盘噪声/回撤吓出场
                    blocked_by_guard = False
                    if (
                        enable_sell_guard
                        and should_call_ai
                        and use_t_signal
                        and enable_deepseek
                        and signal == "立即卖出"
                        and rule_signal in ("买入", "偏买入")
                    ):
                        exec_price = _to_float(_extract_field(report, "执行价格"))
                        support = _to_float(_extract_field(report, "支撑位"))
                        minutes_since_open = (
                            (now_bj.hour * 60 + now_bj.minute) - (9 * 60 + 30)
                        )

                        allow_sell = False
                        if exec_price is not None and support is not None:
                            # 只有“跌破支撑”才允许逆势卖出（含缓冲）
                            if exec_price <= support * (1.0 - float(sell_guard_support_buffer)):
                                allow_sell = True
                            # 开盘前 N 分钟更保守：必须更明显跌破支撑
                            if minutes_since_open >= 0 and minutes_since_open < int(
                                sell_guard_open_minutes
                            ):
                                if exec_price <= support * (1.0 - float(sell_guard_support_buffer) * 2):
                                    allow_sell = True
                                else:
                                    allow_sell = False

                        if not allow_sell:
                            blocked_by_guard = True
                            signal = "暂不操作"
                            reason = (
                                f"卖出被过滤：规则信号={rule_signal} 仍偏多；"
                                f"需跌破支撑位后再考虑（支撑={support if support is not None else 'N/A'}）。"
                            )

                    # 判断是否需要打印
                    if print_all_signals:
                        # 打印所有信号（包括"暂不操作"）
                        should_print = True
                    elif use_t_signal:
                        # 新版AI指令：只打印"立即买入"和"立即卖出"
                        should_print = signal in ("立即买入", "立即卖出")
                    else:
                        # 标准信号：只打印买入/卖出
                        should_print = signal in ("买入", "卖出")
                        if print_bias and signal in ("偏买入", "偏卖出"):
                            should_print = True

                    # 只在"信号变化"时打印
                    if should_print and last_printed.get(code) != signal:
                        last_printed[code] = signal

                        _log_block_marker(
                            logger,
                            now_bj.strftime("%Y-%m-%d %H:%M:%S"),
                            code_label(code),
                            f"signal_change -> {signal}",
                        )

                        # 新版输出格式（简洁明确）
                        if use_t_signal and enable_deepseek and should_call_ai:
                            # 根据信号类型选择 emoji
                            if signal == "立即卖出":
                                action_emoji = "🔴 卖出"
                            elif signal == "立即买入":
                                action_emoji = "🟢 买入"
                            else:  # 暂不操作
                                action_emoji = "⚪ 观望"

                            exec_price = _extract_field(report, "执行价格") or "N/A"
                            size = _extract_field(report, "建议数量") or "N/A"
                            stop_loss = _extract_field(report, "止损价格") or "N/A"
                            target = _extract_field(report, "目标价格") or "N/A"

                            msg = (
                                f"\n{'='*50}\n"
                                f"⏰ {now_bj.strftime('%H:%M:%S')}  |  {code_label(code)}\n"
                                f"{'='*50}\n"
                                f"{action_emoji}  【{signal}】\n"
                                f"{'─'*50}\n"
                                f"💰 执行价格: {exec_price}\n"
                                f"📊 建议数量: {size}\n"
                                f"🛡️ 止损价格: {stop_loss}\n"
                                f"🎯 目标价格: {target}\n"
                                f"{'─'*50}\n"
                                f"💡 原因: {reason}\n"
                                f"{'='*50}\n"
                            )
                        else:
                            # 标准策略保持原格式
                            strategy_label = "规则策略"
                            msg = (
                                f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] "
                                f"{code_label(code)} {rt_date}\n【{strategy_label}】信号={signal}\n理由={reason}"
                            )

                        # 输出简洁信号到控制台
                        logger.info(msg)

                        # 如果启用了 AI 详细日志，将完整的 report（包含AI详细分析）记录到日志文件
                        if log_ai_detail and use_t_signal and enable_deepseek and should_call_ai:
                            # 清理格式：移除多余的缩进
                            import logging
                            import re

                            # 移除每行开头的多余空格（保留相对缩进）
                            lines = report.split("\n")
                            cleaned_lines = []
                            for line in lines:
                                # 移除行首的多余空格，但保留相对缩进结构
                                stripped = line.lstrip()
                                # 如果是以 "- **" 开头的，去掉 "- "
                                if stripped.startswith("- **"):
                                    stripped = stripped[2:]
                                cleaned_lines.append(stripped)

                            cleaned_report = "\n".join(cleaned_lines)

                            for handler in logger.handlers:
                                if isinstance(handler, logging.FileHandler):
                                    # 创建日志记录，记录格式化后的 report
                                    record = logging.LogRecord(
                                        name=logger.name,
                                        level=logging.INFO,
                                        pathname=__file__,
                                        lineno=0,
                                        msg=f"\n{cleaned_report}\n",  # 完整的 AI 分析报告（已格式化）
                                        args=(),
                                        exc_info=None,
                                    )
                                    handler.emit(record)
                    else:
                        # 信号没变但触发了“定期刷新 AI”：把结果写到日志里（不推飞书）
                        if (
                            is_ai_refresh
                            and use_t_signal
                            and enable_deepseek
                            and should_call_ai
                            and log_ai_detail
                        ):
                            import logging

                            cleaned_lines = [ln.lstrip() for ln in str(report).split("\n")]
                            cleaned_report = "\n".join(cleaned_lines).strip()

                            # 可选：打一个简短摘要，方便肉眼确认“确实每 5 分钟跑了一次 AI”
                            if ai_refresh_log_summary:
                                _log_block_marker(
                                    logger,
                                    now_bj.strftime("%Y-%m-%d %H:%M:%S"),
                                    code_label(code),
                                    "AI refresh (signal unchanged)",
                                )
                                logger.info(
                                    f"[AI refresh] {now_bj.strftime('%H:%M:%S')} {code_label(code)} "
                                    f"signal={signal or 'N/A'} reason={(reason or '').strip()[:60]}"
                                )

                            for handler in logger.handlers:
                                if isinstance(handler, logging.FileHandler):
                                    record = logging.LogRecord(
                                        name=logger.name,
                                        level=logging.INFO,
                                        pathname=__file__,
                                        lineno=0,
                                        msg=f"\n{cleaned_report}\n",
                                        args=(),
                                        exc_info=None,
                                    )
                                    handler.emit(record)

                    # 如果被卖出过滤器拦截，也把“原始 AI 报告”写入日志，便于复盘
                    if blocked_by_guard and log_ai_detail and should_call_ai:
                        import logging

                        _log_block_marker(
                            logger,
                            now_bj.strftime("%Y-%m-%d %H:%M:%S"),
                            code_label(code),
                            "FILTERED SELL (guarded)",
                        )

                        cleaned_lines = [ln.lstrip() for ln in str(report).split("\n")]
                        cleaned_report = "\n".join(cleaned_lines).strip()
                        for handler in logger.handlers:
                            if isinstance(handler, logging.FileHandler):
                                record = logging.LogRecord(
                                    name=logger.name,
                                    level=logging.INFO,
                                    pathname=__file__,
                                    lineno=0,
                                    msg=f"\n[FILTERED SELL] rule_signal={rule_signal}\n{cleaned_report}\n",
                                    args=(),
                                    exc_info=None,
                                )
                                handler.emit(record)

                        # AI 辅助分析（仅在非做T模式下，或做T模式但未启用 DeepSeek 时）
                        ai_msg = ""
                        if enable_deepseek and not use_t_signal:
                            try:
                                logger.info(f"  -> 正在调用 DeepSeek AI 辅助分析...")
                                ai_report = deepseek_trade_signal(code=code)
                                ai_signal = (
                                    _extract_field(ai_report, "AI 信号") or "未知"
                                )
                                ai_reason = _extract_field(ai_report, "核心理由") or ""
                                ai_stop_loss = (
                                    _extract_field(ai_report, "止损位") or "N/A"
                                )
                                ai_target = _extract_field(ai_report, "目标位") or "N/A"

                                ai_msg = (
                                    f"\n【DeepSeek AI】信号={ai_signal}\n"
                                    f"理由={ai_reason}\n"
                                    f"止损位={ai_stop_loss} | 目标位={ai_target}"
                                )
                                logger.info(f"AI建议: {ai_msg}")

                                # 信号一致性检查
                                if signal in ("买入", "卖出") and ai_signal == signal:
                                    consistency_msg = (
                                        f"\n✅ 规则策略与 AI 信号一致！置信度更高"
                                    )
                                    logger.info(consistency_msg)
                                    ai_msg += consistency_msg
                                elif signal in ("买入", "卖出") and ai_signal != signal:
                                    conflict_msg = (
                                        f"\n⚠️ 规则策略与 AI 信号不一致，建议谨慎决策"
                                    )
                                    logger.warning(conflict_msg)
                                    ai_msg += conflict_msg

                            except Exception as e:
                                ai_error = f"\n[DeepSeek AI 调用失败: {e}]"
                                logger.error(ai_error)
                                ai_msg = ai_error

                        # 发送飞书通知（包含 AI 分析，如果有）
                        if (
                            enable_feishu
                            and _is_actionable_signal(signal, use_t_signal)
                        ):
                            full_msg = msg + ai_msg if ai_msg else msg
                            send_to_lark(full_msg, is_error=False)

                except Exception as e:
                    error_msg = f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] {code} 获取信号失败: {e}"
                    logger.error(error_msg)
        else:
            # 非交易时段不打扰（你也可以删掉这行）
            pass

        cost = time.time() - start
        time.sleep(max(0.0, float(interval) - cost))


if __name__ == "__main__":
    raise SystemExit(main())
