"""
Suite: vectorization_batch_cap — embed-batch-cap check for bug 16b1abbe.

Exercises: create_project, session_create, update_indexes, start_worker,
check_vectors, stop_worker, delete_project against an isolated disposable
project with one file whose chunk count exceeds the embed service's
per-request text cap.

Numbered s22 (not s11/s12 — both already taken by
``s11_read_throughput``/``s12_indexer_correctness`` at the time this suite
was added) to avoid colliding with any in-flight sibling suite.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_vectorization_batch_cap import (
    run_vectorization_batch_cap_lifecycle,
)

SUITE_NAME = "vectorization_batch_cap"
LIFECYCLE_RUNNERS = (run_vectorization_batch_cap_lifecycle,)
