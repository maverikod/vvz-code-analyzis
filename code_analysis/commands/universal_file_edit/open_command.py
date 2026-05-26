"""
UniversalFileOpenCommand: starts an editing session for one file.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations
import os

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
from code_analysis.commands.universal_file_edit.invalid_write_support import (
    mode_notice_text,
    open_fallback_warning,
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
    write_lockfile_pid,
)
from code_analysis.commands.universal_file_edit.open_command_metadata import (
    get_universal_file_open_metadata,
)
from code_analysis.commands.universal_file_edit.session import create_session
from code_analysis.commands.universal_file_edit.tree_temp_open_support import (
    acquire_tree_temp_for_open,
)


def _fix_yaml_string_values(text: str) -> str:
    """Quote YAML scalar values containing ': ' or inline comments.

    Args:
        text: Raw YAML text.

    Returns:
        YAML text with problematic values double-quoted.
    """
    import re as _re

    _YAML_SCALARS = frozenset({"true", "false", "null", "~", "yes", "no", "on", "off"})
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    in_block_scalar = False
    block_indent = 0
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if in_block_scalar:
            if stripped and indent <= block_indent and not stripped[0].isspace():
                in_block_scalar = False
            else:
                result.append(line)
                continue
        if stripped.startswith("#"):
            result.append(line)
            continue
        if _re.match(r"^(\s*)[\w_-]+:\s*[>|](\s*#.*)?$", line.rstrip()):
            in_block_scalar = True
            block_indent = indent
            result.append(line)
            continue
        m = _re.match(r"^(\s*)([\w_-]+):\s+(.+)$", line.rstrip())
        if not m:
            result.append(line)
            continue
        key_indent, key, value = m.group(1), m.group(2), m.group(3)
        if value.startswith(("'", '"')) or value.startswith(("{", "[")):
            result.append(line)
            continue
        if value.lower() in _YAML_SCALARS:
            result.append(line)
            continue
        if _re.match(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$", value):
            result.append(line)
            continue
        cm = _re.search(r"\s+#\s", value)
        if cm:
            val_part = value[: cm.start()].strip()
            comment_part = "  " + value[cm.start() :].strip()
        else:
            val_part = value
            comment_part = ""
        needs_quote = ": " in val_part or (
            comment_part and not val_part.startswith(("'", '"'))
        )
        if not needs_quote:
            result.append(line)
            continue
        escaped = val_part.replace("\\", "\\\\").replace('"', '\\"')
        result.append(f'{key_indent}{key}: "{escaped}"{comment_part}\n')
    return "".join(result)


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
                "project_id": {
                    "type": "string",
                    "description": (
                        "Project UUID. Resolves the project root on disk. "
                        "Use list_projects to discover valid values."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Project-relative path to the file. Literal path; no globs. "
                        "Not interchangeable with file_id (DB row id)."
                    ),
                },
                "create": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When True, create the file if it does not exist. "
                        "Requires initial_content for Python files (.py). "
                        "For other formats uses initial_content when provided, "
                        "otherwise a format-specific empty default."
                    ),
                },
                "initial_content": {
                    "type": "string",
                    "description": (
                        "Initial file content used only when create=True. "
                        "For Python (.py): valid Python source code written to disk "
                        "before the CST tree is built via load_file_to_tree. "
                        "For JSON: written as-is when non-empty, else `{}\\n`. "
                        "For YAML: written as-is when non-empty, else `{}\\n`. "
                        "For other text formats: written as-is when non-empty, else empty."
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
        from typing import cast

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
            initial_content: Initial source when create=True (.py required; also used
                for .json/.yaml and other text extensions per suffix rules).
            **kwargs: Unused; accepted for adapter compatibility.

        Returns:
            SuccessResult with session_id and available_operations, or ErrorResult
            on failure. When a parse error triggers line-based fallback, the
            response also includes is_invalid, fallback_reason, and warning.
            Every success response carries mode_notice describing the active mode
            and addressing scheme (identifier-based vs line-based).
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
                abs_path.write_text(
                    initial_content if initial_content else "{}\n",
                    encoding="utf-8",
                )
            elif suffix in (".yaml", ".yml"):
                abs_path.write_text(
                    _fix_yaml_string_values(
                        initial_content if initial_content else "{}\n"
                    ),
                    encoding="utf-8",
                )
            else:
                abs_path.write_text(
                    initial_content if initial_content else "",
                    encoding="utf-8",
                )
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
            session_extra["is_invalid"] = True
            session_extra["fallback_reason"] = fallback_info["fallback_reason"]
            session_extra["original_format_group"] = fallback_info[
                "original_format_group"
            ]
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
        write_lockfile_pid(abs_path, os.getpid(), session.session_id)
        data: Dict[str, Any] = {
            "success": True,
            "session_id": session.session_id,
            "available_operations": descriptor.available_operations,
        }
        if created:
            data["created"] = True
        if fallback_info is not None:
            reason = fallback_info["fallback_reason"]
            data["is_invalid"] = True
            data["fallback_reason"] = reason
            data["warning"] = open_fallback_warning(reason)
            data["mode_notice"] = mode_notice_text(True, reason)
        else:
            data["mode_notice"] = mode_notice_text(False)
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
        ``original_format_group`` in the session (not exposed in the API response).

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
            # For tree-temp (JSON/YAML) and sidecar (.py) fall back to text-mode
            # so the file remains accessible despite syntax errors.
            if original_fg in (FORMAT_TREE_TEMP, FORMAT_SIDECAR):
                try:
                    return self._text_fallback_descriptor(
                        abs_path, original_fg, str(exc)
                    )
                except Exception:
                    pass  # fall through to original error
            return make_error(PARSE_ERROR, f"Cannot parse file: {exc}")

        return descriptor

    def _text_fallback_descriptor(
        self,
        abs_path: Path,
        original_fg: str,
        parse_error: str,
    ) -> FormatDescriptor:
        """Build a text-mode descriptor after parse failure at open."""
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
            "fallback_reason": parse_error,
            "original_format_group": original_fg,
        }
        return text_descriptor

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
