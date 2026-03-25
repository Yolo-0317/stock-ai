from __future__ import annotations

import re
import time
from datetime import datetime
from datetime import time as dtime
from datetime import timedelta, timezone
from pathlib import Path
import sys
import logging

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入必要的工具
# 注意：直接导入函数，跳过 FastMCP 装饰器逻辑
from tushare_mcp import deepseek_intraday_t_signal
from feishu_notice import send_to_lark
from logger_config import setup_logging

# 初始化日志
logger = setup_logging(name="monitor_v2", log_dir="logs")

def _beijing_now() -> datetime:
    """获取北京时间。"""
    now_utc = datetime.now(timezone.utc)
    bj = now_utc + timedelta(hours=8)
    return bj.replace(tzinfo=None)

def _is_trading_time_bj(dt: datetime) -> bool:
    """判断是否处于交易时段（北京时间）。"""
    t = dt.time()
    # A 股交易时段：9:30-11:30, 13:00-15:00
    am = dtime(9, 30) <= t <= dtime(11, 30)
    pm = dtime(13, 0) <= t <= dtime(15, 0)
    return am or pm

def _extract_field(report: str, field_name: str) -> str | None:
    """从 AI 报告中提取字段。"""
    # 尝试匹配 markdown 格式：**field_name**: value
    pattern1 = rf"\*\*{re.escape(field_name)}\*\*:\s*([^\n]+)"
    m = re.search(pattern1, report)
    if m:
        return m.group(1).strip()

    # 尝试匹配纯文本格式（可能带图标）：执行价格: value 或 📍 执行价格: value
    pattern2 = rf"(?:^|[\s\-📍💰📊🛡️🎯💡])\s*{re.escape(field_name)}:\s*([^\n]+)"
    m = re.search(pattern2, report, re.MULTILINE)
    if m:
        return m.group(1).strip()

    return None

def run_analysis_for_stocks(codes: list[str], position_info: dict):
    """为指定股票运行实时分析并发送通知。"""
    now_bj = _beijing_now()
    timestamp = now_bj.strftime("%H:%M:%S")
    
    logger.info(f"\n{'='*60}\n[开始轮询] {now_bj.strftime('%Y-%m-%d %H:%M:%S')}\n{'='*60}")
    
    for code in codes:
        try:
            logger.info(f"正在分析 {code}...")
            
            # 获取持仓信息
            info = position_info.get(code, {})
            cost = info.get("cost")
            ratio = info.get("ratio", 0.1) # 默认 10% 仓位
            
            # 调用 AI 实时分析
            report = deepseek_intraday_t_signal(
                code=code,
                position_cost=cost,
                position_ratio=ratio
            )
            
            # 提取关键信号
            signal = _extract_field(report, "操作指令") or "暂不操作"
            reason = _extract_field(report, "核心原因") or "无明确原因"
            
            # 只有在有明确操作建议时才推送飞书（立即买入/立即卖出/加仓/减仓）
            # 如果是“暂不操作”，则只记录日志
            is_actionable = any(kw in signal for kw in ["买入", "卖出", "加仓", "减仓"]) and "暂不操作" not in signal
            
            # 格式化通知消息
            exec_price = _extract_field(report, "执行价格") or "N/A"
            target_price = _extract_field(report, "目标价格") or "N/A"
            stop_loss = _extract_field(report, "止损价格") or "N/A"
            
            emoji = "🟢" if "买" in signal or "加" in signal else "🔴" if "卖" in signal or "减" in signal else "⚪"
            
            msg = (
                f"{emoji} 【{signal}】 | {code}\n"
                f"⏰ 时间: {timestamp}\n"
                f"💰 执行价: {exec_price}\n"
                f"🎯 目标价: {target_price}\n"
                f"🛡️ 止损价: {stop_loss}\n"
                f"💡 原因: {reason}"
            )
            
            logger.info(f"[{code}] 信号: {signal} | 原因: {reason}")
            
            if is_actionable:
                logger.info(f"发现可执行信号，发送飞书通知...")
                send_to_lark(msg)
            else:
                # 即使不推送飞书，也把完整报告存入日志供查阅
                logger.debug(f"完整报告:\n{report}")
                
        except Exception as e:
            error_msg = f"分析 {code} 时出错: {str(e)}"
            logger.error(error_msg)
            # send_to_lark(error_msg, is_error=True)

def main():
    # 目标股票列表
    target_stocks = ["000990", "600098", "600583", "600873"]
    
    # 持仓信息（根据 holdings.csv 手动或自动维护）
    position_info = {
        "000990": {"cost": 10.045, "ratio": 0.1},
        "600098": {"cost": 7.75, "ratio": 0.1},
        "600583": {"cost": 7.683, "ratio": 0.1},
        "600873": {"cost": None, "ratio": 0.0},
    }
    
    # 轮询间隔：盘中建议 5-10 分钟跑一次
    # 考虑到 DeepSeek API 消耗和实时性平衡，设定为 10 分钟 (600秒)
    interval = 600 
    
    logger.info(f"启动监控脚本 v2.0，监控列表: {target_stocks}，间隔: {interval}s")
    
    while True:
        now_bj = _beijing_now()
        
        # 仅在交易时段运行
        if _is_trading_time_bj(now_bj):
            run_analysis_for_stocks(target_stocks, position_info)
            logger.info(f"等待 {interval} 秒进行下一次轮询...")
            time.sleep(interval)
        else:
            # 非交易时段，每分钟检查一次是否进入交易时段
            # 或者如果是收盘后，可以考虑退出或长休
            t = now_bj.time()
            if t > dtime(15, 5):
                logger.info("已收盘，脚本退出。")
                break
            
            time.sleep(60)

if __name__ == "__main__":
    main()
