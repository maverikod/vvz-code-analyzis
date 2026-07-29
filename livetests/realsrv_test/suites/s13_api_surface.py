"""
Suite: apisurface — command-surface TODOs 1b6cc124 / 9c2018a3 / a7091850.

Exercises: get_ast bounded pagination + node projection, read_only_batch
paginated inline retrieval, get_file_lines absence from the live catalog.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_api_surface import (
    run_get_ast_pagination_check,
    run_get_file_lines_absent_check,
    run_read_only_batch_pagination_check,
)

SUITE_NAME = "apisurface"
LIFECYCLE_RUNNERS = (
    run_get_ast_pagination_check,
    run_read_only_batch_pagination_check,
    run_get_file_lines_absent_check,
)
