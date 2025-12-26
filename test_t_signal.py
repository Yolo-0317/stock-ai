"""
测试盘中做T信号

使用前确保设置环境变量：
- DEEPSEEK_API_KEY: DeepSeek API 密钥
- MYSQL_URL: MySQL 连接串

示例：
export DEEPSEEK_API_KEY="sk-xxx"
export MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data"
python test_t_signal.py
"""

from tushare_mcp import deepseek_intraday_t_signal, intraday_trade_signal

# 测试代码
CODE = "159218"

# 模拟持仓信息（可选）
POSITION_COST = 1.55  # 持仓成本价
POSITION_RATIO = 0.5  # 当前仓位 50%

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print(f"测试 {CODE} 的盘中做T信号")
    print("=" * 80)

    # 1. 规则策略信号（MA 均线）
    print("\n【规则策略 - MA5/MA20】")
    print("-" * 80)
    rule_result = intraday_trade_signal(code=CODE)
    print(rule_result)

    # 2. DeepSeek AI 做T信号
    print("\n【DeepSeek AI - 盘中做T分析】")
    print("-" * 80)
    try:
        # 不传持仓信息
        print("## 场景 1：空仓观望，寻找入场机会")
        ai_result = deepseek_intraday_t_signal(code=CODE)
        print(ai_result)

        print("\n" + "=" * 80)
        print("## 场景 2：已有持仓，考虑做T降本")
        # 传入持仓信息
        ai_result_with_position = deepseek_intraday_t_signal(
            code=CODE, position_cost=POSITION_COST, position_ratio=POSITION_RATIO
        )
        print(ai_result_with_position)

    except Exception as e:
        print(f"DeepSeek 分析失败: {e}")
        import traceback

        traceback.print_exc()
        print("提示：请确保设置了 DEEPSEEK_API_KEY 环境变量")

    print("\n")
