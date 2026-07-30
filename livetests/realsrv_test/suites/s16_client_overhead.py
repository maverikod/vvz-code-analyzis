"""
Suite: client_overhead -- client-side per-call overhead regression guard (bug 8e6acb34).

Exercises: a fresh ``CodeAnalysisAsyncClient`` per iteration calling
``call_validated("health", {})`` for the first time on that instance
(the realistic one-process-per-invocation pattern), compared against a
warm, connection-reused raw ``httpx.AsyncClient`` floor. Asserts the gap
stays within a stated budget -- see
``realsrv_test.core.lifecycle_client_overhead`` for the full rationale and
the pre-/post-Fix-1 numbers this threshold separates.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_client_overhead import run_client_overhead_check

SUITE_NAME = "client_overhead"
LIFECYCLE_RUNNERS = (run_client_overhead_check,)
