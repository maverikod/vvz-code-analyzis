"""
Resolve grep scan sources: disk paths and universal_file draft sessions.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from code_analysis.commands.universal_file_edit.format_group import FORMAT_TEXT
from code_analysis.commands.universal_file_edit.session import get_session
from code_analysis.commands.universal_file_edit.tree_temp_write_commit import (
    serialize_tree_temp_session_source,
)

SourceMode = Literal["disk", "draft_session", "both"]


@dataclass(frozen=True)
class GrepScanTarget:
    """One logical file to grep (disk path key + content provider)."""

    relative_path: str
    source: Literal["disk", "draft_session"]
    session_id: Optional[str] = None

    def read_content(self, project_root: Path) -> str:
        """Read grep content from a draft session or disk file."""
        if self.source == "draft_session":
            if not self.session_id:
                raise ValueError("session_id required for draft_session source")
            return read_draft_session_content(self.session_id)
        abs_path = (project_root / self.relative_path).resolve()
        return abs_path.read_text(encoding="utf-8", errors="replace")


def read_draft_session_content(session_id: str) -> str:
    """Load current draft text for a universal_file edit session."""
    try:
        session = get_session(session_id)
    except ValueError as exc:
        if "SESSION_NOT_FOUND" in str(exc):
            raise ValueError("SESSION_NOT_FOUND") from exc
        raise
    if session.format_group == FORMAT_TEXT:
        if not session.draft_path.is_file():
            raise ValueError("DRAFT_NOT_AVAILABLE")
        return session.draft_path.read_text(encoding="utf-8", errors="replace")
    try:
        return serialize_tree_temp_session_source(session)
    except Exception as exc:
        raise ValueError(f"UNSUPPORTED_SESSION_FORMAT: {exc}") from exc


def build_scan_targets(
    *,
    project_root: Path,
    fs_paths: List[Path],
    source: SourceMode,
    session_id: Optional[str],
) -> Tuple[List[GrepScanTarget], List[dict]]:
    """
    Build grep targets from disk enumeration and optional draft session.

    Returns (targets, warnings).
    """
    warnings: List[dict] = []
    targets: List[GrepScanTarget] = []
    rel_seen: set[str] = set()

    if source in ("disk", "both"):
        for abs_path in fs_paths:
            rel = abs_path.relative_to(project_root).as_posix()
            rel_seen.add(rel)
            targets.append(
                GrepScanTarget(relative_path=rel, source="disk", session_id=None)
            )

    if source in ("draft_session", "both"):
        if not session_id:
            warnings.append(
                {
                    "code": "SESSION_ID_REQUIRED",
                    "message": "session_id is required when source includes draft_session.",
                }
            )
            return targets, warnings
        try:
            session = get_session(session_id)
        except ValueError:
            warnings.append(
                {
                    "code": "SESSION_NOT_FOUND",
                    "message": f"session_id {session_id!r} not found.",
                }
            )
            return targets, warnings
        rel = Path(session.file_path).as_posix()
        if rel not in rel_seen or source == "draft_session":
            targets.append(
                GrepScanTarget(
                    relative_path=rel,
                    source="draft_session",
                    session_id=session_id,
                )
            )
    return targets, warnings
