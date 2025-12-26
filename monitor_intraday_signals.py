from __future__ import annotations

import re
import time
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta, timezone
from pathlib import Path

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ 已加载环境变量：{env_path}")
except ImportError:
    print("⚠ python-dotenv 未安装，跳过 .env 加载（请使用 uv sync 安装依赖）")

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
    print("未找到 feishu_notice 模块，飞书通知功能将被禁用")


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
    从 intraday_trade_signal 的 markdown 报告里提取字段。
    例如 field_name='信号'，匹配 '- **信号**: 买入'
    """
    # 使用 [^\n]+ 只匹配当前行，不跨行
    pattern = rf"\*\*{re.escape(field_name)}\*\*:\s*([^\n]+)"
    m = re.search(pattern, report)
    if not m:
        return None
    value = m.group(1).strip()
    # 如果提取到的值为空或者以 "- **" 开头（说明匹配到下一行了），返回 None
    if not value or value.startswith("- **"):
        return None
    return value


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
    position_costs = {  # 各品种的持仓成本（可选，用于计算盈亏）
        "159218": 1.197,
        "159840": 0.869,
    }
    position_ratios = {  # 各品种的当前仓位比例 0-1（可选）
        "159218": 0.2374,  # 50% 仓位
        "159840": 0.1058,  # 空仓
    }

    if not codes:
        print("未提供 codes")
        return 2

    last_printed: dict[str, str] = {}  # code -> last_signal_printed

    print(f"开始盯盘：codes={codes} interval={interval}s")
    if use_t_signal:
        print("模式：盘中做T信号（专注日内波动）")
    else:
        print("模式：标准买卖信号（趋势跟踪）")
    if enable_feishu and FEISHU_ENABLED:
        print("飞书通知已启用")
    if enable_deepseek:
        print("DeepSeek AI 辅助分析已启用")

    while True:
        start = time.time()
        now_bj = _beijing_now()

        if all_day or _is_trading_time_bj(now_bj):
            for code in codes:
                try:
                    # 根据配置选择使用标准信号还是做T信号
                    if use_t_signal and enable_deepseek:
                        # 使用 DeepSeek 做T信号
                        report = deepseek_intraday_t_signal(
                            code=code,
                            position_cost=position_costs.get(code),
                            position_ratio=position_ratios.get(code, 0.0),
                        )
                        signal_field = "AI 操作建议"
                        reason_field = "核心理由"
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
                        print(error_msg)
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
                    if use_t_signal:
                        # 做T信号：打印所有操作建议（做T买入/做T卖出/加仓/减仓）
                        should_print = signal in ("做T买入", "做T卖出", "加仓", "减仓")
                    else:
                        # 标准信号：只打印买入/卖出
                        should_print = signal in ("买入", "卖出")
                        if print_bias and signal in ("偏买入", "偏卖出"):
                            should_print = True

                    should_print = True
                    # 只在"信号变化"时打印
                    if should_print and last_printed.get(code) != signal:
                        last_printed[code] = signal

                        # 根据信号类型生成不同的消息标签
                        if use_t_signal and enable_deepseek:
                            strategy_label = "AI 做T策略"
                        else:
                            strategy_label = "规则策略"

                        msg = (
                            f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] "
                            f"{code} {rt_date}\n【{strategy_label}】信号={signal}\n理由={reason}"
                        )

                        # 如果是做T信号，增加目标位和止损位信息
                        if use_t_signal and enable_deepseek:
                            target = _extract_field(report, "目标价位") or "N/A"
                            stop_loss = _extract_field(report, "止损价位") or "N/A"
                            size = _extract_field(report, "建议操作量") or "N/A"
                            msg += (
                                f"\n操作量={size}\n目标位={target} | 止损位={stop_loss}"
                            )

                        print(msg)

                        # AI 辅助分析（仅在非做T模式下，或做T模式但未启用 DeepSeek 时）
                        ai_msg = ""
                        if enable_deepseek and not use_t_signal:
                            try:
                                print(f"  -> 正在调用 DeepSeek AI 辅助分析...")
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
                                print(f"AI建议: {ai_msg}")

                                # 信号一致性检查
                                if signal in ("买入", "卖出") and ai_signal == signal:
                                    consistency_msg = (
                                        f"\n✅ 规则策略与 AI 信号一致！置信度更高"
                                    )
                                    print(consistency_msg)
                                    ai_msg += consistency_msg
                                elif signal in ("买入", "卖出") and ai_signal != signal:
                                    conflict_msg = (
                                        f"\n⚠️ 规则策略与 AI 信号不一致，建议谨慎决策"
                                    )
                                    print(conflict_msg)
                                    ai_msg += conflict_msg

                            except Exception as e:
                                ai_error = f"\n[DeepSeek AI 调用失败: {e}]"
                                print(ai_error)
                                ai_msg = ai_error

                        # 发送飞书通知（包含 AI 分析，如果有）
                        if enable_feishu and FEISHU_ENABLED:
                            full_msg = msg + ai_msg if ai_msg else msg
                            send_to_lark(full_msg, is_error=False)

                except Exception as e:
                    error_msg = f"[{now_bj.strftime('%Y-%m-%d %H:%M:%S')}] {code} 获取信号失败: {e}"
                    print(error_msg)

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
