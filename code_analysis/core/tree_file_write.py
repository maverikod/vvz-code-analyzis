"""
Atomic writes for sibling ``*.tree`` sidecars with source-file ownership.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def match_file_owner(target: Path, reference: Path) -> None:
    """Set *target* uid/gid to match *reference* when the platform supports it.

    When *reference* is not a file, its parent directory stat is used as a fallback
    (e.g. sidecar written immediately after creating a new source file).
    """
    if sys.platform == "win32":
        return

    target = target.resolve()
    reference = reference.resolve()
    if not target.is_file():
        return

    ref_path = reference
    if not ref_path.is_file():
        ref_path = reference.parent
        if not ref_path.is_dir():
            return

    try:
        st = os.stat(ref_path, follow_symlinks=True)
        os.chown(target, st.st_uid, st.st_gid)
    except (OSError, AttributeError) as exc:
        logger.debug(
            "Could not match owner of %s to %s: %s",
            target,
            reference,
            exc,
        )


def atomic_write_sibling_tree_file(
    *,
    source_abs: Path,
    sidecar_path: Path,
    text: str,
) -> Path:
    """Atomically write *text* to *sidecar_path*; owner matches *source_abs*."""
    sidecar_path = sidecar_path.resolve()
    source_abs = source_abs.resolve()
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    match_file_owner(sidecar_path, source_abs)
    return sidecar_path


__all__ = ["atomic_write_sibling_tree_file", "match_file_owner"]
