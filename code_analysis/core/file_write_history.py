"""
Shared helpers for file mutations: cooperative locks and documentation hooks.

**Policy:** mutating commands should (1) take :func:`file_lock_many` on all affected
paths (sorted, de-duplicated), (2) create a :class:`~code_analysis.core.backup_manager.BackupManager`
snapshot before overwriting or removing existing files, and (3) call
:func:`code_analysis.core.git_integration.commit_after_write` when
``code_analysis.git_commit_on_write`` is enabled.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from contextlib import contextmanager
from contextlib import ExitStack
from pathlib import Path
from typing import Iterator, List, Sequence

from .file_lock import file_lock


@contextmanager
def file_lock_many(paths: Sequence[Path]) -> Iterator[None]:
    """Hold :func:`file_lock` on each distinct path, in stable sorted order.

    Avoids deadlocks when two commands use the same global ordering.
    """
    seen: set[str] = set()
    ordered: List[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            ordered.append(p)
    ordered.sort(key=lambda x: str(x.resolve()))
    with ExitStack() as stack:
        for p in ordered:
            stack.enter_context(file_lock(p))
        yield
