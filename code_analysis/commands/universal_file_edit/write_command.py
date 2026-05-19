"""
UniversalFileWriteCommand: two-phase write with diff and lockfile.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Type, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.commands.universal_file_edit.errors import (
    SESSION_NOT_FOUND,
    WRITE_FAILED,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TREE_TEMP,
    delete_lockfile,
    read_lockfile_pid,
    write_lockfile_pid,
)
from code_analysis.commands.universal_file_edit.session import EditSession, get_session
from code_analysis.commands.universal_file_edit.tree_temp_write_commit import (
    build_tree_temp_preview_text,
    commit_tree_temp_to_disk,
    serialize_tree_temp_session_source,
)
from code_analysis.commands.universal_file_edit.write_command_metadata import (
    get_universal_file_write_metadata,
)
from code_analysis.core.backup_manager import BackupManager
from code_analysis.core.cst_tree.node_stable_id import (
    strip_inline_node_id_lines_from_source,
)
from code_analysis.core.cst_tree.tree_builder import get_tree as get_cst_tree
from code_analysis.core.exceptions import ValidationError
from code_analysis.core.file_handlers.diff_support import unified_diff_text
from code_analysis.core.git_integration import commit_after_write
from code_analysis.commands.universal_file_edit.invalid_write_support import (
    try_clear_invalid_after_write,
)


class UniversalFileWriteCommand(BaseMCPCommand):
    """MCP command implementing the two-phase write protocol.

    Tree-temp uses explicit preview vs commit; other groups use PID lockfile two-phase.

    """

    name = "universal_file_write"

    version = "1.0.0"

    descr = (
        "Write universal file edit draft: preview/commit for tree-temp; "
        "two-phase PID lockfile for sidecar/text."
    )

    category = "file_management"

    author = "Vasiliy Zdanovskiy"

    email = "vasilyvz@gmail.com"

    use_queue = False

    @staticmethod
    def get_name() -> str:
        """Return the MCP command name.

        Returns:
            MCP command name string.
        """
        return "universal_file_write"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and session_id.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "session_id": {"type": "string"},
                "write_mode": {
                    "type": "string",
                    "enum": ["preview", "commit"],
                    "default": "preview",
                    "description": (
                        "Tree-temp only: preview returns a diff without writing or "
                        "lockfile side effects; commit persists source and sidecar. "
                        "Ignored for sidecar/text (two-phase PID protocol)."
                    ),
                },
            },
            "required": ["project_id", "session_id"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate optional write_mode."""
        params = super().validate_params(params)
        wm = params.get("write_mode", "preview")
        if wm not in ("preview", "commit"):
            raise ValidationError(
                "write_mode must be 'preview' or 'commit'",
                field="write_mode",
                details={"write_mode": wm},
            )
        params["write_mode"] = wm
        return params

    @classmethod
    def metadata(cls: Type["UniversalFileWriteCommand"]) -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_write.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_write_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        session_id: str,
        write_mode: str = "preview",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Execute the write command.

        First call (no matching lockfile): generate diff, write lockfile, return diff.
        Second call (lockfile matches current pid + session_id): commit to disk.

        Args:
            project_id: Project UUID.
            session_id: Active session identifier.
            write_mode: For tree-temp: preview vs commit; ignored otherwise.
            **kwargs: Adapter context.

        Returns:
            Preview or committed-phase result with diff, or ErrorResult.
        """
        _ = kwargs
        try:
            session = get_session(session_id)
        except ValueError:
            return error_result_from_make_error(
                make_error(SESSION_NOT_FOUND, f"Unknown session: {session_id}")
            )

        if session.format_group == FORMAT_TREE_TEMP:
            if write_mode == "preview":
                return self._tree_temp_preview(session)
            return self._tree_temp_write_commit(session, project_id)

        current_pid = os.getpid()
        lock = read_lockfile_pid(session.abs_path)
        is_second_call = (
            lock is not None
            and lock[0] == current_pid
            and lock[1] == session.session_id
        )
        if is_second_call:
            return self._second_call(session, project_id)
        return self._first_call(session, current_pid)

    def _tree_temp_preview(self, session: EditSession) -> SuccessResult | ErrorResult:
        """Tree-temp preview: unified diff vs disk without lockfile or writes."""
        try:
            code = build_tree_temp_preview_text(
                abs_path=session.abs_path,
                session=session,
            )
        except Exception as exc:
            return error_result_from_make_error(
                make_error(WRITE_FAILED, f"Preview generation failed: {exc}")
            )
        original = session.abs_path.read_text(encoding="utf-8")
        diff = unified_diff_text(
            original,
            code,
            before_label=str(session.abs_path),
            after_label=str(session.abs_path),
        )
        return SuccessResult(
            data={
                "success": True,
                "phase": "preview",
                "write_mode": "preview",
                "diff": diff,
            }
        )

    def _tree_temp_write_commit(
        self, session: EditSession, project_id: str
    ) -> SuccessResult | ErrorResult:
        """Tree-temp commit: backup, atomic source + optional sidecar, git hook."""
        fp_parts = Path(session.file_path).parts
        root_dir = session.abs_path.parents[len(fp_parts) - 1]
        rel = session.abs_path.relative_to(root_dir)
        rel_str = str(rel)
        bm = BackupManager(root_dir)
        bm.create_backup(session.abs_path, command="universal_file_write")
        try:
            sha_hex, diff = commit_tree_temp_to_disk(
                session=session,
                project_id=project_id,
                bm=bm,
                rel_str=rel_str,
            )
        except ValueError as exc:
            bm.restore_file(rel_str)
            return error_result_from_make_error(make_error(WRITE_FAILED, str(exc)))
        except OSError as exc:
            bm.restore_file(rel_str)
            return error_result_from_make_error(
                make_error(WRITE_FAILED, f"Write failed: {exc}")
            )

        delete_lockfile(session.abs_path)
        try_clear_invalid_after_write(session)
        try:
            commit_after_write(
                root_dir,
                [rel],
                command_name="universal_file_write",
                config_data={},
            )
        except Exception:
            pass
        return SuccessResult(
            data={
                "success": True,
                "phase": "committed",
                "write_mode": "commit",
                "diff": diff,
                "source_sha256_at_open": sha_hex,
                "is_invalid": session.is_invalid,
            }
        )

    def _generate_code(self, session: EditSession) -> str:
        """Generate source code from the draft file.

        Args:
            session: Active EditSession with format_group and draft_path.

        Returns:
            Generated source code as a string.
        """
        fg = session.format_group
        if fg == FORMAT_SIDECAR:
            tid = session.tree_id
            if not tid:
                raise ValueError(
                    "Session has no registered tree id for sidecar format.",
                )
            tree = get_cst_tree(tid)
            if tree is None:
                raise ValueError(
                    f"CST tree {tid!r} not found in memory.",
                )
            return cast(
                str,
                strip_inline_node_id_lines_from_source(str(tree.module.code)),
            )
        if fg == FORMAT_TREE_TEMP:
            return serialize_tree_temp_session_source(session)
        return str(session.draft_path.read_text())

    def _first_call(
        self, session: EditSession, current_pid: int
    ) -> SuccessResult | ErrorResult:
        """Handle first write call: generate code, compute diff, write lockfile.

        Args:
            session: Active EditSession.
            current_pid: Current server process PID.

        Returns:
            SuccessResult with diff string showing changes.
        """
        code = self._generate_code(session)
        original = session.abs_path.read_text()
        diff = unified_diff_text(
            original,
            code,
            before_label=str(session.abs_path),
            after_label=str(session.abs_path),
        )
        write_lockfile_pid(session.abs_path, current_pid, session.session_id)
        return SuccessResult(data={"success": True, "phase": "preview", "diff": diff})

    def _second_call(
        self, session: EditSession, _project_id: str
    ) -> SuccessResult | ErrorResult:
        """Handle second write call: backup, commit, cleanup.

        Args:
            session: Active EditSession.
            _project_id: Reserved for callers that delegate path helpers (unused here).

        Returns:
            SuccessResult with success flag and committed-phase diff.
        """
        _ = _project_id
        fp_parts = Path(session.file_path).parts
        root_dir = session.abs_path.parents[len(fp_parts) - 1]
        rel = session.abs_path.relative_to(root_dir)
        rel_str = str(rel)
        bm = BackupManager(root_dir)
        bm.create_backup(session.abs_path, command="universal_file_write")
        original_content = session.abs_path.read_text()
        try:
            code = self._generate_code(session)
        except Exception as exc:
            bm.restore_file(rel_str)
            return error_result_from_make_error(
                make_error(WRITE_FAILED, f"Code generation failed: {exc}")
            )
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=session.abs_path.suffix,
                dir=str(session.abs_path.parent),
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            os.replace(tmp_path, str(session.abs_path))
        except OSError as exc:
            bm.restore_file(rel_str)
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)
            return error_result_from_make_error(
                make_error(WRITE_FAILED, f"Write failed: {exc}")
            )

        delete_lockfile(session.abs_path)
        diff = unified_diff_text(
            original_content,
            code,
            before_label=str(session.abs_path),
            after_label=str(session.abs_path),
        )
        try_clear_invalid_after_write(session)
        try:
            commit_after_write(
                root_dir,
                [rel],
                command_name="universal_file_write",
                config_data={},
            )
        except Exception:
            pass
        return SuccessResult(
            data={
                "success": True,
                "phase": "committed",
                "diff": diff,
                "is_invalid": session.is_invalid,
            }
        )
