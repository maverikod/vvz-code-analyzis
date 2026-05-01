"""
Pure verification helpers before/after CST tree save (snapshot, replay, read-back).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping, MutableMapping, Sequence, cast

from .models import CSTTree, TreeOperation
from .tree_builder import create_tree_from_code, get_tree, remove_tree
from .tree_modifier import modify_tree

FILE_CHANGED_SINCE_LOAD = "FILE_CHANGED_SINCE_LOAD"
CST_REPLAY_MISMATCH = "CST_REPLAY_MISMATCH"
WRITE_VERIFY_FAILED = "WRITE_VERIFY_FAILED"


class SaveVerificationError(Exception):
    """Raised when a save-time verification invariant fails."""

    def __init__(
        self, *, code: str, details: Mapping[str, object] | None = None
    ) -> None:
        self.code = code
        self.details: dict[str, object] = dict(details) if details is not None else {}
        super().__init__(code)


def _replay_operations_produce_code_at_path(
    original_source: str,
    tree_operations: Sequence[TreeOperation],
    replay_file_path: str,
) -> str:
    replay_tree = create_tree_from_code(replay_file_path, original_source)
    new_id = replay_tree.tree_id
    try:
        modify_tree(new_id, list(tree_operations))
        final = get_tree(new_id)
        if final is None:
            raise SaveVerificationError(
                code=CST_REPLAY_MISMATCH,
                details={
                    "reason": "replay_tree_missing_after_modify",
                    "tree_id": new_id,
                    "replay_file_path": replay_file_path,
                },
            )
        return cast(str, final.module.code)
    finally:
        remove_tree(new_id)


def disk_matches_tree_snapshot(target_path: Path, tree: CSTTree) -> bool:
    """
    Compare current disk UTF-8 bytes (sha256 + length) with the snapshot on ``tree``.

    Returns False when the snapshot is absent, when the path is unreadable, or when
    the digest/size do not match.
    """
    snapshot_hex = tree.disk_source_sha256_hex
    if snapshot_hex is None:
        return False
    path = Path(target_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    raw = text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return bool(digest == snapshot_hex and len(raw) == tree.disk_source_length)


def assert_disk_matches_tree_snapshot(target_path: Path, tree: CSTTree) -> None:
    """Raise SaveVerificationError if the file on disk no longer matches the load snapshot."""
    if disk_matches_tree_snapshot(target_path, tree):
        return
    path = Path(target_path)
    snapshot_hex = tree.disk_source_sha256_hex
    snapshot_len = tree.disk_source_length
    disk_hex: str | None = None
    disk_len: int | None = None
    read_error: str | None = None
    try:
        text = path.read_text(encoding="utf-8")
        raw = text.encode("utf-8")
        disk_hex = hashlib.sha256(raw).hexdigest()
        disk_len = len(raw)
    except OSError as exc:
        read_error = str(exc)
    details: MutableMapping[str, object] = {
        "target_path": str(path),
        "snapshot_sha256_hex": snapshot_hex,
        "snapshot_length": snapshot_len,
    }
    if disk_hex is not None:
        details["disk_sha256_hex"] = disk_hex
    if disk_len is not None:
        details["disk_length"] = disk_len
    if read_error is not None:
        details["read_error"] = read_error
    raise SaveVerificationError(code=FILE_CHANGED_SINCE_LOAD, details=dict(details))


def replay_operations_produce_code(
    original_source: str,
    tree_operations: Sequence[TreeOperation],
) -> str:
    """Parse ``original_source``, apply ``tree_operations`` on a fresh tree; return serialized code."""
    stub = str(Path("_cst_save_verification_replay_stub.py").resolve())
    return _replay_operations_produce_code_at_path(
        original_source, tree_operations, stub
    )


def assert_replay_matches(
    *,
    original_source: str,
    target_path: Path,
    tree: CSTTree,
    tree_operations: Sequence[TreeOperation],
) -> None:
    """
    Replay the same edits on ``original_source`` and require the result equals ``tree.module.code``.
    Removes the temporary replay tree from ``_trees`` via try/finally.
    """
    replayed = _replay_operations_produce_code_at_path(
        original_source, tree_operations, str(target_path)
    )
    working = cast(str, tree.module.code)
    if replayed == working:
        return
    raise SaveVerificationError(
        code=CST_REPLAY_MISMATCH,
        details={
            "target_path": str(Path(target_path)),
            "replay_length": len(replayed),
            "working_length": len(working),
        },
    )


def assert_file_bytes_match(*, target_path: Path, expected: str) -> None:
    """After atomic replace: require ``read_text`` matches ``expected`` (UTF-8, strict equality)."""
    actual = Path(target_path).read_text(encoding="utf-8")
    if actual == expected:
        return
    raise SaveVerificationError(
        code=WRITE_VERIFY_FAILED,
        details={
            "target_path": str(Path(target_path)),
            "expected_length": len(expected),
            "actual_length": len(actual),
        },
    )
