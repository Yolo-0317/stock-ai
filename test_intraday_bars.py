#!/usr/bin/env python3
"""
测试分钟线数据是否被正确读取并传给 AI
"""

from tushare_mcp import deepseek_intraday_t_signal

print("="*60)
print("测试 AI 分析是否包含分钟线数据")
print("="*60)

# 测试 159218
code = "159218"
print(f"\n正在分析 {code}...\n")

try:
    report = deepseek_intraday_t_signal(
        code=code,
        position_cost=1.55,
        position_ratio=0.5,
    )
    
    # 检查报告中是否包含分钟线相关的内容
    if "分钟线" in report or "日内走势" in report:
        print("✓ AI 分析已包含分钟线数据")
    else:
        print("⚠️  AI 分析可能未充分利用分钟线数据")
    
    print("\n完整报告：")
    print(report)
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)

