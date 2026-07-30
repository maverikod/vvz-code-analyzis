"""
Suite: stability -- ambient-load-detection contract guard (bug 2aaac911).

Exercises: ``list_project_files`` (cheap, page_size=1) against the pipeline's
own disposable fixture project, probed quiet (nothing else in flight) then
probed again while a small self-generated concurrent load is deliberately in
flight, and asserts the ambient-load probe (the same mechanism
``lifecycle_read_throughput.py`` uses to gate its own timing metrics)
correctly flags the second round as degraded. RE-AIMED from an earlier form
that asserted an absolute latency-divergence ceiling under self-generated
load -- see ``realsrv_test.core.lifecycle_measurement_stability`` module
docstring for why that form was retired and what this check verifies now.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_measurement_stability import (
    run_measurement_stability_check,
)

SUITE_NAME = "stability"
LIFECYCLE_RUNNERS = (run_measurement_stability_check,)
