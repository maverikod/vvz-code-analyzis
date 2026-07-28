"""
Suite: transfer — file transfer upload/download/metadata lifecycle.

Exercises: project_file_transfer_upload_save, project_file_transfer_download,
project_file_transfer_metadata, and related transfer commands.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import realsrv_test._bootstrap  # noqa: F401 — must run before any scripts/ import

from _verify_client_all_commands_lifecycle_transfer import run_transfer_lifecycle

SUITE_NAME = "transfer"
LIFECYCLE_RUNNERS = (run_transfer_lifecycle,)
