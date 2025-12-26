from __future__ import annotations

import re
import time
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta, timezone
from pathlib import Path

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
try:
    from feishu_notice import send_to_lark

    FEISHU_ENABLED = True
except ImportError:
    FEISHU_ENABLED = False
    logger.warning("未找到 feishu_notice 模块，飞书通知功能将被禁用")


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


def main() -> int:
    # =========================
    # 配置区：按需修改即可（不通过命令行传参）
    # =========================
    codes = ["159218", "159840"]  # 关注标的
    interval = 60.0  # 轮询间隔（秒）
    print_bias = False  # True：也打印"偏买入/偏卖出"
    all_day = True  # True：全天都跑；False：只在交易时段判断
    enable_feishu = True  # True：启用飞书通知；False：仅控制台打印
    enable_deepseek = True  # True：启用 DeepSeek AI 辅助分析（需要 DEEPSEEK_API_KEY）

    # 做T专用配置
    use_t_signal = True  # True：使用做T信号（专注盘中波动）；False：使用标准买卖信号
    # True：打印所有信号（包括"暂不操作"）；False：只打印买入/卖出
    print_all_signals = True
    log_ai_detail = True  # True：在日志文件中记录AI完整分析；False：只记录简洁信号
    position_costs = {  # 各品种的持仓成本（可选，用于计算盈亏）
        "159218": 1.197,
        "159840": 0.869,
    }
    position_ratios = {  # 各品种的当前仓位比例 0-1（可选）
        "159218": 0.2374,  # 50% 仓位
        "159840": 0.1058,  # 空仓
    }

    if not codes:
        logger.error("未提供 codes")
        return 2

    last_printed: dict[str, str] = {}  # code -> last_signal_printed

    logger.info(f"开始盯盘：codes={codes} interval={interval}s")
    if use_t_signal:
        logger.info("模式：盘中做T信号（专注日内波动）")
    else:
        logger.info("模式：标准买卖信号（趋势跟踪）")
    if print_all_signals:
        logger.info('打印模式：显示所有信号（包括"暂不操作"）')
    else:
        logger.info("打印模式：仅显示买入/卖出信号")
    if enable_feishu and FEISHU_ENABLED:
        logger.info("飞书通知已启用")
    if enable_deepseek:
        logger.info("DeepSeek AI 辅助分析已启用")

    while True:
        start = time.time()
        now_bj = _beijing_now()

        if all_day or _is_trading_time_bj(now_bj):
            for code in codes:
                try:
                    # 根据配置选择使用标准信号还是做T信号
                    if use_t_signal and enable_deepseek:
                        # 使用 DeepSeek 做T信号（新版简化指令）
                        report = deepseek_intraday_t_signal(
                            code=code,
                            position_cost=position_costs.get(code),
                            position_ratio=position_ratios.get(code, 0.0),
                        )
                        signal_field = "操作指令"
                        reason_field = "核心原因"
                    else:
                        # 使用标准规则策略信号
                        report = intraday_trade_signal(code=code)
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
                        if enable_feishu and FEISHU_ENABLED:
                            send_to_lark(error_msg, is_error=True)
                        continue

                    signal = _extract_field(report, signal_field) or ""
                    reason = _extract_field(report, reason_field) or ""
                    rt_date = (
                        _extract_field(report, "盘中日期")
                        or _extract_field(report, "日期")
                        or "未知"
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

                        # 新版输出格式（简洁明确）
                        if use_t_signal and enable_deepseek:
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
                                f"⏰ {now_bj.strftime('%H:%M:%S')}  |  {code}\n"
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
                                f"{code} {rt_date}\n【{strategy_label}】信号={signal}\n理由={reason}"
                            )

                        # 输出简洁信号到控制台
                        logger.info(msg)

                        # 如果启用了 AI 详细日志，将完整的 report（包含AI详细分析）记录到日志文件
                        if log_ai_detail and use_t_signal and enable_deepseek:
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
                        if enable_feishu and FEISHU_ENABLED:
                            full_msg = msg + ai_msg if ai_msg else msg
                            send_to_lark(full_msg, is_error=False)

                except Exception as e:
                    error_msg = f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] {code} 获取信号失败: {e}"
                    logger.error(error_msg)

                    # 错误也发飞书（可选）
                    if enable_feishu and FEISHU_ENABLED:
                        send_to_lark(error_msg, is_error=True)
        else:
            # 非交易时段不打扰（你也可以删掉这行）
            pass

        cost = time.time() - start
        time.sleep(max(0.0, float(interval) - cost))


if __name__ == "__main__":
    raise SystemExit(main())
