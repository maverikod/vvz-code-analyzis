"""
Suite: filemode — a save preserves the file's permissions (bug 92e6d693).

Asserts that overwriting an already-indexed project file leaves its POSIX
permission bits unchanged, for the CST (``.py``) write path and the plain
text write path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_file_mode import (
    run_py_update_preserves_mode,
    run_text_update_preserves_mode,
)

SUITE_NAME = "filemode"
LIFECYCLE_RUNNERS = (
    run_py_update_preserves_mode,
    run_text_update_preserves_mode,
)
