"""
TreeRepresentation validation lifecycle for paginated search sessions.

Integration layer over existing tree-temp and CST sidecar storage. Full tree
parsers are delegated to indexer hooks; this module resolves sidecar paths,
classifies formats, and validates checksum freshness before structural search.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, cast

from code_analysis.core.cst_tree.tree_sidecar import (
    read_sidecar_payload,
    sidecar_path_for_py,
)
from code_analysis.core.structure_extraction.format_registry import (
    JSON_SUFFIX,
    MD_SUFFIXES,
    PY_SUFFIXES,
    TEXT_PLAIN_SUFFIXES,
    YAML_SUFFIXES,
    suffix_for_path,
)
from code_analysis.core.tree_temp.sidecar_paths import resolve_trees_sidecar_path
from code_analysis.core.tree_temp.sidecar_payload import (
    SidecarParseError,
    loads_sidecar,
)

_ADJACENT_SIDECAR_SUFFIX = ".tree_sidecar"


class TreeFormatKind(str, Enum):
    """Supported TreeRepresentation storage formats."""

    json = "json"
    yaml = "yaml"
    python_cst = "python_cst"
    markdown = "markdown"
    text = "text"


@dataclass(frozen=True)
class TreeRepresentationRef:
    """Validated on-disk tree sidecar reference for one project file."""

    file_path: str
    sidecar_path: Path
    content_checksum: str
    root_stable_id: Optional[str]


def classify_tree_format(file_path: str) -> TreeFormatKind:
    """Map a project-relative file path to its TreeRepresentation format."""
    suffix = suffix_for_path(file_path)
    if suffix == JSON_SUFFIX:
        return TreeFormatKind.json
    if suffix in YAML_SUFFIXES:
        return TreeFormatKind.yaml
    if suffix in PY_SUFFIXES:
        return TreeFormatKind.python_cst
    if suffix in MD_SUFFIXES:
        return TreeFormatKind.markdown
    if suffix in TEXT_PLAIN_SUFFIXES:
        return TreeFormatKind.text
    raise ValueError(f"unsupported tree format for path: {file_path}")


def sidecar_path_for(file_path: str, project_root: Path) -> Path:
    """Return the absolute sidecar path for *file_path* under *project_root*.

    JSON and YAML use ``project_root/.trees/<rel>.tree`` (tree-temp layout).
    Python CST uses ``<parent>/.cst/<stem>.tree`` next to the source file.
    Markdown and plain text use adjacent ``<source>.tree_sidecar`` naming when
    no shared ``.trees/`` mirror exists for that format group.
    """
    rel = Path(file_path)
    kind = classify_tree_format(file_path)
    source_abs = (project_root / rel).resolve()
    if kind == TreeFormatKind.python_cst:
        return cast(Path, sidecar_path_for_py(source_abs))
    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        return cast(Path, resolve_trees_sidecar_path(project_root.resolve(), rel))
    return source_abs.with_name(source_abs.name + _ADJACENT_SIDECAR_SUFFIX)


def _compute_file_sha256_hex(source_abs: Path) -> str:
    digest = hashlib.sha256()
    with source_abs.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_tree_temp_root_stable_id(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = loads_sidecar(text)
    except (SidecarParseError, ValueError):
        return None
    if not doc.root_nodes:
        return None
    return cast(str, doc.root_nodes[0].stable_id)


def _read_tree_temp_digest(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = loads_sidecar(text)
    except (SidecarParseError, ValueError):
        return None
    return cast(str, doc.source_sha256)


def _read_cst_digest_and_root(
    source_abs: Path, sidecar_path: Path
) -> tuple[Optional[str], Optional[str]]:
    payload = read_sidecar_payload(source_abs)
    if payload is None:
        return None, None
    digest = payload.get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return None, None
    root_id = payload.get("root_node_id")
    root_stable_id = root_id if isinstance(root_id, str) and root_id else None
    if sidecar_path != sidecar_path_for_py(source_abs):
        return digest.lower(), root_stable_id
    return digest.lower(), root_stable_id


def _read_adjacent_sidecar_digest(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    digest = payload.get("source_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return None
    return digest.lower()


def _read_adjacent_root_stable_id(sidecar_path: Path) -> Optional[str]:
    try:
        text = sidecar_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    root_id = payload.get("root_stable_id")
    if isinstance(root_id, str) and root_id:
        return root_id
    root_nodes = payload.get("root")
    if isinstance(root_nodes, list) and root_nodes:
        first = root_nodes[0]
        if isinstance(first, dict):
            stable_id = first.get("stable_id")
            if isinstance(stable_id, str) and stable_id:
                return stable_id
    return None


def _read_sidecar_state(
    *,
    kind: TreeFormatKind,
    source_abs: Path,
    sidecar_path: Path,
) -> tuple[Optional[str], Optional[str]]:
    if not sidecar_path.is_file():
        return None, None
    if kind == TreeFormatKind.python_cst:
        return _read_cst_digest_and_root(source_abs, sidecar_path)
    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        digest = _read_tree_temp_digest(sidecar_path)
        root_id = _read_tree_temp_root_stable_id(sidecar_path)
        return digest, root_id
    digest = _read_adjacent_sidecar_digest(sidecar_path)
    root_id = _read_adjacent_root_stable_id(sidecar_path)
    return digest, root_id


def _recreate_tree_for_format(
    *,
    kind: TreeFormatKind,
    project_root: Path,
    file_path: str,
    source_abs: Path,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild a missing or stale sidecar via the indexer hook (not wired yet)."""
    raise NotImplementedError(
        f"tree recreation for format {kind.value!r} is not wired; "
        f"indexer must materialize sidecar for {file_path!r} under {project_root}"
    )


def validate_or_recreate_tree(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> TreeRepresentationRef:
    """Validate sidecar checksum against source SHA-256 or recreate when stale.

    When the sidecar is present and its ``source_sha256`` matches the current
    source file digest, returns a :class:`TreeRepresentationRef` without
    rebuilding. When the sidecar is missing, invalid, or *force* is True,
    delegates to :func:`_recreate_tree_for_format` (indexer hook; currently
    raises ``NotImplementedError`` until wired).
    """
    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content_checksum = _compute_file_sha256_hex(source_abs)
    sidecar_path = sidecar_path_for(file_path, root)

    if not force:
        sidecar_digest, root_stable_id = _read_sidecar_state(
            kind=kind,
            source_abs=source_abs,
            sidecar_path=sidecar_path,
        )
        if sidecar_digest is not None and sidecar_digest == content_checksum:
            return TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            )

    return _recreate_tree_for_format(
        kind=kind,
        project_root=root,
        file_path=file_path,
        source_abs=source_abs,
        content_checksum=content_checksum,
    )


__all__ = [
    "TreeFormatKind",
    "TreeRepresentationRef",
    "classify_tree_format",
    "sidecar_path_for",
    "validate_or_recreate_tree",
]
