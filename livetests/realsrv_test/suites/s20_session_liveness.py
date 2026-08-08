"""
Suite: sessionliveness — locks do not outlive the session that took them.

Guards TODO d75d5e9a: a client crash orphaned its session and its exclusive file
lock survived indefinitely, unopenable by anyone and releasable only by a manual
session_delete.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_session_liveness import run_dead_session_lock_release

SUITE_NAME = "sessionliveness"
LIFECYCLE_RUNNERS = (run_dead_session_lock_release,)
