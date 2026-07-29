"""
Suite: indexer — indexer-correctness checks for three long-standing planner TODOs.

Exercises: entity_cross_ref built by the CST-editor/batch write path (bug
3e7177d6), entity end_line population (bug d4cd9525), and update_indexes
usages idempotence across re-index (bug a586efdb). See
``realsrv_test.core.lifecycle_indexer_correctness`` for each check's exact
mechanism and RED/GREEN criteria.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_indexer_correctness import (
    run_cst_batch_write_builds_entity_cross_ref,
    run_indexer_populates_entity_end_line,
    run_update_indexes_usages_idempotent,
)

SUITE_NAME = "indexer"
LIFECYCLE_RUNNERS = (
    run_cst_batch_write_builds_entity_cross_ref,
    run_indexer_populates_entity_end_line,
    run_update_indexes_usages_idempotent,
)
