"""
测试 DeepSeek AI 交易信号

使用前确保设置环境变量：
- DEEPSEEK_API_KEY: DeepSeek API 密钥
- MYSQL_URL: MySQL 连接串

示例：
export DEEPSEEK_API_KEY="sk-xxx"
export MYSQL_URL="mysql+pymysql://user:pass@localhost:3306/stock_data"
python test_deepseek_signal.py
"""

from tushare_mcp import deepseek_trade_signal, intraday_trade_signal

# 测试代码
CODES = ["159218", "159840"]

if __name__ == "__main__":
    for code in CODES:
        print("\n" + "=" * 80)
        print(f"测试 {code} 的交易信号")
        print("=" * 80)
        
        # 1. 规则策略信号（MA 均线）
        print("\n【规则策略 - MA5/MA20】")
        print("-" * 80)
        rule_result = intraday_trade_signal(code=code)
        print(rule_result)
        
        # 2. DeepSeek AI 信号
        print("\n【DeepSeek AI 分析】")
        print("-" * 80)
        try:
            ai_result = deepseek_trade_signal(code=code)
            print(ai_result)
        except Exception as e:
            print(f"DeepSeek 分析失败: {e}")
            print("提示：请确保设置了 DEEPSEEK_API_KEY 环境变量")
        
        print("\n")

