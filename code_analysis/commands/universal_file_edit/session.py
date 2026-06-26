"""
EditSession facade and command-layer metadata over core C-012 EditSession.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from code_analysis.commands.universal_file_edit.format_group import FormatDescriptor
from code_analysis.core.edit_session import (
    EditSession as CoreEditSession,
    SessionTreeValidity,
)
from code_analysis.tree.edit_operations import EditOperation
from code_analysis.core.edit_session.edit_session import _active_sessions
from code_analysis.core.tree_temp.tree_node import TreeNode

# group session_id -> project-relative file_path -> EditSession facade
_session_bundles: dict[str, dict[str, "EditSession"]] = {}


@dataclass
class EditSession:
    """Universal-file command facade over one core EditSession (C-012)."""

    session_id: str
    file_path: str
    abs_path: Path
    draft_path: Path
    lockfile_path: Path
    format_group: str
    handler_id: str
    tree_id: Optional[str]
    core: CoreEditSession
    source_sha256_at_open: Optional[str] = None
    dirty: bool = False
    tree_temp_roots: Optional[List[TreeNode]] = None
    sidecar_write_intent: Optional[str] = None
    fallback_reason: Optional[str] = None
    original_format_group: Optional[str] = None
    is_invalid: bool = False


def _norm_file_path(file_path: str) -> str:
    """Return norm file path."""
    return Path(str(file_path).replace("\\", "/")).as_posix()


def _resolve_project_root_near(abs_path: Path) -> Path:
    """Locate project root upward from ``abs_path`` for core session open."""
    resolved = abs_path.resolve()
    probe = resolved.parent if resolved.is_file() else resolved
    for candidate in (probe,) + tuple(probe.parents):
        if (candidate / "pyproject.toml").exists() or (
            candidate / "projectid"
        ).exists():
            return candidate
    return probe


def create_session(
    abs_path: Path,
    descriptor: FormatDescriptor,
    file_path: str,
    tree_id: Optional[str] = None,
    *,
    project_root: Optional[Path] = None,
    source_sha256_at_open: Optional[str] = None,
    tree_temp_roots: Optional[List[TreeNode]] = None,
    sidecar_write_intent: Optional[str] = None,
    fallback_reason: Optional[str] = None,
    original_format_group: Optional[str] = None,
    is_invalid: bool = False,
    initial_source_text: Optional[str] = None,
    group_session_id: Optional[str] = None,
) -> EditSession:
    """Open a core EditSession and register command-layer metadata.

    When ``group_session_id`` is omitted, a new group id is allocated and returned
    on ``EditSession.session_id``. When provided, the file is attached to that
    existing group so one session can hold multiple open files.
    """
    norm_path = _norm_file_path(file_path)
    if group_session_id is None:
        group_id = str(uuid.uuid4())
        bundle: dict[str, EditSession] = {}
        _session_bundles[group_id] = bundle
    else:
        group_id = str(group_session_id).strip()
        bundle = _session_bundles.get(group_id)
        if bundle is None:
            raise ValueError("SESSION_NOT_FOUND")
        if norm_path in bundle:
            raise ValueError("FILE_ALREADY_IN_SESSION")

    root = (
        project_root
        if project_root is not None
        else _resolve_project_root_near(abs_path)
    )
    content = initial_source_text
    if content is None and not abs_path.is_file():
        content = ""
    core = CoreEditSession.open(
        source_abs=abs_path,
        project_root=root,
        file_path=file_path,
        content=content if not abs_path.is_file() else None,
    )
    session = EditSession(
        session_id=group_id,
        file_path=file_path,
        abs_path=abs_path,
        draft_path=core.session_source_path,
        lockfile_path=descriptor.lockfile_path,
        format_group=descriptor.format_group,
        handler_id=descriptor.handler_id,
        tree_id=tree_id,
        core=core,
        source_sha256_at_open=source_sha256_at_open,
        dirty=False,
        tree_temp_roots=tree_temp_roots,
        sidecar_write_intent=sidecar_write_intent,
        fallback_reason=fallback_reason,
        original_format_group=original_format_group,
        is_invalid=is_invalid,
    )
    bundle[norm_path] = session
    return session


def get_session(session_id: str, file_path: Optional[str] = None) -> EditSession:
    """Return the command facade for a group session and optional file path."""
    bundle = _session_bundles.get(session_id)
    if not bundle:
        raise ValueError("SESSION_NOT_FOUND")
    if file_path is None:
        if len(bundle) == 1:
            session = next(iter(bundle.values()))
        else:
            raise ValueError("SESSION_FILE_PATH_REQUIRED")
    else:
        session = bundle.get(_norm_file_path(file_path))
        if session is None:
            raise ValueError("SESSION_NOT_FOUND")
    if not session.core.is_open:
        raise ValueError("SESSION_NOT_FOUND")
    return session


def release_session(session_id: str, file_path: Optional[str] = None) -> None:
    """Remove one file (or the sole file) from a group and close its core session."""
    bundle = _session_bundles.get(session_id)
    if bundle is None:
        return
    if file_path is None:
        if len(bundle) != 1:
            raise ValueError("SESSION_FILE_PATH_REQUIRED")
        norm_path = next(iter(bundle))
    else:
        norm_path = _norm_file_path(file_path)
    session = bundle.pop(norm_path, None)
    if session is not None and session.core.is_open:
        session.core.close()
    if not bundle:
        _session_bundles.pop(session_id, None)


def active_session_uses_abs_path(abs_path: Path) -> bool:
    """Return True if any registered core session uses this resolved absolute path."""
    target = abs_path.resolve()
    for core in _active_sessions.values():
        if core.source_abs.resolve() == target:
            return True
    return False


def apply_tree_operation(session: EditSession, operation: EditOperation) -> None:
    """Apply one G-004 EditOperation via core session adapter ({h008})."""
    session.core.apply_tree_operation(operation)
    session.draft_path = session.core.session_source_path
    session.dirty = True


def apply_source_mutation(session: EditSession, new_source_text: str) -> None:
    """Apply in-session source change via core valid-tree or plaintext mutation."""
    if session.is_invalid or session.core.tree_validity == SessionTreeValidity.INVALID:
        session.core.apply_plaintext_mutation(new_source_text)
    else:
        session.core.apply_valid_tree_mutation(lambda _: new_source_text)
    session.draft_path = session.core.session_source_path
    session.dirty = True


def apply_cst_sidecar_mutation(
    session: EditSession,
    new_source_text: str,
    *,
    sidecar_abs: Path,
) -> None:
    """Persist legacy CST sidecar edit into the session repo and undo history."""
    session.core.apply_cst_sidecar_mutation(
        new_source_text,
        sidecar_abs=sidecar_abs,
    )
    session.draft_path = session.core.session_source_path
    session.dirty = True
