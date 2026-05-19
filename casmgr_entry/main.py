"""
Console script entry for ``casmgr``.

Ensures the repository / editable ``code_analysis`` package is importable even when
a stale third-party ``code_analysis`` directory exists in site-packages (e.g. old
``cli.py`` shadowing ``code_analysis.cli``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path | None:
    for base in [start, *start.parents]:
        marker = base / "code_analysis" / "cli" / "server_manager_cli.py"
        if marker.is_file():
            return base
    return None


def main() -> None:
    here = Path(__file__).resolve()
    root = _find_repo_root(here.parent)
    if root is not None:
        root_s = str(root)
        if root_s not in sys.path:
            sys.path.insert(0, root_s)
        try:
            os.chdir(root)
        except OSError:
            pass

    from code_analysis.cli.server_manager_cli import server

    raise SystemExit(server())
