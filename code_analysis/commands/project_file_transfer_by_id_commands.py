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
from ..core.file_disk_registration import (
    ensure_file_row_for_disk_path,
    register_file_row_for_new_content,
)
from ..core.backup_manager import BackupManager
from ..core.client_sessions import (
    SessionNotFoundError,
    close_session_file,
    open_session_file,
    touch_or_error,
)
from ..core.database_client.client import DatabaseClient
from ..core.database_driver_pkg.domain.projects import get_project
from ..core.exceptions import ValidationError
from ..core.file_lock import acquire_persistent_file_lock, release_persistent_file_lock
from ..core.runtime_lock_sessions import (
    ensure_client_lock_session,
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


def _validate_client_session_id(
    database: DatabaseClient,
    session_id: Optional[str],
    *,
    lock_mode: str,
) -> Optional[ErrorResult]:
    """Touch client session when ``session_id`` is set; require it for non-none locks."""
    sid = str(session_id or "").strip()
    mode = normalize_lock_mode(lock_mode)
    if not sid:
        if mode == "none":
            return None
        return ErrorResult(
            message="session_id is required when lock_mode is not none",
            code="SESSION_ID_REQUIRED",
            details={"lock_mode": lock_mode},
        )
    try:
        touch_or_error(database, sid)
    except SessionNotFoundError:
        return ErrorResult(
            code="SESSION_NOT_FOUND",
            message=f"Session {sid!r} not found.",
        )
    try:
        ensure_client_lock_session(database, sid)
    except ValueError as exc:
        return ErrorResult(
            message=str(exc),
            code="SESSION_NOT_FOUND",
            details={"session_id": sid},
        )
    return None


def _resolve_advisory_lock_session_id(
    database: DatabaseClient,
    *,
    client_session_id: Optional[str],
    lock_mode: str,
) -> str:
    """Pick lock owner: client session when provided, else daemon runtime session."""
    sid = str(client_session_id or "").strip()
    mode = normalize_lock_mode(lock_mode)
    if mode == "none":
        return sid
    if sid:
        return sid
    lock_session_id = get_session_id_for_current_pid(database, role="daemon")
    if not runtime_session_exists(database, lock_session_id):
        register_runtime_session(database, role="daemon", session_id=lock_session_id)
    return lock_session_id


def _record_client_file_lock(
    database: DatabaseClient,
    *,
    client_session_id: Optional[str],
    project_id: str,
    row: Optional[Dict[str, Any]],
) -> None:
    """Mirror indexed file lock in session_file_locks when client session is known."""
    sid = str(client_session_id or "").strip()
    if not sid or not row or row.get("id") is None:
        return
    open_session_file(
        database,
        session_id=sid,
        project_id=project_id,
        file_id=str(row["id"]),
    )


def _release_client_file_lock(
    database: DatabaseClient,
    *,
    client_session_id: Optional[str],
    project_id: str,
    file_id: Optional[str],
) -> None:
    """Remove a file from a client session's tracked locks when identifiers exist."""
    sid = str(client_session_id or "").strip()
    fid = str(file_id or "").strip()
    if not sid or not fid:
        return
    close_session_file(
        database,
        session_id=sid,
        project_id=project_id,
        file_id=fid,
    )


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
    rel_raw = (row.get("relative_path") or row.get("path") or "").strip()
    if not rel_raw:
        return ErrorResult(
            message="File row has no path",
            code="FILE_PATH_MISSING",
            details={"file_id": fid},
        )
    rel_posix = str(Path(rel_raw).as_posix())
    if Path(rel_posix).is_absolute():
        project = get_project(database, effective_pid)
        if not project:
            return ErrorResult(
                message=f"Project {effective_pid} not found",
                code="PROJECT_NOT_FOUND",
                details={"project_id": effective_pid},
            )
        root = Path(project.root_path).resolve()
        try:
            rel_posix = Path(rel_posix).resolve().relative_to(root).as_posix()
        except ValueError:
            return ErrorResult(
                message=(
                    "File path is outside project root; "
                    "use a project-relative path in the files index"
                ),
                code="PATH_ERROR",
                details={"file_id": fid, "path": rel_posix, "project_root": str(root)},
            )
    return row, rel_posix, effective_pid


def _validate_download_params(params: Dict[str, Any]) -> None:
    """Download accepts ``file_id`` only; optional ``project_id`` must match the row."""
    fid = str(params.get("file_id") or "").strip()
    fp = str(params.get("file_path") or "").strip()
    pid = str(params.get("project_id") or "").strip()

    if fp:
        raise ValidationError(
            "file_path is not supported for download; use file_id",
            field="file_path",
            details={},
        )
    if not fid:
        raise ValidationError(
            "file_id is required",
            field="file_id",
            details={},
        )
    if pid:
        BaseMCPCommand._validate_project_id_exists(pid)


def _validate_upload_selector_params(params: Dict[str, Any]) -> None:
    """file_id xor file_path; project_id required only in path mode.

    When ``file_id`` is set, ``project_id`` is optional (the row determines the
    project). If ``project_id`` is also provided, it must refer to a registered
    project and match the file row (enforced during resolve). When ``file_id`` is
    omitted, ``project_id`` and ``file_path`` are both required.
    """
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
    project = get_project(database, pid)
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


def _require_on_disk_project_file(
    database: DatabaseClient,
    project_id: str,
    rel_posix: str,
) -> Union[Path, ErrorResult]:
    """Resolve ``rel_posix`` under the project root and require a regular file on disk."""
    pid = str(project_id).strip()
    project = get_project(database, pid)
    if not project:
        return ErrorResult(
            message=f"Project {pid} not found",
            code="PROJECT_NOT_FOUND",
            details={"project_id": pid},
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
        msg = str(e).lower()
        if "does not exist" in msg or "not a file" in msg or "not found" in msg:
            code = "FILE_NOT_FOUND"
        else:
            code = "PATH_ERROR"
        return ErrorResult(
            message=str(e),
            code=code,
            details=getattr(e, "details", None) or {},
        )
    if not abs_path.is_file():
        return ErrorResult(
            message=f"File not found on disk: {rel_posix}",
            code="FILE_NOT_FOUND",
            details={"project_id": pid, "file_path": rel_posix},
        )
    return abs_path


def _ensure_db_row_for_on_disk_file(
    database: DatabaseClient,
    project_id: str,
    abs_path: Path,
    rel_posix: str,
    row: Optional[Dict[str, Any]],
) -> Union[Tuple[Dict[str, Any], Path], ErrorResult]:
    """Require on-disk file and a ``files`` row (register when missing)."""
    if row is not None and row.get("id") is not None:
        return row, abs_path
    registered = ensure_file_row_for_disk_path(
        database,
        project_id,
        abs_path,
    )
    if registered is None or registered.get("id") is None:
        return ErrorResult(
            message=f"File not found on disk: {rel_posix}",
            code="FILE_NOT_FOUND",
            details={"project_id": project_id, "file_path": rel_posix},
        )
    return registered, abs_path


def _create_path_on_disk(
    database: DatabaseClient, project_id: str, rel_posix: str
) -> bool:
    """Return True when the project-relative path currently exists on disk."""
    project = get_project(database, project_id)
    if project is None:
        return False
    try:
        abs_path = resolve_under_project_root(
            Path(project.root_path).resolve(),
            rel_posix,
            require_exists=False,
            must_be_file=None,
        )
    except ValidationError:
        return False
    return Path(abs_path).is_file()


def _rollback_registered_file_row(
    database: DatabaseClient,
    project_id: str,
    file_id: str,
) -> None:
    """Remove a files row registered for a new file whose write later failed.

    Best-effort cascade purge so the atomic create path leaves no orphan row when
    the subsequent disk write does not succeed.
    """
    try:
        database.purge_file_ids_cascade(
            project_id, [file_id], operation_name="upload_save_rollback"
        )
    except Exception:
        logger.warning(
            "Failed to roll back registered file row id=%s in project %s",
            file_id,
            project_id,
            exc_info=True,
        )


def _create_row_is_persisted(
    database: DatabaseClient,
    project_id: str,
    absolute_path: Path,
    expected_file_id: str,
) -> bool:
    """Confirm a freshly registered ``files`` row is durably visible.

    Re-reads the row by path on a fresh statement (a different pooled connection
    than the INSERT) so a row that was inserted but not committed — or otherwise
    not visible — is detected. Returns True only when a row exists and its id
    matches the id the caller is about to return. When the database client cannot
    answer (no ``get_file_by_path``), returns True so the check never blocks a
    backend that does not support it.
    """
    get_by_path = getattr(database, "get_file_by_path", None)
    if not callable(get_by_path):
        return True
    try:
        path = Path(absolute_path).resolve()
    except OSError:
        path = Path(absolute_path)
    try:
        row = get_by_path(str(path), str(project_id).strip(), include_deleted=False)
    except Exception:
        logger.warning(
            "Persistence check failed to re-read file row id=%s path=%s",
            expected_file_id,
            path,
            exc_info=True,
        )
        return False
    return bool(
        row and str(row.get("id") or "").strip() == str(expected_file_id).strip()
    )


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
        "Begin chunked download for an indexed project file. Pass ``file_id`` "
        "(``files.id`` UUID). ``project_id`` is optional; if set, the row must "
        "belong to that project. Same transfer session as ``transfer_download_begin`` "
        "(GET chunks). Client façade: ``FileSessionClient.download`` with ``lock`` "
        "→ ``lock_mode`` (``true`` → ``full``, ``false`` → ``none``)."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the schema for starting an indexed-file download."""
        return cast(Dict[str, Any], get_project_file_transfer_download_begin_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the file selector, compression, lock, and chunk options."""
        params = super().validate_params(params)
        _validate_download_params(params)
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
        mode = normalize_lock_mode(params.get("lock_mode") or "none")
        sid = str(params.get("session_id") or "").strip()
        if mode != "none" and not sid:
            raise ValidationError(
                "session_id is required when lock_mode is not none",
                field="session_id",
                details={"lock_mode": params.get("lock_mode")},
            )
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
        """Return registration metadata for indexed-file downloads."""
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
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Create a resumable download session for an indexed project file."""
        database = self._open_database_from_config(auto_analyze=False)
        session_err = _validate_client_session_id(
            database, session_id, lock_mode=lock_mode
        )
        if session_err is not None:
            return session_err
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

        disk_out = _require_on_disk_project_file(
            database, effective_project_id, rel_posix
        )
        if isinstance(disk_out, ErrorResult):
            return disk_out
        abs_path = disk_out

        ensured = _ensure_db_row_for_on_disk_file(
            database,
            effective_project_id,
            abs_path,
            rel_posix,
            row,
        )
        if isinstance(ensured, ErrorResult):
            return ensured
        row, abs_path = ensured

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
            resolved_sid = _resolve_advisory_lock_session_id(
                database,
                client_session_id=session_id,
                lock_mode=lock_mode,
            )
            lock_session_id = resolved_sid
            try:
                lock_handle = acquire_persistent_file_lock(
                    abs_path,
                    mode=lock_mode,
                    database=database,
                    project_id=effective_project_id,
                    file_path=rel_posix,
                    session_id=lock_session_id,
                    register_role="client" if session_id else "daemon",
                )
            except Exception as exc:
                return ErrorResult(
                    message=f"Failed to acquire transfer lock: {exc}",
                    code="LOCK_ACQUIRE_FAILED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                        "lock_mode": mode,
                        "session_id": lock_session_id,
                    },
                )
            _record_client_file_lock(
                database,
                client_session_id=session_id,
                project_id=effective_project_id,
                row=row,
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
        if session_id:
            merged["session_id"] = str(session_id).strip()
        if include_backup_history:
            project = get_project(database, effective_project_id)
            if project:
                root = Path(project.root_path).resolve()
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
        "After transfer upload completes, saves buffer to a project file. **Update "
        "existing:** pass ``file_id`` only (``project_id`` / ``file_path`` optional; "
        "if ``project_id`` is set it must match the row). **Create new:** pass "
        "``project_id`` + project-relative ``file_path`` (path must not already be "
        "in the ``files`` index). Same pipeline as ``universal_file_save``. Client "
        "façade: ``upload`` / ``upload_new`` with ``unlock`` → ``unlock_after_write``."
    )
    category = "file_management"
    author = "Vasiliy Zdanovskiy"
    email = "vasilyvz@gmail.com"
    use_queue = False

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Return the schema for saving a completed upload to a project file."""
        return cast(Dict[str, Any], get_project_file_transfer_upload_save_schema())

    def validate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate the upload transfer, file selector, diff, and lock options."""
        params = super().validate_params(params)
        _validate_upload_selector_params(params)
        tid = str(params.get("transfer_id") or "").strip()
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
        mode = normalize_lock_mode(params.get("lock_mode") or "none")
        sid = str(params.get("session_id") or "").strip()
        if mode != "none" and not sid:
            raise ValidationError(
                "session_id is required when lock_mode is not none",
                field="session_id",
                details={"lock_mode": params.get("lock_mode")},
            )
        return params

    @classmethod
    def metadata(cls: Type["ProjectFileTransferUploadSaveCommand"]) -> Dict[str, Any]:
        """Return registration metadata for saving uploaded project files."""
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
        session_id: Optional[str] = None,
        **kwargs: Any,
    ) -> SuccessResult | ErrorResult:
        """Save a completed upload through the universal file-save pipeline."""
        database = self._open_database_from_config(auto_analyze=False)
        session_err = _validate_client_session_id(
            database, session_id, lock_mode=lock_mode
        )
        if session_err is not None:
            return session_err
        if session_id and not str(session_id).strip():
            session_id = None
        elif session_id:
            session_id = str(session_id).strip()
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
        if not str(file_id or "").strip() and str(file_path or "").strip() and _row:
            # A row already exists for this create path. Only reject when the file
            # is genuinely on disk: a row without bytes is an interrupted prior
            # create (e.g. a sync-timeout retry) and is completed idempotently
            # below by treating the existing row as the write target.
            if _create_path_on_disk(database, effective_project_id, rel_posix):
                existing_id = str(_row.get("id") or "").strip()
                return ErrorResult(
                    message=(
                        f"Path {rel_posix!r} is already indexed in the database; "
                        "use file_id to update an existing file"
                    ),
                    code="FILE_ALREADY_INDEXED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                        "file_id": existing_id or None,
                    },
                )

        read_out = _read_completed_upload_text(transfer_id)
        if isinstance(read_out, ErrorResult):
            return read_out
        content, _compression = read_out

        mode = normalize_lock_mode(lock_mode)
        is_create = _row is None
        lock_session_id: Optional[str] = None
        lock_handle = None
        abs_path: Optional[Path] = None

        # Resolve the absolute target path up front: the advisory lock (when
        # requested) and the pre-write row registration for a new file both need it.
        if mode != "none" or is_create:
            project = get_project(database, effective_project_id)
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

        # Step 1 — acquire the advisory lock FIRST so its lease row is committed
        # and visible before any files row or bytes appear. The file watcher skips
        # locked paths, so it cannot race the registration/write below.
        if mode != "none":
            lock_session_id = _resolve_advisory_lock_session_id(
                database,
                client_session_id=session_id,
                lock_mode=lock_mode,
            )
            try:
                lock_handle = acquire_persistent_file_lock(
                    cast(Path, abs_path),
                    mode=lock_mode,
                    database=database,
                    project_id=effective_project_id,
                    file_path=rel_posix,
                    session_id=lock_session_id,
                    register_role="client" if session_id else "daemon",
                )
            except Exception as exc:
                return ErrorResult(
                    message=f"Failed to acquire transfer save lock: {exc}",
                    code="LOCK_ACQUIRE_FAILED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                        "lock_mode": mode,
                        "session_id": lock_session_id,
                    },
                )

        # Step 2 — register the files row for a NEW file BEFORE writing bytes, so
        # the caller's commit has files.id immediately and does not depend on the
        # file watcher. A real write (not dry-run) is required to allocate the row;
        # any later failure rolls this row back (see the failure branch below).
        pre_registered_file_id: Optional[str] = None
        if is_create and not dry_run:
            reg_row = register_file_row_for_new_content(
                database,
                effective_project_id,
                cast(Path, abs_path),
                content,
            )
            if reg_row is None or reg_row.get("id") is None:
                if lock_handle is not None:
                    lock_handle.release(force_lease=True)
                return ErrorResult(
                    message=f"Failed to register file row for {rel_posix!r}",
                    code="FILE_REGISTER_FAILED",
                    details={
                        "project_id": effective_project_id,
                        "file_path": rel_posix,
                    },
                )
            pre_registered_file_id = str(reg_row["id"])

        # Step 3 — write the bytes to disk.
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
        if not isinstance(result, SuccessResult):
            # Roll back so no partial lock/row/bytes state persists: drop the
            # pre-registered row, then release the lock.
            if pre_registered_file_id is not None:
                _rollback_registered_file_row(
                    database, effective_project_id, pre_registered_file_id
                )
            if lock_handle is not None:
                lock_handle.release(force_lease=True)
        if isinstance(result, SuccessResult) and isinstance(result.data, dict):
            result.data.setdefault("resolved_file_path", rel_posix)
            result.data.setdefault("lock_mode", lock_mode)
            result.data.setdefault("lock_session_id", lock_session_id)
            if not dry_run:
                if pre_registered_file_id is not None:
                    # Durability post-condition: never return a file_id whose row
                    # is not actually persisted. A phantom id would make a later
                    # commit fail with "file not found in project index" even
                    # though create reported success. If the row is not visible on
                    # a fresh read, roll it back and fail loudly instead.
                    if not _create_row_is_persisted(
                        database,
                        effective_project_id,
                        cast(Path, abs_path),
                        pre_registered_file_id,
                    ):
                        _rollback_registered_file_row(
                            database, effective_project_id, pre_registered_file_id
                        )
                        if lock_handle is not None:
                            lock_handle.release(force_lease=True)
                        return ErrorResult(
                            message=(
                                f"Registered file row for {rel_posix!r} did not "
                                "persist; refusing to return a phantom file_id"
                            ),
                            code="FILE_REGISTER_NOT_PERSISTED",
                            details={
                                "project_id": effective_project_id,
                                "file_path": rel_posix,
                                "file_id": pre_registered_file_id,
                            },
                        )
                    result.data["file_id"] = pre_registered_file_id
                else:
                    disk_out = _require_on_disk_project_file(
                        database, effective_project_id, rel_posix
                    )
                    if isinstance(disk_out, ErrorResult):
                        return disk_out
                    ensured = _ensure_db_row_for_on_disk_file(
                        database,
                        effective_project_id,
                        disk_out,
                        rel_posix,
                        _row,
                    )
                    if isinstance(ensured, ErrorResult):
                        return ensured
                    reg_row_existing, _abs_path = ensured
                    result.data["file_id"] = str(reg_row_existing["id"])
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
                fid_for_unlock: Optional[str] = None
                if file_id and str(file_id).strip():
                    fid_for_unlock = str(file_id).strip()
                elif _row and _row.get("id") is not None:
                    fid_for_unlock = str(_row["id"]).strip() or None
                elif isinstance(result.data, dict) and result.data.get("file_id"):
                    fid_for_unlock = str(result.data["file_id"])
                _release_client_file_lock(
                    database,
                    client_session_id=session_id,
                    project_id=effective_project_id,
                    file_id=fid_for_unlock,
                )
                result.data["lock_released"] = True
            elif bool(dry_run) and lock_handle is not None:
                lock_handle.release(force_lease=True)
                result.data["lock_released"] = True
        return result
