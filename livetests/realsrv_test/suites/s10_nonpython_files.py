"""
Suite: nonpy — non-Python text-file indexing (bugs 688d2d01 / 13945588 /
597ea8c5 / a51769dc / fe1cf739).

Exercises: pyproject.toml / script.sh / .gitignore / notes.md get a lockable
``file_id`` and fulltext-visible ``code_content`` after ``update_indexes``,
and ``universal_file_preview`` succeeds on ``.toml``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from realsrv_test.core.lifecycle_nonpython_files import run_nonpython_files_check

SUITE_NAME = "nonpy"
LIFECYCLE_RUNNERS = (run_nonpython_files_check,)
