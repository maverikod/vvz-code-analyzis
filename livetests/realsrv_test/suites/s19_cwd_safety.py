"""
Suite: cwdsafety — the client never touches the caller's working directory.

Guards bug c3fafbd4: uploads used to stage their payload at a path relative to
the process's cwd and then delete it, destroying same-named files belonging to
whoever ran the pipeline.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_cwd_safety import run_upload_does_not_touch_caller_cwd

SUITE_NAME = "cwdsafety"
LIFECYCLE_RUNNERS = (run_upload_does_not_touch_caller_cwd,)
