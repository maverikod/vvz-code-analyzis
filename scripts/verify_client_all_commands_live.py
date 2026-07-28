#!/usr/bin/env python3
"""
Shim: delegates to the installable ``realsrv-test`` CLI package.

The real implementation now lives in ``livetests/realsrv_test/``.
This file is kept so that existing references (docs, history, ops files
updated separately) remain resolvable without change.

    CLI:       realsrv-test [options] [suite ...]
    Package:   livetests/  (distribution name realsrv-test, version 0.1.0)
    No-args:   runs all suites sequentially.

Certificate recipe and usage: see ``livetests/realsrv_test/_cli.py`` docstring,
or run ``realsrv-test --help``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package is importable from a direct invocation of this shim
# (e.g. ``python scripts/verify_client_all_commands_live.py --cert ...``).
_LIVETESTS = Path(__file__).resolve().parents[1] / "livetests"
if str(_LIVETESTS) not in sys.path:
    sys.path.insert(0, str(_LIVETESTS))

from realsrv_test._cli import main_sync  # noqa: E402

if __name__ == "__main__":
    main_sync()
