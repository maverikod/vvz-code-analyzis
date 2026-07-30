"""
Suite: sessions — search-session idle-sweep retention regression.

Exercises: search, search_close, search_sessions_purge, search_get_page.
Reproduces/covers the unbounded data/search_sessions growth bug (measured:
69 sessions / 56,505 files / 1.6 GB locally, nothing ever expiring them).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_session_retention import (
    run_session_retention_sweep_check,
)

SUITE_NAME = "sessions"
LIFECYCLE_RUNNERS = (run_session_retention_sweep_check,)
