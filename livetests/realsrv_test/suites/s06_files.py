"""
Suite: files — filesystem/project-file lifecycle and related fast-path checks.

Exercises: change_project_id (deferred), list_project_files,
list_project_files_exact_path (fast), list_project_files_glob (fast),
list_projects (paginated fast), project_lock/rename roundtrip,
project_trash/restore roundtrip, restore_database dry-run,
content_stale roundtrip, content_stale git roundtrip.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_fs import run_fs_lifecycle
from realsrv_test.core.lifecycle_list_files_fast import (
    run_list_project_files_exact_path_fast_check,
)
from realsrv_test.core.lifecycle_list_files_glob_fast import (
    run_list_project_files_glob_fast_check,
)
from realsrv_test.core.lifecycle_list_projects_fast import (
    run_list_projects_paginated_fast_check,
)
from realsrv_test.core.lifecycle_project_lock import (
    run_project_lock_rename_roundtrip_check,
)
from realsrv_test.core.lifecycle_project_trash_restore import (
    run_project_trash_restore_roundtrip_check,
)
from realsrv_test.core.lifecycle_restore_db_dryrun import (
    run_restore_database_dry_run_watch_dirs_fallback_check,
)
from realsrv_test.core.lifecycle_content_stale import (
    run_content_stale_roundtrip_check,
)

SUITE_NAME = "files"
# Order preserves the proven pre-package aggregator's relative order:
# the project_lock rename roundtrip runs LAST — it renames the project
# directory, and the content_stale check registers the project's own
# root_path as a git self-remote, which is path-sensitive.
LIFECYCLE_RUNNERS = (
    run_fs_lifecycle,
    run_list_project_files_exact_path_fast_check,
    run_list_project_files_glob_fast_check,
    run_list_projects_paginated_fast_check,
    run_project_trash_restore_roundtrip_check,
    run_restore_database_dry_run_watch_dirs_fallback_check,
    run_content_stale_roundtrip_check,
    run_project_lock_rename_roundtrip_check,
)
