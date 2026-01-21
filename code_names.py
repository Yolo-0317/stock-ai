"""
统一管理证券代码 -> 名称的映射和关注列表。

用法：
  from code_names import code_label, CODES
  print(code_label("159218"))  # 159218（卫星产业ETF）
  
  # 在脚本中使用
  from code_names import CODES
"""

from __future__ import annotations


# 在这里维护你的关注标的名称（手工最稳定、无网络依赖）
CODE_NAMES: dict[str, str] = {
    "159218": "卫星产业ETF",
    "159840": "锂电池ETF",
    "512400": "有色ETF",
    "159530": "科创50ETF",
    "600783": "鲁信创投",
    "002471": "中超控股",
    "000592": "平潭发展",
    "601727": "上海电气",
    "002611": "东方精工",
    "300002": "神州泰岳",
    "600703": "三安光电",
    "002195": "岩山科技",
    "512980": "传媒ETF",
    "588430": "科创创业人工智能ETF工银",
}


# 统一的关注代码列表
CODES: list[str] = [
    "159218",
    "002195",
    "512980",
    "588430",
]


def code_label(code: str) -> str:
    """
    获取代码的显示标签（代码+名称）。
    
    Args:
        code: 证券代码
        
    Returns:
        格式化的标签，如 "159218（卫星产业ETF）"
    """
    c = str(code).strip()
    name = CODE_NAMES.get(c, "").strip()
    return f"{c}（{name}）" if name else c


