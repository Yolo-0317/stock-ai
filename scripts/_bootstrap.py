from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_path() -> None:
    """
    Make repo root importable when running scripts via:
      uv run python scripts/xxx.py

    In that mode, sys.path[0] is usually ".../scripts", so root-level modules like
    `tushare_mcp.py`, `feishu_notice.py`, `logger_config.py` aren't found unless we
    explicitly add the repository root.
    """
    repo_root = Path(__file__).resolve().parents[1]
    root_str = str(repo_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


