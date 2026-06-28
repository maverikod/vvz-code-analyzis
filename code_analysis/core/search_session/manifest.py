"""
SearchSessionManifest and ServerProcessIdentity persistence.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from code_analysis.core.constants import DEFAULT_FILE_LOCK_TIMEOUT
from code_analysis.core.file_lock import FileLockTimeoutError
from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout

METRIC_PRODUCED_RESULTS = "produced_results"
METRIC_WRITTEN_BLOCKS = "written_blocks"
METRIC_SCANNED_FILES = "scanned_files"
METRIC_WARNINGS = "warnings"
METRIC_ERRORS = "errors"

DEFAULT_METRICS: dict[str, int] = {
    METRIC_PRODUCED_RESULTS: 0,
    METRIC_WRITTEN_BLOCKS: 0,
    METRIC_SCANNED_FILES: 0,
    METRIC_WARNINGS: 0,
    METRIC_ERRORS: 0,
}
INITIAL_MANIFEST_PHASE: str = "starting"


@dataclass(frozen=True)
class ManifestConcurrencyPolicy:
    """
    Documents concurrent access rules for the session manifest.

    MANIFEST_CONCURRENCY_POLICY:
    - single_writer_under_update_lock: concurrent updates serialize on manifest.json.lock.
    - atomic_create_via_tmp_replace: initial write uses tmp + os.replace without lock.
    - readers_may_read_without_lock: read_manifest opens JSON directly.
    """

    single_writer_under_update_lock: bool
    atomic_create_via_tmp_replace: bool
    readers_may_read_without_lock: bool


MANIFEST_CONCURRENCY_POLICY = ManifestConcurrencyPolicy(
    single_writer_under_update_lock=True,
    atomic_create_via_tmp_replace=True,
    readers_may_read_without_lock=True,
)


@dataclass
class ServerProcessIdentity:
    """Owning server process identity for orphan detection."""

    main_pid: int
    process_start_time: float
    host: Optional[str] = None
    instance_id: Optional[str] = None


@dataclass
class SearchSessionManifest:
    """Session manifest stored as manifest.json in the session directory."""

    search_id: str
    created_at: float
    last_access_at: float
    heartbeat_at: Optional[float]
    status: str
    phase: str
    request: dict[str, Any]
    metrics: dict[str, int]
    process: ServerProcessIdentity
    block_ready_count: int = 0


def capture_server_process_identity() -> ServerProcessIdentity:
    """
    Capture current process identity using wall-clock time for ``process_start_time``.

    ``process_start_time`` is the wall time at capture (not monotonic clock).
    """
    return ServerProcessIdentity(
        main_pid=os.getpid(),
        process_start_time=time.time(),
    )


def create_initial_manifest(
    *,
    layout: SearchSessionDirectoryLayout,
    search_id: str,
    request: dict[str, Any],
    process: Optional[ServerProcessIdentity] = None,
) -> SearchSessionManifest:
    """
    Create and write the initial manifest for a new search session.

    Consumes: layout (session directory), search_id, request context dict,
    and optional server process identity; produces the initial SearchSessionManifest.

    Args:
        layout: Provisioned session directory layout.
        search_id: Session UUID string.
        request: Request context dict copied into manifest.
        process: Server process identity; captured automatically when omitted.

    Returns:
        Initial SearchSessionManifest written to disk.
    """
    now = time.time()
    if process is None:
        process = capture_server_process_identity()
    manifest = SearchSessionManifest(
        search_id=search_id,
        created_at=now,
        last_access_at=now,
        heartbeat_at=None,
        status="running",
        phase=INITIAL_MANIFEST_PHASE,
        request=dict(request),
        metrics=dict(DEFAULT_METRICS),
        process=process,
        block_ready_count=0,
    )
    write_manifest_atomic(layout, manifest)
    return manifest


def _manifest_to_dict(manifest: SearchSessionManifest) -> dict[str, Any]:
    """Return manifest to dict."""
    data = asdict(manifest)
    return data


def _manifest_from_dict(data: dict[str, Any]) -> SearchSessionManifest:
    """Return manifest from dict."""
    process_raw = data.get("process") or {}
    process = ServerProcessIdentity(
        main_pid=int(process_raw["main_pid"]),
        process_start_time=float(process_raw["process_start_time"]),
        host=process_raw.get("host"),
        instance_id=process_raw.get("instance_id"),
    )
    metrics = dict(DEFAULT_METRICS)
    metrics.update(data.get("metrics") or {})
    return SearchSessionManifest(
        search_id=str(data["search_id"]),
        created_at=float(data["created_at"]),
        last_access_at=float(data["last_access_at"]),
        heartbeat_at=(
            float(data["heartbeat_at"])
            if data.get("heartbeat_at") is not None
            else None
        ),
        status=str(data["status"]),
        phase=str(data.get("phase") or ""),
        request=dict(data.get("request") or {}),
        metrics=metrics,
        process=process,
        block_ready_count=int(data.get("block_ready_count") or 0),
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Return atomic write json."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _lock_path(manifest_path: Path) -> Path:
    """Return lock path."""
    return manifest_path.with_suffix(manifest_path.suffix + ".lock")


def write_manifest_atomic(
    layout: SearchSessionDirectoryLayout,
    manifest: SearchSessionManifest,
) -> None:
    """Write manifest JSON atomically (tmp + replace)."""
    _atomic_write_json(layout.manifest_path, _manifest_to_dict(manifest))


def read_manifest(layout: SearchSessionDirectoryLayout) -> SearchSessionManifest:
    """Load manifest JSON; raise FileNotFoundError when missing."""
    with open(layout.manifest_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _manifest_from_dict(data)


def update_manifest_atomic(
    layout: SearchSessionDirectoryLayout,
    mutator: Callable[[SearchSessionManifest], SearchSessionManifest],
) -> SearchSessionManifest:
    """
    Read-modify-write manifest under an exclusive lock on ``manifest.json.lock``.

    Lock scope: single session manifest file; released before return.
    """
    lock_file_path = _lock_path(layout.manifest_path)
    lock_file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_file_path, "a+", encoding="utf-8") as lock_handle:
        # Bounded acquire: an unbounded LOCK_EX can freeze a worker-pool thread
        # forever under contention. Poll with LOCK_NB up to a default budget and
        # surface FileLockTimeoutError (handled as LOCK_ACQUIRE_FAILED upstream).
        _deadline = time.monotonic() + DEFAULT_FILE_LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= _deadline:
                    raise FileLockTimeoutError(
                        f"Timed out acquiring manifest lock for {layout.manifest_path}"
                    ) from exc
                time.sleep(0.05)
        try:
            if layout.manifest_path.is_file():
                current = read_manifest(layout)
            else:
                raise FileNotFoundError(f"Manifest not found: {layout.manifest_path}")
            updated = mutator(current)
            write_manifest_atomic(layout, updated)
            return updated
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
