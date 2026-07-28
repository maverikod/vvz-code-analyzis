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

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from _verify_client_all_commands_lifecycle_fs import run_fs_lifecycle
from _verify_client_all_commands_lifecycle_list_files_fast import (
    run_list_project_files_exact_path_fast_check,
)
from _verify_client_all_commands_lifecycle_list_files_glob_fast import (
    run_list_project_files_glob_fast_check,
)
from _verify_client_all_commands_lifecycle_list_projects_fast import (
    run_list_projects_paginated_fast_check,
)
from _verify_client_all_commands_lifecycle_project_lock import (
    run_project_lock_rename_roundtrip_check,
)
from _verify_client_all_commands_lifecycle_project_trash_restore import (
    run_project_trash_restore_roundtrip_check,
)
from _verify_client_all_commands_lifecycle_restore_db_dryrun import (
    run_restore_database_dry_run_watch_dirs_fallback_check,
)
from _verify_client_all_commands_lifecycle_content_stale import (
    run_content_stale_roundtrip_check,
)

SUITE_NAME = "files"
LIFECYCLE_RUNNERS = (
    run_fs_lifecycle,
    run_list_project_files_exact_path_fast_check,
    run_list_project_files_glob_fast_check,
    run_list_projects_paginated_fast_check,
    run_project_lock_rename_roundtrip_check,
    run_project_trash_restore_roundtrip_check,
    run_restore_database_dry_run_watch_dirs_fallback_check,
    run_content_stale_roundtrip_check,
)
