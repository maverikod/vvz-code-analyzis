"""
realsrv_test — installable live-server acceptance pipeline for code-analysis-server.

Distribution: realsrv-test 0.1.0 (independent of the root server version).
CLI entry point: ``realsrv-test`` (console_scripts in livetests/pyproject.toml).

Layout: ``realsrv_test.core`` holds the whole implementation (fixtures,
classifiers, lifecycles, sweep engine, teardown, pipeline);
``realsrv_test.suites`` holds the auto-discovered suite modules — the single
source of truth for which lifecycle runners execute.
``scripts/verify_client_all_commands_live.py`` remains as a thin
backward-compatibility shim delegating to ``realsrv_test._cli.main_sync``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
