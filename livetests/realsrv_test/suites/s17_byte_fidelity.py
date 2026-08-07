"""
Suite: bytes — byte fidelity of the project file save path (bug 44724d35).

Asserts that bytes handed to ``project_file_transfer_upload_save`` are stored
verbatim: CRLF stays CRLF on the create path, the update path, and the gzip
transfer branch, and mixed terminators / a missing trailing newline survive
a save unchanged.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_byte_fidelity import (
    run_create_preserves_crlf,
    run_gzip_preserves_crlf,
    run_mixed_line_endings,
    run_update_preserves_crlf,
)

SUITE_NAME = "bytes"
LIFECYCLE_RUNNERS = (
    run_create_preserves_crlf,
    run_update_preserves_crlf,
    run_gzip_preserves_crlf,
    run_mixed_line_endings,
)
