"""
统一管理证券代码 -> 名称的映射。

用法：
  from code_names import code_label
  print(code_label("159218"))  # 159218（名称）或 159218
"""

from __future__ import annotations


# 在这里维护你的关注标的名称（手工最稳定、无网络依赖）
CODE_NAMES: dict[str, str] = {
    "159218": "卫星产业ETF",
    "159840": "锂电池ETF",
    "512400": "有色ETF",
}


def code_label(code: str) -> str:
    c = str(code).strip()
    name = CODE_NAMES.get(c, "").strip()
    return f"{c}（{name}）" if name else c


