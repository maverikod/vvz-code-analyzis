"""
Console script entry for ``casmgr``.

Ensures the repository / editable ``code_analysis`` package is importable even when
a stale third-party ``code_analysis`` directory exists in site-packages (e.g. old
``cli.py`` shadowing ``code_analysis.cli``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    here = Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        marker = base / "code_analysis" / "cli" / "server_manager_cli.py"
        if marker.is_file():
            root = str(base)
            if root not in sys.path:
                sys.path.insert(0, root)
            break

    from code_analysis.cli.server_manager_cli import server

    raise SystemExit(server())
