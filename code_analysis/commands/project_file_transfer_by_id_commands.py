"""
MCP commands: chunked download / upload for project files addressed by DB file UUID.

Bridges ``files.id`` to the mcp-proxy-adapter transfer API (transfer_download_begin flow)
and to the same save pipeline as ``universal_file_save`` for uploads (backups, handlers,
metadata, optional git).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import gzip
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, Union, cast

from mcp_proxy_adapter.commands.result import ErrorResult, SuccessResult
from mcp_proxy_adapter.api.transfer_session_service import (
    TransferPayloadValidationError,
    build_transfer_chunk_transport,
    run_create_download_session,
)
from mcp_proxy_adapter.commands.transfer_command_support import (
    transfer_domain_error_result,
    transfer_validation_error_result,
)
from mcp_proxy_adapter.transfer import TransferCompressionError
from mcp_proxy_adapter.transfer import TransferError
from mcp_proxy_adapter.transfer import TransferTooLargeError

from .base_mcp_command import BaseMCPCommand
from .base_mcp_command_resolve_path import resolve_under_project_root
from .project_file_transfer_by_id_commands_metadata import (
    get_project_file_transfer_download_begin_metadata,
    get_project_file_transfer_upload_save_metadata,
)
from .project_file_transfer_by_id_commands_schema import (
    get_project_file_transfer_download_begin_schema,
    get_project_file_transfer_upload_save_schema,
)
from .universal_file_save_command import UniversalFileSaveCommand
from ..core.backup_manager import BackupManager
from ..core.database_client.client import DatabaseClient
from ..core.exceptions import ValidationError
from ..core.file_lock import acquire_persistent_file_lock, release_persistent_file_lock
from ..core.runtime_lock_sessions import (
    get_session_id_for_current_pid,
    normalize_lock_mode,
    register_runtime_session,
    runtime_session_exists,
)
from ..core.transfer_lock_registry import (
    TransferLockEntry,
    install_transfer_lock_hooks,
    register_transfer_lock,
    release_transfer_lock,
)

logger = logging.getLogger(__name__)
install_transfer_lock_hooks()


def _read_completed_upload_text(
    transfer_id: str,
) -> Union[Tuple[str, str], ErrorResult]:
    """Read finalized upload buffer as text; same rules as ``cst_apply_buffer``."""
    try:
        from mcp_proxy_adapter.api.handlers import get_transfer_store
    except ImportError as e:
        return ErrorResult(
            message=f"mcp_proxy_adapter not available: {e}",
            code="IMPORT_ERROR",
        )
    tid = str(transfer_id).strip()
    try:
        store = get_transfer_store()
        local_path = store.get_committed_upload_path(tid)
    except Exception as e:
        err_msg = str(e)
        if "not complete" in err_msg.lower() or "not an upload" in err_msg.lower():
            return ErrorResult(
                message=f"Transfer not ready: {err_msg}",
                code="TRANSFER_NOT_COMPLETE",
                details={"transfer_id": tid},
            )
        return ErrorResult(
            message=f"Transfer not found or expired: {err_msg}",
            code="TRANSFER_NOT_FOUND",
            details={"transfer_id": tid},
        )
    try:
        session_info = store.get_completed_transfer(tid)
        compression = str(session_info.get("compression", "identity"))
        buffer_path = Path(local_path)
        if compression == "gzip":
            with gzip.open(buffer_path, "rt", encoding="utf-8") as f:
                text = f.read()
        else:
            text = buffer_path.read_text(encoding="utf-8")
    except Exception as e:
        return ErrorResult(
            message=f"Failed to read transfer buffer: {e}",
            code="BUFFER_READ_ERROR",
            details={"transfer_id": tid, "local_path": local_path},
        )
    return text, compression


def _resolve_file_by_id(
    database: DatabaseClient,
    file_id: str,
    project_id_filter: Optional[str] = None,
) -> Union[Tuple[Dict[str, Any], str, str], ErrorResult]:
    """Return (row, project-relative posix path, effective project_id) or ErrorResult."""
    fid = str(file_id).strip()
    if not fid:
        return ErrorResult(
            message="file_id is required",
            code="VALIDATION_ERROR",
            details={"field": "file_id"},
        )
    where: Dict[str, Any] = {"id": fid}
    pid_f = str(project_id_filter or "").strip()
    if pid_f:
        where["project_id"] = pid_f
    rows = database.select("files", where=where)
    if not rows:
        if pid_f:
            return ErrorResult(
                message=f"No file with id {fid} in project {pid_f}",
                code="FILE_NOT_FOUND",
                details={"file_id": fid, "project_id": pid_f},
            )
        return ErrorResult(
            message=f"No file with id {fid}",
            code="FILE_NOT_FOUND",
            details={"file_id": fid},
        )
    row = rows[0]
    effective_pid = str(row.get("project_id") or "").strip()
    if not effective_pid:
        return ErrorResult(
            message="File row has no project_id",
            code="FILE_PATH_MISSING",
            details={"file_id": fid},
        )
    if row.get("deleted"):
        return ErrorResult(
            message="File is marked deleted in the database",
            code="FILE_DELETED",
            details={"file_id": fid, "project_id": effective_pid},
        )
    rel = (row.get("relative_path") or row.get("path") or "").strip()
    if not rel:
        return ErrorResult(
            message="File row has no path",
            code="FILE_PATH_MISSING",
            details={"file_id": fid},
        )
    rel_posix = str(Path(rel).as_posix())
    return row, rel_posix, effective_pid


def _validate_file_selector_params(params: Dict[str, Any]) -> None:
    """file_id xor file_path; if file_id omitted, project_id and file_path are required."""
    fid = str(params.get("file_id") or "").strip()
    fp = str(params.get("file_path") or "").strip()
    pid = str(params.get("project_id") or "").strip()

    if fid and fp:
        raise ValidationError(
            "Specify exactly one of file_id or file_path, not both",
            field="file_id",
            details={"file_id": bool(fid), "file_path": bool(fp)},
        )
    if fid:
        if pid:
            BaseMCPCommand._validate_project_id_exists(pid)
        return
    if not pid:
        raise ValidationError(
            "project_id is required when file_id is omitted",
            field="project_id",
            details={},
        )
    if not fp:
        raise ValidationError(
            "file_path is required when file_id is omitted",
            field="file_path",
            details={},
        )
    BaseMCPCommand._validate_project_id_exists(pid)


def _resolve_by_file_path(
    database: DatabaseClient,
    project_id: str,
    file_path: str,
    *,
    require_file_exists: bool,
) -> Union[Tuple[Optional[Dict[str, Any]], str, str], ErrorResult]:
    """Resolve project-relative path; optional ``files`` row. Row may be None if not indexed."""
    raw = str(file_path or "").strip()
    if not raw:
        return ErrorResult(
            message="file_path is empty",
            code="VALIDATION_ERROR",
            details={"field": "file_path"},
        )
    pid = str(project_id).strip()
    project = database.get_project(pid)
    if not project:
        return ErrorResult(
            message=f"Project {pid} not found",
            code="PROJECT_NOT_FOUND",
            details={"project_id": pid},
        )
    root = Path(project.root_path).resolve()
    rel_posix = str(Path(raw).as_posix())
    try:
        abs_path = resolve_under_project_root(
            root,
            rel_posix,
            require_exists=require_file_exists,
            must_be_file=True if require_file_exists else None,
        )
    except ValidationError as e:
        return ErrorResult(
            message=str(e),
            code="PATH_ERROR",
            details=getattr(e, "details", None) or {},
        )
    if abs_path.exists() and not abs_path.is_file():
        return ErrorResult(
            message=f"Not a regular file: {abs_path}",
            code="PATH_ERROR",
            details={"file_path": rel_posix},
        )
    row = database.get_file_by_path(str(abs_path), pid, include_deleted=False)
    if row and row.get("deleted"):
        return ErrorResult(
            message="File is marked deleted in the database",
            code="FILE_DELETED",
            details={"file_path": rel_posix, "project_id": pid},
        )
    return row, rel_posix, pid


def _resolve_file_target(
    database: DatabaseClient,
    project_id: Optional[str],
    *,
    file_id: Optional[str],
    file_path: Optional[str],
    path_must_exist: bool,
) -> Union[Tuple[Optional[Dict[str, Any]], str, str], ErrorResult]:
    """Return (optional files row, rel_posix, effective_project_id)."""
    fid = str(file_id or "").strip() or None
    fp = str(file_path or "").strip() or None
    pid_in = str(project_id or "").strip() or None
    if fid and fp:
        return ErrorResult(
            message="Specify exactly one of file_id or file_path, not both",
            code="VALIDATION_ERROR",
            details={"fields": ["file_id", "file_path"]},
        )
    if not fid and not fp:
        return ErrorResult(
            message="Exactly one of file_id or file_path is required",
            code="VALIDATION_ERROR",
            details={"fields": ["file_id", "file_path"]},
        )
    if fid:
        out = _resolve_file_by_id(database, fid, project_id_filter=pid_in)
        if isinstance(out, ErrorResult):
            return out
        row, rel_posix, effective_pid = out
        return row, rel_posix, effective_pid
    if not pid_in:
        return ErrorResult(
            message="project_id is required when resolving by file_path",
            code="VALIDATION_ERROR",
            details={"field": "project_id"},
        )
    assert fp is not None
    out = _resolve_by_file_path(
        database, pid_in, fp, require_file_exists=path_must_exist
    )
    if isinstance(out, ErrorResult):
        return out
    row, rel_posix, effective_pid = out
    return row, rel_posix, effective_pid


class ProjectFileTransferDownloadBeginCommand(BaseMCPCommand):
    """Start a resumable download of an on-disk project file identified by ``files.id``."""

    name = "project_file_transfer_download_begin"
    version = "1.2.0"
    descr = (
        "Begin chunked download for a project file: pass ``files.id`` **or** "
        "``project_id`` + project-relative ``file_path``. With ``file_id`` only, "
        "``project_id`` / ``file_path`` are optional. Same transfer session as "
        "``transfer_download_begin`` (GET chunks). Optional ``old_code`` backup history."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_transfer_download_begin_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        _validate_file_selector_params(params)
        if str(params.get("compression", "")) not in ("identity", "gzip"):
            raise ValidationError(
                "compression must be identity or gzip",
                field="compression",
                details={},
            )
        try:
            normalize_lock_mode(params.get("lock_mode") or "none")
        except ValueError as exc:
            raise ValidationError(
                str(exc),
                field="lock_mode",
                details={"lock_mode": params.get("lock_mode")},
            ) from exc
        cs = params.get("chunk_size")
        if cs is not None:
            if not isinstance(cs, int) or cs <= 0:
                raise ValidationError(
                    "chunk_size must be a positive integer when provided",
                    field="chunk_size",
                    details={"chunk_size": cs},
                )
        return params

    @classmethod
    def metadata(
        cls: Type["ProjectFileTransferDownloadBeginCommand"],
    ) -> Dict[str, Any]:
        return cast(
            Dict[str, Any], get_project_file_transfer_download_begin_metadata(cls)
        )

    async def execute(
        self,
        compression: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        chunk_size: Optional[int] = None,
        include_backup_history: bool = True,
        lock_mode: str = "none",
        job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        database = self._open_database_from_config(auto_analyze=False)
        resolved = _resolve_file_target(
            database,
            project_id,
            file_id=file_id,
            file_path=file_path,
            path_must_exist=True,
        )
        if isinstance(resolved, ErrorResult):
            return resolved
        row, rel_posix, effective_project_id = resolved

        project = database.get_project(effective_project_id)
        if not project:
            return ErrorResult(
                message=f"Project {effective_project_id} not found",
                code="PROJECT_NOT_FOUND",
                details={"project_id": effective_project_id},
            )
        root = Path(project.root_path).resolve()
        try:
            abs_path = resolve_under_project_root(
                root,
                rel_posix,
                require_exists=True,
                must_be_file=True,
            )
        except ValidationError as e:
            return ErrorResult(
                message=str(e),
                code="PATH_ERROR",
                details=getattr(e, "details", None) or {},
            )

        payload: Dict[str, Any] = {
            "source_path": str(abs_path),
            "filename": Path(rel_posix).name,
            "compression": compression,
            "command": self.name,
        }
        if chunk_size is not None:
            payload["chunk_size"] = int(chunk_size)
        if job_id:
            payload["job_id"] = str(job_id).strip()
        if correlation_id:
            payload["correlation_id"] = str(correlation_id).strip()

        mode = normalize_lock_mode(lock_mode)
        lock_session_id: Optional[str] = None
        lock_handle = None
        if mode != "none":
            lock_session_id = get_session_id_for_current_pid(database, role="daemon")
            if not runtime_session_exists(database, lock_session_id):
                register_runtime_session(
                    database, role="daemon", session_id=lock_session_id
                )
            try:
                lock_handle = acquire_persistent_file_lock(
                    abs_path,
                    mode=lock_mode,
                    database=database,
                    project_id=effective_project_id,
                    file_path=rel_posix,
                    session_id=lock_session_id,
                    register_role="daemon",
                )
            except Exception as exc:
                return ErrorResult(
                    message=f"Failed to acquire transfer lock: {exc}",
                    code="LOCK_ACQUIRE_FAILED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                        "lock_mode": mode,
                    },
                )
        try:
            data = await run_create_download_session(payload)
        except TransferPayloadValidationError as exc:
            if lock_handle is not None:
                lock_handle.release(force_lease=True)
            return transfer_validation_error_result(exc.missing_fields)
        except (TransferTooLargeError, TransferCompressionError, TransferError) as exc:
            if lock_handle is not None:
                lock_handle.release(force_lease=True)
            return transfer_domain_error_result(exc)

        tid = str(data.get("transfer_id", "")).strip()
        if lock_handle is not None and lock_session_id is not None:
            register_transfer_lock(
                TransferLockEntry(
                    transfer_id=tid,
                    direction="download",
                    project_id=effective_project_id,
                    file_path=rel_posix,
                    session_id=lock_session_id,
                    lock_mode=lock_mode,
                    handle=lock_handle,
                )
            )
        transport = build_transfer_chunk_transport(
            direction="download", transfer_id=tid
        )
        fid_out: Optional[str] = None
        if row and row.get("id") is not None:
            fid_out = str(row["id"]).strip() or None
        merged: Dict[str, Any] = {
            **data,
            "transport": transport,
            "file_id": fid_out,
            "project_id": effective_project_id,
            "file_path": rel_posix,
            "lock_mode": lock_mode,
            "lock_session_id": lock_session_id,
        }
        if include_backup_history:
            bm = BackupManager(root)
            merged["backup_history"] = bm.list_versions(rel_posix)

        logger.info(
            "[%s] project_id=%s file_id=%s file_path=%s path=%s transfer_id=%s",
            self.name,
            effective_project_id,
            fid_out,
            file_path,
            rel_posix,
            tid,
        )
        return SuccessResult(data=merged)


class ProjectFileTransferUploadSaveCommand(BaseMCPCommand):
    """Apply a completed transfer upload to the file row identified by ``files.id``."""

    name = "project_file_transfer_upload_save"
    version = "1.2.0"
    descr = (
        "After transfer upload completes, saves buffer to a project file identified by "
        "``files.id`` **or** ``project_id`` + project-relative ``file_path``. With "
        "``file_id`` only, ``project_id`` / ``file_path`` are optional. Same pipeline as "
        "``universal_file_save`` (backups, handlers, DB metadata, optional git)."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_transfer_upload_save_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params = super().validate_params(params)
        _validate_file_selector_params(params)
        tid = str(params.get("transfer_id", "")).strip()
        if not tid:
            raise ValidationError(
                "transfer_id must be non-empty",
                field="transfer_id",
                details={},
            )
        dcl = params.get("diff_context_lines")
        if dcl is not None:
            if not isinstance(dcl, int) or dcl < 0:
                raise ValidationError(
                    "diff_context_lines must be a non-negative integer when provided",
                    field="diff_context_lines",
                    details={"diff_context_lines": dcl},
                )
        try:
            normalize_lock_mode(params.get("lock_mode") or "none")
        except ValueError as exc:
            raise ValidationError(
                str(exc),
                field="lock_mode",
                details={"lock_mode": params.get("lock_mode")},
            ) from exc
        return params

    @classmethod
    def metadata(cls: Type["ProjectFileTransferUploadSaveCommand"]) -> Dict[str, Any]:
        return cast(Dict[str, Any], get_project_file_transfer_upload_save_metadata(cls))

    async def execute(
        self,
        transfer_id: str,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        dry_run: bool = False,
        diff: bool = False,
        backup: bool = True,
        commit_message: Optional[str] = None,
        diff_context_lines: Optional[int] = None,
        validate_syntax_only: bool = False,
        tree_id: Optional[str] = None,
        unlock_after_write: bool = True,
        lock_mode: str = "none",
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        database = self._open_database_from_config(auto_analyze=False)
        resolved = _resolve_file_target(
            database,
            project_id,
            file_id=file_id,
            file_path=file_path,
            path_must_exist=False,
        )
        if isinstance(resolved, ErrorResult):
            return resolved
        _row, rel_posix, effective_project_id = resolved

        read_out = _read_completed_upload_text(transfer_id)
        if isinstance(read_out, ErrorResult):
            return read_out
        content, _compression = read_out

        mode = normalize_lock_mode(lock_mode)
        lock_session_id: Optional[str] = None
        lock_handle = None
        if mode != "none":
            project = database.get_project(effective_project_id)
            if not project:
                return ErrorResult(
                    message=f"Project {effective_project_id} not found",
                    code="PROJECT_NOT_FOUND",
                    details={"project_id": effective_project_id},
                )
            root = Path(project.root_path).resolve()
            try:
                abs_path = resolve_under_project_root(
                    root,
                    rel_posix,
                    require_exists=False,
                    must_be_file=None,
                )
            except ValidationError as e:
                return ErrorResult(
                    message=str(e),
                    code="PATH_ERROR",
                    details=getattr(e, "details", None) or {},
                )
            lock_session_id = get_session_id_for_current_pid(database, role="daemon")
            if not runtime_session_exists(database, lock_session_id):
                register_runtime_session(
                    database, role="daemon", session_id=lock_session_id
                )
            try:
                lock_handle = acquire_persistent_file_lock(
                    abs_path,
                    mode=lock_mode,
                    database=database,
                    project_id=effective_project_id,
                    file_path=rel_posix,
                    session_id=lock_session_id,
                    register_role="daemon",
                )
            except Exception as exc:
                return ErrorResult(
                    message=f"Failed to acquire transfer save lock: {exc}",
                    code="LOCK_ACQUIRE_FAILED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                        "lock_mode": mode,
                    },
                )

        saver = UniversalFileSaveCommand()
        result = await saver.execute(
            project_id=effective_project_id,
            file_path=rel_posix,
            content=content,
            dry_run=bool(dry_run),
            diff=bool(diff),
            backup=bool(backup),
            commit_message=commit_message,
            diff_context_lines=diff_context_lines,
            validate_syntax_only=bool(validate_syntax_only),
            tree_id=tree_id,
            **kwargs,
        )
        if not isinstance(result, SuccessResult) and lock_handle is not None:
            lock_handle.release(force_lease=True)
        if isinstance(result, SuccessResult) and isinstance(result.data, dict):
            result.data.setdefault("resolved_file_path", rel_posix)
            result.data.setdefault("lock_mode", lock_mode)
            result.data.setdefault("lock_session_id", lock_session_id)
            fid_out: Optional[str] = None
            if file_id and str(file_id).strip():
                fid_out = str(file_id).strip()
            elif _row and _row.get("id") is not None:
                fid_out = str(_row["id"]).strip() or None
            if fid_out:
                result.data.setdefault("file_id", fid_out)
            elif not dry_run:
                project = database.get_project(effective_project_id)
                if project:
                    root = Path(project.root_path).resolve()
                    try:
                        abs_p = resolve_under_project_root(
                            root, rel_posix, require_exists=True, must_be_file=True
                        )
                        row2 = database.get_file_by_path(
                            str(abs_p), effective_project_id, include_deleted=False
                        )
                        if row2 and row2.get("id") is not None:
                            result.data["file_id"] = str(row2["id"])
                    except (ValidationError, OSError, ValueError):
                        pass
            if bool(unlock_after_write) and not bool(dry_run):
                released_by_transfer = release_transfer_lock(
                    str(transfer_id),
                    reason="upload_save",
                )
                if not released_by_transfer and lock_session_id is not None:
                    release_persistent_file_lock(
                        session_id=lock_session_id,
                        project_id=effective_project_id,
                        file_path=rel_posix,
                        database=database,
                        force=True,
                    )
                result.data["lock_released"] = True
            elif bool(dry_run) and lock_handle is not None:
                lock_handle.release(force_lease=True)
                result.data["lock_released"] = True
        return result
