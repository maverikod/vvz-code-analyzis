"""
Suite: workers — repair-worker and vectorization-worker lifecycle.

Exercises: get_worker_status, repair_database, repair_worker_status,
revectorize (force=False), rebuild_faiss (force=False), update_indexes,
start_repair_worker, stop_repair_worker (verify-only safety list).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_workers import run_worker_lifecycle

SUITE_NAME = "workers"
LIFECYCLE_RUNNERS = (run_worker_lifecycle,)
