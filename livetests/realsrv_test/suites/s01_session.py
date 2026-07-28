"""
Suite: session — session/subordinate-session/file-lock command chain.

Exercises: session_create, session_delete, session_open_file, session_close_file,
session_list_open_files, subordinate_session_create, subordinate_session_delete,
subordinate_session_list.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from _verify_client_all_commands_lifecycle_session import run_session_lifecycle

SUITE_NAME = "session"
LIFECYCLE_RUNNERS = (run_session_lifecycle,)
