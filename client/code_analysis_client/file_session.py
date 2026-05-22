"""
High-level file transfer and session workflow on top of CodeAnalysisAsyncClient.

Wraps ``session_*`` and ``subordinate_session_*`` MCP commands plus transfer and
advisory-lock commands that accept ``session_id``.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from code_analysis_client.exceptions import ClientValidationError
from code_analysis_client.responses import unwrap_command_result

if TYPE_CHECKING:
    from code_analysis_client.client import CodeAnalysisAsyncClient


class SessionNotFoundError(ClientValidationError):
    """Raised when session_id is absent from client_sessions."""


def _unwrap(data: Dict[str, Any]) -> Dict[str, Any]:
    return unwrap_command_result(
        data,
        session_not_found_type=SessionNotFoundError,
    )


def _require_non_empty(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ClientValidationError(f"{field} is required", field=field)
    return text


def _validate_download_target(*, file_id: Optional[str]) -> None:
    """Download requires ``file_id``."""
    fid = str(file_id or "").strip()
    if not fid:
        raise ClientValidationError("file_id is required", field="file_id")


def _lock_mode_from_flag(lock: bool) -> str:
    return "full" if lock else "none"


def _extract_file_id(payload: Dict[str, Any], *, field: str = "file_id") -> str:
    """Return non-empty ``file_id`` from a command payload or raise."""
    fid = str(payload.get(field) or "").strip()
    if not fid:
        raise ClientValidationError(
            f"{field} missing from server response",
            field=field,
            details=payload,
        )
    return fid


class FileSessionClient:
    """Session-scoped DB sessions, subordinate links, file locks, and transfer helpers."""

    __slots__ = ("_client",)

    def __init__(self, client: CodeAnalysisAsyncClient) -> None:
        self._client = client

    async def create_session(
        self,
        comment: str,
        *,
        role_ids: Optional[List[str]] = None,
    ) -> str:
        """Create a client session (``session_create``) and return ``session_id``."""
        params: Dict[str, Any] = {"comment": comment}
        if role_ids is not None:
            params["role_ids"] = role_ids
        payload = _unwrap(await self._client.call_validated("session_create", params))
        sid = str(payload.get("session_id") or "").strip()
        if not sid:
            raise ClientValidationError(
                "session_create returned no session_id",
                field="session_id",
                details=payload,
            )
        return sid

    async def assert_session_exists(self, session_id: str) -> None:
        """Verify ``session_id`` is registered (touch via ``session_list_file_locks``)."""
        sid = str(session_id).strip()
        if not sid:
            raise ClientValidationError("session_id is required", field="session_id")
        _unwrap(
            await self._client.call_validated(
                "session_list_file_locks",
                {"session_id": sid},
            )
        )

    async def delete_session(
        self, session_id: str, *, force: bool = False
    ) -> Dict[str, Any]:
        """Delete a client session (``session_delete``).

        ``force`` defaults to false (omit on the wire when false). Safe delete
        requires no ``session_file_locks`` and no ``subordinate_sessions`` rows
        where this session is ``parent_session_id``. When ``force`` is true,
        linked subordinate client sessions and file locks are removed first.

        Returns ``session_id``, ``deleted``, ``released_lock_count``, and
        ``released_subordinate_count``.
        """
        params: Dict[str, Any] = {"session_id": session_id}
        if force:
            params["force"] = True
        return _unwrap(
            await self._client.call_validated(
                "session_delete",
                params,
            )
        )

    async def view_session(self, session_id: str) -> Dict[str, Any]:
        """Aggregated session view (``session_view``).

        Returns ``locked_files_by_project`` (file_id, file_path,
        project_presentation per project) and ``subordinate_sessions``
        (subordinate_session_id, server_uuid, session_presentation,
        server_presentation, link_comment).
        """
        sid = _require_non_empty(session_id, field="session_id")
        return _unwrap(
            await self._client.call_validated(
                "session_view",
                {"session_id": sid},
            )
        )

    async def create_subordinate_session(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        comment: str,
        *,
        server_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Link subordinate to parent (``subordinate_session_create``).

        ``server_uuid`` defaults to the server's ``registration.instance_uuid``
        when omitted.
        """
        params: Dict[str, Any] = {
            "parent_session_id": _require_non_empty(
                parent_session_id, field="parent_session_id"
            ),
            "subordinate_session_id": _require_non_empty(
                subordinate_session_id, field="subordinate_session_id"
            ),
            "comment": comment,
        }
        if server_uuid is not None:
            params["server_uuid"] = _require_non_empty(server_uuid, field="server_uuid")
        return _unwrap(
            await self._client.call_validated("subordinate_session_create", params)
        )

    async def get_subordinate_session(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
    ) -> Dict[str, Any]:
        """Fetch one subordinate link (``subordinate_session_get``)."""
        return _unwrap(
            await self._client.call_validated(
                "subordinate_session_get",
                {
                    "parent_session_id": _require_non_empty(
                        parent_session_id, field="parent_session_id"
                    ),
                    "subordinate_session_id": _require_non_empty(
                        subordinate_session_id, field="subordinate_session_id"
                    ),
                    "server_uuid": _require_non_empty(server_uuid, field="server_uuid"),
                },
            )
        )

    async def update_subordinate_session(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
        comment: str,
    ) -> Dict[str, Any]:
        """Update link comment (``subordinate_session_update``)."""
        return _unwrap(
            await self._client.call_validated(
                "subordinate_session_update",
                {
                    "parent_session_id": _require_non_empty(
                        parent_session_id, field="parent_session_id"
                    ),
                    "subordinate_session_id": _require_non_empty(
                        subordinate_session_id, field="subordinate_session_id"
                    ),
                    "server_uuid": _require_non_empty(server_uuid, field="server_uuid"),
                    "comment": comment,
                },
            )
        )

    async def delete_subordinate_session(
        self,
        parent_session_id: str,
        subordinate_session_id: str,
        server_uuid: str,
    ) -> Dict[str, Any]:
        """Remove subordinate link only (``subordinate_session_delete``).

        Does not delete ``client_sessions`` rows; use :meth:`delete_session` for that.
        """
        return _unwrap(
            await self._client.call_validated(
                "subordinate_session_delete",
                {
                    "parent_session_id": _require_non_empty(
                        parent_session_id, field="parent_session_id"
                    ),
                    "subordinate_session_id": _require_non_empty(
                        subordinate_session_id, field="subordinate_session_id"
                    ),
                    "server_uuid": _require_non_empty(server_uuid, field="server_uuid"),
                },
            )
        )

    async def list_subordinate_sessions(
        self,
        *,
        parent_session_id: Optional[str] = None,
        subordinate_session_id: Optional[str] = None,
        server_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List subordinate links (``subordinate_session_list``).

        Returns ``links`` and ``count``. All filter parameters are optional.
        """
        params: Dict[str, Any] = {}
        if parent_session_id is not None:
            params["parent_session_id"] = parent_session_id
        if subordinate_session_id is not None:
            params["subordinate_session_id"] = subordinate_session_id
        if server_uuid is not None:
            params["server_uuid"] = server_uuid
        return _unwrap(
            await self._client.call_validated("subordinate_session_list", params)
        )

    async def list_sessions(
        self,
        *,
        session_id: Optional[str] = None,
        stale_threshold_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """List client sessions (``session_list``)."""
        params: Dict[str, Any] = {}
        if session_id is not None:
            params["session_id"] = session_id
        if stale_threshold_seconds is not None:
            params["stale_threshold_seconds"] = stale_threshold_seconds
        return _unwrap(await self._client.call_validated("session_list", params))

    async def lock_file(
        self,
        session_id: str,
        project_id: str,
        file_id: str,
    ) -> Dict[str, Any]:
        """Acquire a DB file lock without transfer (``session_open_file``)."""
        await self.assert_session_exists(session_id)
        return _unwrap(
            await self._client.call_validated(
                "session_open_file",
                {
                    "session_id": session_id,
                    "project_id": project_id,
                    "file_id": file_id,
                },
            )
        )

    async def unlock_file(
        self,
        session_id: str,
        project_id: str,
        file_id: str,
    ) -> Dict[str, Any]:
        """Release a DB file lock without transfer (``session_close_file``)."""
        await self.assert_session_exists(session_id)
        return _unwrap(
            await self._client.call_validated(
                "session_close_file",
                {
                    "session_id": session_id,
                    "project_id": project_id,
                    "file_id": file_id,
                },
            )
        )

    async def list_file_locks(self, session_id: str) -> Dict[str, Any]:
        """Return locks held by the session (``session_list_file_locks``)."""
        return _unwrap(
            await self._client.call_validated(
                "session_list_file_locks",
                {"session_id": session_id},
            )
        )

    async def lock_files_advisory(
        self,
        session_id: str,
        project_id: str,
        file_paths: List[str],
        *,
        lock_mode: str = "full",
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Cooperative flock + DB lease for paths (``project_file_advisory_lock_batch``)."""
        await self.assert_session_exists(session_id)
        items = [
            {
                "session_id": session_id,
                "project_id": project_id,
                "file_path": path,
                "action": "lock",
                "lock_mode": lock_mode,
            }
            for path in file_paths
        ]
        params: Dict[str, Any] = {
            "items": items,
            "allow_foreign_session": True,
        }
        if timeout_seconds is not None:
            params["timeout_seconds"] = timeout_seconds
        return _unwrap(
            await self._client.call_validated(
                "project_file_advisory_lock_batch",
                params,
            )
        )

    async def unlock_files_advisory(
        self,
        session_id: str,
        project_id: str,
        file_paths: List[str],
    ) -> Dict[str, Any]:
        """Release cooperative locks without transfer."""
        await self.assert_session_exists(session_id)
        items = [
            {
                "session_id": session_id,
                "project_id": project_id,
                "file_path": path,
                "action": "unlock",
            }
            for path in file_paths
        ]
        return _unwrap(
            await self._client.call_validated(
                "project_file_advisory_lock_batch",
                {
                    "items": items,
                    "allow_foreign_session": True,
                },
            )
        )

    async def _begin_download(
        self,
        session_id: str,
        *,
        file_id: str,
        compression: str = "identity",
        lock: bool = True,
        chunk_size: Optional[int] = None,
        include_backup_history: bool = False,
    ) -> Dict[str, Any]:
        """Begin chunked download; returns payload including ``file_id`` and ``transfer_id``."""
        fid = _require_non_empty(file_id, field="file_id")
        _validate_download_target(file_id=fid)
        await self.assert_session_exists(session_id)
        params: Dict[str, Any] = {
            "session_id": session_id,
            "compression": compression,
            "lock_mode": _lock_mode_from_flag(lock),
            "include_backup_history": include_backup_history,
            "file_id": fid,
        }
        if chunk_size is not None:
            params["chunk_size"] = chunk_size
        payload = _unwrap(
            await self._client.call_validated(
                "project_file_transfer_download_begin",
                params,
            )
        )
        _extract_file_id(payload)
        return payload

    async def download(
        self,
        session_id: str,
        destination: Union[str, Path],
        file_id: str,
        *,
        compression: str = "identity",
        lock: bool = True,
        include_backup_history: bool = False,
    ) -> Tuple[Dict[str, Any], Any]:
        """Download an indexed file by ``file_id``; returns (begin_payload, receipt)."""
        fid = _require_non_empty(file_id, field="file_id")
        begin = await self._begin_download(
            session_id,
            file_id=fid,
            compression=compression,
            lock=lock,
            include_backup_history=include_backup_history,
        )
        transfer_id = str(begin.get("transfer_id") or "").strip()
        if not transfer_id:
            raise ClientValidationError(
                "download begin returned no transfer_id",
                field="transfer_id",
                details=begin,
            )
        receipt = await self.download_to_path(transfer_id, destination)
        return begin, receipt

    async def download_to_path(
        self,
        transfer_id: str,
        destination: Union[str, Path],
    ) -> Any:
        """Stream download chunks to ``destination`` via the adapter client."""
        return await self._client.rpc.download_file(
            str(transfer_id).strip(),
            str(destination),
        )

    async def upload_bytes(
        self,
        payload: bytes,
        *,
        filename: str,
        compression: str = "identity",
    ) -> Any:
        """Upload raw bytes through the adapter buffer; returns upload receipt."""
        dest = Path(filename)
        dest.write_bytes(payload)
        try:
            return await self._client.rpc.upload_file(
                str(dest),
                filename=filename,
                compression=compression,
            )
        finally:
            if dest.is_file():
                dest.unlink(missing_ok=True)

    async def _commit_upload(
        self,
        session_id: str,
        transfer_id: str,
        *,
        project_id: Optional[str] = None,
        file_id: Optional[str] = None,
        file_path: Optional[str] = None,
        unlock_after_write: bool = True,
        dry_run: bool = False,
        backup: bool = True,
    ) -> Dict[str, Any]:
        """Persist a completed adapter upload (``project_file_transfer_upload_save``)."""
        await self.assert_session_exists(session_id)
        params: Dict[str, Any] = {
            "session_id": session_id,
            "transfer_id": transfer_id,
            "unlock_after_write": unlock_after_write,
            "dry_run": dry_run,
            "backup": backup,
        }
        if project_id is not None:
            params["project_id"] = project_id
        if file_id is not None:
            params["file_id"] = file_id
        if file_path is not None:
            params["file_path"] = file_path
        return _unwrap(
            await self._client.call_validated(
                "project_file_transfer_upload_save",
                params,
            )
        )

    async def upload_new(
        self,
        session_id: str,
        payload: bytes,
        project_id: str,
        file_path: str,
        *,
        filename: Optional[str] = None,
        compression: str = "identity",
        unlock: bool = True,
        dry_run: bool = False,
        backup: bool = True,
    ) -> str:
        """Create a new project file from uploaded bytes; returns the new ``file_id``.

        ``project_id`` and project-relative ``file_path`` are required. The path must
        not already be indexed in the database (new file). Server errors otherwise.
        """
        pid = _require_non_empty(project_id, field="project_id")
        fp = _require_non_empty(file_path, field="file_path")
        name = filename or Path(fp).name
        receipt = await self.upload_bytes(
            payload,
            filename=name,
            compression=compression,
        )
        if not getattr(receipt, "completed", False):
            raise ClientValidationError(
                "upload did not complete",
                field="transfer_id",
                details={"receipt": repr(receipt)},
            )
        saved = await self._commit_upload(
            session_id,
            str(receipt.transfer_id),
            project_id=pid,
            file_path=fp,
            unlock_after_write=unlock,
            backup=backup,
            dry_run=dry_run,
        )
        if dry_run:
            fid = str(saved.get("file_id") or "").strip()
            return fid
        return _extract_file_id(saved)

    async def upload(
        self,
        session_id: str,
        payload: bytes,
        file_id: str,
        *,
        filename: Optional[str] = None,
        compression: str = "identity",
        unlock: bool = True,
        backup: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Overwrite an existing indexed file from uploaded bytes.

        Only ``file_id`` is required. Returns the server save payload on success
        or raises :class:`ClientValidationError` on failure.
        """
        fid = _require_non_empty(file_id, field="file_id")
        name = filename or "payload.bin"
        receipt = await self.upload_bytes(
            payload,
            filename=name,
            compression=compression,
        )
        if not getattr(receipt, "completed", False):
            raise ClientValidationError(
                "upload did not complete",
                field="transfer_id",
                details={"receipt": repr(receipt)},
            )
        saved = await self._commit_upload(
            session_id,
            str(receipt.transfer_id),
            file_id=fid,
            unlock_after_write=unlock,
            backup=backup,
            dry_run=dry_run,
        )
        if not dry_run:
            _extract_file_id(saved)
        return saved
