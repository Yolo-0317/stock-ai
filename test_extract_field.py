"""测试字段提取逻辑"""

import re


def _extract_field(report: str, field_name: str) -> str | None:
    """
    从 markdown 报告里提取字段。
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


# 测试用例 1：正常情况
test_report_1 = """
### DeepSeek AI 盘中做T信号: 159840
- **盘中日期**: 2025-12-26
- **AI 操作建议**: 做T卖出
- **核心理由**: 当前价位于高位，适合高抛
- **建议操作量**: 标准仓位20-30%
- **目标价位**: 0.855
- **止损价位**: 0.875
"""

print("测试用例 1：正常情况")
print(f"操作建议: {_extract_field(test_report_1, 'AI 操作建议')}")
print(f"核心理由: {_extract_field(test_report_1, '核心理由')}")
print(f"建议操作量: {_extract_field(test_report_1, '建议操作量')}")
print(f"目标价位: {_extract_field(test_report_1, '目标价位')}")
print()

# 测试用例 2：核心理由为空
test_report_2 = """
### DeepSeek AI 盘中做T信号: 159840
- **盘中日期**: 2025-12-26
- **AI 操作建议**: 做T卖出
- **核心理由**: 
- **建议操作量**: 标准仓位20-30%
- **目标价位**: 0.855
"""

print("测试用例 2：核心理由为空")
print(f"操作建议: {_extract_field(test_report_2, 'AI 操作建议')}")
print(f"核心理由: {_extract_field(test_report_2, '核心理由')}")  # 应返回 None
print(f"建议操作量: {_extract_field(test_report_2, '建议操作量')}")
print()

# 测试用例 3：核心理由在下一行
test_report_3 = """
### DeepSeek AI 盘中做T信号: 159840
- **AI 操作建议**: 做T卖出
- **核心理由**: 
  1. 当前价位于高位
  2. 日内振幅较大
- **建议操作量**: 标准仓位20-30%
"""

print("测试用例 3：核心理由在下一行（换行）")
print(f"操作建议: {_extract_field(test_report_3, 'AI 操作建议')}")
print(
    f"核心理由: {_extract_field(test_report_3, '核心理由')}"
)  # 应返回 None（因为理由在下一行）
print(f"建议操作量: {_extract_field(test_report_3, '建议操作量')}")
