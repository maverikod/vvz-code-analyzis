"""
Suite: search — fulltext/semantic/grep search lifecycle plus bounded-liveness
and global-attribution regression checks.

Exercises: search, search_get_status, search_get_page, search_cancel,
search_close; also grep bounded-liveness and global search attribution.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_search import run_search_lifecycle
from realsrv_test.core.lifecycle_grep_bounded import (
    run_search_grep_bounded_liveness_check,
)
from realsrv_test.core.lifecycle_fulltext_seeded import (
    run_search_fulltext_seeded_literal_check,
)
from realsrv_test.core.lifecycle_global_search import (
    run_global_search_attribution_check,
)

SUITE_NAME = "search"
LIFECYCLE_RUNNERS = (
    run_search_lifecycle,
    run_search_grep_bounded_liveness_check,
    run_search_fulltext_seeded_literal_check,
    run_global_search_attribution_check,
)
