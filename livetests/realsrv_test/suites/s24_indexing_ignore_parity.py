"""
Suite: indexing_ignore_parity — update_indexes vs. watcher ignore-policy parity.

Exercises: ``update_indexes``' eligibility walk must exclude what the file
watcher's own ignore policy excludes (bug 5b663fbb), e.g. ``test_data/``. See
``realsrv_test.core.lifecycle_indexing_ignore_parity`` for the check's exact
mechanism and RED/GREEN criteria.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_indexing_ignore_parity import (
    run_update_indexes_excludes_watcher_ignored_test_data,
)

SUITE_NAME = "indexing_ignore_parity"
LIFECYCLE_RUNNERS = (run_update_indexes_excludes_watcher_ignored_test_data,)
