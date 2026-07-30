"""
Suite: loop -- main event-loop liveness under concurrent load (bug 4d1a2895).

Exercises: search (concurrent, read-only, against a real pre-existing
project) plus health (control call), to detect main-event-loop starvation
caused by synchronous work executed inline before a command's offload
dispatch.

SUITE_CATEGORY = "load_generator" (bug 2aaac911): this suite deliberately
fires K=32 concurrent heavy search calls against the same shared project
(``44a8ce88-b467-42a8-b874-033562b89bd0``) that
``lifecycle_read_throughput.py`` (suite "throughput") also measures.
Confirmed on the real deployed server, running immediately in this suite's
wake corrupted that suite's timing verdict (0.646s/call vs a clean
0.009-0.010s/call standalone) -- see
``realsrv_test.core.lifecycle_read_throughput`` module docstring. Tagging
this suite pushes it to run LAST in a full sweep (see
``realsrv_test.suites`` package docstring) instead of adding a cooldown
sleep, so no timing-sensitive suite runs in its immediate wake.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_loop_liveness import run_loop_liveness_check

SUITE_NAME = "loop"
SUITE_CATEGORY = "load_generator"
LIFECYCLE_RUNNERS = (run_loop_liveness_check,)
