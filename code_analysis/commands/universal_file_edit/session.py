"""
EditSession entity and module-level session registry.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from code_analysis.commands.universal_file_edit.format_group import FormatDescriptor
from code_analysis.core.tree_temp.tree_node import TreeNode

_sessions: dict[str, EditSession] = {}


@dataclass
class EditSession:
    """In-memory record for one active file-editing session."""

    session_id: str
    file_path: str
    abs_path: Path
    draft_path: Path
    lockfile_path: Path
    format_group: str
    handler_id: str
    tree_id: Optional[str]
    source_sha256_at_open: Optional[str] = None
    dirty: bool = False
    tree_temp_roots: Optional[List[TreeNode]] = None
    sidecar_write_intent: Optional[str] = None
    fallback_reason: Optional[str] = None
    original_format_group: Optional[str] = None


def create_session(
    abs_path: Path,
    descriptor: FormatDescriptor,
    file_path: str,
    tree_id: Optional[str] = None,
    *,
    source_sha256_at_open: Optional[str] = None,
    tree_temp_roots: Optional[List[TreeNode]] = None,
    sidecar_write_intent: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    original_format_group: Optional[str] = None,
) -> EditSession:
    """Create and register a new EditSession."""
    session_id = str(uuid.uuid4())
    session = EditSession(
        session_id=session_id,
        file_path=file_path,
        abs_path=abs_path,
        draft_path=descriptor.draft_path,
        lockfile_path=descriptor.lockfile_path,
        format_group=descriptor.format_group,
        handler_id=descriptor.handler_id,
        tree_id=tree_id,
        source_sha256_at_open=source_sha256_at_open,
        dirty=False,
        tree_temp_roots=tree_temp_roots,
        sidecar_write_intent=sidecar_write_intent,
        fallback_reason=fallback_reason,
        original_format_group=original_format_group,
    )
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> EditSession:
    """Return the EditSession for session_id, or raise SESSION_NOT_FOUND."""
    session = _sessions.get(session_id)
    if session is None:
        raise ValueError("SESSION_NOT_FOUND")
    return session


def release_session(session_id: str) -> None:
    """Remove a session from the registry; silent if session_id is unknown."""
    _sessions.pop(session_id, None)


def active_session_uses_abs_path(abs_path: Path) -> bool:
    """Return True if any registered session uses this resolved absolute path."""
    target = abs_path.resolve()
    for sess in _sessions.values():
        if sess.abs_path.resolve() == target:
            return True
    return False
