"""
Suite: loop -- main event-loop liveness under concurrent load (bug 4d1a2895).

Exercises: search (concurrent, read-only, against a real pre-existing
project) plus health (control call), to detect main-event-loop starvation
caused by synchronous work executed inline before a command's offload
dispatch.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_loop_liveness import run_loop_liveness_check

SUITE_NAME = "loop"
LIFECYCLE_RUNNERS = (run_loop_liveness_check,)
