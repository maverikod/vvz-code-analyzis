"""
Suite: throughput -- concurrent vs sequential read throughput (bug 8e6acb34).

Exercises: list_project_files (concurrent N=16 vs sequential N=16, cheap
project_id-bearing reads against a real pre-existing project) to detect
process-wide serialization of the whole-project-lock-gate select() path.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_read_throughput import run_read_throughput_check

SUITE_NAME = "throughput"
LIFECYCLE_RUNNERS = (run_read_throughput_check,)
