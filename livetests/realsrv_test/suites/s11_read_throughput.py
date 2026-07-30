"""
Suite: throughput -- read-path performance, two independent metrics (bug 8e6acb34).

Exercises: list_project_files (concurrent N=16 vs sequential N=16, cheap
project_id-bearing reads against a real pre-existing project). Reports two
SEPARATE outcomes -- see ``realsrv_test.core.lifecycle_read_throughput`` for
the full rationale of each:

- ``read_latency_per_call_regression``: guards the SHIPPED per-call latency
  fix (sequential per-call time must stay at or below a regression ceiling).
- ``read_concurrency_speedup_8e6acb34``: the original concurrency-scaling
  question, unchanged 4.0x threshold, expected to stay red until bug
  8e6acb34's scaling defect is fixed.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_read_throughput import run_read_throughput_check

SUITE_NAME = "throughput"
LIFECYCLE_RUNNERS = (run_read_throughput_check,)
