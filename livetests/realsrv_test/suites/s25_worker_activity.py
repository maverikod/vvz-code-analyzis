"""
Suite: worker_activity — manual start_worker(vectorization) makes real progress (bug 827e2b05).

Exercises: create_project, file_sessions.upload_new, update_indexes,
stop_worker/start_worker(vectorization), check_vectors, get_worker_status
(diagnostics only). RED before the fix (a manually-started vectorization
worker computes svo_config=None and can never embed, so total_chunks/
chunks_with_vector never move); GREEN after (the worker's start kwargs are
resolved through the same boot-parity resolvers the server itself uses at
startup, per code_analysis/core/worker_start_args.py).

See ``realsrv_test.core.lifecycle_worker_activity`` module docstring for the
mechanism and, IMPORTANTLY, the teardown constraint: a RED run against a
pre-fix server leaves a duplicate, permanently-broken vectorization worker
process behind that only a service restart heals. Schedule a deliberate RED
run of this suite only immediately before a deploy that restarts the
service -- never against a long-lived pre-fix production server.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_worker_activity import run_worker_activity_check

SUITE_NAME = "worker_activity"
LIFECYCLE_RUNNERS = (run_worker_activity_check,)
