from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_path() -> None:
    """
    Make repo root importable when running manual tests via:
      uv run python tests/manual/test_xxx.py
    """
    repo_root = Path(__file__).resolve().parents[2]
    root_str = str(repo_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


