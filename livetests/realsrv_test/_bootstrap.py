"""
Bootstrap: add the scripts directory to sys.path so the implementation modules
(``_verify_client_all_commands_*``) are importable.  Also ensures the
``code_analysis_client`` package is importable from the checkout's
``client/`` tree when the package has not been installed from PyPI.

This module must be imported before any ``_verify_client_all_commands_*``
import.  Every other module in ``realsrv_test`` and ``realsrv_test.suites``
imports this module first.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import sys
from pathlib import Path

# livetests/realsrv_test/_bootstrap.py → repo root is three levels up
_THIS = Path(__file__).resolve()
_REPO = _THIS.parents[2]
_SCRIPTS = _REPO / "scripts"
_CLIENT = _REPO / "client"

for _p in (_SCRIPTS, _CLIENT):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
