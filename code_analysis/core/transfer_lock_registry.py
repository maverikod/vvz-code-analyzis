"""In-process transfer lock registry and adapter lifecycle monkeypatches."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .file_lock import FileLockHandle

logger = logging.getLogger(__name__)


@dataclass
class TransferLockEntry:
    """Lock state tied to an adapter transfer id."""

    transfer_id: str
    direction: str
    project_id: str
    file_path: str
    session_id: str
    lock_mode: str
    handle: FileLockHandle


_guard = threading.Lock()
_entries: Dict[str, TransferLockEntry] = {}
_hooks_installed = False


def register_transfer_lock(entry: TransferLockEntry) -> None:
    """Remember a held lock for later transfer lifecycle cleanup."""
    with _guard:
        old = _entries.pop(entry.transfer_id, None)
        _entries[entry.transfer_id] = entry
    if old is not None and old.handle is not entry.handle:
        old.handle.release(force_lease=True)


def release_transfer_lock(transfer_id: str, *, reason: str = "") -> bool:
    """Release and forget a transfer-bound lock."""
    with _guard:
        entry = _entries.pop(str(transfer_id).strip(), None)
    if entry is None:
        return False
    try:
        entry.handle.release(force_lease=True)
        logger.info(
            "Released transfer lock transfer_id=%s reason=%s", transfer_id, reason
        )
        return True
    except Exception:
        logger.warning("Failed to release transfer lock %s", transfer_id, exc_info=True)
        return False


def get_transfer_lock_entry(transfer_id: str) -> Optional[TransferLockEntry]:
    """Return registry entry for tests/diagnostics."""
    with _guard:
        return _entries.get(str(transfer_id).strip())


def install_transfer_lock_hooks() -> None:
    """Patch adapter store methods so terminal transfer states release held locks."""
    global _hooks_installed
    if _hooks_installed:
        return
    try:
        from mcp_proxy_adapter.transfer.server_store import TransferServerStore
    except Exception as exc:
        logger.debug("Transfer lock hooks skipped; adapter unavailable: %s", exc)
        return

    original_read_download_chunk = TransferServerStore.read_download_chunk
    original_ack = TransferServerStore.acknowledge_download_transfer
    original_expire = TransferServerStore.expire_stale_sessions
    original_complete_upload = TransferServerStore.complete_upload_session

    def read_download_chunk(
        self: Any, transfer_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        try:
            chunk_result = original_read_download_chunk(
                self, transfer_id, *args, **kwargs
            )
        except Exception:
            raise
        receipt = chunk_result
        if isinstance(chunk_result, tuple) and len(chunk_result) >= 2:
            receipt = chunk_result[1]
        if getattr(receipt, "completed", False):
            release_transfer_lock(transfer_id, reason="download_completed")
        return chunk_result

    def acknowledge_download_transfer(
        self: Any, transfer_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        try:
            return original_ack(self, transfer_id, *args, **kwargs)
        finally:
            release_transfer_lock(transfer_id, reason="download_ack")

    def complete_upload_session(
        self: Any, transfer_id: str, *args: Any, **kwargs: Any
    ) -> Any:
        try:
            return original_complete_upload(self, transfer_id, *args, **kwargs)
        except Exception:
            release_transfer_lock(transfer_id, reason="upload_complete_error")
            raise

    def expire_stale_sessions(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_expire(self, *args, **kwargs)
        for expired in getattr(result, "expired", ()) or ():
            try:
                tid = expired[0]
            except Exception:
                continue
            release_transfer_lock(tid, reason="expired")
        return result

    setattr(TransferServerStore, "read_download_chunk", read_download_chunk)
    setattr(
        TransferServerStore,
        "acknowledge_download_transfer",
        acknowledge_download_transfer,
    )
    setattr(TransferServerStore, "complete_upload_session", complete_upload_session)
    setattr(TransferServerStore, "expire_stale_sessions", expire_stale_sessions)
    _hooks_installed = True
    logger.info("Installed transfer advisory lock lifecycle hooks")
