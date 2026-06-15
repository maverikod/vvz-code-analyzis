"""
SearchSessionDirectory layout and provisioning.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from code_analysis.core.search_session.session import SearchSession

MANIFEST_FILENAME = "manifest.json"
INDEX_FILENAME = "index.json"
SERVICE_METADATA_FILENAME = "service_metadata.json"
BLOCKS_DIRNAME = "blocks"
RELEVANCE_BLOCKS_DIRNAME = "blocks_relevance"
BUFFER_DIRNAME = "buffer"


@dataclass(frozen=True)
class SearchSessionDirectoryLayout:
    """
    Resolved paths for one search session directory.

    Attributes:
        root: Session root directory.
        manifest_path: manifest.json path.
        index_path: index.json path.
        service_metadata_path: service_metadata.json path.
        blocks_dir: Immutable published blocks directory.
        buffer_dir: Raw finding buffer directory (findings awaiting assembly).
    """

    root: Path
    manifest_path: Path
    index_path: Path
    service_metadata_path: Path
    blocks_dir: Path
    buffer_dir: Path
    relevance_blocks_dir: Path


def provision_search_session_directory(
    *,
    sessions_root: Path,
    search_id: str,
) -> SearchSessionDirectoryLayout:
    """
    Create on-disk session directory tree for ``search_id``.

    Creates ``root``, ``blocks/``, ``blocks_relevance/``, and ``buffer/``.
    Manifest, index, and service metadata files are created by later steps.

    Args:
        sessions_root: Writable directory for all search sessions (see
            ``resolve_search_sessions_root`` in ``storage_paths``).
        search_id: Session UUID string (used as subdirectory name).

    Returns:
        Populated layout with absolute paths.

    Raises:
        FileExistsError: If ``root`` already exists.
    """
    root = sessions_root.resolve() / search_id
    blocks_dir = root / BLOCKS_DIRNAME
    relevance_blocks_dir = root / RELEVANCE_BLOCKS_DIRNAME
    buffer_dir = root / BUFFER_DIRNAME

    root.mkdir(parents=True, exist_ok=False)
    blocks_dir.mkdir(exist_ok=True)
    relevance_blocks_dir.mkdir(exist_ok=True)
    buffer_dir.mkdir(exist_ok=True)

    return SearchSessionDirectoryLayout(
        root=root,
        manifest_path=root / MANIFEST_FILENAME,
        index_path=root / INDEX_FILENAME,
        service_metadata_path=root / SERVICE_METADATA_FILENAME,
        blocks_dir=blocks_dir,
        relevance_blocks_dir=relevance_blocks_dir,
        buffer_dir=buffer_dir,
    )


DIRECTORY_SESSION_MISMATCH: str = "DIRECTORY_SESSION_MISMATCH"


def bind_session_directory(
    session: "SearchSession",
    layout: SearchSessionDirectoryLayout,
) -> "SearchSession":
    """
    Attach a provisioned directory to an unbound session.

    Validates that layout.root.name matches session.search_id, then returns
    a new session with directory_path set to layout.root.resolve().

    Args:
        session: SearchSession with directory_path=None.
        layout: Provisioned layout whose root.name must match session.search_id.

    Returns:
        SearchSession with directory_path set to layout.root.resolve().

    Raises:
        ValueError: With code DIRECTORY_SESSION_MISMATCH when names differ.
    """
    if layout.root.name != session.search_id:
        raise ValueError(
            f"{DIRECTORY_SESSION_MISMATCH}: layout root '{layout.root.name}' "
            f"does not match search_id '{session.search_id}'"
        )
    return replace(session, directory_path=layout.root.resolve())
