"""
MCP command: universal_file_delete

Registry-first deletes: resolves handler by extension before validation, backup,
write, DB updates, or indexing. Requires explicit delete_mode — accidental
full-file delete is blocked unless delete_mode=file.

Modes (public contract; mapped to handler ``extra``):
- ``file`` — remove entire file (all handler types).
- ``range`` — text only: ``start_line`` / ``end_line`` (1-based inclusive).
- ``yaml_path`` — YAML only: structured delete at ``yaml_path`` (JSON Pointer).
- ``node`` / ``json_pointer`` — JSON only: non-empty ``operations`` list
  (modify_tree ops; each ``action`` must be ``delete`` per json handler).
- ``cst_selector`` — Python only: non-empty CST ``ops`` (``new_code`` may be "").
- ``node_id`` — Python only: CST ``node_id`` (UUID from query_cst /
  ``cst_load_file``) plus ``tree_id``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Set, Type

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult

from .base_mcp_command import BaseMCPCommand
from .project_text_file_guard import reject_if_write_under_project_venv
from .registration import (
    MCP_FILE_MANAGEMENT_REGISTRY_HELP,
    REGISTRY_SCHEMA_DISCOVERY_SHORT,
)
from ..core.backup_manager import BackupManager
from ..core.exceptions import ValidationError
from ..core.file_handlers.base import FileHandlerRequest, FileHandlerResult
from ..core.file_handlers.json_handler import JsonFileHandler
from ..core.file_handlers.python_handler import PythonFileHandler
from ..core.file_handlers.registry import (
    HANDLER_JSON,
    HANDLER_PYTHON,
    HANDLER_TEXT,
    HANDLER_YAML,
    RegistryError,
    resolve_handler,
)
from ..core.file_handlers.text_handler import (
    TextFileHandler,
    lines_after_delete_range,
    persist_plain_text_file_metadata,
)
from ..core.file_handlers.yaml_handler import YamlFileHandler
from ..core.file_lock import file_lock
from ..core.path_normalization import normalize_path_simple

logger = logging.getLogger(__name__)

DELETE_MODE_FILE = "file"
DELETE_MODE_RANGE = "range"
DELETE_MODE_NODE = "node"
DELETE_MODE_YAML_PATH = "yaml_path"
DELETE_MODE_JSON_POINTER = "json_pointer"
DELETE_MODE_CST_SELECTOR = "cst_selector"
DELETE_MODE_NODE_ID = "node_id"

_ALLOWED_TEXT: FrozenSet[str] = frozenset({DELETE_MODE_FILE, DELETE_MODE_RANGE})
_ALLOWED_JSON: FrozenSet[str] = frozenset(
    {DELETE_MODE_FILE, DELETE_MODE_NODE, DELETE_MODE_JSON_POINTER}
)
_ALLOWED_YAML: FrozenSet[str] = frozenset({DELETE_MODE_FILE, DELETE_MODE_YAML_PATH})
_ALLOWED_PYTHON: FrozenSet[str] = frozenset(
    {DELETE_MODE_FILE, DELETE_MODE_CST_SELECTOR, DELETE_MODE_NODE_ID}
)


def _success_from_handler(fr: FileHandlerResult, *, operation: str) -> SuccessResult:
    data: Dict[str, Any] = {
        "success": True,
        "handler_id": fr.handler_id,
        "operation": operation,
        "file_path": fr.file_path,
        "project_id": fr.project_id,
        "dry_run": fr.dry_run,
        "changed": fr.changed,
    }
    data.update(fr.data)
    return SuccessResult(data=data)


def _error_from_handler(fr: FileHandlerResult) -> ErrorResult:
    return ErrorResult(
        message=fr.message or fr.code,
        code=fr.code or "VALIDATION_FAILED",
        details=fr.details
        or {
            "file_path": fr.file_path,
            "handler_id": fr.handler_id,
            "operation": fr.operation,
        },
    )


def _validate_text_delete_local(
    absolute_path: Path,
    *,
    start_line: int,
    end_line: int,
    req: FileHandlerRequest,
) -> Optional[FileHandlerResult]:
    if not absolute_path.exists():
        return FileHandlerResult(
            success=False,
            handler_id=req.handler_id,
            operation=req.operation,
            file_path=req.file_path,
            project_id=req.project_id,
            dry_run=req.dry_run,
            changed=False,
            message=f"File not found: {absolute_path}",
            code="FILE_NOT_FOUND",
            details={"resolved_path": str(absolute_path)},
        )
    text = absolute_path.read_text(encoding="utf-8", errors="replace")
    all_lines = text.splitlines(keepends=False)
    try:
        lines_after_delete_range(all_lines, start_line, end_line)
    except ValueError as e:
        return FileHandlerResult(
            success=False,
            handler_id=req.handler_id,
            operation=req.operation,
            file_path=req.file_path,
            project_id=req.project_id,
            dry_run=req.dry_run,
            changed=False,
            message=str(e),
            code="INVALID_RANGE",
            details={"reason": str(e)},
        )
    return None


def _validate_delete_payload(
    handler_id: str,
    delete_mode: str,
    *,
    start_line: Optional[int],
    end_line: Optional[int],
    yaml_path: Optional[str],
    operations: Optional[Any],
    ops: Optional[Any],
    node_id: Optional[str],
    tree_id: Optional[str],
) -> Optional[ErrorResult]:
    allowed: Set[str]
    if handler_id == HANDLER_TEXT:
        allowed = set(_ALLOWED_TEXT)
    elif handler_id == HANDLER_JSON:
        allowed = set(_ALLOWED_JSON)
    elif handler_id == HANDLER_YAML:
        allowed = set(_ALLOWED_YAML)
    elif handler_id == HANDLER_PYTHON:
        allowed = set(_ALLOWED_PYTHON)
    else:
        return ErrorResult(
            message=f"Unhandled handler_id for delete validation: {handler_id!r}",
            code="INTERNAL_ERROR",
            details={"handler_id": handler_id},
        )

    if delete_mode not in allowed:
        return ErrorResult(
            message=(
                f"delete_mode {delete_mode!r} is not valid for handler {handler_id!r}. "
                f"Allowed: {sorted(allowed)}"
            ),
            code="VALIDATION_ERROR",
            details={"delete_mode": delete_mode, "handler_id": handler_id},
        )

    if delete_mode == DELETE_MODE_RANGE:
        if start_line is None or end_line is None:
            return ErrorResult(
                message="delete_mode=range requires start_line and end_line",
                code="VALIDATION_ERROR",
                details={"fields": ["start_line", "end_line"]},
            )
        return None

    if delete_mode == DELETE_MODE_YAML_PATH:
        if not isinstance(yaml_path, str) or not yaml_path.strip():
            return ErrorResult(
                message="delete_mode=yaml_path requires non-empty yaml_path",
                code="VALIDATION_ERROR",
                details={"field": "yaml_path"},
            )
        return None

    if delete_mode in (DELETE_MODE_NODE, DELETE_MODE_JSON_POINTER):
        if not isinstance(operations, list) or len(operations) == 0:
            return ErrorResult(
                message=(
                    "delete_mode=node/json_pointer requires a non-empty "
                    "operations list (structured JSON deletes)"
                ),
                code="VALIDATION_ERROR",
                details={"field": "operations"},
            )
        return None

    if delete_mode == DELETE_MODE_CST_SELECTOR:
        if not isinstance(ops, list) or len(ops) == 0:
            return ErrorResult(
                message="delete_mode=cst_selector requires a non-empty ops list",
                code="VALIDATION_ERROR",
                details={"field": "ops"},
            )
        return None

    if delete_mode == DELETE_MODE_NODE_ID:
        if not isinstance(node_id, str) or not str(node_id).strip():
            return ErrorResult(
                message="delete_mode=node_id requires node_id (non-empty UUID string)",
                code="VALIDATION_ERROR",
                details={"field": "node_id"},
            )
        if not isinstance(tree_id, str) or not str(tree_id).strip():
            return ErrorResult(
                message="delete_mode=node_id requires tree_id from cst_load_file",
                code="VALIDATION_ERROR",
                details={"field": "tree_id"},
            )
        return None

    if delete_mode == DELETE_MODE_FILE:
        return None

    return ErrorResult(
        message=f"No extra validation implemented for delete_mode={delete_mode!r}",
        code="INTERNAL_ERROR",
        details={"delete_mode": delete_mode},
    )


class UniversalFileDeleteCommand(BaseMCPCommand):
    """Delete regions or entire files via the universal handler registry."""

    name = "universal_file_delete"
    version = "1.0.0"
    descr = (
        "Deletes via universal handler routing. Explicit delete_mode is required "
        "(file, range, yaml_path, node, json_pointer, cst_selector, node_id) so "
        "full-file removal never happens implicitly. Unsupported extensions raise "
        "UNSUPPORTED_FILE_EXTENSION before backup or filesystem changes. Supports "
        "dry_run and diff where the handler serializes recoverable previews."
        + " "
        + MCP_FILE_MANAGEMENT_REGISTRY_HELP
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        dm_desc = (
            "Required targeting mode (prevents ambiguous deletes). Allowed values depend "
            f"on file type once resolved: text — {sorted(_ALLOWED_TEXT)}; "
            f"JSON — {sorted(_ALLOWED_JSON)}; YAML — {sorted(_ALLOWED_YAML)}; "
            f"Python — {sorted(_ALLOWED_PYTHON)}."
        )
        return {
            "type": "object",
            "title": "universal_file_delete",
            "description": (
                "Registry-first delete with explicit delete_mode. "
                "`resolve_handler` runs before validation, backups, writes, DB, indexing, trash. "
                "Text lines: delete_mode range + start_line/end_line, or delete_mode file for "
                "full file. JSON/YAML structured: yaml_path / operations / file. "
                "Python: cst_selector (ops) or node_id (+ tree_id) or file. "
                + REGISTRY_SCHEMA_DISCOVERY_SHORT
            ),
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project UUID (from create_project or list_projects).",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Single path relative to project root (literal; globs not supported)."
                    ),
                },
                "delete_mode": {
                    "type": "string",
                    "description": dm_desc,
                    "enum": [
                        DELETE_MODE_FILE,
                        DELETE_MODE_RANGE,
                        DELETE_MODE_NODE,
                        DELETE_MODE_YAML_PATH,
                        DELETE_MODE_JSON_POINTER,
                        DELETE_MODE_CST_SELECTOR,
                        DELETE_MODE_NODE_ID,
                    ],
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, no write, backup, or DB/index side effects.",
                },
                "diff": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, include unified diff when supported.",
                },
                "backup": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true (default), create backups where applicable.",
                },
                "commit_message": {
                    "type": "string",
                    "description": "Optional git commit message for handlers that support it.",
                },
                "diff_context_lines": {
                    "type": "integer",
                    "description": "Optional unified-diff context line count (default 3).",
                },
                "validate_syntax_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "Python handler: validate syntax only when applying ops.",
                },
                "tree_id": {
                    "type": "string",
                    "description": "CST tree_id (Python; required for delete_mode=node_id).",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Text delete_mode=range: first line (1-based, inclusive).",
                },
                "end_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Text delete_mode=range: last line (1-based, inclusive).",
                },
                "yaml_path": {
                    "type": "string",
                    "description": "YAML delete_mode=yaml_path: JSON Pointer to remove.",
                },
                "operations": {
                    "type": "array",
                    "description": (
                        "JSON delete_mode=node or json_pointer: json_modify_tree operations "
                        "(action=delete per op)."
                    ),
                },
                "ops": {
                    "type": "array",
                    "description": (
                        "Python delete_mode=cst_selector: compose_cst_module replace ops "
                        "(empty new_code removes matched nodes)."
                    ),
                },
                "node_id": {
                    "type": "string",
                    "description": (
                        "Python delete_mode=node_id: LibCST node UUID from query_cst / "
                        "cst_get_node_info."
                    ),
                },
            },
            "required": ["project_id", "file_path", "delete_mode"],
            "additionalProperties": False,
        }

    @classmethod
    def metadata(cls: Type["UniversalFileDeleteCommand"]) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "version": cls.version,
            "description": cls.descr,
            "detailed_description": cls.descr,
            "registry_discovery_python": (
                "code_analysis.core.file_handlers.registry — get_handler_schema, "
                "list_handler_mappings, HANDLER_IDS"
            ),
            "category": cls.category,
            "author": cls.author,
            "email": cls.email,
        }

    async def execute(
        self,
        project_id: str,
        file_path: str,
        delete_mode: str,
        dry_run: bool = False,
        diff: bool = False,
        backup: bool = True,
        commit_message: Optional[str] = None,
        diff_context_lines: Optional[int] = None,
        validate_syntax_only: bool = False,
        tree_id: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        yaml_path: Optional[str] = None,
        operations: Optional[Any] = None,
        ops: Optional[Any] = None,
        node_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        dm_raw = (delete_mode or "").strip().lower()
        if not dm_raw:
            return ErrorResult(
                message="delete_mode is required and must be explicit",
                code="VALIDATION_ERROR",
                details={"field": "delete_mode"},
            )

        try:
            try:
                handler_id = resolve_handler(file_path, "delete")
            except RegistryError as e:
                return ErrorResult(
                    message=str(e),
                    code=e.code,
                    details=e.details,
                )

            bad = _validate_delete_payload(
                handler_id,
                dm_raw,
                start_line=start_line,
                end_line=end_line,
                yaml_path=yaml_path,
                operations=operations,
                ops=ops,
                node_id=node_id,
                tree_id=tree_id,
            )
            if bad is not None:
                return bad

            database = self._open_database_from_config(auto_analyze=False)
            absolute_path = self._resolve_file_path_from_project(
                database, project_id, file_path
            )
            project = database.get_project(project_id)
            if not project:
                return ErrorResult(
                    message=f"Project {project_id} not found",
                    code="PROJECT_NOT_FOUND",
                    details={"project_id": project_id},
                )
            root_dir = Path(project.root_path)

            blocked_venv = reject_if_write_under_project_venv(absolute_path, root_dir)
            if blocked_venv is not None:
                return blocked_venv

            if not absolute_path.exists():
                return ErrorResult(
                    message=f"File not found: {absolute_path}",
                    code="FILE_NOT_FOUND",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "handler_id": handler_id,
                        "resolved_path": str(absolute_path),
                    },
                )

            extra: Dict[str, Any] = {"absolute_path": absolute_path}
            if diff_context_lines is not None:
                extra["diff_context_lines"] = diff_context_lines
            if isinstance(commit_message, str) and commit_message.strip():
                extra["commit_message"] = commit_message

            if dm_raw == DELETE_MODE_FILE:
                extra["delete_full_file"] = True

            if handler_id == HANDLER_TEXT:
                if dm_raw == DELETE_MODE_RANGE:
                    extra["start_line"] = int(start_line)  # type: ignore[arg-type]
                    extra["end_line"] = int(end_line)  # type: ignore[arg-type]

            elif handler_id == HANDLER_JSON:
                if dm_raw in (DELETE_MODE_NODE, DELETE_MODE_JSON_POINTER):
                    extra["operations"] = list(operations or [])

            elif handler_id == HANDLER_YAML:
                if dm_raw == DELETE_MODE_YAML_PATH:
                    extra["yaml_path"] = str(yaml_path)

            elif handler_id == HANDLER_PYTHON:
                extra["root_path"] = root_dir.resolve()
                extra["validate_syntax_only"] = validate_syntax_only
                if dm_raw == DELETE_MODE_CST_SELECTOR:
                    extra["ops"] = list(ops or [])
                elif dm_raw == DELETE_MODE_NODE_ID:
                    nid = str(node_id).strip()
                    extra["ops"] = [
                        {
                            "selector": {"kind": "node_id", "node_id": nid},
                            "new_code": "",
                        }
                    ]
                    extra["tree_id"] = str(tree_id).strip()
                if (
                    tree_id is not None
                    and str(tree_id).strip()
                    and dm_raw not in (DELETE_MODE_NODE_ID,)
                ):
                    extra["tree_id"] = str(tree_id).strip()

            if handler_id in (HANDLER_JSON, HANDLER_YAML):
                extra["database"] = database
                extra["root_dir"] = root_dir.resolve()
                extra["normalized_path"] = normalize_path_simple(str(absolute_path))

            backup_for_handler = bool(backup)
            if handler_id == HANDLER_TEXT and (not dry_run) and backup_for_handler:
                backup_for_handler = False

            req = FileHandlerRequest(
                project_id=project_id,
                file_path=file_path,
                handler_id=handler_id,
                operation="delete",
                dry_run=bool(dry_run),
                diff=bool(diff),
                backup=backup_for_handler,
                extra=extra,
            )

            if handler_id == HANDLER_TEXT:
                fr = self._run_text_delete(
                    req=req,
                    database=database,
                    absolute_path=absolute_path,
                    root_dir=root_dir,
                    backup=bool(backup),
                    dry_run=bool(dry_run),
                    dm=dm_raw,
                )
            elif handler_id == HANDLER_JSON:
                fr = JsonFileHandler().delete(req)
            elif handler_id == HANDLER_YAML:
                fr = YamlFileHandler().delete(req)
            elif handler_id == HANDLER_PYTHON:
                fr = PythonFileHandler().delete(req)
            else:
                return ErrorResult(
                    message=f"Unhandled handler_id after registry resolve: {handler_id!r}",
                    code="INTERNAL_ERROR",
                    details={
                        "project_id": project_id,
                        "file_path": file_path,
                        "handler_id": handler_id,
                        "operation": "delete",
                    },
                )

            if not fr.success:
                return _error_from_handler(fr)
            return _success_from_handler(fr, operation="delete")

        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="VALIDATION_ERROR",
                details=getattr(e, "details", None)
                or {"field": getattr(e, "field", None)},
            )
        except Exception as e:
            logger.exception("universal_file_delete failed: %s", e)
            return ErrorResult(
                message=f"universal_file_delete failed: {e}",
                code="UNIVERSAL_FILE_DELETE_ERROR",
            )

    def _run_text_delete(
        self,
        *,
        req: FileHandlerRequest,
        database: Any,
        absolute_path: Path,
        root_dir: Path,
        backup: bool,
        dry_run: bool,
        dm: str,
    ) -> FileHandlerResult:
        """Text deletes with BackupManager; metadata update when a file remains."""

        def _restore(rel: str, uuid_: str) -> None:
            bm = BackupManager(root_dir)
            bm.restore_file(rel, uuid_)

        with file_lock(absolute_path):
            if dm == DELETE_MODE_RANGE:
                sl = req.extra.get("start_line")
                el = req.extra.get("end_line")
                if sl is None or el is None:
                    return FileHandlerResult(
                        success=False,
                        handler_id=req.handler_id,
                        operation=req.operation,
                        file_path=req.file_path,
                        project_id=req.project_id,
                        dry_run=req.dry_run,
                        changed=False,
                        message="internal: range delete missing start_line/end_line in extra",
                        code="INTERNAL_ERROR",
                    )
                pre_val = _validate_text_delete_local(
                    absolute_path,
                    start_line=int(sl),
                    end_line=int(el),
                    req=req,
                )
                if pre_val is not None:
                    return pre_val

            backup_uuid: Optional[str] = None
            if not dry_run and backup and absolute_path.exists():
                bm = BackupManager(root_dir)
                try:
                    rel = str(absolute_path.relative_to(root_dir.resolve()))
                except ValueError:
                    rel = str(absolute_path)
                backup_uuid = bm.create_backup(
                    absolute_path,
                    command="universal_file_delete",
                    comment=f"Before universal_file_delete {req.file_path}",
                )
                if not backup_uuid:
                    return FileHandlerResult(
                        success=False,
                        handler_id=req.handler_id,
                        operation=req.operation,
                        file_path=req.file_path,
                        project_id=req.project_id,
                        dry_run=False,
                        changed=False,
                        message=(
                            "Backup to old_code (versions) is mandatory before write; "
                            "create_backup failed. Aborting universal_file_delete."
                        ),
                        code="BACKUP_REQUIRED",
                        details={
                            "file_path": req.file_path,
                            "resolved_path": str(absolute_path),
                        },
                    )

            fr = TextFileHandler().delete(req)
            if not fr.success:
                return fr

            if dry_run:
                return fr

            normalized_path = normalize_path_simple(str(absolute_path))

            # Full-file unlink: no plaintext metadata row to refresh.
            if dm == DELETE_MODE_FILE or not absolute_path.exists():
                out = dict(fr.data or {})
                if backup_uuid:
                    out["backup_uuid"] = backup_uuid
                return FileHandlerResult(
                    success=True,
                    handler_id=fr.handler_id,
                    operation=fr.operation,
                    file_path=fr.file_path,
                    project_id=fr.project_id,
                    dry_run=fr.dry_run,
                    changed=fr.changed,
                    data=out,
                )

            meta = persist_plain_text_file_metadata(
                database=database,
                project_id=req.project_id,
                absolute_path=absolute_path,
                normalized_path=normalized_path,
                source_code=absolute_path.read_text(encoding="utf-8", errors="replace"),
            )
            if not meta.get("success"):
                if backup_uuid:
                    try:
                        rel = str(absolute_path.relative_to(root_dir.resolve()))
                    except ValueError:
                        rel = str(absolute_path)
                    _restore(rel, backup_uuid)
                return FileHandlerResult(
                    success=False,
                    handler_id=req.handler_id,
                    operation=req.operation,
                    file_path=req.file_path,
                    project_id=req.project_id,
                    dry_run=False,
                    changed=False,
                    message="Failed to update file metadata: "
                    + str(meta.get("error", "unknown")),
                    code="UPDATE_FILE_DATA_ERROR",
                    details=meta,
                )
            out = dict(fr.data or {})
            out["metadata_update"] = meta
            if backup_uuid:
                out["backup_uuid"] = backup_uuid
            return FileHandlerResult(
                success=True,
                handler_id=fr.handler_id,
                operation=fr.operation,
                file_path=fr.file_path,
                project_id=fr.project_id,
                dry_run=fr.dry_run,
                changed=fr.changed,
                data=out,
            )
