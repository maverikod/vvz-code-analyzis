"""
Suite: stability -- self-contained measurement-stability guard (bug 2aaac911).

Exercises: ``list_project_files`` (cheap, page_size=1) against the pipeline's
own disposable fixture project, measured quiet (sequential, nothing else in
flight) then under a small self-generated concurrent load, and asserts the
divergence between the two stays within a stated factor. See
``realsrv_test.core.lifecycle_measurement_stability`` for the full rationale
and the numeric justification of the divergence ceiling.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_measurement_stability import (
    run_measurement_stability_check,
)

SUITE_NAME = "stability"
LIFECYCLE_RUNNERS = (run_measurement_stability_check,)
