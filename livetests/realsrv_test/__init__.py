"""
realsrv_test — installable live-server acceptance pipeline for code-analysis-server.

Distribution: realsrv-test 0.1.0 (independent of the root server version).
CLI entry point: ``realsrv-test`` (console_scripts in livetests/pyproject.toml).

The implementation lives in ``scripts/_verify_client_all_commands_*.py``; this
package provides the CLI wrapper, auto-discovery of suite modules, and a thin
shim so the existing ``scripts/verify_client_all_commands_live.py`` still works
unchanged.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
