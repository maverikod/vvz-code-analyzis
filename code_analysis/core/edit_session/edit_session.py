"""
EditSession entity: on-disk session directory and dual-mode edit lifecycle (C-012).

Distinct from ``commands.universal_file_edit.session`` (in-memory draft registry).
Supports FINAL-2 open, valid/invalid tree mutations, re-validation, and staged
external copy-out.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import difflib
import enum
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from code_analysis.core.edit_session.marker_cycle import (
    denude_marked_tree,
    restore_marked_tree,
)
from code_analysis.core.edit_session.session_history import SessionHistory
from code_analysis.core.edit_session.session_repo import SessionRepo
from code_analysis.core.search_session.tree_representation import sidecar_path_for
from code_analysis.core.tree_lifecycle import (
    compute_content_checksum,
    is_tree_valid,
    validate_or_recreate_tree_file,
)
from code_analysis.core.tree_lifecycle.node_id_map import (
    ChecksumsSection,
    DiscoveredNode,
    NodeIdMap,
    compute_content_fingerprint,
    parse_tree_file,
    serialize_tree_file,
)
from code_analysis.tree.edit_operations import EditOperation
from code_analysis.tree.handler_registry import HandlerRegistry


class SessionTreeValidity(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"


class EditSessionError(ValueError):
    """EditSession lifecycle violations."""


CONTENT_NOT_ALLOWED_FOR_VALID_FILE = "CONTENT_NOT_ALLOWED_FOR_VALID_FILE"

SESSION_VALID_TRUTH_INVARIANT = (
    "When tree_validity is valid, the in-session tree is truth; "
    "the external SourceFile is stale."
)
SESSION_INVALID_TRUTH_INVARIANT = (
    "When tree_validity is invalid, the in-session source copy is the editing surface."
)

#: Process-level registry; open registers, close removes (C-012, C-014).
_active_sessions: dict[str, EditSession] = {}


def _external_source_and_tree_valid(
    *,
    source_abs: Path,
    project_root: Path,
    file_path: str,
) -> bool:
    """Return True when external source parses and tree checksums align (FINAL-2)."""
    if not source_abs.is_file():
        return False
    external_text = source_abs.read_text(encoding="utf-8")
    try:
        HandlerRegistry.default_registry().resolve(source_abs).parse_content(
            Path(file_path),
            external_text,
        )
    except Exception:
        return False
    try:
        ref, _validity_state = validate_or_recreate_tree_file(
            project_root=project_root,
            file_path=file_path,
        )
    except Exception:
        return False
    ext_checksum = compute_content_checksum(external_text)
    return is_tree_valid(ext_checksum, ref.content_checksum)


@dataclass
class EditSession:
    """On-disk edit session with dual-mode valid/invalid tree lifecycle (C-012)."""

    session_id: str
    source_abs: Path
    tree_abs: Path
    session_dir: Path
    session_source_path: Path
    session_tree_path: Path
    session_repo_path: Path
    session_repo: SessionRepo
    project_root: Path
    file_path: str
    tree_validity: SessionTreeValidity
    source_checksum: str
    tree_checksum: Optional[str]
    is_open: bool = field(default=False)
    history: SessionHistory = field(default_factory=SessionHistory)

    @classmethod
    def open(
        cls,
        *,
        source_abs: Path,
        project_root: Path,
        file_path: str,
        content: Optional[str] = None,
    ) -> EditSession:
        if content is not None and source_abs.is_file():
            if _external_source_and_tree_valid(
                source_abs=source_abs,
                project_root=project_root,
                file_path=file_path,
            ):
                raise EditSessionError(
                    CONTENT_NOT_ALLOWED_FOR_VALID_FILE,
                    "content parameter not allowed when source and tree are valid",
                )

        session_id = str(uuid.uuid4())
        session_dir = source_abs.parent / f"{source_abs.name}-{session_id}"
        session_dir.mkdir(exist_ok=False)

        session_source_path = session_dir / source_abs.name
        if content is not None:
            session_source_path.write_text(content, encoding="utf-8")
        elif source_abs.is_file():
            shutil.copy2(source_abs, session_source_path)
        else:
            raise EditSessionError("SOURCE_MISSING")

        source_text = session_source_path.read_text(encoding="utf-8")
        source_checksum = compute_content_checksum(source_text)

        resolved_root = project_root.resolve()
        tree_abs = sidecar_path_for(file_path, resolved_root)
        ref_content_checksum: Optional[str] = None
        try:
            ref, _validity_state = validate_or_recreate_tree_file(
                project_root=project_root,
                file_path=file_path,
            )
            tree_abs = ref.sidecar_path
            ref_content_checksum = ref.content_checksum
        except Exception:
            ref_content_checksum = None

        session_tree_path = session_dir / tree_abs.name
        if tree_abs.is_file():
            shutil.copy2(tree_abs, session_tree_path)

        try:
            HandlerRegistry.default_registry().resolve(source_abs).parse_content(
                Path(file_path),
                source_text,
            )
            if (
                session_tree_path.is_file()
                and ref_content_checksum is not None
                and is_tree_valid(source_checksum, ref_content_checksum)
            ):
                tree_validity = SessionTreeValidity.VALID
            else:
                tree_validity = SessionTreeValidity.INVALID
        except Exception:
            tree_validity = SessionTreeValidity.INVALID

        session_repo_path = session_dir
        tree_checksum = (
            compute_content_checksum(session_tree_path.read_text(encoding="utf-8"))
            if session_tree_path.is_file()
            else None
        )

        include_tree = (
            tree_validity == SessionTreeValidity.VALID and session_tree_path.is_file()
        )
        session_repo = SessionRepo.init(
            repo_dir=session_dir,
            source_name=session_source_path.name,
            tree_name=session_tree_path.name,
            include_tree=include_tree,
            source_abs=source_abs,
        )
        history = SessionHistory()
        history.reset(session_repo.log()[-1].hash)

        session = cls(
            session_id=session_id,
            source_abs=source_abs,
            tree_abs=tree_abs,
            session_dir=session_dir,
            session_source_path=session_source_path,
            session_tree_path=session_tree_path,
            session_repo_path=session_repo_path,
            session_repo=session_repo,
            project_root=project_root,
            file_path=file_path,
            tree_validity=tree_validity,
            source_checksum=source_checksum,
            tree_checksum=tree_checksum,
            is_open=True,
            history=history,
        )
        _active_sessions[session_id] = session
        return session

    def apply_tree_operation(self, operation: EditOperation) -> None:
        """Apply one G-004 EditOperation on the in-session marked tree ({h008})."""
        from code_analysis.core.edit_session.edit_operations_adapter import (
            apply_edit_on_session_tree,
        )

        apply_edit_on_session_tree(self, operation)

    def apply_valid_tree_mutation(
        self,
        mutation_fn: Callable[[str], str],
    ) -> None:
        if not self.is_open or self.tree_validity != SessionTreeValidity.VALID:
            raise RuntimeError(
                "Valid-tree mutation requires open session with valid tree"
            )
        marked = self.session_tree_path.read_text(encoding="utf-8")
        denuded, state = denude_marked_tree(
            source_abs=self.source_abs,
            marked_tree=marked,
        )
        denuded_after = mutation_fn(denuded)
        restored = restore_marked_tree(
            source_abs=self.source_abs,
            denuded_after_mutation=denuded_after,
            state=state,
        )
        self.session_tree_path.write_text(restored, encoding="utf-8")
        self._post_mutation_full()

    def apply_plaintext_mutation(self, new_source_text: str) -> None:
        if not self.is_open or self.tree_validity != SessionTreeValidity.INVALID:
            raise RuntimeError(
                "Plaintext mutation requires open session with invalid tree"
            )
        self.session_source_path.write_text(new_source_text, encoding="utf-8")
        self.source_checksum = compute_content_checksum(new_source_text)
        self._post_mutation_degraded()
        self._try_revalidate()

    def apply_cst_sidecar_mutation(
        self,
        new_source_text: str,
        *,
        sidecar_abs: Path,
    ) -> None:
        """Sync session workspace after legacy CST ``write_sidecar_atomic`` edit."""
        if not self.is_open:
            raise RuntimeError("EditSession is not open")
        self.session_source_path.write_text(new_source_text, encoding="utf-8")
        shutil.copy2(sidecar_abs, self.session_tree_path)
        self.source_checksum = compute_content_checksum(new_source_text)
        self.tree_checksum = compute_content_checksum(
            self.session_tree_path.read_text(encoding="utf-8")
        )
        self.tree_validity = SessionTreeValidity.VALID
        self.session_repo.commit_full(message="session: mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _post_mutation_full(self) -> None:
        self._export_source_via_unmark()
        self.source_checksum = compute_content_checksum(
            self.session_source_path.read_text(encoding="utf-8")
        )
        self._update_session_tree_checksums(self.source_checksum)
        self.tree_checksum = compute_content_checksum(
            self.session_tree_path.read_text(encoding="utf-8")
        )
        self.session_repo.commit_full(message="session: mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _post_mutation_degraded(self) -> None:
        self.source_checksum = compute_content_checksum(
            self.session_source_path.read_text(encoding="utf-8")
        )
        self.tree_checksum = None
        self.session_repo.commit_degraded(message="session: plaintext mutation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def _record_history_commit(self, commit_hash: str) -> None:
        self.history.record(commit_hash)

    def _sync_state_after_checkout(self, *, mode: str) -> None:
        source_text = self.session_source_path.read_text(encoding="utf-8")
        self.source_checksum = compute_content_checksum(source_text)
        if mode == "full":
            self.tree_validity = SessionTreeValidity.VALID
            self.tree_checksum = (
                compute_content_checksum(
                    self.session_tree_path.read_text(encoding="utf-8")
                )
                if self.session_tree_path.is_file()
                else None
            )
            return
        self.tree_validity = SessionTreeValidity.INVALID
        self.tree_checksum = None

    def checkout_history_index(self, index: int) -> None:
        """Restore working artefacts to ``timeline[index]`` without a new commit."""
        if not self.is_open:
            raise RuntimeError("EditSession is not open")
        commit_hash = self.history.timeline[index]
        mode = self.session_repo.checkout_revision(rev=commit_hash)
        self._sync_state_after_checkout(mode=mode)
        self.history.move_to(index)

    def undo(self) -> dict[str, object]:
        """Step back one edit; classic undo without creating a commit."""
        if not self.is_open:
            raise RuntimeError("EditSession is not open")
        if not self.history.can_undo():
            raise RuntimeError("nothing to undo")
        target = self.history.undo_index()
        self.checkout_history_index(target)
        return self.history.snapshot()

    def redo(self) -> dict[str, object]:
        """Step forward one edit; classic redo without creating a commit."""
        if not self.is_open:
            raise RuntimeError("EditSession is not open")
        if not self.history.can_redo():
            raise RuntimeError("nothing to redo")
        target = self.history.redo_index()
        self.checkout_history_index(target)
        return self.history.snapshot()

    def record_revert_commit(self, *, rev: str) -> str:
        """Git-style revert: checkout ``rev`` and append a new tracked commit."""
        new_commit = self.session_repo.revert(rev=rev)
        self._sync_state_after_checkout(
            mode=(
                "full"
                if self.session_repo.revision_includes_tree(rev=new_commit)
                else "degraded"
            )
        )
        self._record_history_commit(new_commit)
        return new_commit

    def _export_source_via_unmark(self) -> None:
        handler = HandlerRegistry.default_registry().resolve(self.source_abs)
        sections = parse_tree_file(self.session_tree_path.read_text(encoding="utf-8"))
        clean = handler.unmark(sections.tree)
        self.session_source_path.write_text(clean, encoding="utf-8")

    def _update_session_tree_checksums(self, source_sha256: str) -> None:
        """Write fresh source_sha256 into CHECKSUMS section of session tree file."""
        tree_text = self.session_tree_path.read_text(encoding="utf-8")
        sections = parse_tree_file(tree_text)
        sections.checksums = {"source_sha256": source_sha256}
        updated = serialize_tree_file(sections)
        tmp = self.session_tree_path.with_suffix(self.session_tree_path.suffix + ".tmp")
        tmp.write_text(updated, encoding="utf-8")
        os.replace(tmp, self.session_tree_path)

    def _build_session_tree(self, source_text: str) -> bool:
        """Build marked tree in session dir using MAP from session tree file."""
        handler = HandlerRegistry.default_registry().resolve(self.source_abs)
        marked_text = handler.mark(source_text)
        nodes = handler.parse_content(Path(self.file_path), source_text)
        discovered: list[DiscoveredNode] = [
            DiscoveredNode(
                content_fingerprint=compute_content_fingerprint(node.content),
                kind=node.kind,
                marker_short_id=int(node.short_id),
                attributes=dict(node.attributes),
            )
            for node in nodes
        ]
        if not discovered:
            return False
        prior_map = None
        if self.session_tree_path.is_file():
            try:
                prior_map = parse_tree_file(
                    self.session_tree_path.read_text(encoding="utf-8")
                ).map
            except Exception:
                prior_map = None
        checksums: ChecksumsSection = {"source_sha256": self.source_checksum}
        sections, node_map = NodeIdMap.build(
            tree_marked_text=marked_text,
            discovered_nodes=discovered,
            source_sha256=self.source_checksum,
            prior_map=prior_map,
        )
        if prior_map is not None:
            sections = node_map.validate_and_repair(
                tree_marked_text=marked_text,
                discovered_nodes=discovered,
                checksums=checksums,
            )
        file_text = serialize_tree_file(sections)
        tmp = self.session_tree_path.with_suffix(self.session_tree_path.suffix + ".tmp")
        tmp.write_text(file_text, encoding="utf-8")
        os.replace(tmp, self.session_tree_path)
        return True

    def _try_revalidate(self) -> None:
        if self.tree_validity != SessionTreeValidity.INVALID:
            return
        source_text = self.session_source_path.read_text(encoding="utf-8")
        try:
            HandlerRegistry.default_registry().resolve(self.source_abs).parse_content(
                Path(self.file_path),
                source_text,
            )
        except Exception:
            return
        if not self._build_session_tree(source_text):
            return
        self._export_source_via_unmark()
        self.source_checksum = compute_content_checksum(
            self.session_source_path.read_text(encoding="utf-8")
        )
        self._update_session_tree_checksums(self.source_checksum)
        self.tree_validity = SessionTreeValidity.VALID
        self.tree_checksum = compute_content_checksum(
            self.session_tree_path.read_text(encoding="utf-8")
        )
        self.session_repo.commit_full(message="session: revalidation")
        self._record_history_commit(self.session_repo.log()[0].hash)

    def preview_external_write(self) -> dict[str, Any]:
        """Compute unified diffs of in-session artefacts vs live external files; no external writes."""
        if not self.is_open:
            raise RuntimeError(
                "EditSession is not open; cannot preview external write."
            )
        in_source = (
            self.session_source_path.read_text(encoding="utf-8")
            if self.session_source_path.is_file()
            else ""
        )
        in_tree = (
            self.session_tree_path.read_text(encoding="utf-8")
            if self.session_tree_path.is_file()
            else ""
        )
        ext_source = (
            self.source_abs.read_text(encoding="utf-8")
            if self.source_abs.is_file()
            else ""
        )
        ext_tree = (
            self.tree_abs.read_text(encoding="utf-8") if self.tree_abs.is_file() else ""
        )
        source_diff = "".join(
            difflib.unified_diff(
                in_source.splitlines(keepends=True),
                ext_source.splitlines(keepends=True),
                fromfile="in-session-source",
                tofile="external-source",
            )
        )
        tree_diff = "".join(
            difflib.unified_diff(
                in_tree.splitlines(keepends=True),
                ext_tree.splitlines(keepends=True),
                fromfile="in-session-tree",
                tofile="external-tree",
            )
        )
        has_changes = bool(source_diff.strip() or tree_diff.strip())
        return {
            "has_changes": has_changes,
            "source_diff": source_diff,
            "tree_diff": tree_diff,
        }

    def confirm_external_copy_out(self) -> None:
        """Atomically copy in-session artefacts to external co-located paths; both or neither when valid."""
        if not self.is_open:
            raise RuntimeError(
                "EditSession is not open; cannot confirm external copy-out."
            )
        preview = self.preview_external_write()
        if not preview["has_changes"]:
            return
        if self.tree_validity == SessionTreeValidity.VALID:
            if (
                not self.session_tree_path.is_file()
                or not self.session_source_path.is_file()
            ):
                raise RuntimeError("Session artefacts missing for external copy-out")
            tmp_tree = self.tree_abs.with_suffix(self.tree_abs.suffix + ".tmp")
            tmp_source = self.source_abs.with_suffix(self.source_abs.suffix + ".tmp")
            backup_tree = self.tree_abs.with_suffix(self.tree_abs.suffix + ".bak")
            try:
                shutil.copy2(self.session_tree_path, tmp_tree)
                shutil.copy2(self.session_source_path, tmp_source)
                if self.tree_abs.exists():
                    shutil.copy2(self.tree_abs, backup_tree)
                tmp_tree.replace(self.tree_abs)
                try:
                    tmp_source.replace(self.source_abs)
                except Exception:
                    if backup_tree.exists():
                        shutil.copy2(backup_tree, self.tree_abs)
                    raise
            except Exception:
                tmp_tree.unlink(missing_ok=True)
                tmp_source.unlink(missing_ok=True)
                raise
            finally:
                backup_tree.unlink(missing_ok=True)
        else:
            tmp_source = self.source_abs.with_suffix(self.source_abs.suffix + ".tmp")
            try:
                shutil.copy2(self.session_source_path, tmp_source)
                tmp_source.replace(self.source_abs)
            except Exception:
                tmp_source.unlink(missing_ok=True)
                raise

    def close(self) -> None:
        _active_sessions.pop(self.session_id, None)
        if self.session_dir.exists():
            shutil.rmtree(self.session_dir)
        self.is_open = False

    def record_tree_modification(self) -> None:
        raise RuntimeError("use apply_valid_tree_mutation or apply_tree_operation")


def get_active_session(session_id: str) -> EditSession:
    """Resolve live EditSession; KeyError if absent (no sessionless access)."""
    try:
        return _active_sessions[session_id]
    except KeyError as exc:
        raise KeyError(f"No active edit session: {session_id}") from exc
