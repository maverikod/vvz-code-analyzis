"""
Centralized tree-lifecycle: checksum + validate + recreate.

This module owns ONE responsibility: "is there a valid tree (sidecar) for this
content; if not, build it". Every consumer that needs a structurally valid tree
(preview, grep, watcher, indexer, edit sessions, builders) routes through here
so the rule lives in a single place.

Design:
- The CORE works on CONTENT (strings), not file paths. Builders and edit
  sessions that already hold the source text in memory call the core directly,
  avoiding a redundant file read.
- A thin FILE wrapper sits on top: it reads the source once, computes the
  checksum, reads the sidecar digest, and delegates to the core.

Representation building (turning a valid tree into a preview/structure) is NOT
this module's job — that stays in ``tree_representation``. This module only
guarantees the tree is valid and rebuilds it when stale.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from code_analysis.core.search_session.tree_representation import (
    TreeFormatKind,
    TreeRepresentationRef,
    TreeValidityState,
    classify_tree_format,
    sidecar_path_for,
)


def compute_content_checksum(content: str) -> str:
    """Return the SHA-256 hex digest of *content*.

    This is the content-based counterpart of hashing a file: callers that hold
    the source text in memory hash it directly, without touching disk.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def is_tree_valid(content_checksum: str, sidecar_digest: str | None) -> bool:
    """Return True when a sidecar digest exists and matches the content checksum."""
    return sidecar_digest is not None and sidecar_digest == content_checksum


def recreate_tree_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    content_checksum: str,
) -> TreeRepresentationRef:
    """Rebuild the sidecar tree for *content* using the per-format tree builders.

    Takes the already-in-memory ``content`` instead of re-reading the file, so a
    caller that just hashed the content does not pay a second read. Writes the
    sidecar atomically and returns a validated reference.
    """
    # Local imports break a module-load cycle with tree_representation and keep
    # the per-format builder dependencies lazy (heavy modules).
    if kind == TreeFormatKind.python_cst:
        from code_analysis.core.cst_tree.tree_builder import create_tree_from_code
        from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic
        from code_analysis.core.search_session.tree_representation import (
            _read_cst_digest_and_root,
        )

        create_tree_from_code(str(source_abs), content, persist_sidecar=True)
        if not sidecar_path.is_file():
            write_sidecar_atomic(source_abs, {"source_sha256": content_checksum})
        _digest, root_stable_id = _read_cst_digest_and_root(source_abs, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=root_stable_id,
        )

    if kind in {TreeFormatKind.json, TreeFormatKind.yaml}:
        from code_analysis.core.tree_temp.sidecar_payload import (
            serialize_sidecar_to_json_text,
        )
        from code_analysis.core.search_session.tree_representation import (
            _read_tree_temp_root_stable_id,
        )

        if kind == TreeFormatKind.json:
            from code_analysis.core.json_tree.tree_builder import build_tree_from_data

            data = json.loads(content)
            tree = build_tree_from_data(data, source_path=str(source_abs))
        else:
            import yaml as _yaml

            from code_analysis.core.yaml_tree.tree_builder import (
                build_yaml_tree_from_data,
            )

            data = _yaml.safe_load(content)
            tree = build_yaml_tree_from_data(data, source_path=str(source_abs))

        sidecar_text = serialize_sidecar_to_json_text(
            tree, source_sha256=content_checksum
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
        tmp.write_text(sidecar_text, encoding="utf-8")
        os.replace(tmp, sidecar_path)
        return TreeRepresentationRef(
            file_path=file_path,
            sidecar_path=sidecar_path,
            content_checksum=content_checksum,
            root_stable_id=_read_tree_temp_root_stable_id(sidecar_path),
        )

    # markdown or plain text — adjacent .tree_sidecar
    from code_analysis.core.structure_extraction.extractor import extract_structure
    from code_analysis.core.search_session.tree_representation import (
        _read_adjacent_root_stable_id,
    )

    extract_structure(str(source_abs), ensure_persisted_tree=True)
    payload: dict = {"source_sha256": content_checksum}
    root_stable_id = _read_adjacent_root_stable_id(sidecar_path)
    if root_stable_id is not None:
        payload["root_stable_id"] = root_stable_id
    tmp = sidecar_path.with_suffix(sidecar_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar_path)
    return TreeRepresentationRef(
        file_path=file_path,
        sidecar_path=sidecar_path,
        content_checksum=content_checksum,
        root_stable_id=root_stable_id,
    )


def validate_or_recreate_from_content(
    *,
    kind: TreeFormatKind,
    content: str,
    source_abs: Path,
    sidecar_path: Path,
    file_path: str,
    sidecar_digest: str | None,
    root_stable_id: str | None,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """Decide reuse vs recreate for already-in-memory *content*.

    The caller supplies the current sidecar digest (and root stable id) it has
    already read. When the digest matches the content checksum and ``force`` is
    false, the existing sidecar is reused; otherwise the tree is rebuilt.
    """
    content_checksum = compute_content_checksum(content)
    if not force and is_tree_valid(content_checksum, sidecar_digest):
        return (
            TreeRepresentationRef(
                file_path=file_path,
                sidecar_path=sidecar_path,
                content_checksum=content_checksum,
                root_stable_id=root_stable_id,
            ),
            TreeValidityState.reused,
        )
    ref = recreate_tree_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        content_checksum=content_checksum,
    )
    return ref, TreeValidityState.recreated


def validate_or_recreate_tree_file(
    *,
    project_root: Path,
    file_path: str,
    force: bool = False,
) -> tuple[TreeRepresentationRef, TreeValidityState]:
    """File wrapper over the content core.

    Reads the source once, computes its checksum, reads the current sidecar
    digest, then delegates to ``validate_or_recreate_from_content``. This is the
    entry point for path-based consumers (preview, grep, watcher).

    Raises FileNotFoundError when the source file is absent.
    """
    from code_analysis.core.search_session.tree_representation import (
        _read_sidecar_state,
    )

    kind = classify_tree_format(file_path)
    root = project_root.resolve()
    source_abs = (root / file_path).resolve()
    if not source_abs.is_file():
        raise FileNotFoundError(f"source file not found: {source_abs}")
    content = source_abs.read_text(encoding="utf-8")
    sidecar_path = sidecar_path_for(file_path, root)
    sidecar_digest, root_stable_id = _read_sidecar_state(
        kind=kind, source_abs=source_abs, sidecar_path=sidecar_path
    )
    return validate_or_recreate_from_content(
        kind=kind,
        content=content,
        source_abs=source_abs,
        sidecar_path=sidecar_path,
        file_path=file_path,
        sidecar_digest=sidecar_digest,
        root_stable_id=root_stable_id,
        force=force,
    )


__all__ = [
    "compute_content_checksum",
    "is_tree_valid",
    "recreate_tree_from_content",
    "validate_or_recreate_from_content",
    "validate_or_recreate_tree_file",
]
