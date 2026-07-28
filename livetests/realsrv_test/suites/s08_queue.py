"""
Suite: queue — queue job lifecycle (long_task / job_status / queue_* commands).

Exercises: long_task, job_status, queue_add_job, queue_start_job,
queue_stop_job, queue_delete_job, queue_get_job_status, queue_get_job_logs,
queue_list_jobs, queue_health.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from _verify_client_all_commands_lifecycle_queue import run_queue_lifecycle

SUITE_NAME = "queue"
LIFECYCLE_RUNNERS = (run_queue_lifecycle,)
