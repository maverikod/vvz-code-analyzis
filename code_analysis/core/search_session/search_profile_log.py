"""
Dedicated search profiling log (JSONL) for bottleneck analysis.

Each line is one checkpoint with wall timing since job start and since the
previous checkpoint. Written to ``{server.log_dir}/search_profile.jsonl`` by
default (configurable via ``search_session.profile_log_filename``).

Author: Vasiliy Zdanovskiy
email: vasilyvz@gmail.com
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from code_analysis.core.storage_paths import resolve_service_log_dir

_WRITE_LOCK = threading.Lock()
_DEFAULT_FILENAME = "search_profile.jsonl"


def resolve_search_profile_log_path(
    *,
    config_data: Mapping[str, Any],
    config_path: Path,
) -> Path:
    """Return absolute path to the search profile JSONL file."""
    code_analysis = config_data.get("code_analysis") or {}
    search_session = (
        code_analysis.get("search_session") or config_data.get("search_session") or {}
    )
    if not isinstance(search_session, Mapping):
        search_session = {}
    filename = search_session.get("profile_log_filename", _DEFAULT_FILENAME)
    if not isinstance(filename, str) or not filename.strip():
        filename = _DEFAULT_FILENAME
    log_dir = resolve_service_log_dir(
        config_data=config_data,
        config_path=config_path,
    )
    return log_dir / filename


def is_search_profile_enabled(config_data: Mapping[str, Any]) -> bool:
    """Whether search profile JSONL is enabled (default True)."""
    code_analysis = config_data.get("code_analysis") or {}
    search_session = (
        code_analysis.get("search_session") or config_data.get("search_session") or {}
    )
    if not isinstance(search_session, Mapping):
        return True
    enabled = search_session.get("profile_log_enabled", True)
    return bool(enabled)


@dataclass
class SearchProfileRecorder:
    """
    Append-only checkpoint writer for one search job or pagination read.

    Attributes:
        job_id: Search session id (or job_id for get_page/status).
        log_path: Destination JSONL file.
        enabled: When False, ``checkpoint`` is a no-op.
    """

    job_id: str
    log_path: Path
    enabled: bool = True
    _t0: float = field(default_factory=time.monotonic, repr=False)
    _last: float = field(default_factory=time.monotonic, repr=False)

    def checkpoint(self, name: str, **fields: Any) -> None:
        """Record one timing checkpoint; never raises."""
        if not self.enabled:
            return
        try:
            now = time.monotonic()
            record: dict[str, Any] = {
                "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "job_id": self.job_id,
                "checkpoint": name,
                "since_start_sec": round(now - self._t0, 4),
                "since_prev_sec": round(now - self._last, 4),
            }
            for key, value in fields.items():
                if value is not None:
                    record[key] = value
            self._last = now
            line = json.dumps(record, ensure_ascii=False, default=str)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with _WRITE_LOCK:
                with open(self.log_path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception:
            return


def open_search_profile_recorder(
    *,
    job_id: str,
    raw_config: Mapping[str, Any],
    config_path: Path,
) -> SearchProfileRecorder:
    """Build a recorder for ``job_id`` using server config."""
    return SearchProfileRecorder(
        job_id=job_id,
        log_path=resolve_search_profile_log_path(
            config_data=raw_config,
            config_path=config_path,
        ),
        enabled=is_search_profile_enabled(raw_config),
    )


def request_summary_fields(params: Mapping[str, Any]) -> dict[str, Any]:
    """Safe request metadata for profile lines (no full query text)."""
    query = str(params.get("query") or "")
    return {
        "project_id": params.get("project_id"),
        "query_len": len(query),
        "enable_semantic": bool(params.get("enable_semantic", True)),
        "enable_grep": bool(params.get("enable_grep", False)),
        "fulltext_limit": params.get("fulltext_limit"),
        "semantic_limit": params.get("semantic_limit"),
        "page_size": params.get("page_size"),
    }
