#!/usr/bin/env python3
"""
快速测试当前AI操作指令
"""

from tushare_mcp import deepseek_intraday_t_signal

if __name__ == "__main__":
    # 配置参数
    codes = {
        "159218": {"cost": 1.55, "ratio": 0.5},  # 持仓成本1.55，仓位50%
        "159840": {"cost": None, "ratio": 0.0},  # 空仓
    }

    print("\n" + "="*60)
    print("📊 AI 操作指令实时查询")
    print("="*60 + "\n")

    for code, position in codes.items():
        try:
            report = deepseek_intraday_t_signal(
                code=code,
                position_cost=position["cost"],
                position_ratio=position["ratio"],
            )
            print(report)
            print()
        except Exception as e:
            print(f"❌ {code} 查询失败: {e}\n")

    print("="*60)

