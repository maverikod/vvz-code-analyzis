"""
UniversalFileOpenCommand: starts an editing session for one file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Union, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from code_analysis.commands.base_mcp_command import BaseMCPCommand
from code_analysis.core.exceptions import ValidationError
from code_analysis.commands.universal_file_edit.errors import (
    PARSE_ERROR,
    UNKNOWN_FORMAT,
    error_result_from_make_error,
    make_error,
)
from code_analysis.commands.universal_file_edit.format_group import (
    FORMAT_SIDECAR,
    FORMAT_TEXT,
    FORMAT_TREE_TEMP,
    FormatDescriptor,
    check_lock,
    delete_lockfile,
    draft_path_for,
    lockfile_path_for,
    resolve_format_group,
)
from code_analysis.commands.universal_file_edit.open_command_metadata import (
    get_universal_file_open_metadata,
)
from code_analysis.commands.universal_file_edit.session import (
    active_session_uses_abs_path,
    create_session,
)
from code_analysis.commands.universal_file_edit.tree_temp_open_support import (
    acquire_tree_temp_for_open,
)


class UniversalFileOpenCommand(BaseMCPCommand):
    """MCP command that starts an editing session for one file.

    Cleans stale artefacts, creates draft, creates initial backup when
    file has no history, registers session, returns session_id.
    """

    name = "universal_file_open"
    version = "1.0.0"
    descr = "Open a project file for universal edit-session workflow."
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
        return "universal_file_open"

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the JSON schema for command parameters.

        Returns:
            JSON schema dict describing project_id and file_path parameters.
        """
        return {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "file_path": {"type": "string"},
                "create": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When True, create the file if it does not exist. "
                        "Requires initial_content for Python files (.py). "
                        "For all other formats creates an empty file."
                    ),
                },
                "initial_content": {
                    "type": "string",
                    "description": (
                        "Initial file content used only when create=True. "
                        "For Python (.py): valid Python source code written to disk "
                        "before the CST tree is built via load_file_to_tree. "
                        "For other formats: ignored (file is created empty)."
                    ),
                },
            },
            "required": ["project_id", "file_path"],
            "additionalProperties": False,
        }

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters; require initial_content for new .py files."""
        params = super().validate_params(params)
        if params.get("create"):
            file_path = str(params.get("file_path", ""))
            if Path(file_path).suffix == ".py":
                content = params.get("initial_content")
                if content is None or content == "":
                    raise ValidationError(
                        "initial_content is required when create=True for .py files",
                        field="initial_content",
                        details={"file_path": file_path},
                    )
        return params

    @classmethod
    def metadata(cls: "type[UniversalFileOpenCommand]") -> Dict[str, Any]:
        """Return extended AI/docs metadata for universal_file_open.

        Returns:
            Metadata dict with description, parameters, examples, errors.
        """
        return cast(Dict[str, Any], get_universal_file_open_metadata(cls))

    async def execute(  # type: ignore[override]
        self,
        project_id: str,
        file_path: str,
        create: bool = False,
        initial_content: str = "",
        **kwargs: Any,
    ) -> Union[SuccessResult, ErrorResult]:
        """Execute the open command.

        Args:
            project_id: Project UUID.
            file_path: Path relative to project root.
            create: When True, create the file if it does not exist.
            initial_content: Initial source for new .py files (create=True).
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with session_id, format_group, and available_operations,
            or ErrorResult on failure. When a parse error triggers text-mode
            fallback, the response also includes fallback_reason and
            original_format_group.
        """
        abs_path = self._resolve_abs_path(project_id, file_path)
        if abs_path is None:
            return error_result_from_make_error(
                make_error(UNKNOWN_FORMAT, f"Cannot resolve path: {file_path}")
            )

        # Check lock before any file operations.
        if abs_path.exists():
            lock_owner = check_lock(abs_path, "")
            if lock_owner:
                return error_result_from_make_error(
                    make_error(PARSE_ERROR, f"File is locked by session {lock_owner}")
                )
        if active_session_uses_abs_path(abs_path):
            return error_result_from_make_error(
                make_error(
                    PARSE_ERROR,
                    "Another edit session is already open for this file.",
                )
            )

        created = False
        if not abs_path.exists():
            if not create:
                return error_result_from_make_error(
                    make_error(PARSE_ERROR, f"File not found: {file_path}")
                )
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            suffix = abs_path.suffix.lower()
            if suffix == ".py":
                abs_path.write_text(initial_content, encoding="utf-8")
            elif suffix == ".json":
                abs_path.write_text("{}\n", encoding="utf-8")
            elif suffix in (".yaml", ".yml"):
                abs_path.write_text("{}\n", encoding="utf-8")
            else:
                abs_path.write_text("", encoding="utf-8")
            created = True

        cleanup_result = self._cleanup_stale(abs_path)
        if cleanup_result is not None:
            return error_result_from_make_error(cleanup_result)

        descriptor_result = self._resolve_and_create_draft(abs_path, project_id)
        if isinstance(descriptor_result, dict):
            return error_result_from_make_error(descriptor_result)
        descriptor: FormatDescriptor = descriptor_result

        self._create_initial_backup(project_id, abs_path)
        fallback_info: Optional[Dict[str, str]] = descriptor.__dict__.pop(
            "_fallback_info", None
        )
        tree_temp_kwargs = descriptor.__dict__.pop("_tree_temp_session_kwargs", None)
        tree_id: Optional[str] = getattr(descriptor, "tree_id", None)
        session_extra: Dict[str, Any] = {}
        if fallback_info is not None:
            session_extra["fallback_reason"] = fallback_info["fallback_reason"]
            session_extra["original_format_group"] = fallback_info[
                "original_format_group"
            ]
            session_extra["is_invalid"] = fallback_info.get("is_invalid", False)
        if tree_temp_kwargs is not None:
            session = create_session(
                abs_path=abs_path,
                descriptor=descriptor,
                file_path=file_path,
                **tree_temp_kwargs,
                **session_extra,
            )
        else:
            session = create_session(
                abs_path=abs_path,
                descriptor=descriptor,
                file_path=file_path,
                tree_id=tree_id,
                **session_extra,
            )
        data: Dict[str, Any] = {
            "success": True,
            "session_id": session.session_id,
            "available_operations": descriptor.available_operations,
            "format_group": descriptor.format_group,
        }
        if created:
            data["created"] = True
        if fallback_info is not None:
            data["fallback_reason"] = fallback_info["fallback_reason"]
            data["original_format_group"] = fallback_info["original_format_group"]
        if session.is_invalid:
            data["is_invalid"] = True
        return SuccessResult(data=data)

    def _resolve_abs_path(self, project_id: str, file_path: str) -> Optional[Path]:
        """Resolve file_path to an absolute Path using the project root.

        Args:
            project_id: UUID of the project.
            file_path: Project-relative path to the file.

        Returns:
            Absolute Path if resolution succeeds, None otherwise.
        """
        try:
            root = BaseMCPCommand._resolve_project_root(project_id)
            return (Path(root) / file_path).resolve()
        except Exception:
            return None

    def _cleanup_stale(self, abs_path: Path) -> Optional[Dict[str, Any]]:
        """Delete stale write lockfile and stale draft (not sidecar).

        For Python files the sidecar is left intact; only the write
        lockfile is removed on open.

        Args:
            abs_path: Absolute path to the original file.

        Returns:
            None on success; an error dict if an unexpected error occurs.
        """
        try:
            delete_lockfile(abs_path)
            draft = abs_path.with_suffix(abs_path.suffix + ".draft")
            draft.unlink(missing_ok=True)
            return None
        except OSError as exc:
            return cast(
                Dict[str, Any], make_error(PARSE_ERROR, f"Cleanup failed: {exc}")
            )

    def _resolve_and_create_draft(
        self,
        abs_path: Path,
        project_id: str,
    ) -> Union[FormatDescriptor, Dict[str, Any]]:
        """Resolve format group and create the draft file.

        For tree-temp formats (JSON/YAML), if the file cannot be parsed,
        falls back to text-mode transparently. The returned descriptor has
        ``_fallback_info`` so ``execute`` can record ``fallback_reason`` and
        ``original_format_group`` in the session and response.

        Args:
            abs_path: Absolute path to the original file.
            project_id: Project UUID (needed for tree-temp sidecar resolution).

        Returns:
            FormatDescriptor on success, or an error dict on unrecoverable failure.
        """
        try:
            descriptor = resolve_format_group(abs_path)
        except ValueError:
            return make_error(
                UNKNOWN_FORMAT,
                f"Unsupported file type: {abs_path.suffix}",
            )

        original_fg = descriptor.format_group
        try:
            tree_id = self._write_draft(abs_path, descriptor, project_id)
            descriptor.__dict__["tree_id"] = tree_id
        except Exception as exc:
            # Fall back to text-mode so broken source remains editable.
            if original_fg in (FORMAT_TREE_TEMP, FORMAT_SIDECAR):
                try:
                    text_descriptor = FormatDescriptor(
                        format_group=FORMAT_TEXT,
                        handler_id="text",
                        draft_path=draft_path_for(abs_path, FORMAT_TEXT),
                        lockfile_path=lockfile_path_for(abs_path),
                        available_operations=["insert", "delete", "replace"],
                    )
                    shutil.copy2(str(abs_path), str(text_descriptor.draft_path))
                    text_descriptor.__dict__["tree_id"] = None
                    text_descriptor.__dict__["_fallback_info"] = {
                        "fallback_reason": "PARSE_ERROR",
                        "original_format_group": original_fg,
                        "is_invalid": True,
                    }
                    return text_descriptor
                except Exception:
                    pass  # fall through to original error
            return make_error(PARSE_ERROR, f"Cannot parse file: {exc}")

        return descriptor

    def _create_initial_backup(self, project_id: str, abs_path: Path) -> None:
        """Create initial backup if file has no backup history.

        Uses BackupManager (C-012) to check history and create backup.
        Only creates backup when list_versions returns an empty list.

        Args:
            project_id: UUID of the project (used to resolve root dir).
            abs_path: Absolute path to the original file.
        """
        from code_analysis.core.backup_manager import BackupManager

        root_dir = BaseMCPCommand._resolve_project_root(project_id)
        root_path = Path(root_dir).resolve()
        bm = BackupManager(root_path)
        rel_path = abs_path.relative_to(root_path)
        versions = bm.list_versions(str(rel_path))
        if not versions:
            bm.create_backup(abs_path, command="universal_file_open")

    def _write_draft(
        self,
        abs_path: Path,
        descriptor: FormatDescriptor,
        project_id: str,
    ) -> Optional[str]:
        """Write the initial draft file for the resolved format group.

        Args:
            abs_path: Absolute path to the original file.
            descriptor: Resolved FormatDescriptor.
            project_id: Project UUID (tree-temp acquisition).

        Returns:
            In-memory tree UUID for sidecar group; None for tree-temp and text.

        Raises:
            Exception: when the file cannot be parsed or written.
        """
        fg = descriptor.format_group
        if fg == FORMAT_SIDECAR:
            return self._write_sidecar_draft(abs_path)
        if fg == FORMAT_TREE_TEMP:
            return self._write_tree_temp_draft(abs_path, descriptor, project_id)
        if fg == FORMAT_TEXT:
            shutil.copy2(str(abs_path), str(descriptor.draft_path))
            return None
        raise ValueError(f"Unknown format group: {fg!r}")

    def _write_sidecar_draft(self, abs_path: Path) -> str:
        """Load Python file into CST tree and write sidecar.

        Args:
            abs_path: Absolute path to the Python file.

        Returns:
            In-memory CST tree UUID for subsequent edit/write commands.
        """
        from code_analysis.core.cst_tree import tree_builder as cst_builder
        from code_analysis.core.cst_tree.tree_sidecar import write_sidecar_atomic

        tree = cst_builder.load_file_to_tree(str(abs_path))
        write_sidecar_atomic(abs_path, tree)
        return str(tree.tree_id)

    def _write_tree_temp_draft(
        self,
        abs_path: Path,
        descriptor: FormatDescriptor,
        project_id: str,
    ) -> Optional[str]:
        """Acquire TreeNode roots (SHASync + optional sidecar) and write draft text.

        Args:
            abs_path: Absolute path to the JSON or YAML file.
            descriptor: Resolved FormatDescriptor with draft_path.
            project_id: Project UUID for project root resolution.

        Returns:
            None: tree-temp sessions use ``tree_temp_roots`` on EditSession, not
            ``tree_id``.
        """
        raw_bytes = abs_path.read_bytes()
        project_root = Path(BaseMCPCommand._resolve_project_root(project_id)).resolve()
        acq = acquire_tree_temp_for_open(
            project_root=project_root,
            source_abs=abs_path,
            handler_id=descriptor.handler_id,
            raw_source_bytes=raw_bytes,
        )
        if descriptor.handler_id == "json":
            from code_analysis.core.tree_temp.json_source_serializer import (
                serialize_json_source,
            )

            draft_text = serialize_json_source(acq.roots)
        elif descriptor.handler_id == "yaml":
            from code_analysis.core.tree_temp.yaml_source_serializer import (
                serialize_yaml_source,
            )

            draft_text = serialize_yaml_source(acq.roots)
        else:
            raise ValueError(
                f"Unsupported handler for tree-temp open: {descriptor.handler_id!r}"
            )
        descriptor.draft_path.write_text(draft_text, encoding="utf-8")
        descriptor.__dict__["_tree_temp_session_kwargs"] = {
            "tree_id": None,
            "source_sha256_at_open": acq.source_sha256,
            "tree_temp_roots": acq.roots,
            "sidecar_write_intent": acq.sidecar_write_intent.value,
        }
        return None
