"""
Last-access service metadata for search session TTL cleanup.

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from code_analysis.core.search_session.directory import SearchSessionDirectoryLayout


@dataclass(frozen=True)
class SessionServiceMetadata:
    """
    Service metadata distinct from manifest heartbeat.

    Attributes:
        last_access_at: Wall time refreshed by HTTP index/block/status reads.
    """

    last_access_at: float


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Return atomic write json."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def initialize_service_metadata(
    layout: SearchSessionDirectoryLayout,
    *,
    now: float,
) -> SessionServiceMetadata:
    """Write initial service_metadata.json with ``last_access_at``."""
    metadata = SessionServiceMetadata(last_access_at=now)
    _atomic_write_json(
        layout.service_metadata_path,
        {"last_access_at": metadata.last_access_at},
    )
    return metadata


def read_service_metadata(
    layout: SearchSessionDirectoryLayout,
) -> SessionServiceMetadata:
    """Load service metadata; raise FileNotFoundError when missing."""
    with open(layout.service_metadata_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return SessionServiceMetadata(last_access_at=float(data["last_access_at"]))


def refresh_last_access(
    layout: SearchSessionDirectoryLayout,
    *,
    now: float,
) -> SessionServiceMetadata:
    """Atomically update ``last_access_at`` only."""
    metadata = SessionServiceMetadata(last_access_at=now)
    _atomic_write_json(
        layout.service_metadata_path,
        {"last_access_at": metadata.last_access_at},
    )
    return metadata
