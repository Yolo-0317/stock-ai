"""调试脚本：查看 intraday_trade_signal 的原始输出"""

from tushare_mcp import intraday_trade_signal

code = "159218"

print(f"正在获取 {code} 的信号...")
print("=" * 80)

try:
    report = intraday_trade_signal(code=code)
    print("原始返回内容：")
    print(report)
    print("=" * 80)
    print(f"返回类型: {type(report)}")
    print(f"返回长度: {len(report)}")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

