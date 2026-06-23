"""
Filesystem permission pre-checks for the file watcher.

The watcher runs as an unprivileged service account (``casuser``) over
directories that may be created or mutated by other accounts (root-owned
mounts, host tooling). Touching a path the account has no rights to raises
``EACCES`` deep inside a scan or settings write and can abort an entire reload
or scan cycle (one bad directory taking down the whole worker).

These helpers check access up front, emit a single clear ``[FS_PERM]`` log
line on denial, and let callers skip the offending path and continue.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
from typing import Union

logger = logging.getLogger(__name__)

PathLike = Union[str, "os.PathLike[str]"]

FS_PERM_TAG = "[FS_PERM]"


def is_readable_dir(path: PathLike, *, log: logging.Logger = logger) -> bool:
    """True when ``path`` is a directory the process can list and traverse.

    Requires both read (``R_OK``) and execute/search (``X_OK``) permission.
    Logs an error and returns ``False`` when access is denied.
    """
    p = os.fspath(path)
    if not os.access(p, os.R_OK | os.X_OK):
        log.error(
            "%s no read/traverse permission on directory, skipping: %s",
            FS_PERM_TAG,
            p,
        )
        return False
    return True


def is_readable_file(path: PathLike, *, log: logging.Logger = logger) -> bool:
    """True when ``path`` can be read (``R_OK``); logs and returns ``False`` otherwise."""
    p = os.fspath(path)
    if not os.access(p, os.R_OK):
        log.error("%s no read permission on file, skipping: %s", FS_PERM_TAG, p)
        return False
    return True


def is_writable_dir(path: PathLike, *, log: logging.Logger = logger) -> bool:
    """True when files can be created/replaced in directory ``path``.

    Requires write (``W_OK``) and execute/search (``X_OK``) permission. Logs an
    error and returns ``False`` when access is denied.
    """
    p = os.fspath(path)
    if not os.access(p, os.W_OK | os.X_OK):
        log.error(
            "%s no write permission on directory, skipping: %s",
            FS_PERM_TAG,
            p,
        )
        return False
    return True


def log_walk_error(error: OSError, *, log: logging.Logger = logger) -> None:
    """``os.walk(onerror=...)`` callback: log denied/IO errors instead of swallowing.

    ``os.walk`` silently skips directories it cannot list unless an ``onerror``
    callback is supplied; this makes such skips visible in the logs.
    """
    log.error("%s cannot access during scan, skipping: %s", FS_PERM_TAG, error)
